# How to run

To run the bot add .env file with the following content

```
TELEGRAM_BOT_TOKEN=TOKEN
TELEGRAM_CHANNEL_ID=-1001234567890
NOTIFICATION_CHAT_ID=-1009876543210 # Where to send notifications if bot is down
START_FROM_PARSING_DATE="2024-01-01 00:00:00Z"
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
DB_FILE=data/database.db
CHECK_INTERVAL_IN_SECONDS=60
RSSHUB_URL=http://rsshub:1200/
ADMIN_IDS=123456789,987654321
```
Set the PIXIV_REFRESHTOKEN, TWITTER_AUTH_TOKEN and TWITTER_COOKIE in docker-compose.yml.
How to get refresh token - https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362
Log in and get cookie auth_token from https://x.com/ -> F12 -> Application -> Cookies -> auth_token
For chrome Cookie-Editor extension https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm -> Export -> As Header String

``` 
PIXIV_REFRESHTOKEN=TOKEN
TWITTER_AUTH_TOKEN=AUTH_TOKEN
TWITTER_COOKIE=ALL_COOKIES

```

Then run the bot with docker-compose

```sh
docker-compose up -d
```
And then populate the database with pixiv users via your bot DM
```
/adduser <pixiv_user_id> <pixiv_user_id> ...
```

## Where to get user id?

Open pixiv user in browser and check the url. It should be like this

https://www.pixiv.net/en/users/123456789

The user id here is 123456789

# Requirements

```
aiosqlite==0.20.0
beautifulsoup4==4.12.3
feedparser==6.0.11
httpx==0.28.1
loguru==0.7.3
pillow==11.1.0
python-dotenv==1.0.1
python-telegram-bot==21.10
```

# NSFW
Bot checks everypost for nsfw content. If it finds it, it will not send it to the channel. 
https://github.com/tmplink/nsfw_detector?tab=readme-ov-file
