import traceback

import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from animachBot.logger.logger import logger
from animachBot.database.database import Database
from hashlib import sha256
from animachBot.image.image_validator import ImageValidator
from animachBot.image.image_resizer import ImageResizer


def extract_img_links_from_entry_description(html):
    """@html: a string with HTML code that contains <img> tags."""
    soup = BeautifulSoup(html, 'html.parser')
    return [img['src'] for img in soup.find_all('img')]


def hash_post_guid(post_guid):
    """Hash the post guid."""
    return sha256(post_guid.encode('utf-8')).hexdigest()


class FeedParser:
    def __init__(self, database: Database):
        self.database = database
        self._cut_off_date = None  # Initialize the cashed cut-off date to None

    def get_post_date_cut_off(self):
        # If the cut-off date is not cached, fetch it from the database
        if self._cut_off_date is None:
            date_str = self.database.get_post_date_cut_off()  # Fetch the date from the database
            if date_str:
                # Transform object from db to datetime
                self._cut_off_date = datetime.fromisoformat(date_str)
        return self._cut_off_date

    def get_last_published_guid(self, feed_url):
        """Get the last post ID from the database."""
        last_published_guid = self.database.get_last_posted_guid(feed_url)
        return last_published_guid

    def process_entries(self, entries, feed_url):
        cut_off_date = self.get_post_date_cut_off()

        for entry in entries:
            published_datetime = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            if published_datetime < cut_off_date:
                logger.debug(f"Post is older than {cut_off_date}: {entry.link}, skipping...")
                continue

            if "R-18" in entry.category:
                logger.info(f"Post with R-18 category found: {entry.link}, skipping...")
                continue

            if not self.database.is_post_exists_in_db(hash_post_guid(entry.id)):

                img_links = extract_img_links_from_entry_description(entry.description)

                images = []
                for img_link in img_links:
                    if img_link:
                        if not ImageValidator().is_valid_image(img_link):
                            img_path = ImageResizer().resize_image(img_link)
                            images.append(img_path)
                        else:
                            images.append(img_link)
                if images is not None:
                    yield {
                        "author": entry.author,
                        "post_link": entry.id,
                        "title": entry.title,
                        "images": images,
                        "feed_url": feed_url
                    }
            else:
                logger.info(f"Post already exists in the database: {entry.link}, skipping...")
                continue

    def process_fetched_feeds(self):
        obtained_urls = self.database.fetch_feed_urls()
        for feed_url in obtained_urls:
            try:
                feed_data = feedparser.parse(feed_url)
                logger.info(f"Fetching feed: {feed_url}")

                if feed_data.status != 200:
                    continue
                get_last_published_guid = self.get_last_published_guid(feed_url)
                new_entries = []
                if get_last_published_guid is None:
                    feed_data.entries.reverse()
                    yield from self.process_entries(feed_data.entries, feed_url)

                for entry in feed_data.entries:
                    if entry.id == get_last_published_guid:
                        break
                    new_entries.append(entry)
                new_entries.reverse()
                yield from self.process_entries(new_entries, feed_url)

            except Exception as e:
                logger.error(f"Error while parsing the feed: {e}")
                traceback.print_exc()
                continue
