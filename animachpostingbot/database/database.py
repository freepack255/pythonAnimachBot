import os
import aiosqlite
import traceback
from loguru import logger
from animachpostingbot.config.config import DB_FILE
from typing import Optional, Union, List

_instance_count = 0

class Database:
    def __init__(self, db_file: str = DB_FILE):
        global _instance_count
        _instance_count += 1
        self.instance_id = _instance_count
        self.db_file = db_file
        # Ensure that the directory for the database file exists.
        db_dir = os.path.dirname(os.path.abspath(self.db_file))
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"[Database instance {self.instance_id}] Database initialized with file: {self.db_file}")
        logger.info(f"[Database instance {self.instance_id}] Database file path: {os.path.abspath(self.db_file)}")
        # Log a short traceback to see where this instance was created.
        stack = "".join(traceback.format_stack(limit=10))
        logger.debug(f"[Database instance {self.instance_id}] Created with call stack:\n{stack}")

    async def _execute(self, query: str, params: tuple = (), commit: bool = False):
        try:
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                async with db.execute(query, params) as cursor:
                    result = await cursor.fetchall()
                if commit:
                    await db.commit()
                return result
        except Exception as e:
            logger.error(f"[Database instance {self.instance_id}] Database error: {e}\nQuery: {query}\nParams: {params}")
            raise

    async def init_db(self):
        """
        Create the users, posted_guids, and settings tables if they don't exist.
        """
        create_users_query = """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY
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
        logger.info(f"[Database instance {self.instance_id}] Database initialized with tables 'users', 'posted_guids', and 'settings'.")

    # ---------------------------
    # CRUD for the "users" table
    # ---------------------------
    async def add_user(self, user_id: str):
        await self._execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,), commit=True)
        logger.info(f"[Database instance {self.instance_id}] Added user: {user_id}")

    async def remove_user(self, user_id: Union[str, List[str]]):
        """
        Removes a user or a list of users from the database.
        If a list is provided, deletes all matching user IDs.
        """
        if isinstance(user_id, list):
            placeholders = ",".join("?" for _ in user_id)
            query = f"DELETE FROM users WHERE user_id IN ({placeholders})"
            params = tuple(user_id)
        else:
            query = "DELETE FROM users WHERE user_id = ?"
            params = (user_id,)
        await self._execute(query, params, commit=True)
        logger.info(f"[Database instance {self.instance_id}] Removed user(s): {user_id}")

    async def list_users(self) -> list:
        rows = await self._execute("SELECT user_id FROM users")
        user_list = [row[0] for row in rows]
        logger.info(f"[Database instance {self.instance_id}] Listed users: {user_list}")
        return user_list

    async def user_exists(self, user_id: str) -> bool:
        rows = await self._execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = len(rows) > 0
        logger.info(f"[Database instance {self.instance_id}] User '{user_id}' exists: {exists}")
        return exists

    # -------------------------------------
    # CRUD for the "posted_guids" table
    # -------------------------------------
    async def add_posted_guid(self, guid: str):
        await self._execute("INSERT OR IGNORE INTO posted_guids (guid) VALUES (?)", (guid,), commit=True)
        logger.info(f"[Database instance {self.instance_id}] Added posted guid: {guid}")

    async def is_guid_posted(self, guid: str) -> bool:
        rows = await self._execute("SELECT guid FROM posted_guids WHERE guid = ?", (guid,))
        is_posted = len(rows) > 0
        logger.info(f"[Database instance {self.instance_id}] GUID '{guid}' is already posted: {is_posted}")
        return is_posted

    async def list_posted_guids(self) -> list:
        rows = await self._execute("SELECT guid FROM posted_guids")
        posted_guids = [row[0] for row in rows]
        logger.info(f"[Database instance {self.instance_id}] Listed posted guids: {posted_guids}")
        return posted_guids

    async def remove_posted_guid(self, guid: str):
        await self._execute("DELETE FROM posted_guids WHERE guid = ?", (guid,), commit=True)
        logger.info(f"[Database instance {self.instance_id}] Removed posted guid: {guid}")

    async def update_posted_guid(self, guid: str):
        await self._execute("UPDATE posted_guids SET posted_at = CURRENT_TIMESTAMP WHERE guid = ?", (guid,), commit=True)
        logger.info(f"[Database instance {self.instance_id}] Updated posted guid: {guid}")

    async def update_tg_message_link(self, guid: str, tg_message_link: str):
        await self._execute(
            "UPDATE posted_guids SET tg_message_link = ? WHERE guid = ?",
            (tg_message_link, guid),
            commit=True
        )
        logger.info(f"[Database instance {self.instance_id}] Updated Telegram message link for GUID {guid}: {tg_message_link}")

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
        logger.info(f"[Database instance {self.instance_id}] Updated setting '{key}' to '{value}'.")

# Create a singleton instance.
db_instance = Database()
