import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from animachBot.logger.logger import logger
from animachBot.database.database import Database


def extract_img_links_from_entry_description(html):
    """@html: a string with HTML code that contains <img> tags."""
    soup = BeautifulSoup(html, 'html.parser')
    return [img['src'] for img in soup.find_all('img')]


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

    def last_published_guid(self, feed_url):
        """Get the last post ID from the database."""
        last_published_guid = self.database.get_last_post_id(feed_url)
        return last_published_guid

    def process_entries(self, entries):
        cut_off_date = self.get_post_date_cut_off()
        for entry in entries:
            published_datetime = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published_datetime < cut_off_date:
                continue
            if "R-18" in entry.category:
                logger.info(f"Post with R-18 category found: {entry.link}, skipping...")
                continue
            if not self.database.is_post_exists_in_db(entry.id):
                img_links = extract_img_links_from_entry_description(entry.description)
                yield {
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.published,
                    'img_links': img_links,
                    'author': entry.author,
                    'id': entry.id,
                    'category': entry.category,
                }

    def process_fetched_feeds(self):
        obtained_urls = self.database.fetch_feed_urls()
        for feed_url in obtained_urls:
            try:
                feed_data = feedparser.parse(feed_url)
                logger.info(f"Fetching feed: {feed_url}")

                if feed_data.status == 200:
                    last_published_guid = self.last_published_guid(feed_url)
                    new_entries = []
                    if last_published_guid is not None:
                        for entry in feed_data.entries:
                            if entry.id == last_published_guid:
                                break
                            new_entries.append(entry)
                        processed_entries = reversed(new_entries)
                    else:
                        processed_entries = feed_data.entries  # If no last_published_guid, process all entries

                    yield from self.process_entries(processed_entries)
            except Exception as e:
                logger.error(f"Error while parsing the feed: {e}")
                continue
