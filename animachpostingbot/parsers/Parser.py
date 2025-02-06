import asyncio
from datetime import datetime, timezone
from typing import Any, List, Optional
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup
from loguru import logger


# Helper functions that can be used across all classes.
def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Splits a list into chunks of the specified size.
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

class Parser:
    def __init__(self, url: str, queue: asyncio.Queue, database, soup_parser=BeautifulSoup):
        """
        Initializes the parser with the feed URL, a processing queue, and a database object.
        """
        self.url = url
        self.queue = queue
        self.db = database
        self.soup_parser = soup_parser
        logger.info(f"{self.__class__.__name__} initialized with URL: {self.url}")

    async def fetch_feed(self) -> feedparser.FeedParserDict:
        """
        Asynchronously fetches and parses the RSS feed.
        """
        logger.info(f"Fetching data from feed: {self.url}")
        feed = await asyncio.to_thread(feedparser.parse, self.url)
        if feed.get("bozo"):
            logger.error(f"Error fetching/parsing feed {self.url}: {feed.get('bozo_exception')}")
        if "status" in feed and feed["status"] != 200:
            logger.error(f"Unexpected HTTP status {feed['status']} when fetching feed {self.url}")
        logger.debug(f"Fetched feed with {len(feed.entries)} entries.")
        return feed

    async def parse_data(self) -> feedparser.FeedParserDict:
        """
        Wrapper method for fetch_feed.
        """
        return await self.fetch_feed()

    async def process_feed(self, feed: feedparser.FeedParserDict, default_start: datetime) -> Optional[str]:
        """
        Processes RSS feed entries:
          - Checks publication date (comparing with the last processed timestamp)
          - Filters entries (via the should_skip_entry hook)
          - Extracts image URLs from the description
          - Splits the image URLs into chunks and adds them to the queue

        Parameters:
          feed: the parsed RSS feed;
          default_start: the date to start processing from if the DB doesn't contain a timestamp.

        Returns:
          An ISO-formatted string of the maximum publication date among processed entries,
          or None if no entries were processed.
        """
        logger.info(f"Processing data from {self.url}")

        last_posted = await self.get_last_posted_timestamp(default_start)
        logger.debug(f"Using last posted timestamp: {last_posted.isoformat()}")

        processed_entries = set()  # To avoid processing duplicates within the same cycle.
        user_link = feed.feed.get("link", "") or self.url
        max_processed_ts = None

        for entry in feed.entries:
            guid = entry.get("guid", "")
            if not guid:
                logger.debug("Skipping entry with no valid GUID.")
                continue

            title = entry.get("title", "No title")
            logger.debug(f"Processing entry: title='{title}', normalized GUID='{guid}'")

            if guid in processed_entries:
                logger.info(f"Skipping duplicate entry for GUID: {guid}")
                continue
            processed_entries.add(guid)

            published_str = entry.get("published")
            if not published_str:
                logger.warning(f"Missing publication date for entry: {entry.get('link', 'no link')}")
                continue

            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                else:
                    published = datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %Z")
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                logger.debug(f"Parsed publication date: {published}")
            except Exception as e:
                logger.error(f"Error parsing date for entry {entry.get('link', 'no link')}: {e}")
                continue

            if published < last_posted:
                logger.info(f"Skipping old entry: {entry.get('link', 'no link')} (published: {published})")
                continue

            # Hook method for filtering entries. The base implementation (e.g., for Pixiv) checks for forbidden categories.
            if self.should_skip_entry(entry):
                logger.info(f"Skipping entry (restricted content): {entry.get('link', 'no link')}")
                continue

            if guid and self.db:
                if await self.db.is_guid_posted(guid):
                    logger.info(f"Entry already posted (DB check): {entry.get('link', 'no link')}")
                    continue

            description = entry.get("description", "")
            image_urls = self.extract_img_links(description)
            author = entry.get("author", "")

            if not image_urls:
                logger.warning(f"No images found in entry: {entry.get('link', 'no link')}")
                continue

            logger.debug(f"Found {len(image_urls)} images in entry '{title}'. Enqueuing batches...")
            for batch in chunk_list(image_urls, 10):
                await self.queue.put((title, batch, user_link, guid, author))
                logger.info(
                    f"Enqueued batch: title='{title}', GUID='{guid}', batch size={len(batch)}; "
                    f"queue size: {self.queue.qsize()}"
                )

            if max_processed_ts is None or published > max_processed_ts:
                max_processed_ts = published

        if max_processed_ts:
            return max_processed_ts.isoformat()
        return None

    async def get_last_posted_timestamp(self, default: datetime) -> datetime:
        """
        Retrieves the last posted timestamp from the database.
        If no timestamp is found or the format is invalid, returns the default value.
        """
        last_posted_ts = await self.db.get_setting("last_posted_timestamp")
        if last_posted_ts:
            try:
                last_posted = datetime.fromisoformat(last_posted_ts)
                if last_posted.tzinfo is None:
                    last_posted = last_posted.replace(tzinfo=timezone.utc)
                return last_posted
            except Exception as e:
                logger.error(f"Invalid timestamp format in settings: {last_posted_ts} ({e}). Using default.")
        logger.info("last_posted_timestamp not found, using default.")
        if default.tzinfo is None:
            default = default.replace(tzinfo=timezone.utc)
        return default

    def extract_img_links(self, html: str) -> List[str]:
        """
        Extracts image URLs from HTML content.
        """
        soup = self.soup_parser(html, 'html.parser')
        links = [img.get('src') for img in soup.find_all('img') if img.get('src')]
        logger.debug(f"Extracted {len(links)} image links from HTML.")
        return links

    def should_skip_entry(self, entry: feedparser.FeedParserDict) -> bool:
        """
        Hook method for filtering an entry.
        The base implementation (for Pixiv) checks for the presence of forbidden categories:
        "漫画", "R-18", "AI".

        Child classes can override this method.
        """
        category = entry.get("category", "")
        if isinstance(category, list):
            if any(("漫画" in cat) or ("R-18" in cat) or ("AI" in cat) for cat in category):
                return True
        else:
            if ("漫画" in category) or ("R-18" in category) or ("AI" in category):
                return True
        return False
