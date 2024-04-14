import sqlite3
from pathlib import Path
from datetime import datetime
from animachBot.logger.logger import logger


def _handle_error(error: Exception):
    """Handle exceptions and log them."""
    error_type = error.__class__.__name__
    logger.error(f"{error_type} occurred: {error}")


class Database:
    """Class to initialize the database, check if the database file is present, and create tables."""

    def __init__(self, db_name: str) -> None:
        self.db_path = Path(db_name)
        if not self.db_path.exists():
            raise FileNotFoundError(f"The database file {self.db_path} does not exist.")
        if self.db_path.suffix != '.db':
            raise ValueError("Database name must end with '.db'")
        self.conn = None

    def connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
            self._configure_connection()

    def _configure_connection(self):
        """Configure the connection to the database."""
        self.conn.execute('PRAGMA journal_mode = WAL')  # Write-Ahead Logging enabled https://www.sqlite.org/wal.html

    def __enter__(self):
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
        if exc_type or exc_val or exc_tb:
            logger.exception(f"Exception has been handled: {exc_val}")

    def query(self, sql_script, args=None, fetch_one=False):
        """
        Executing query with possibility to choose from fetchall() and fetchone() methods.
        """
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
        with self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute(sql_script, args or ())
                if sql_script.strip().lower().startswith("select"):
                    if fetch_one:
                        return cursor.fetchone()
                    else:
                        return cursor.fetchall()
            finally:
                cursor.close()

    def execute_sql_commands_from_file(self, filename: str):
        """Execute a series of SQL commands from a file."""
        file_path = Path(filename)
        if not file_path.exists():
            logger.error(f"File not found: {filename}")
            return

        sql_file = file_path.read_text()  # Using read_text() method of Path object

        sql_commands = [command.strip() for command in sql_file.split(';') if command.strip()]

        for command in sql_commands:
            try:
                if command:
                    self.query(command)
            except (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError,
                    sqlite3.DataError, sqlite3.NotSupportedError) as e:
                error_type = e.__class__.__name__
                logger.exception(f"{error_type} occurred while executing SQL command: {e}")

    def insert_new_feed(self, feed_url: str, source: str, username: str) -> None:
        """Insert a new feed into the database."""
        try:
            self.query("INSERT INTO rss_feeds (url, source, username) VALUES (?, ?, ?)", (feed_url, source, username))
            logger.info("New feed has been added to the database")
        except sqlite3.IntegrityError:
            logger.info("Feed already exists in the database")

    def get_all_feeds(self):
        """Get all feeds from the database."""
        try:
            self.query("SELECT url FROM rss_feeds")
            logger.info("All feeds have been fetched from the database")
        except sqlite3.IntegrityError:
            logger.info("No feeds found in the database")

    def fetch_feed_urls(self, batch_size=50):
        """Generator for paginated getting of feed urls from db."""
        offset = 0
        while True:
            urls = self.query("SELECT url FROM rss_feeds LIMIT ? OFFSET ?", (batch_size, offset))

            if not urls:
                break  # If no urls are returned, break the loop

            for url in urls:
                yield url[0]  # Suggesting that url is a tuple with one element

            offset += batch_size

    def delete_feed(self, feed_url: tuple) -> None:
        """Delete a feed from the database."""
        try:
            self.query("DELETE FROM rss_feeds WHERE url = ?", feed_url)
            logger.info("Feed has been deleted from the database")
        except sqlite3.IntegrityError:
            logger.info("Feed not found in the database")

    def is_post_exists_in_db(self, hashed_published_guid) -> bool:
        """Check if a post has been posted."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT EXISTS(SELECT 1 FROM published_guids WHERE hashed_published_guid = ?)",
                       (hashed_published_guid,))
        return cursor.fetchone()[0] == 1

    def get_last_posted_guid(self, feed_url):
        """Get the last post ID from the database."""
        try:
            result = self.query("SELECT last_published_rss_entry_guid FROM rss_feeds "
                                "WHERE url = ?", (feed_url,), fetch_one=True)
            if result and result[0] is not None:
                logger.info(f"Last published guid found in db rss_feeds table for the feed {feed_url}: {result[0]}")
                return result[0]
            else:
                logger.info("No last published guid found in rss_feeds.last_published_rss_entry_guid"
                            " for the feed {feed_url}".format(feed_url=feed_url))
                return None
        except sqlite3.IntegrityError as e:
            logger.error(f"Database error when fetching last published guid: {e}")
            return None

    def update_last_posted_guid(self, feed_url, last_published_guid):
        """Update the last posted guid into the database."""
        try:
            self.query("UPDATE rss_feeds SET last_published_rss_entry_guid = ? WHERE url = ?",
                       (last_published_guid, feed_url))
            logger.info("Last published guid has been added to the database")
        except sqlite3.Error:
            logger.error("Failed to insert last published guid into the database")

    def get_post_date_cut_off(self):
        """Get the cut-off date for posts."""
        try:
            result = self.query("SELECT post_date_cut_off FROM config", fetch_one=True)
            if result:
                # Transform object from db to datetime
                logger.info(f"Cut-off date found in db config table: {result[0]}")
                return result[0]
            else:
                logger.error("No cut-off date found in config.post_date_cut_off")
                return None
        except sqlite3.IntegrityError as e:
            logger.error(f"Database error when fetching cut-off date: {e}")
            return None

    def insert_new_hashed_post_guid(self, published_guid, hashed_published_guid) -> None:
        """Insert a new post guid into the database."""
        try:
            self.query("INSERT INTO published_guids (published_guid, hashed_published_guid) VALUES (?, ?)",
                       (published_guid, hashed_published_guid, ))
            logger.info("New post has been added to the database")
        except sqlite3.Error:
            logger.error("Failed to insert new post into the database")
