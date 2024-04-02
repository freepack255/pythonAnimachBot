CREATE TABLE IF NOT EXISTS rss_feeds (
                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                         source TEXT NOT NULL,
                                         url TEXT NOT NULL,
                                         username TEXT NOT NULL,
                                         last_published_rss_entry_guid TEXT
);
CREATE TABLE IF NOT EXISTS posted_images (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            posted_image_url TEXT NOT NULL,
                                            hashed_posted_image_url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hashed_posted_image_url ON posted_images (hashed_posted_image_url);
CREATE TABLE IF NOT EXISTS config (
                                                post_date_cut_off TEXT NOT NULL
);