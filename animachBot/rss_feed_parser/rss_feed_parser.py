import feedparser
from animachBot.database.database import Database


class FeedParser:
    def __init__(self, feed_url, database: Database):
        self.database = database
        self.feed_url = feed_url
        self.feed_data = None

    def fetch_feeds(self):
        self.feed_data = feedparser.parse(self.feed_url)
        if self.feed_data.bozo:
            raise ValueError(f"FeedParserError: {self.feed_data.bozo_exception}")
