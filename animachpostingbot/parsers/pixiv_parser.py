import asyncio
import feedparser
from datetime import datetime, timezone
from typing import Any, List, Tuple, Optional
from bs4 import BeautifulSoup
from loguru import logger
from animachpostingbot.config.config import START_FROM_PARSING_DATE
from animachpostingbot.database.database import db_instance as db
from urllib.parse import urlparse


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Splits a list into chunks of the specified size.
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def normalize_guid(guid: str) -> str:
    if not guid:
        return ""
    # Use urlparse to extract the path part, then take the last segment.
    path = urlparse(guid).path
    normalized = path.rstrip("/").split("/")[-1]
    return normalized


class PixivParser:
    def __init__(self, url: str, queue: asyncio.Queue[Tuple[str, List[str], str, str, str]], database: db = None):
        """
        Initializes the parser with an RSS feed URL, a processing queue, and an optional Database instance.

        :param url: The URL of the RSS feed.
        :param queue: An asynchronous queue for storing results.
                      Each item is a tuple: (title, list of image URLs, user_link, normalized_guid, author).
        :param database: (Optional) A Database instance used for duplicate checking.
        """
        self.url = url
        self.queue = queue
        self.db = database
        self.soup_parser = BeautifulSoup
        logger.info(f"PixivParser initialized with URL: {self.url}")

    async def fetch_feed(self) -> feedparser.FeedParserDict:
        """
        Fetches and parses the RSS feed.
        """
        logger.info(f"Fetching data from Pixiv feed: {self.url}")
        feed = await asyncio.to_thread(feedparser.parse, self.url)
        if feed.get("bozo"):
            logger.error(f"Error fetching/parsing feed from {self.url}: {feed.get('bozo_exception')}")
        if "status" in feed and feed["status"] != 200:
            logger.error(f"Unexpected HTTP status {feed['status']} while fetching feed from {self.url}")
        logger.debug(f"Fetched feed with {len(feed.entries)} entries.")
        return feed

    async def parse_data(self) -> feedparser.FeedParserDict:
        """
        A helper method wrapping fetch_feed().
        """
        return await self.fetch_feed()

    async def process_feed(self, feed: feedparser.FeedParserDict) -> Optional[str]:
        """
        Processes RSS feed entries and adds valid items to the queue.
        Duplicate-checking is performed using a local in-memory set so that the same feed entry (normalized GUID)
        is processed only once per cycle. Also returns the maximum published timestamp (as an ISO string)
        among the processed entries, or None if no entry was processed.
        """
        logger.info(f"Processing data from {self.url}")

        # Get last posted timestamp from the settings table; fallback to default if not set.
        last_posted_ts = await self.db.get_setting("last_posted_timestamp")
        if last_posted_ts:
            try:
                last_posted = datetime.fromisoformat(last_posted_ts)
                if last_posted.tzinfo is None:
                    last_posted = last_posted.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.error(f"Invalid timestamp format in settings: {last_posted_ts} ({e}). Using default.")
                last_posted = START_FROM_PARSING_DATE
        else:
            logger.info("No last_posted_timestamp setting found, using default start date.")
            last_posted = START_FROM_PARSING_DATE
            if last_posted.tzinfo is None:
                last_posted = last_posted.replace(tzinfo=timezone.utc)

        logger.debug(f"Using last_posted timestamp: {last_posted.isoformat()}")

        # Local set to track processed feed entries (by normalized GUID) in this cycle.
        processed_entries = set()

        # Extract the user (channel) link from the feed's channel data.
        user_link = feed.feed.get("link", "")
        if not user_link:
            logger.warning("No user link found in channel data; falling back to self.url")
            user_link = self.url

        max_processed_ts = None  # Track the maximum published timestamp among processed entries

        for entry in feed.entries:
            raw_guid = entry.get("guid", "")
            normalized_guid = normalize_guid(raw_guid)
            if not normalized_guid:
                logger.debug("Skipping entry with no valid GUID.")
                continue

            title = entry.get("title", "No title")
            logger.debug(f"Processing entry: title='{title}', normalized GUID='{normalized_guid}'")

            # Skip duplicate feed entries in this cycle.
            if normalized_guid in processed_entries:
                logger.info(f"Skipping duplicate feed entry for GUID: {normalized_guid}")
                continue
            processed_entries.add(normalized_guid)

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

            category = entry.get("category", "")
            if isinstance(category, list):
                if any(("漫画" in cat) or ("R-18" in cat) or ("AI" in cat) for cat in category):
                    logger.info(f"Skipping restricted entry (manga/R-18/AI): {entry.get('link', 'no link')}")
                    continue
            else:
                if ("漫画" in category) or ("R-18" in category) or ("AI" in category):
                    logger.info(f"Skipping restricted entry (manga/R-18/AI): {entry.get('link', 'no link')}")
                    continue

            if normalized_guid and self.db:
                if await self.db.is_guid_posted(normalized_guid):
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
                await self.queue.put((title, batch, user_link, normalized_guid, author))
                logger.info(
                    f"Enqueued batch: title='{title}', GUID='{normalized_guid}', batch size={len(batch)}; queue size now: {self.queue.qsize()}"
                )

            # Update max_processed_ts if this entry's published date is greater.
            if max_processed_ts is None or published > max_processed_ts:
                max_processed_ts = published

        if max_processed_ts:
            return max_processed_ts.isoformat()
        return None

    def extract_img_links(self, html: str) -> List[str]:
        """
        Extracts image URLs from an HTML description.
        """
        soup = self.soup_parser(html, 'html.parser')
        links = [img.get('src') for img in soup.find_all('img') if img.get('src')]
        logger.debug(f"Extracted {len(links)} image links from HTML.")
        return links
