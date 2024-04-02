CREATE TABLE IF NOT EXISTS rss_feeds (
                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                         source TEXT NOT NULL,
                                         url TEXT NOT NULL,
                                         username TEXT NOT NULL,
                                         last_published_rss_entry_guid TEXT
);
CREATE TABLE IF NOT EXISTS PostedImages (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            Posted_Image_URL TEXT NOT NULL,
                                            Hashed_Posted_Image_URL TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hashed_posted_image_url ON PostedImages (Hashed_Posted_Image_URL);