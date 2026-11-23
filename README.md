# Sherry VIP Music Bot (Python)

Telegram bot that searches Jamendo and sends MP3 files only when the artist has enabled downloads for that track.

## Files
- `bot.py` — main bot
- `requirements.txt` — Python dependencies

## Environment variables on Fadehost
Add these as separate variables (do not paste them into one field):

| Name | Value |
|---|---|
| `BOT_TOKEN` | Your Telegram bot token from BotFather |
| `JAMENDO_CLIENT_ID` | Your Jamendo API client ID |

Keep both values private. Do not put real tokens in GitHub.

## Fadehost settings
- Runtime: Python 3.10+
- Install/dependency command: `pip install -r requirements.txt`
- Start command: `python bot.py`

If Fadehost has a separate Start File field, set it to `bot.py`.

## Run locally
```bash
pip install -r requirements.txt
python bot.py
```

Send `/start` to your bot, then send a song title as a normal message.

## Important
This bot only sends tracks for which Jamendo reports `audiodownload_allowed=true`.
It cannot guarantee that every commercial/copyrighted song is available as a downloadable MP3.
