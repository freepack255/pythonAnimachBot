import asyncio
from loguru import logger
from animachpostingbot.bot.telegram_bot import send_images_to_telegram
from animachpostingbot.config.config import TELEGRAM_CHANNEL_ID
from animachpostingbot.database.database import db_instance  # if needed for type hints

# Global lock to protect duplicate checking.
duplicate_lock = asyncio.Lock()
# In-memory set to track normalized GUIDs processed during the current cycle.
processed_guids = set()
# Global dictionary to record the media_group_id for each GUID.
sent_media_groups = {}  # <-- NEW: holds {normalized_guid: media_group_id}

# Import the Telegram application instance (used to delete duplicate messages)
from animachpostingbot.bot.telegram_bot import application

async def worker(queue, db, worker_id: int):
    while True:
        # Note: The queue items are (title, image_urls, user_link, normalized_guid, author)
        title, image_urls, user_link, normalized_guid, author = await queue.get()
        logger.info(
            f"[Worker {worker_id}] Processing queue item: title='{title}', normalized_guid='{normalized_guid}', images={len(image_urls)}"
        )

        async with duplicate_lock:
            # Check if this GUID is already processed or in DB.
            if normalized_guid in processed_guids or await db.is_guid_posted(normalized_guid):
                logger.info(f"[Worker {worker_id}] Skipping duplicate normalized_guid '{normalized_guid}'.")
                queue.task_done()
                continue
            # Mark as processing immediately.
            processed_guids.add(normalized_guid)

        try:
            success, result = await send_images_to_telegram(title, image_urls, user_link, normalized_guid, author)
            logger.debug(f"[Worker {worker_id}] send_images_to_telegram returned: success={success}, result={result}")
        except Exception as e:
            logger.error(f"[Worker {worker_id}] Error sending images for normalized_guid '{normalized_guid}': {e}")
            success, result = False, str(e)

        if success:
            messages = result  # Expecting a list of Telegram Message objects.
            if messages and hasattr(messages[0], "message_id"):
                short_id = str(TELEGRAM_CHANNEL_ID)[4:]
                tg_message_link = f"https://t.me/c/{short_id}/{messages[0].message_id}"
                logger.info(
                    f"[Worker {worker_id}] Posting succeeded for normalized_guid '{normalized_guid}', adding to database with link {tg_message_link}."
                )
                # Get the media_group_id from the first message (if available)
                media_group_id = getattr(messages[0], "media_group_id", None)
                # NEW: Check if we already have a media_group_id for this GUID.
                if normalized_guid in sent_media_groups:
                    original_media_group_id = sent_media_groups[normalized_guid]
                    if media_group_id != original_media_group_id:
                        logger.warning(
                            f"[Worker {worker_id}] Duplicate detected for normalized_guid '{normalized_guid}'. "
                            f"Original media_group_id: {original_media_group_id}, new: {media_group_id}. "
                            f"Deleting duplicate message with ID {messages[0].message_id}."
                        )
                        try:
                            await application.bot.delete_message(chat_id=TELEGRAM_CHANNEL_ID, message_id=messages[0].message_id)
                        except Exception as e:
                            logger.error(f"[Worker {worker_id}] Error deleting duplicate message: {e}")
                    else:
                        logger.warning(f"[Worker {worker_id}] Received identical media_group_id for normalized_guid '{normalized_guid}'.")
                else:
                    # NEW: Record the media_group_id for this GUID.
                    sent_media_groups[normalized_guid] = media_group_id
                    await db.add_posted_guid(normalized_guid)
                    await db.update_tg_message_link(normalized_guid, tg_message_link)
            else:
                logger.info(
                    f"[Worker {worker_id}] Posting succeeded for normalized_guid '{normalized_guid}' but no message link extracted; adding to database without link."
                )
                await db.add_posted_guid(normalized_guid)
        else:
            logger.error(f"[Worker {worker_id}] Posting failed for normalized_guid '{normalized_guid}': {result}.")

        queue.task_done()
