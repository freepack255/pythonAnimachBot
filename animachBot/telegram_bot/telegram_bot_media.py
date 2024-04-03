from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

from animachBot.logger.logger import logger
import os
import validators


def is_url(image_source):
    return validators.url(image_source)


def is_file(image_source):
    return os.path.isfile(image_source)


class TelegramMediaGroupSender:
    def __init__(self, token, chat_id):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    def send_media_group(self, entries):
        for entry in entries:
            media_group = []
            for img_link in entry['images']:
                caption = f"Author: {entry['author']}\nLink: {entry['post_link']}" if media_group == [] else None
                media_group.append(InputMediaPhoto(media=img_link, caption=caption))

            if media_group:
                try:
                    self.bot.send_media_group(chat_id=self.chat_id, media=media_group)
                    logger.info("Media group sent successfully.")
                except Exception as e:
                    logger.error(f"Failed to send media group: {str(e)}")
