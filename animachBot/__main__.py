from animachBot.config.config import Config
from pathlib import Path
from animachBot.logger.logger import logger
from animachBot.database.database import Database
from animachBot.rss_feed_parser.rss_feed_parser import FeedParser
from animachBot.telegram_bot.telegram_bot_media import TelegramMediaGroupSender


def main():
    config_path = Path("../config/config.yml")
    config = Config(config_path)
    db = Database(config.get("animachBot.database.path"))
    db.connect()
    feed_parser = FeedParser(db)
    telegram_sender = TelegramMediaGroupSender(config.get("animachBot.telegram.bot_token"), config.get("animachBot.telegram.channel_id"))
    for entry_data in feed_parser.process_fetched_feeds():
        telegram_sender.send_media_group([entry_data])


if __name__ == '__main__':
    main()
