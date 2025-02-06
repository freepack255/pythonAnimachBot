import os
import traceback
from typing import Optional, List, Union, Tuple

import aiosqlite
from loguru import logger

from animachpostingbot.config.config import DB_FILE


class Database:
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        # Ensure that the directory for the database file exists.
        db_dir = os.path.dirname(os.path.abspath(self.db_file))
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Database initialized with file: {self.db_file}")
        logger.info(f"Database file path: {os.path.abspath(self.db_file)}")
        # Log a short traceback to see where this instance was created.
        stack = "".join(traceback.format_stack(limit=10))
        logger.debug(f"Created with call stack:\n{stack}")

    async def _execute(self, query: str, params: Tuple = (), commit: bool = False):
        try:
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                async with db.execute(query, params) as cursor:
                    result = await cursor.fetchall()
                if commit:
                    await db.commit()
                return result
        except Exception as e:
            logger.error(f"Database error: {e}\nQuery: {query}\nParams: {params}")
            raise

    async def init_db(self):
        """
        Create the users, posted_guids, and settings tables if they don't exist.
        The users table is unified to include a 'source' column.
        """
        create_users_query = """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT,
                source TEXT,
                PRIMARY KEY (user_id, source)
            )
        """
        create_guids_query = """
            CREATE TABLE IF NOT EXISTS posted_guids (
                guid TEXT PRIMARY KEY,
                tg_message_link TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        create_settings_query = """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """
        await self._execute(create_users_query, commit=True)
        await self._execute(create_guids_query, commit=True)
        await self._execute(create_settings_query, commit=True)
        logger.info("Database initialized with tables 'users', 'posted_guids', and 'settings'.")

    # ---------------------------
    # CRUD for the "users" table
    # ---------------------------
    async def add_user(self, user_id: str, source: str):
        """
        Adds a user with the given user_id and source.
        """
        await self._execute(
            "INSERT OR IGNORE INTO users (user_id, source) VALUES (?, ?)",
            (user_id, source),
            commit=True
        )
        logger.info(f"Added user: {user_id} with source: {source}")

    async def remove_user(self, user_ids: Union[str, List[str]], source: str):
        """
        Removes a user or a list of users from the database for a given source.
        If a list is provided, deletes all matching user IDs.
        """
        if isinstance(user_ids, list):
            placeholders = ",".join("?" for _ in user_ids)
            query = f"DELETE FROM users WHERE user_id IN ({placeholders}) AND source = ?"
            params = tuple(user_ids) + (source,)
        else:
            query = "DELETE FROM users WHERE user_id = ? AND source = ?"
            params = (user_ids, source)
        await self._execute(query, params, commit=True)
        logger.info(f"Removed user(s): {user_ids} from source: {source}")

    async def list_users_by_source(self, source: str) -> List[str]:
        """
        Returns a list of user_ids filtered by the given source.
        """
        rows = await self._execute("SELECT user_id FROM users WHERE source = ?", (source,))
        user_list = [row[0] for row in rows]
        logger.info(f"Listed users from source '{source}': {user_list}")
        return user_list

    async def user_exists(self, user_id: str, source: str) -> bool:
        """
        Checks if a user with the given user_id and source exists.
        """
        rows = await self._execute("SELECT user_id FROM users WHERE user_id = ? AND source = ?", (user_id, source))
        exists = len(rows) > 0
        logger.info(f"User '{user_id}' with source '{source}' exists: {exists}")
        return exists

    # -------------------------------------
    # CRUD for the "posted_guids" table
    # -------------------------------------
    async def add_posted_guid(self, guid: str):
        await self._execute("INSERT OR IGNORE INTO posted_guids (guid) VALUES (?)", (guid,), commit=True)
        logger.info(f"Added posted guid: {guid}")

    async def is_guid_posted(self, guid: str) -> bool:
        rows = await self._execute("SELECT guid FROM posted_guids WHERE guid = ?", (guid,))
        is_posted = len(rows) > 0
        logger.info(f"GUID '{guid}' is already posted: {is_posted}")
        return is_posted

    async def list_posted_guids(self) -> List[str]:
        rows = await self._execute("SELECT guid FROM posted_guids")
        posted_guids = [row[0] for row in rows]
        logger.info(f"Listed posted guids: {posted_guids}")
        return posted_guids

    async def remove_posted_guid(self, guid: str):
        await self._execute("DELETE FROM posted_guids WHERE guid = ?", (guid,), commit=True)
        logger.info(f"Removed posted guid: {guid}")

    async def update_posted_guid(self, guid: str):
        await self._execute("UPDATE posted_guids SET posted_at = CURRENT_TIMESTAMP WHERE guid = ?", (guid,), commit=True)
        logger.info(f"Updated posted guid: {guid}")

    async def update_tg_message_link(self, guid: str, tg_message_link: str):
        await self._execute(
            "UPDATE posted_guids SET tg_message_link = ? WHERE guid = ?",
            (tg_message_link, guid),
            commit=True
        )
        logger.info(f"Updated Telegram message link for GUID {guid}: {tg_message_link}")

    # ---------------------------
    # CRUD for the "settings" table
    # ---------------------------
    async def get_setting(self, key: str) -> Optional[str]:
        rows = await self._execute("SELECT value FROM settings WHERE key = ?", (key,))
        if rows:
            return rows[0][0]
        return None

    async def set_setting(self, key: str, value: str):
        await self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value), commit=True)
        logger.info(f"Updated setting '{key}' to '{value}'.")


# Create a singleton instance.
db_instance = Database()
