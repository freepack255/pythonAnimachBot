from animachpostingbot.parsers.Parser import Parser
from loguru import logger


class PixivParser(Parser):
    def __init__(self, url: str, queue, database):
        """
        Initializes PixivParser by calling the parent class constructor.
        """
        super().__init__(url, queue, database)
        logger.info("PixivParser initialized")

    # If the logic for Pixiv is identical to the base class, no further overrides are necessary.
    # You can override methods (e.g., should_skip_entry) if specific behavior is needed.
