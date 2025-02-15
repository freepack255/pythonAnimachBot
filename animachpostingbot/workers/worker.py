import asyncio
from loguru import logger
from animachpostingbot.bot.telegram_bot import send_images_to_telegram, application
from animachpostingbot.config.config import TELEGRAM_CHANNEL_ID
from animachpostingbot.database.database import db_instance  # for type hints

# Global lock to protect duplicate checking.
duplicate_lock = asyncio.Lock()

# In-memory set to track normalized GUIDs processed during the current cycle.
processed_guids = set()

# Global dictionary to record the media_group_id for each GUID.
sent_media_groups = {}  # {normalized_guid: media_group_id}

# Global counter for messages posted
messages_posted_count = 0


async def check_duplicate_and_mark(db, guid: str, worker_id: int) -> bool:
    """
    Checks if the normalized_guid has already been processed or exists in the database.
    If not, marks it as processed.

    Returns True if it is a duplicate; False otherwise.
    """
    async with duplicate_lock:
        if guid in processed_guids or await db.is_guid_posted(guid):
            logger.info(f"[Worker {worker_id}] Skipping duplicate normalized_guid '{guid}'.")
            return True
        processed_guids.add(guid)
        return False


async def process_successful_post(worker_id: int, guid: str, messages, db) -> None:
    """
    Process a successful posting to Telegram by extracting message details,
    updating the database, and handling potential duplicate media groups.
    """
    # Extract Telegram message link from the first message in the returned list
    short_id = str(TELEGRAM_CHANNEL_ID)[4:]
    first_msg = messages[0]
    tg_message_link = f"https://t.me/c/{short_id}/{first_msg.message_id}"
    logger.info(
        f"[Worker {worker_id}] Posting succeeded for normalized_guid '{guid}', "
        f"adding to database with link {tg_message_link}."
    )

    media_group_id = getattr(first_msg, "media_group_id", None)

    # If this normalized_guid has been seen before, compare media_group_ids
    if guid in sent_media_groups:
        original_media_group_id = sent_media_groups[guid]
        if media_group_id != original_media_group_id:
            logger.warning(
                f"[Worker {worker_id}] Duplicate detected for normalized_guid '{guid}'. "
                f"Original media_group_id: {original_media_group_id}, new: {media_group_id}. "
                f"Deleting duplicate message with ID {first_msg.message_id}."
            )
            try:
                await application.bot.delete_message(
                    chat_id=TELEGRAM_CHANNEL_ID, message_id=first_msg.message_id
                )
            except Exception as e:
                logger.error(f"[Worker {worker_id}] Error deleting duplicate message: {e}")
        else:
            logger.warning(
                f"[Worker {worker_id}] Received identical media_group_id for normalized_guid '{guid}'."
            )
    else:
        # Save the media group id for future comparisons
        sent_media_groups[guid] = media_group_id
        await db.add_posted_guid(guid)
        await db.update_tg_message_link(guid, tg_message_link)

    global messages_posted_count
    messages_posted_count += 1


async def process_failed_post(worker_id: int, guid: str, result: str) -> None:
    """
    Logs the failure of a post operation.
    If the error message indicates that there are no images to send,
    it logs a warning instead of an error.
    """
    if "No images to send" in result:
        logger.warning(f"[Worker {worker_id}] Posting skipped for GUID '{guid}': {result}")
    else:
        logger.error(f"[Worker {worker_id}] Posting failed for GUID '{guid}': {result}")



async def worker(queue: asyncio.Queue, db, worker_id: int) -> None:
    """
    Worker loop that processes queue items.

    Each queue item is a tuple:
       (image_urls, guid)
    """
    global messages_posted_count
    while True:
        image_urls, user_link, guid = await queue.get()
        logger.info(
            f"[Worker {worker_id}] Processing item: user_link='{user_link}', guid='{guid}', "
            f"number of images={len(image_urls)}"
        )

        # Check for duplicate processing
        is_duplicate = await check_duplicate_and_mark(db, guid, worker_id)
        if is_duplicate:
            queue.task_done()
            continue

        try:
            success, result = await send_images_to_telegram(
                image_urls, user_link, guid
            )
            logger.debug(
                f"[Worker {worker_id}] send_images_to_telegram returned: success={success}, result={result}"
            )
        except Exception as e:
            logger.error(
                f"[Worker {worker_id}] Error sending images for guid '{guid}': {e}"
            )
            success, result = False, str(e)

        if success:
            # Expecting result to be a list of Telegram Message objects.
            messages = result
            if messages and hasattr(messages[0], "message_id"):
                await process_successful_post(worker_id, guid, messages, db)
            else:
                logger.info(
                    f"[Worker {worker_id}] Posting succeeded for guid '{guid}' "
                    f"but no message link was extracted; adding to database without link."
                )
                await db.add_posted_guid(guid)
                messages_posted_count += 1
        else:
            await process_failed_post(worker_id, guid, result)

        queue.task_done()
