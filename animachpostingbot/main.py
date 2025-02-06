import asyncio
from datetime import datetime, timezone
from typing import Optional, List

from loguru import logger
from animachpostingbot.logging_config import setup_logging

setup_logging()

from animachpostingbot.config.config import (
    RSSHUB_URL,
    TELEGRAM_BOT_TOKEN,
    CHECK_INTERVAL_IN_SECONDS,
    NOTIFICATION_CHAT_ID, START_FROM_PARSING_DATE,
)
from animachpostingbot.parsers.PixivParser import PixivParser
from animachpostingbot.parsers.TwitterParser import TwitterParser  # Assumed to exist
from animachpostingbot.workers import worker  # for worker.worker and shared globals
from animachpostingbot.database.database import db_instance as db
from animachpostingbot.bot.admin import register_admin_handlers


async def get_pixiv_urls_from_db(database: type(db)) -> List[str]:
    """
    Retrieve a list of Pixiv user IDs from the database and construct Pixiv feed URLs.
    If no Pixiv users are found, a default user ID is used.
    """
    user_ids_pixiv = await database.list_users_by_source("pixiv")
    if not user_ids_pixiv:
        user_ids_pixiv = ["4729811"]
        logger.warning(
            f"No Pixiv users found in the database; using default user IDs: {user_ids_pixiv}"
        )
    urls = [f"{RSSHUB_URL}pixiv/user/{user_id}" for user_id in user_ids_pixiv]
    return urls


async def get_twitter_urls_from_db(database: type(db)) -> List[str]:
    """
    Retrieve a list of Twitter user IDs from the database and construct Twitter feed URLs.
    If no Twitter users are found, returns an empty list.
    """
    user_ids_twitter = await database.list_users_by_source("twitter")
    if not user_ids_twitter:
        logger.warning("No Twitter users found in the database; skipping Twitter feeds.")
        return []
    # Construct URL for each Twitter user. Adjust query parameters as needed.
    urls = [
        f"{RSSHUB_URL}twitter/media/{user_id}/onlyMedia=1&addLinkForPics=1"
        for user_id in user_ids_twitter
    ]
    return urls


async def process_feeds(database: type(db), queue: asyncio.Queue) -> Optional[str]:
    """
    Creates parsers for each URL (both Pixiv and Twitter), processes their feeds,
    and adds items to the queue.
    Returns the maximum published timestamp (as an ISO string) among all processed entries,
    or None if no entry was processed.
    """
    # Retrieve URLs for each source
    pixiv_urls = await get_pixiv_urls_from_db(database)
    twitter_urls = await get_twitter_urls_from_db(database)

    # Create parser instances for each URL
    pixiv_parsers = [PixivParser(url, queue, database) for url in pixiv_urls]
    twitter_parsers = [TwitterParser(url, queue, database) for url in twitter_urls]

    # Combine both lists
    all_parsers = pixiv_parsers+twitter_parsers

    # Start feed parsing tasks in parallel.
    parser_tasks = [asyncio.create_task(parser.parse_data()) for parser in all_parsers]
    parsed_data = await asyncio.gather(*parser_tasks)

    max_timestamps = []
    for parser, data in zip(all_parsers, parsed_data):
        ts = await parser.process_feed(data, default_start=START_FROM_PARSING_DATE)
        if ts:
            max_timestamps.append(ts)

    return max(max_timestamps) if max_timestamps else None


async def initialize_posted_guids(database: type(db)) -> None:
    """
    Loads posted GUIDs from the database and updates the in-memory set in the worker module.
    """
    posted_guids = await database.list_posted_guids()
    worker.processed_guids.update(posted_guids)
    logger.info(f"Initialized posted GUIDs: {len(posted_guids)} items loaded.")


async def init_telegram_bot() -> "Application":
    """
    Initializes the Telegram bot application, registers admin handlers,
    and starts the updater polling.
    """
    from telegram.ext import ApplicationBuilder

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    register_admin_handlers(app)

    await app.initialize()
    await app.start()
    # Start polling in a separate task.
    polling_task = asyncio.create_task(app.updater.start_polling())
    logger.info("Telegram bot initialized and polling started.")
    return app, polling_task


async def shutdown_telegram_bot(app, polling_task, worker_tasks: List[asyncio.Task]) -> None:
    """
    Cancels worker tasks, stops polling, and shuts down the Telegram bot.
    """
    for task in worker_tasks:
        task.cancel()
    polling_task.cancel()
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("Telegram bot shutdown completed.")


async def processing_cycle(app, db, queue: asyncio.Queue) -> Optional[str]:
    """
    Processes one feed processing cycle:
      - Processes feeds and enqueues new items.
      - Waits for the queue to be emptied.
      - Updates the last posted timestamp in the database.
    Returns the new last posted timestamp (if any).
    """
    logger.info("Starting a new feed processing cycle.")
    new_last_ts = await process_feeds(db, queue)
    await queue.join()  # Wait for all enqueued items to be processed.
    logger.info(
        f"Cycle complete. Total messages posted to Telegram: {worker.messages_posted_count}"
    )
    if new_last_ts:
        await db.set_setting("last_posted_timestamp", new_last_ts)
        logger.info(f"Updated last_posted_timestamp to {new_last_ts}.")
    else:
        logger.info("No new posts processed; last_posted_timestamp not updated.")
    # Reset the counter for the next cycle.
    worker.messages_posted_count = 0
    return new_last_ts


async def main_loop() -> None:
    """
    Main event loop:
      - Initializes the database and posted GUIDs.
      - Initializes the Telegram bot and starts worker tasks.
      - Runs the feed processing cycle repeatedly with a sleep interval.
    """
    await db.init_db()
    await initialize_posted_guids(db)
    queue = asyncio.Queue()

    # Initialize Telegram bot application and start polling.
    app, polling_task = await init_telegram_bot()

    # Start worker tasks.
    num_workers = 2
    worker_tasks = [
        asyncio.create_task(worker.worker(queue, db, worker_id=i + 1))
        for i in range(num_workers)
    ]
    check_interval = CHECK_INTERVAL_IN_SECONDS

    try:
        while True:
            await processing_cycle(app, db, queue)
            logger.info(f"Sleeping for {check_interval} seconds...")
            await asyncio.sleep(check_interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received, cancelling tasks...")
        raise
    except Exception as e:
        error_message = f"Bot encountered an error and stopped: {e}"
        logger.error(error_message)
        try:
            await app.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=error_message)
        except Exception as notify_exception:
            logger.error(
                f"Failed to send notification to chat {NOTIFICATION_CHAT_ID}: {notify_exception}"
            )
        raise
    finally:
        await shutdown_telegram_bot(app, polling_task, worker_tasks)


if __name__ == '__main__':
    asyncio.run(main_loop())
