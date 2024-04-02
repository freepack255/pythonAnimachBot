import feedparser
from bs4 import BeautifulSoup
from animachBot.database.database import Database


def extract_img_links_from_entry_description(html):
    """
    @html: a string with HTML code that contains <img> tags.
    """
    soup = BeautifulSoup(html, 'html.parser')
    return [img['src'] for img in soup.find_all('img')]


class FeedParser:
    def __init__(self, database: Database):
        self.database = database

    def fetch_feeds(self):
        for feed in self.database.fetch_feed_urls():
            feed_data = feedparser.parse(feed['url'])
            if feed.status != 404 and feed_data.bozo:
                for entry in feed_data.entries:
                    img_links = extract_img_links_from_entry_description(entry.description)
                    yield {
                        'title': entry.title,
                        'link': entry.link,
                        'published': entry.published,
                        'img_links': img_links
                    }
                raise ValueError(f"FeedParserError: {feed_data.bozo_exception}")
