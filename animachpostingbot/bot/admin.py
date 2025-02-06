import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from loguru import logger
from animachpostingbot.database.database import db_instance as db
from animachpostingbot.config.config import TELEGRAM_CHANNEL_ID

# Get admin IDs from environment variable.
# Example in .env: ADMIN_IDS=123456789,987654321
raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip()]

DEFAULT_SOURCE = "pixiv"  # Default source if not defined


def parse_user_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses the given URL and returns a tuple (source, user_id).

    Examples:
      - https://www.pixiv.net/en/users/64792103  -> ("pixiv", "64792103")
      - https://twitter.com/asou_asabu            -> ("twitter", "asou_asabu")
      - https://x.com/asou_asabu/                 -> ("twitter", "asou_asabu")

    If the source or user_id cannot be determined, returns (None, None).
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # For Pixiv: look for URLs like /users/<id> or /en/users/<id>
    if "pixiv.net" in domain:
        m = re.search(r"/(?:\w+/)?users/(\d+)", parsed.path)
        if m:
            logger.debug(f"URL parsed as Pixiv with user_id: {m.group(1)}")
            return "pixiv", m.group(1)

    # For Twitter (or x.com)
    if "twitter.com" in domain or "x.com" in domain:
        # Assume the URL is of the form /<username>
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts:
            logger.debug(f"URL parsed as Twitter with user_id: {path_parts[0]}")
            return "twitter", path_parts[0]

    logger.error(f"Could not parse source/user_id from URL: {url}")
    return None, None


async def get_all_users() -> list[str]:
    """Returns a combined list of all user IDs from the database (all sources)."""
    pixiv_users = await db.list_users_by_source("pixiv")
    twitter_users = await db.list_users_by_source("twitter")
    logger.debug(f"Found {len(pixiv_users)} Pixiv users and {len(twitter_users)} Twitter users in DB.")
    return pixiv_users + twitter_users


def paginate_users(user_ids: list[str], page: int = 0, per_page: int = 10) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Splits the list of user IDs into pages and returns formatted text with an inline keyboard.
    """
    total = len(user_ids)
    total_pages = (total - 1) // per_page + 1 if total > 0 else 1
    start = page * per_page
    end = start + per_page
    page_users = user_ids[start:end]

    text = f"<b>Parsed Users (Page {page + 1}/{total_pages}) [Total: {total}]</b>\n"
    text += "\n".join(f"<code>{uid}</code>" for uid in page_users)

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"users_prev:{page - 1}"))
    if end < total:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"users_next:{page + 1}"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
    return text, reply_markup


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command /listusers [source]
    Lists all users. If a source (pixiv or twitter) is specified,
    only users from that source are shown; otherwise, a combined list is shown.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None

    if admin_id not in ADMIN_IDS:
        logger.warning(f"Unauthorized access attempt to /listusers by user {admin_id}.")
        await message.reply_text("You are not authorized to use this command.")
        return

    if context.args and context.args[0].lower() in ["pixiv", "twitter"]:
        source = context.args[0].lower()
        user_ids = await db.list_users_by_source(source)
        logger.info(f"Listing users from source '{source}': found {len(user_ids)} user(s).")
    else:
        user_ids = await get_all_users()
        logger.info(f"Listing all users from all sources: found {len(user_ids)} user(s).")

    if not user_ids:
        await message.reply_text("No users found in the database.")
        return

    text, reply_markup = paginate_users(user_ids, page=0, per_page=10)
    await message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def paginate_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles inline button callbacks for paginating the user list.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    try:
        action, page_str = query.data.split(":")
        page = int(page_str)
    except Exception as e:
        logger.error(f"Error parsing callback data: {query.data} - {e}")
        return

    user_ids = await get_all_users()
    text, reply_markup = paginate_users(user_ids, page=page, per_page=10)
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=reply_markup)


async def find_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command /finduser <url> OR /finduser <source> <user_id>

    If a URL is provided, the source and user_id are determined automatically.
    If two arguments are provided, the first is treated as the source.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None

    if admin_id not in ADMIN_IDS:
        logger.warning(f"Unauthorized access attempt to /finduser by user {admin_id}.")
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /finduser <url> OR /finduser <source> <user_id>")
        return

    if context.args[0].startswith("http"):
        # URL provided
        source, user_id = parse_user_from_url(context.args[0])
        if not source or not user_id:
            await message.reply_text("Failed to parse the URL.")
            return
    else:
        # Explicit source provided
        if len(context.args) < 2:
            await message.reply_text("Usage: /finduser <source> <user_id>")
            return
        source = context.args[0].lower()
        user_id = context.args[1].strip()

    logger.info(f"Finding user: {user_id} in source: {source}")
    users_in_source = await db.list_users_by_source(source)
    if user_id in users_in_source:
        await message.reply_text(
            f"User <code>{user_id}</code> exists in the <b>{source}</b> database. (Total in source: {len(users_in_source)})",
            parse_mode="HTML",
        )
    else:
        await message.reply_text(
            f"User <code>{user_id}</code> not found in the <b>{source}</b> database.",
            parse_mode="HTML",
        )


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command /adduser <url1> <url2> ...

    Accepts one or more URLs, automatically determines the source and user_id,
    and adds them to the database.

    Example:
      /adduser https://twitter.com/asou_asabu https://www.pixiv.net/en/users/64792103
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None

    if admin_id not in ADMIN_IDS:
        logger.warning(f"Unauthorized access attempt to /adduser by user {admin_id}.")
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /adduser <url1> <url2> ...")
        return

    added = []
    duplicates = []
    errors = []

    for url in context.args:
        source, user_id = parse_user_from_url(url)
        if not source or not user_id:
            errors.append(url)
            logger.error(f"Failed to parse URL: {url}")
            continue

        try:
            exists = await db.user_exists(user_id, source)
            if exists:
                duplicates.append(f"{url} ({source}:{user_id})")
                logger.info(f"User already exists: {user_id} with source: {source}")
            else:
                await db.add_user(user_id, source)
                added.append(f"{url} ({source}:{user_id})")
                logger.info(f"Added user: {user_id} with source: {source} to the database.")
        except Exception as e:
            logger.error(f"Error adding user from URL {url}: {e}")
            errors.append(url)

    reply_parts = []
    if added:
        reply_parts.append(f"Added {len(added)} user(s): {', '.join(added)}.")
    if duplicates:
        reply_parts.append(f"These URLs correspond to users that already exist: {', '.join(duplicates)}.")
    if errors:
        reply_parts.append(f"Failed to add these URLs due to errors: {', '.join(errors)}.")

    reply_text = "\n".join(reply_parts)
    await message.reply_text(reply_text, parse_mode="HTML")
    logger.info(f"Admin {admin_id} adduser result - Added: {added}, Duplicates: {duplicates}, Errors: {errors}")


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command /removeuser <url1> <url2> ...

    Accepts one or more URLs, parses them to get the source and user_id,
    and removes them from the database.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None

    if admin_id not in ADMIN_IDS:
        logger.warning(f"Unauthorized access attempt to /removeuser by user {admin_id}.")
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /removeuser <url1> <url2> ...")
        return

    errors = []
    removed = []

    for url in context.args:
        source, user_id = parse_user_from_url(url)
        if not source or not user_id:
            errors.append(url)
            logger.error(f"Failed to parse URL: {url}")
            continue

        try:
            # Assumes that the remove_user method in the database accepts a list of user_ids and a source
            await db.remove_user([user_id], source)
            removed.append(f"{url} ({source}:{user_id})")
            logger.info(f"Removed user: {user_id} with source: {source} from the database.")
        except Exception as e:
            logger.error(f"Error removing user from URL {url}: {e}")
            errors.append(url)

    reply_parts = []
    if removed:
        reply_parts.append(f"Removed {len(removed)} user(s): {', '.join(removed)}.")
    if errors:
        reply_parts.append(f"Failed to remove these URLs: {', '.join(errors)}.")

    reply_text = "\n".join(reply_parts)
    await message.reply_text(reply_text, parse_mode="HTML")
    logger.info(f"Admin {admin_id} removeuser result - Removed: {removed}, Errors: {errors}")


async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command /deletepost <message_id1> [message_id2 ...]
    Deletes the specified messages from the Telegram channel.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None

    if admin_id not in ADMIN_IDS:
        logger.warning(f"Unauthorized access attempt to /deletepost by user {admin_id}.")
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /deletepost <message_id1> [message_id2 ...]")
        return

    channel_id = TELEGRAM_CHANNEL_ID
    message_ids = []
    for arg in context.args:
        try:
            message_ids.append(int(arg.strip()))
        except Exception as e:
            logger.error(f"Invalid message ID '{arg}': {e}")

    if not message_ids:
        await message.reply_text("No valid message IDs provided.")
        return

    successes = []
    failures = []
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
            successes.append(str(msg_id))
        except Exception as e:
            logger.error(f"Failed to delete message {msg_id}: {e}")
            failures.append(str(msg_id))

    response_parts = []
    if successes:
        response_parts.append(f"Deleted messages: {', '.join(successes)}")
    if failures:
        response_parts.append(f"Failed to delete messages: {', '.join(failures)}")
    await message.reply_text("\n".join(response_parts))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends help text with available commands.
    If the user is not authorized, shows an unauthorized message instead.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return

    text = (
        "Available commands:\n\n"
        "<b>/listusers [source]</b> - List all parsed users. Optionally filter by source (pixiv or twitter).\n\n"
        "<b>/finduser <url> OR /finduser <source> <user_id></b> - Check if a user exists in the database.\n\n"
        "<b>/adduser <url1> [url2 ...]</b> - Add one or more users by URL. Example:\n"
        "<code>/adduser https://twitter.com/asou_asabu https://www.pixiv.net/en/users/64792103</code>\n\n"
        "<b>/removeuser <url1> [url2 ...]</b> - Remove one or more users by URL.\n\n"
        "<b>/deletepost <message_id1> [message_id2 ...]</b> - Delete posts from the Telegram channel.\n\n"
        "<b>/help</b> - Show this help text.\n\n"
        "Note: URL parsing is used to automatically determine the source and user ID."
    )
    await message.reply_text(text, parse_mode="HTML")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles unknown commands by showing a message.
    If the user is not authorized, shows an unauthorized message.
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
    else:
        await message.reply_text("Unknown command. Use /help to see available commands.")


def register_admin_handlers(app: Application) -> None:
    """
    Registers admin command handlers.
    """
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(CommandHandler("finduser", find_user))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("deletepost", delete_post))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(paginate_users_callback, pattern=r'^users_'))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
