from io import BytesIO
import asyncio
import re
from typing import Optional, Any, Tuple
from urllib.parse import urlparse

from telegram import InputMediaPhoto
from telegram.error import RetryAfter, TimedOut
from loguru import logger
from animachpostingbot.image.image_resizer import validate_and_resize_image
from animachpostingbot.config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

# Build the Telegram application instance once.
from telegram.ext import ApplicationBuilder
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()


def parse_user_from_url(url: str) -> str | None | Any:
    """
    Parses the given URL and returns a tuple (source, user_id).

    Examples:
      - https://www.pixiv.net/en/users/64792103  -> ("pixiv", "64792103")
      - https://twitter.com/asou_asabu            -> ("twitter", "asou_asabu")
      - https://x.com/asou_asabu/                 -> ("twitter", "asou_asabu")

    If the source or user_id cannot be determined, returns None
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # For Pixiv: look for URLs like /users/<id> or /en/users/<id>
    if "pixiv.net" in domain:
        m = re.search(r"/(?:\w+/)?users/(\d+)", parsed.path)
        if m:
            user_id = m.group(1)
            logger.debug(f"URL parsed as Pixiv with user_id: {user_id}")
            if user_id.isdigit():
                return f"I{user_id}"
            return user_id

    # For Twitter (or x.com)
    if "twitter.com" in domain or "x.com" in domain:
        # Assume the URL is of the form /<username>
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts:
            logger.debug(f"URL parsed as Twitter with user_id: {path_parts[0]}")
            return path_parts[0]

    logger.error(f"Could not parse source/user_id from URL: {url}")
    return None


async def send_media_group_with_retries(chat_id: int | str, media_group: list, guid: str) -> Optional[Any]:
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
            logger.debug(
                f"[send_media_group_with_retries] Message for GUID '{guid}' sent successfully on attempt {retries + 1}: {messages}"
            )
            return messages
        except RetryAfter as e:
            retries += 1
            recommended_delay = getattr(e, 'retry_after', delay)
            delay = max(delay, recommended_delay)
            logger.warning(
                f"[send_media_group_with_retries] Attempt {retries}/{max_retries} for GUID '{guid}' failed with error {e}. Retrying in {delay} seconds."
            )
            await asyncio.sleep(delay)
            delay *= 2
        except TimedOut as e:
            logger.warning(
                f"[send_media_group_with_retries] TimedOut for GUID '{guid}': {e}. Assuming message delivered and not retrying."
            )
            return None
        except Exception as e:
            logger.error(f"[send_media_group_with_retries] Error sending media group for GUID '{guid}': {e}")
            return None

    logger.error(f"[send_media_group_with_retries] Exceeded maximum attempts for GUID '{guid}'.")
    return None


async def send_images_to_telegram(images: list, user_link: str, guid: str) -> tuple:
    """
    Sends an album to Telegram by ensuring at least one image has a caption.
    The caption is attached to the first valid image.
    Returns a tuple: (True, messages) if successful, or (False, error_detail) on failure.
    """
    media_group = []
    caption_added = False

    # Parse user info from the URL1
    user_id = parse_user_from_url(user_link)
    # Form the hashtag with username if available, else leave it empty.
    hashtag = f"#{user_id}" if user_id else ""

    for image_url in images:
        try:
            image_data = await validate_and_resize_image(image_url)
            if image_data is None:
                logger.warning(f"Image data is None for URL: {image_url}. This image will be skipped.")
                continue

            if not caption_added:
                # Form the caption: first line - hashtag (if available), second line - link to the post (guid)
                album_info = f"{hashtag}\n<a href='{guid}'>{guid}</a>"
                media_group.append(InputMediaPhoto(media=image_data, caption=album_info, parse_mode="HTML"))
                caption_added = True
            else:
                media_group.append(InputMediaPhoto(media=image_data))
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            continue

    if not media_group:
        err_msg = "No images to send"
        logger.error(err_msg)
        return False, err_msg

    # If no image got a caption, assign a caption to the first image as a fallback.
    if not caption_added and media_group:
        album_info = f"<b>{hashtag}</b>\n<a href='{guid}'>{guid}</a>"
        first_media = media_group[0]
        first_media.caption = album_info

    # Send the media group using the GUID for logging
    messages = await send_media_group_with_retries(TELEGRAM_CHANNEL_ID, media_group, guid)
    if messages is None:
        err_msg = f"Failed to send media group for GUID '{guid}' after multiple attempts."
        logger.error(err_msg)
        return False, err_msg

    await asyncio.sleep(1)
    return True, messages
