import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from animachpostingbot.logging_config import setup_logging

setup_logging()

from animachpostingbot.config.config import RSSHUB_URL, TELEGRAM_BOT_TOKEN, CHECK_INTERVAL_IN_SECONDS, \
    NOTIFICATION_CHAT_ID
from animachpostingbot.parsers.pixiv_parser import PixivParser
from animachpostingbot.workers import worker
from animachpostingbot.database.database import db_instance as db
from animachpostingbot.bot.admin import register_admin_handlers


async def get_urls_from_db(database: type(db)):
    """
    Retrieve a list of user IDs from the database and construct local feed URLs.
    If no users are found, a default user ID is used.
    """
    user_ids = await database.list_users()
    if not user_ids:
        user_ids = ["4729811"]
        logger.warning(f"No users found in the database; using default user IDs: {user_ids}")
    urls = [f"{RSSHUB_URL}pixiv/user/{user_id}" for user_id in user_ids]
    return urls


async def process_feeds(database: type(db), queue: asyncio.Queue) -> Optional[str]:
    """
    Creates parsers for each URL and processes their feeds to add items to the queue.
    Returns the maximum published timestamp (ISO string) among all processed entries,
    or None if no entry was processed.
    """
    urls = await get_urls_from_db(database)
    parsers = [PixivParser(url, queue, database) for url in urls]
    parser_tasks = [asyncio.create_task(parser.parse_data()) for parser in parsers]
    parsed_data = await asyncio.gather(*parser_tasks)

    max_timestamps = []
    for parser, data in zip(parsers, parsed_data):
        ts = await parser.process_feed(data)
        if ts:
            max_timestamps.append(ts)

    if max_timestamps:
        return max(max_timestamps)
    return None

async def initialize_posted_guids(db):
    """
    Loads posted GUIDs from the database and updates the in-memory set.
    """
    posted_guids = await db.list_posted_guids()
    worker.processed_guids.update(posted_guids)


async def main_loop():
    await db.init_db()
    await initialize_posted_guids(db)
    queue = asyncio.Queue()

    from telegram.ext import ApplicationBuilder
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    register_admin_handlers(app)

    await app.initialize()
    await app.start()
    polling_task = asyncio.create_task(app.updater.start_polling())

    num_workers = 2
    worker_tasks = [asyncio.create_task(worker.worker(queue, db, worker_id=i + 1)) for i in range(num_workers)]
    check_interval_in_seconds = CHECK_INTERVAL_IN_SECONDS

    try:
        while True:
            logger.info("Starting a new feed processing cycle.")
            new_last_ts = await process_feeds(db, queue)
            await queue.join()

            logger.info(f"Cycle complete. Total messages posted to Telegram: {worker.messages_posted_count}")

            if new_last_ts:
                await db.set_setting("last_posted_timestamp", new_last_ts)
                logger.info(f"Updated last_posted_timestamp to {new_last_ts}.")
            else:
                logger.info("No new posts processed; last_posted_timestamp not updated.")

            # Reset the counter for the next cycle.
            worker.messages_posted_count = 0

            logger.info(f"Sleeping for {check_interval_in_seconds} seconds...")
            await asyncio.sleep(check_interval_in_seconds)
    except (KeyboardInterrupt, asyncio.CancelledError) as e:
        logger.info("Shutdown signal received, cancelling tasks...")
        raise
    except Exception as e:
        error_message = f"Bot encountered an error and stopped: {e}"
        logger.error(error_message)
        try:
            await app.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=error_message)
        except Exception as notify_exception:
            logger.error(f"Failed to send notification to chat {NOTIFICATION_CHAT_ID}: {notify_exception}")
        raise
    finally:
        for task in worker_tasks:
            task.cancel()
        polling_task.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == '__main__':
    asyncio.run(main_loop())
