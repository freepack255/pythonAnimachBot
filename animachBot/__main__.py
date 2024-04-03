from animachBot.config.config import Config
from pathlib import Path
from animachBot.database.database import Database
from animachBot.rss_feed_parser.rss_feed_parser import FeedParser


def main():
    config_path = Path("../config/config.yml")
    config = Config(config_path)
    db = Database(config.get("animachBot.database.path"))
    db.connect()
    parser = FeedParser(db)
    for feed in parser.process_fetched_feeds():
        print(feed)  # Do something with the feed data


if __name__ == '__main__':
    main()
