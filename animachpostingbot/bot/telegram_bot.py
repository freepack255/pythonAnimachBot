import asyncio
from typing import Optional, Any

from telegram import InputMediaPhoto
from telegram.ext import ApplicationBuilder
from telegram.error import RetryAfter, TimedOut
from loguru import logger
from animachpostingbot.image.image_resizer import validate_and_resize_image
from animachpostingbot.config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

# Build the Telegram application instance once.
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

async def send_media_group_with_retries(chat_id: int | str, media_group: list, title: str, guid: str) -> Optional[Any]:
    """
    Sends a media group to the chat with retry logic.
    If a TimedOut exception occurs, it assumes the message was delivered
    and does not retry (to avoid duplicates).
    """
    max_retries = 5
    retries = 0
    delay = 1  # initial delay in seconds

    while retries < max_retries:
        try:
            messages = await application.bot.send_media_group(chat_id=chat_id, media=media_group)
            logger.debug(f"[send_media_group_with_retries] Message for GUID '{guid}' sent successfully on attempt {retries+1}: {messages}")
            return messages

        except RetryAfter as e:
            retries += 1
            recommended_delay = getattr(e, 'retry_after', delay)
            delay = max(delay, recommended_delay)
            logger.warning(f"[send_media_group_with_retries] Attempt {retries}/{max_retries} for '{title}', GUID '{guid}' failed with error {e}. Retrying in {delay} seconds.")
            await asyncio.sleep(delay)
            delay *= 2

        except TimedOut as e:
            # On TimedOut, assume the message was delivered and do not retry to avoid duplicates.
            logger.warning(f"[send_media_group_with_retries] TimedOut for '{title}', GUID '{guid}': {e}. Assuming message delivered and not retrying.")
            return None

        except Exception as e:
            logger.error(f"[send_media_group_with_retries] Error sending media group for '{title}', GUID '{guid}': {e}")
            return None

    logger.error(f"[send_media_group_with_retries] Exceeded maximum attempts for '{title}', GUID '{guid}'.")
    return None

async def send_images_to_telegram(title: str, images: list, url: str, guid: str, author: str) -> tuple:
    """
    Sends an album to Telegram by attaching a caption only to the first image.
    Returns a tuple: (True, messages) if successful, or (False, error_detail) on failure.
    """
    media_group = []
    for idx, image_url in enumerate(images):
        try:
            image_data = await validate_and_resize_image(image_url)
            if image_data is None:
                logger.warning(f"Image data is None for URL: {image_url}. This image will be skipped.")
                continue
            if idx == 0:
                album_info = (
                    f"<i><a href='{url}'>{author}</a></i>\n"
                    f"<b><a href='{guid}'>{title}</a></b>"
                )
                media_group.append(InputMediaPhoto(media=image_data, caption=album_info, parse_mode="HTML"))
            else:
                media_group.append(InputMediaPhoto(media=image_data))
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            continue

    if not media_group:
        err_msg = f"No images to send for title '{title}'"
        logger.error(err_msg)
        return False, err_msg

    # Pass the GUID to the retry function for logging/verification.
    messages = await send_media_group_with_retries(TELEGRAM_CHANNEL_ID, media_group, title, guid)
    if messages is None:
        err_msg = f"Failed to send media group for title '{title}' after multiple attempts."
        logger.error(err_msg)
        return False, err_msg

    await asyncio.sleep(1)
    return True, messages
