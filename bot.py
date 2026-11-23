import os
import tempfile
import logging
from pathlib import Path

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")
JAMENDO_API = "https://api.jamendo.com/v3.0/tracks/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Welcome to MP3 Song Bot!\\n\\n"
        "Song ka naam likho, main Jamendo par available licensed music search karunga.\\n"
        "Misal: Summer, Love, Piano"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bas song ya artist ka naam message mein bhejo.\\n"
        "Main available licensed MP3 track search karke bhej dunga."
    )

async def search_track(query: str):
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": 1,
        "search": query,
        "audioformat": "mp32",
        "order": "popularity_total",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(JAMENDO_API, params=params)
        response.raise_for_status()
        data = response.json()

    results = data.get("results", [])
    return results[0] if results else None

async def download_track(url: str, destination: str):
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = 0
            with open(destination, "wb") as output:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > 24 * 1024 * 1024:
                        raise ValueError("Track file is larger than 24 MB.")
                    output.write(chunk)

async def song_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return

    status = await update.message.reply_text("🔎 Song search ho raha hai...")

    try:
        track = await search_track(query)
        if not track:
            await status.edit_text(
                "😕 Is naam ka licensed MP3 track nahi mila. "
                "Kisi aur song ya artist ka naam try karo."
            )
            return

        audio_url = track.get("audio")
        if not audio_url:
            await status.edit_text("Is track ka playable audio link available nahi hai.")
            return

        title = track.get("name") or query
        artist = track.get("artist_name") or "Unknown artist"
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = str(Path(temp_dir) / "song.mp3")
            await download_track(audio_url, file_path)

            await status.delete()
            with open(file_path, "rb") as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=title[:64],
                    performer=artist[:64],
                    caption=f"🎵 {title}\\n👤 {artist}\\nSource: Jamendo",
                )

    except httpx.HTTPStatusError as exc:
        log.warning("API/Download HTTP error: %s", exc)
        await status.edit_text(
            "⚠️ Music service se response nahi mila. Thori dair baad try karo."
        )
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Track error: %s", exc)
        await status.edit_text(
            "⚠️ Song download nahi ho saka. Doosra track search karo."
        )
    except Exception:
        log.exception("Unexpected error while processing song")
        await status.edit_text("⚠️ Kuch error aa gaya. Bot logs check karo.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")
    if not JAMENDO_CLIENT_ID:
        raise RuntimeError("JAMENDO_CLIENT_ID environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, song_search))

    log.info("MP3 Song Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
