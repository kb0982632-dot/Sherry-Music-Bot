import os
import tempfile
import logging
from pathlib import Path

import requests
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID", "").strip()
JAMENDO_API = "https://api.jamendo.com/v3.0/tracks/"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("sherry-music-bot")


def search_tracks(query: str):
    """Search Jamendo and return only tracks whose creators allow downloads."""
    response = requests.get(
        JAMENDO_API,
        params={
            "client_id": JAMENDO_CLIENT_ID,
            "format": "json",
            "namesearch": query,
            "limit": 8,
            "audioformat": "mp32",
            "audiodlformat": "mp32",
        },
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("headers", {}).get("status") != "success":
        raise RuntimeError(data.get("headers", {}).get("error_message") or "Jamendo API error")

    # Respect each artist's download permission.
    return [
        track for track in data.get("results", [])
        if track.get("audiodownload_allowed") is True and track.get("audiodownload")
    ]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Welcome to Sherry VIP Music Bot!\n\n"
        "Song ka naam bhejo. Main available licensed MP3 tracks search karke bhejunga.\n"
        "Commands: /start  /help"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bas song ka naam message mein likho.\n"
        "Note: Sirf woh tracks bheje ja sakte hain jin ke creators ne download allow kiya ho."
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return

    status = await update.message.reply_text(f"🔎 Searching: {query}")
    try:
        tracks = search_tracks(query)
        if not tracks:
            await status.edit_text(
                "Is naam ka downloadable licensed track nahi mila. "
                "Kisi doosre naam se search karo."
            )
            return

        sent = 0
        for track in tracks[:3]:
            url = track.get("audiodownload")
            title = track.get("name", "Unknown song")
            artist = track.get("artist_name", "Unknown artist")
            track_id = track.get("id", "")
            duration = int(track.get("duration") or 0)

            # Download the permitted file temporarily, then upload it to Telegram.
            with requests.get(url, stream=True, timeout=(20, 90)) as r:
                r.raise_for_status()
                content_type = r.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    raise RuntimeError("Music provider did not return an audio file.")

                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                    total = 0
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            total += len(chunk)
                            if total > 45 * 1024 * 1024:
                                raise RuntimeError("Track is too large to upload through this bot.")
                            tmp.write(chunk)

            try:
                with temp_path.open("rb") as audio_file:
                    await update.message.reply_audio(
                        audio=audio_file,
                        title=title[:64],
                        performer=artist[:64],
                        duration=duration if duration > 0 else None,
                        caption=f"🎵 {title}\n👤 {artist}\n"
                                f"🔗 https://www.jamendo.com/track/{track_id}",
                    )
                sent += 1
            finally:
                temp_path.unlink(missing_ok=True)

        await status.delete()
        if sent == 0:
            await update.message.reply_text("Track send nahi ho saka. Dobara try karo.")
    except requests.RequestException:
        log.exception("Network error while searching/sending")
        await status.edit_text("Network/API error. Thori dair baad dobara try karo.")
    except Exception:
        log.exception("Unexpected error")
        await status.edit_text("Song send nahi ho saka. API key aur hosting logs check karo.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")
    if not JAMENDO_CLIENT_ID:
        raise RuntimeError("JAMENDO_CLIENT_ID environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    log.info("Sherry VIP Music Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
