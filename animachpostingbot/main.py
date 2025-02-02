import asyncio
from datetime import datetime, timezone
from loguru import logger
from animachpostingbot.logging_config import setup_logging

setup_logging()

from animachpostingbot.config.config import RSSHUB_URL, TELEGRAM_BOT_TOKEN, START_FROM_PARSING_DATE, TELEGRAM_CHANNEL_ID
from animachpostingbot.parsers.pixiv_parser import PixivParser
from animachpostingbot.workers.worker import worker, processed_guids
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

async def process_feeds(database: type(db), queue: asyncio.Queue):
    """
    Creates parsers for each URL and processes their feeds to add items to the queue.
    """
    urls = await get_urls_from_db(database)
    parsers = [PixivParser(url, queue, database) for url in urls]
    # Iterate over each parser and call its parse_data method.
    parser_tasks = [asyncio.create_task(parser.parse_data()) for parser in parsers]
    parsed_data = await asyncio.gather(*parser_tasks)
    process_tasks = [
        asyncio.create_task(parser.process_feed(data))
        for parser, data in zip(parsers, parsed_data)
    ]
    await asyncio.gather(*process_tasks)

async def initialize_posted_guids(db):
    """
    Loads posted GUIDs from the database and updates the in-memory set.
    """
    posted_guids = await db.list_posted_guids()
    processed_guids.update(posted_guids)

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
    worker_tasks = [asyncio.create_task(worker(queue, db, worker_id=i + 1)) for i in range(num_workers)]
    check_interval = 6 * 3600  # 6 hours

    try:
        while True:
            logger.info("Starting a new feed processing cycle.")
            await process_feeds(db, queue)
            await queue.join()
            # Update last_posted_timestamp setting to current UTC time.
            now_ts = datetime.now(timezone.utc).isoformat()
            await db.set_setting("last_posted_timestamp", now_ts)
            logger.info(f"Feed processing cycle complete. Updated last_posted_timestamp to {now_ts}. Sleeping for 6 hours...")
            await asyncio.sleep(check_interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received, cancelling tasks...")
    finally:
        for task in worker_tasks:
            task.cancel()
        polling_task.cancel()
        # Stop the updater to avoid "This Updater is still running!" error.
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main_loop())
