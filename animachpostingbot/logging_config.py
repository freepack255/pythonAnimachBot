import sys
from loguru import logger

def setup_logging():
    """
    Configures the logger with both console and file handlers.
    Console output will be colored.
    """
    # Local import ensures that config.py is fully initialized.
    from animachpostingbot.config.config import LOG_LEVEL, LOG_FILE

    # Remove any previously configured sinks
    logger.remove()

    # Add a colored console sink using sys.stdout.
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        colorize=True,
    )

    # Add a file sink (colors are not needed in a log file).
    logger.add(
        LOG_FILE,
        level=LOG_LEVEL,
        encoding="utf-8",
        rotation="10 MB",
        compression="zip",
    )
