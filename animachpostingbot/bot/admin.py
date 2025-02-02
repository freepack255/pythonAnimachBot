import os
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

# Retrieve the initial admin IDs from the environment.
# Example in .env: ADMIN_IDS=123456789,987654321
raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip()]


def paginate_users(user_ids: list[str], page: int = 0, per_page: int = 10) -> tuple[str, InlineKeyboardMarkup]:
    """
    Splits the user IDs list into pages and returns formatted text with an inline keyboard.
    The text includes the current page number, total pages, and the total number of stored users.
    """
    total = len(user_ids)
    total_pages = (total - 1) // per_page + 1 if total > 0 else 1
    start = page * per_page
    end = start + per_page
    page_users = user_ids[start:end]

    # The header now shows pagination info along with the total count.
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
    Lists parsed users from the database in a paginated format.
    Usage: /listusers
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return

    user_ids = await db.list_users()
    if not user_ids:
        await message.reply_text("No users found in the database.")
        return

    text, reply_markup = paginate_users(user_ids, page=0, per_page=10)
    await message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def paginate_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles inline keyboard callbacks for paginating the user list.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    try:
        action, page_str = query.data.split(":")
        page = int(page_str)
    except Exception:
        return

    user_ids = await db.list_users()
    text, reply_markup = paginate_users(user_ids, page=page, per_page=10)
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=reply_markup)


async def find_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Looks up a user in the database.
    Usage: /finduser <user_id>
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /finduser <user_id>")
        return

    user_id = context.args[0].strip()
    user_ids = await db.list_users()
    if user_id in user_ids:
        await message.reply_text(f"User {user_id} exists in the database. (Total: {len(user_ids)})")
    else:
        await message.reply_text(f"User {user_id} not found in the database.")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Adds one or more users to the database.
    Usage: /adduser <user_id1> [user_id2 user_id3 ...]
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /adduser <user_id1> [user_id2 user_id3 ...]")
        return

    user_ids_to_add = context.args
    # Set an upper limit to avoid huge inserts.
    if len(user_ids_to_add) > 50:
        await message.reply_text("Error: Too many user IDs at once (max 50).")
        return

    # Validate user IDs. If a single entry is invalid, skip or handle accordingly.
    valid_user_ids = []
    for uid in user_ids_to_add:
        uid_str = uid.strip()
        if not uid_str:
            continue
        # You can add more checks here (e.g., length or pattern).
        valid_user_ids.append(uid_str)

    added_count = 0
    for uid_str in valid_user_ids:
        await db.add_user(uid_str)
        added_count += 1

    await message.reply_text(f"Added {added_count} users successfully.")
    logger.info(f"{added_count} user(s) added by admin {admin_id}.")


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Removes one or more users from the database.
    Usage: /removeuser <user_id1> [user_id2 ...]
    """
    message = update.effective_message
    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id not in ADMIN_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await message.reply_text("Usage: /removeuser <user_id1> [user_id2 ...]")
        return

    # Create a list of user IDs to remove, stripping any extra whitespace.
    user_ids_to_remove = [uid.strip() for uid in context.args if uid.strip()]
    if not user_ids_to_remove:
        await message.reply_text("No valid user IDs provided.")
        return

    # Call the database method once with the list of user IDs.
    await db.remove_user(user_ids_to_remove)
    removed_count = len(user_ids_to_remove)

    await message.reply_text(f"Removed {removed_count} user(s) successfully.")
    logger.info(f"Removed {removed_count} user(s) by admin {admin_id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends a help text listing all available commands and their usage.
    """
    message = update.effective_message
    text = (
        "Available commands:\n\n"
        "<b>/listusers</b> - List all parsed users in pages of 10, including the total count of stored users.\n"
        "If you want to get user in pixiv then add the <b>&lt;user_id&gt;</b> "
        "to the end of the link <code>https://www.pixiv.net/users/&lt;user_id&gt;</code>\n\n"
        "<b>/finduser &lt;user_id&gt;</b> - Check if an user exists in the database.\n\n"
        "<b>/adduser &lt;user_id1&gt; [user_id2 ...]</b> - Add one or more user IDs (at least one is required).\n\n"
        "<b>/removeuser &lt;user_id1&gt; [user_id2 ...]</b> - Remove one or more user IDs (at least one is required).\n\n"
        "Command Parameter Notation:\n"
        "- &lt; &gt; indicates a required parameter.\n"
        "- [ ] indicates an optional parameter (you can supply multiple values).\n"
        "Examples:\n"
        "<code>/adduser 123 456 789</code>\n"
        "<code>/finduser 123</code>\n"
        "<code>/removeuser 456 789</code>\n"
    )
    await message.reply_text(text, parse_mode="HTML")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles unknown commands by showing the /help text.
    """
    message = update.effective_message
    await message.reply_text("Unknown command. Use /help to see available commands.")


def register_admin_handlers(app: Application) -> None:
    """
    Registers admin command handlers for managing parsed users, plus help and fallback.
    """
    # Command handlers
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(CommandHandler("finduser", find_user))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("help", help_command))

    # Inline callback for pagination
    app.add_handler(CallbackQueryHandler(paginate_users_callback, pattern=r'^users_'))

    # Fallback for unknown commands (any text starting with slash but not matching above)
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
