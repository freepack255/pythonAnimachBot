from animachpostingbot.parsers.Parser import Parser
from loguru import logger


class TwitterParser(Parser):
    def __init__(self, url: str, queue, database):
        """
        Initializes XParser by calling the parent class constructor.
        """
        super().__init__(url, queue, database)
        logger.info("XParser initialized")

    def should_skip_entry(self, entry):
        """
        Overridden filtering logic for XParser.
        For example, this source might not require filtering by categories.
        """
        # There is no tags or categories in the feed, so we skip nothing.
        return False
