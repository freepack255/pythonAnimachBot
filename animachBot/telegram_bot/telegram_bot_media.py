import asyncio
import time
import traceback

from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

from animachBot.database.database import Database
from animachBot.logger.logger import logger
from animachBot.rss_feed_parser.rss_feed_parser import hash_post_guid
import os
import validators


def is_url(image_source):
    return validators.url(image_source)


def is_file(image_source):
    return os.path.isfile(image_source)


def escape_markdown_v2(text):
    """Escape markdownv2 characters."""
    characters_to_escape = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for char in characters_to_escape:
        text = text.replace(char, "\\" + char)
    return text


class TelegramMediaGroupSender:
    def __init__(self, token, chat_id, database: Database):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.database = database

    async def send_telegram_media(self, entries, feed_url):
        for entry in entries:
            caption_added = False
            media_group = []
            for image in entry['images']:
                caption = (f"Author {escape_markdown_v2(entry['author'])}\n[{escape_markdown_v2(entry['title'])}]"
                           f"({escape_markdown_v2(entry['post_link'])})")
                if is_url(image):
                    if len(media_group) == 0 and not caption_added:
                        caption_added = True
                        media_group.append(InputMediaPhoto(media=image,
                                                           caption=caption,
                                                           parse_mode='MarkdownV2'))
                        logger.debug(f"Image url with caption: {caption} added to media group: {image}")
                    else:
                        media_group.append(InputMediaPhoto(media=image))
                        logger.debug(f"Image url added to media group: {image}")
                elif is_file(image):
                    with open(image, "rb") as file:
                        media_group.append(InputMediaPhoto(caption=caption, parse_mode='MarkdownV2', media=file))
                        logger.debug(f"Image file added to media group: {image}")

                else:
                    logger.error(f"Invalid image source: {image}")
            logger.debug(f"media_group {media_group}")
            if 0 < len(media_group) <= 10:
                try:
                    await asyncio.sleep(2)
                    await self.bot.send_media_group(chat_id=self.chat_id, media=media_group,
                                                    read_timeout=60)
                    logger.info(f"Media group sent successfully for post {entry['post_link']}.")
                    self.database.insert_new_hashed_post_guid(entry['post_link'], hash_post_guid(entry['post_link']))
                    last_published_guid = self.database.get_last_posted_guid(feed_url)
                    if last_published_guid is None:
                        self.database.update_last_posted_guid(last_published_guid=entry['post_link'], feed_url=feed_url)
                        logger.info(f"Last published guid updated in db for the feed {feed_url}")
                        return

                    last_published_guid_id = last_published_guid.split("/")[-1]
                    current_last_published_guid_id = entry['post_link'].split("/")[-1]
                    if int(last_published_guid_id) < int(current_last_published_guid_id):
                        self.database.update_last_posted_guid(last_published_guid=entry['post_link'], feed_url=feed_url)
                        logger.info(f"Last published guid updated in db for the feed {feed_url}")
                    else:
                        logger.warning(f"Last published guid not updated in db for the feed {feed_url}")

                except TelegramError as e:
                    logger.error(f"Failed to send media group for post {entry['post_link']}: {str(e)}")
