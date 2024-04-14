CREATE TABLE IF NOT EXISTS rss_feeds (
                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                         source TEXT NOT NULL,
                                         url TEXT NOT NULL,
                                         username TEXT NOT NULL,
                                         last_published_rss_entry_guid TEXT
);
CREATE TABLE IF NOT EXISTS published_guids (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
                                            published_guid TEXT NOT NULL,
                                            hashed_published_guid TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_hashed_published_guid ON published_guids (hashed_published_guid);
CREATE TABLE IF NOT EXISTS config (
                                                post_date_cut_off TEXT NOT NULL
);