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

    def fetch_feeds(self):
        """Fetches feeds from the database and parses them."""
        obtained_urls = self.database.fetch_feed_urls()
        cut_off_date = self.get_post_date_cut_off()
        for feed_url in obtained_urls:
            try:
                feed_data = feedparser.parse(feed_url)
                if feed_data.status == 200:  # Check if the feed was fetched successfully
                    for entry in reversed(feed_data.entries):
                        if entry.published_parsed:  # Check if the entry has a published date
                            published_datetime = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            if published_datetime < cut_off_date:  # If the post is older than the cut-off date,
                                break
                            else:
                                if "R-18" in entry.category:  # Skip R-18 posts
                                    logger.info(f"Post with R-18 category found: {entry.link}, skipping...")
                                    continue
                                elif not self.database.is_post_exists_in_db(entry.id):
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
            except Exception as e:
                logger.error(f"Error while parsing the feed: {e}")
                continue
