import sqlite3
from pathlib import Path

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
            with self.conn.cursor() as cursor:
                cursor.execute(sql_script, args or ())
                if sql_script.strip().lower().startswith("select"):
                    if fetch_one:
                        return cursor.fetchone()
                    else:
                        return cursor.fetchall()

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
        except sqlite3.IntegrityError:
            logger.info("Feed already exists in the database")

    def get_all_feeds(self):
        """Get all feeds from the database."""
        try:
            self.query("SELECT url FROM rss_feeds")
        except sqlite3.IntegrityError:
            logger.info("No feeds found in the database")

    def fetch_feed_urls(self, batch_size=50):
        """Generator for paginated getting of feed urls from db."""
        offset = 0
        while True:
            urls = self.query("SELECT feed_url FROM feeds LIMIT ? OFFSET ?", (batch_size, offset))

            if not urls:
                break  # If no urls are returned, break the loop

            for url in urls:
                yield url[0]  # Suggesting that url is a tuple with one element

            offset += batch_size

    def delete_feed(self, feed_url: tuple) -> None:
        """Delete a feed from the database."""
        try:
            self.query("DELETE FROM rss_feeds WHERE url = ?", feed_url)
        except sqlite3.IntegrityError:
            logger.info("Feed not found in the database")

    def is_post_exists_in_db(self, hashed_posted_image_url: tuple) -> None:
        """Check if a post has been posted."""
        try:
            self.query("SELECT hashed_posted_image_url \
             FROM posted_images WHERE hashed_posted_image_url = ?", hashed_posted_image_url)
        except sqlite3.IntegrityError:
            logger.info("No posts found in the database")

    def get_post_date_cut_off(self):
        """Get the cut-off date for posts."""
        try:
            self.query("SELECT post_date_cut_off FROM config", fetch_one=True)
        except sqlite3.IntegrityError:
            logger.error("No cut-off date found in config.post_date_cut_off")
