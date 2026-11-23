import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/"

# Only deliver tracks with a clearly stated open/public-domain license.
ALLOWED_LICENSES = (
    "creativecommons.org/publicdomain",
    "creativecommons.org/licenses/by/",
    "creativecommons.org/licenses/by-sa/",
    "creativecommons.org/licenses/by-nc/",
    "creativecommons.org/licenses/by-nc-sa/",
    "creativecommons.org/licenses/zero/1.0/",
)

def is_allowed_license(value: str) -> bool:
    value = (value or "").lower().strip()
    return any(marker in value for marker in ALLOWED_LICENSES)

async def search_items(query: str):
    # Search title and creator fields in Internet Archive's audio collection.
    safe_query = re.sub(r'["\\]', " ", query).strip()
    params = {
        "q": f'mediatype:audio AND (title:"{safe_query}" OR creator:"{safe_query}")',
        "fl[]": ["identifier", "title", "creator"],
        "rows": 12,
        "page": 1,
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
    return data.get("response", {}).get("docs", [])

async def get_licensed_mp3(identifier: str):
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(f"{METADATA_URL}{quote(identifier, safe='')}")
        response.raise_for_status()
        metadata = response.json()

    license_value = metadata.get("metadata", {}).get("licenseurl", "")
    if not is_allowed_license(license_value):
        return None

    files = metadata.get("files", [])
    candidates = []
    for item in files:
        name = item.get("name", "")
        if (
            name.lower().endswith(".mp3")
            and item.get("source") != "metadata"
            and item.get("private") != "true"
        ):
            candidates.append(item)

    if not candidates:
        return None

    # Prefer a reasonably sized MP3 so Telegram can send it reliably.
    candidates.sort(key=lambda f: int(f.get("size", 0) or 0))
    for item in candidates:
        try:
            size = int(item.get("size", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        if size == 0 or size <= 49 * 1024 * 1024:
            return item["name"], license_value
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 MP3 Song Search Bot\\n\\n"
        "Song ka naam likho. Main Internet Archive par openly licensed "
        "ya public-domain MP3 dhoondhunga. Har commercial song available nahi hota."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Song ka naam message mein bhejo.")

async def handle_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if len(query) < 2:
        await update.message.reply_text("Song ka naam thora detail se likho.")
        return

    status = await update.message.reply_text("🔎 Legal/free MP3 search ho raha hai...")
    try:
        docs = await search_items(query)
        selected = None

        for doc in docs:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            result = await get_licensed_mp3(identifier)
            if result:
                selected = (doc, result)
                break

        if not selected:
            await status.edit_text(
                "😕 Is search mein clearly licensed MP3 nahi mila. "
                "Koi doosra song title try karo."
            )
            return

        doc, (filename, license_value) = selected
        identifier = doc["identifier"]
        download_url = (
            f"https://archive.org/download/{quote(identifier, safe='')}/"
            f"{quote(filename, safe='/')}"
        )
        title = str(doc.get("title") or query)
        creator = str(doc.get("creator") or "Unknown artist")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "track.mp3"
            async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    total = 0
                    with local_path.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > 49 * 1024 * 1024:
                                raise ValueError("MP3 exceeds the bot's 49 MB limit.")
                            output.write(chunk)

            await status.delete()
            with local_path.open("rb") as audio:
                await update.message.reply_audio(
                    audio=audio,
                    title=title[:64],
                    performer=creator[:64],
                    caption=f"🎵 {title}\\n👤 {creator}\\nLicense: {license_value}",
                )

    except httpx.HTTPError:
        log.exception("Internet Archive request failed")
        await status.edit_text("⚠️ Music service abhi respond nahi kar rahi. Baad mein try karo.")
    except Exception:
        log.exception("Song processing failed")
        await status.edit_text("⚠️ Song send nahi ho saka. Doosra naam try karo.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_song))
    log.info("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
