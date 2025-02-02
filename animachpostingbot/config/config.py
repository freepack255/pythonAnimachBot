import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

from datetime import datetime
from loguru import logger
from typing import Optional
import sys  # For exiting if critical vars are missing

# Retrieve environment variables
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID: Optional[str] = os.getenv("TELEGRAM_CHANNEL_ID")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "../logs/bot.log")
DB_FILE: str = os.getenv("DB_FILE", "../../data/database.db")
RSSHUB_URL: str = os.getenv("RSSHUB_URL", "http://localhost:1200/")

# Retrieve ADMIN_IDS from the environment; expected as a comma-separated list, e.g. "123456789,987654321"
RAW_ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = []
if RAW_ADMIN_IDS:
    try:
        ADMIN_IDS = [int(x.strip()) for x in RAW_ADMIN_IDS.split(",") if x.strip()]
    except Exception as e:
        logger.error(f"Error parsing ADMIN_IDS: {e}")

# Check for critical environment variables
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_BOT_TOKEN.strip():
    logger.critical("TELEGRAM_BOT_TOKEN is not set in the environment. Exiting!")
    sys.exit(1)
if not TELEGRAM_CHANNEL_ID or not TELEGRAM_CHANNEL_ID.strip():
    logger.critical("TELEGRAM_CHANNEL_ID is not set in the environment. Exiting!")
    sys.exit(1)

# Define a default date and the expected date format for the environment variable.
DEFAULT_DATE: datetime = datetime(2025, 1, 1)
ENV_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%SZ"  # For example, "2023-01-01 00:00:00Z"

def parse_env_date(date_str: Optional[str], fmt: str, default: datetime) -> datetime:
    """
    Parses a date string using the provided format.
    If parsing fails or the input is None/empty, returns the default date.

    :param date_str: Date string from the environment variable.
    :param fmt: Format to parse the date string.
    :param default: Default datetime to return in case of parsing failure.
    :return: Parsed datetime object or the default.
    """
    if not date_str or not date_str.strip():
        logger.warning("START_FROM_PARSING_DATE is not set or empty. Using default date.")
        return default
    try:
        return datetime.strptime(date_str, fmt)
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing START_FROM_PARSING_DATE: {e}")
        return default

# Get the date string from the environment variable and parse it using the new format.
env_date_str: Optional[str] = os.getenv("START_FROM_PARSING_DATE")
START_FROM_PARSING_DATE: datetime = parse_env_date(env_date_str, ENV_DATE_FORMAT, DEFAULT_DATE)

# For debugging: print the parsed date
logger.info(f"START_FROM_PARSING_DATE: {START_FROM_PARSING_DATE}")
