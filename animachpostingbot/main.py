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
from animachpostingbot.parsers.TwitterParser import TwitterParser
# Import the specific exception from your Parser module
from animachpostingbot.parsers.Parser import InvalidFeed
from animachpostingbot.workers import worker
from animachpostingbot.database.database import db_instance as db
from animachpostingbot.bot.admin import register_admin_handlers


async def get_pixiv_urls_from_db(database: type(db)) -> List[str]:
    """
    Retrieve a list of Pixiv user IDs from the database and construct Pixiv feed URLs.
    If no Pixiv users are found, a default user ID is used.
    """
    user_ids_pixiv = await database.list_users_by_source("pixiv")
    if not user_ids_pixiv:
        user_ids_pixiv = ["4729811"] # Default user if none in DB
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
    pixiv_urls = await get_pixiv_urls_from_db(database)
    twitter_urls = await get_twitter_urls_from_db(database)

    pixiv_parsers = [PixivParser(url, queue, database) for url in pixiv_urls]
    twitter_parsers = [TwitterParser(url, queue, database) for url in twitter_urls]

    all_parsers = pixiv_parsers + twitter_parsers
    if not all_parsers:
        logger.info("No parsers configured. Skipping feed processing.")
        return None

    # Initialize list for parsed_data with Nones for proper zip pairing later
    parsed_data_results = [None] * len(all_parsers)
    tasks = []
    # Create tasks and store them with their original index
    for i, parser_instance in enumerate(all_parsers):
        # Wrap parser.parse_data() to catch exceptions per-parser
        async def safe_parse_data(p_instance, index):
            try:
                return await p_instance.parse_data()
            except (InvalidFeed, asyncio.TimeoutError) as e:
                logger.error(f"Failed to fetch/parse feed for {p_instance.url} after retries: {e}. This feed will be skipped in the current cycle.")
                return None # Indicate failure for this specific feed
            except Exception as e:
                logger.error(f"Unexpected error fetching/parsing feed for {p_instance.url}: {e}", exc_info=True)
                return None # Indicate failure

        tasks.append(asyncio.create_task(safe_parse_data(parser_instance, i)))

    # Gather results of parsing tasks
    results = await asyncio.gather(*tasks, return_exceptions=False) # Exceptions are handled in safe_parse_data

    for i, data in enumerate(results):
        parsed_data_results[i] = data


    max_timestamps = []
    for parser, feed_data in zip(all_parsers, parsed_data_results):
        if feed_data is None: # Skip if parse_data failed for this parser
            logger.warning(f"Skipping process_feed for {parser.url} as fetching/parsing failed or returned no data.")
            continue
        try:
            ts = await parser.process_feed(feed_data, default_start=START_FROM_PARSING_DATE)
            if ts:
                max_timestamps.append(ts)
        except Exception as e:
            logger.error(f"Error processing feed data for {parser.url}: {e}", exc_info=True)
            # Optionally, decide if this should halt the cycle or just skip this feed's processing part

    return max(max_timestamps) if max_timestamps else None


async def initialize_posted_guids(database: type(db)) -> None:
    """
    Loads posted GUIDs from the database and updates the in-memory set in the worker module.
    """
    posted_guids = await database.list_posted_guids()
    worker.processed_guids.update(posted_guids) #
    logger.info(f"Initialized posted GUIDs: {len(posted_guids)} items loaded.")


async def init_telegram_bot() -> "Application":
    """
    Initializes the Telegram bot application, registers admin handlers,
    and starts the updater polling.
    """
    from telegram.ext import Application # Local import for type hint

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    register_admin_handlers(app) #

    await app.initialize()
    await app.start()
    polling_task = asyncio.create_task(app.updater.start_polling())
    logger.info("Telegram bot initialized and polling started.")
    return app, polling_task


async def shutdown_telegram_bot(app, polling_task, worker_tasks: List[asyncio.Task]) -> None:
    """
    Cancels worker tasks, stops polling, and shuts down the Telegram bot.
    """
    logger.info("Attempting to shut down Telegram bot and worker tasks...")
    for task in worker_tasks:
        if task and not task.done():
            task.cancel()
    if polling_task and not polling_task.done():
        polling_task.cancel()

    # Wait for tasks to cancel
    await asyncio.gather(*worker_tasks, polling_task, return_exceptions=True)


    if app and app.updater and app.updater.running:
        await app.updater.stop()
    if app and app.running:
        await app.stop()
    if app: # Ensure app exists before calling shutdown
        await app.shutdown()
    logger.info("Telegram bot shutdown completed.")


async def processing_cycle(app, db_conn, queue: asyncio.Queue) -> Optional[str]:
    """
    Processes one feed processing cycle:
      - Processes feeds and enqueues new items.
      - Waits for the queue to be emptied.
      - Updates the last posted timestamp in the database.
    Returns the new last posted timestamp (if any).
    """
    logger.info("Starting a new feed processing cycle.")
    # `process_feeds` now handles its own InvalidFeed exceptions per feed.
    # If it raises an unhandled exception, it would be caught by main_loop's critical error handler.
    new_last_ts = await process_feeds(db_conn, queue)

    await queue.join()
    logger.info(
        f"Cycle complete. Total messages posted to Telegram: {worker.messages_posted_count}" #
    )
    if new_last_ts:
        await db_conn.set_setting("last_posted_timestamp", new_last_ts)
        logger.info(f"Updated last_posted_timestamp to {new_last_ts}.")
    else:
        logger.info("No new posts processed; last_posted_timestamp not updated.")
    worker.messages_posted_count = 0 #
    return new_last_ts


async def main_loop() -> None:
    """
    Main event loop:
      - Initializes the database and posted GUIDs.
      - Initializes the Telegram bot and starts worker tasks.
      - Runs the feed processing cycle repeatedly with a sleep interval.
    """
    # Ensure app and polling_task are defined in a broader scope for finally block
    app = None
    polling_task = None
    worker_tasks = []

    try:
        await db.init_db() #
        await initialize_posted_guids(db) #
        queue = asyncio.Queue()

        app, polling_task = await init_telegram_bot()

        num_workers = 2  # Consider moving to config
        worker_tasks = [
            asyncio.create_task(worker.worker(queue, db, worker_id=i + 1)) #
            for i in range(num_workers)
        ]
        check_interval = CHECK_INTERVAL_IN_SECONDS #

        while True:
            try:
                await processing_cycle(app, db, queue)
            except (InvalidFeed, asyncio.TimeoutError) as e:
                # This will catch errors if they escape process_feeds,
                # though process_feeds is designed to handle them internally per feed.
                # This acts as a fallback for the whole cycle.
                logger.error(f"A feed-related error bubbled up to the main loop, "
                               f"skipping current processing cycle: {e}")
                # Optionally, send a notification about cycle skip
                # await app.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=f"Warning: Feed processing cycle skipped. Error: {e}")
            except Exception as e:
                # Catch other unexpected errors during the processing cycle
                logger.error(f"Unexpected error during processing_cycle, skipping cycle: {e}", exc_info=True)
                # Optionally notify, but this might indicate a more serious issue than a single feed failing

            logger.info(f"Sleeping for {check_interval} seconds...")
            await asyncio.sleep(check_interval)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received, initiating graceful shutdown...")
    except Exception as e:  # Catch-all for critical errors during setup or unhandled in loop
        error_message = f"Bot encountered a critical error and will stop: {e}"
        logger.critical(error_message, exc_info=True)
        try:
            if app and hasattr(app, 'bot') and NOTIFICATION_CHAT_ID: #
                 await app.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=error_message) #
        except Exception as notify_exception:
            logger.error(
                f"Failed to send critical error notification to chat {NOTIFICATION_CHAT_ID}: {notify_exception}" #
            )
        # No re-raise here, as 'finally' should always execute for cleanup.
    finally:
        logger.info("Main loop concluding. Initiating shutdown sequence in finally block...")
        if app and polling_task: # Ensure they were initialized
            await shutdown_telegram_bot(app, polling_task, worker_tasks)
        else:
            logger.warning("App or polling_task not initialized, limited shutdown.")
            # Still cancel any worker tasks that might have been created
            for task in worker_tasks:
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        logger.info("Shutdown sequence in finally block completed. Bot exiting.")


if __name__ == '__main__':
    asyncio.run(main_loop())