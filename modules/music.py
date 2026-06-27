"""
Music archive.

  /musicadd                 send an audio file -> title -> artist -> mood -> tags
  /musicsearch <keyword>    search the archive
  /playlist <mood>          list tracks for a given mood
  /getmusic <id>            send a track back to yourself

YouTube -> MP3:
  Send any YouTube link (or use /mp3 <url>) and the bot downloads the audio as
  MP3 and posts it to your music channel (MUSIC_CHANNEL_ID), or to you if that
  is not set. It also files the track in the music archive.

  RESPONSIBLE USE: only download audio you own, that is public domain / Creative
  Commons, or that you have permission to download. See services/youtube.py.
"""

import asyncio
import os
import re
from datetime import datetime

from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
from database import db
from services import youtube
from services.security import restricted, safe_filename
from services.storage import (
    MAX_DOWNLOAD_BYTES,
    TOO_BIG_MESSAGE,
    download_telegram_file,
    exceeds_download_limit,
    storage,
)

M_FILE, M_TITLE, M_ARTIST, M_MOOD, M_TAGS = range(5)

# Matches youtube.com/watch, youtu.be, shorts, and music.youtube links.
YOUTUBE_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/|live/)|youtu\.be/)[\w\-]+[^\s]*",
    re.IGNORECASE,
)

# Telegram bots can SEND files up to 50 MB.
TELEGRAM_SEND_LIMIT = 50 * 1024 * 1024


@restricted
async def music_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Send the audio file. /cancel to stop.")
    return M_FILE


async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.audio:
        file_id = msg.audio.file_id
        original = msg.audio.file_name or f"{msg.audio.title or 'track'}.mp3"
        default_title = msg.audio.title or original
        default_artist = msg.audio.performer or ""
    elif msg.voice:
        file_id = msg.voice.file_id
        original = f"voice_{datetime.now():%Y%m%d_%H%M%S}.ogg"
        default_title, default_artist = original, ""
    elif msg.document:
        file_id = msg.document.file_id
        original = msg.document.file_name or "track"
        default_title, default_artist = original, ""
    else:
        await msg.reply_text("Please send an audio file.")
        return M_FILE
    size = getattr(getattr(msg, "audio", None) or getattr(msg, "document", None), "file_size", None)
    if exceeds_download_limit(size):
        await msg.reply_text(TOO_BIG_MESSAGE)
        return ConversationHandler.END
    context.user_data["track"] = {
        "file_id": file_id, "original": original,
        "default_title": default_title, "default_artist": default_artist,
    }
    await msg.reply_text(f"Title? (or /skip to use “{default_title}”)")
    return M_TITLE


async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track"]["title"] = update.message.text.strip()
    await update.message.reply_text("Artist? (or /skip)")
    return M_ARTIST


async def skip_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = context.user_data["track"]
    t["title"] = t["default_title"]
    await update.message.reply_text("Artist? (or /skip)")
    return M_ARTIST


async def set_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track"]["artist"] = update.message.text.strip()
    await update.message.reply_text("Mood? e.g. calm, happy, focus")
    return M_MOOD


async def skip_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = context.user_data["track"]
    t["artist"] = t["default_artist"]
    await update.message.reply_text("Mood? e.g. calm, happy, focus")
    return M_MOOD


async def set_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track"]["mood"] = update.message.text.strip()
    await update.message.reply_text("Tags? (or /skip)")
    return M_TAGS


async def set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track"]["tags"] = update.message.text.strip()
    return await _save_track(update, context)


async def skip_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track"]["tags"] = ""
    return await _save_track(update, context)


async def _save_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = context.user_data.get("track", {})
    data = await download_telegram_file(context.bot, t["file_id"])
    saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_filename(t['original'])}"
    path = storage.save(data, "Music", saved_name)
    db.execute(
        """INSERT INTO music
           (file_id, title, artist, mood, tags, saved_filename, file_path, upload_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            t["file_id"], t.get("title", t["original"]), t.get("artist", ""),
            t.get("mood", ""), t.get("tags", ""), saved_name, path,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    context.user_data.pop("track", None)
    await update.message.reply_text(f"🎵 Saved “{t.get('title')}”.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("track", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def _format(rows) -> str:
    return "\n".join(
        f"#{r['id']} {r['title']}"
        + (f" — {r['artist']}" if r["artist"] else "")
        + (f"  [{r['mood']}]" if r["mood"] else "")
        for r in rows
    )


@restricted
async def music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = " ".join(context.args).strip()
    if not kw:
        await update.message.reply_text("Usage: /musicsearch <keyword>")
        return
    like = f"%{kw}%"
    rows = db.query(
        "SELECT * FROM music WHERE title LIKE ? OR artist LIKE ? OR mood LIKE ? OR tags LIKE ? "
        "ORDER BY id DESC",
        (like, like, like, like),
    )
    await update.message.reply_text(
        f"🔎 “{kw}”:\n\n" + _format(rows) + "\n\nUse /getmusic <id> to play."
        if rows else "No matching tracks."
    )


@restricted
async def playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mood = " ".join(context.args).strip()
    if not mood:
        await update.message.reply_text("Usage: /playlist <mood>  e.g. /playlist calm")
        return
    rows = db.query(
        "SELECT * FROM music WHERE mood LIKE ? ORDER BY id DESC", (f"%{mood}%",)
    )
    await update.message.reply_text(
        f"🎶 {mood} playlist:\n\n" + _format(rows) + "\n\nUse /getmusic <id> to play."
        if rows else f"No tracks with mood “{mood}”."
    )


@restricted
async def get_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /getmusic <id>")
        return
    row = db.query_one("SELECT * FROM music WHERE id = ?", (context.args[0],))
    if not row:
        await update.message.reply_text("No track with that id.")
        return
    await context.bot.send_audio(
        chat_id=update.effective_chat.id, audio=row["file_id"],
        title=row["title"], performer=row["artist"] or None,
    )


def _channel_target():
    """Return the chat id/username to post to, or None if not configured."""
    cid = (config.MUSIC_CHANNEL_ID or "").strip()
    if not cid:
        return None
    # Numeric ids (possibly negative for channels) must be passed as int.
    return int(cid) if cid.lstrip("-").isdigit() else cid


async def _process_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Download `url` as MP3, post it to the channel (or the user), and archive it."""
    if not youtube.ffmpeg_available():
        await update.message.reply_text(
            "⚠️ I need *ffmpeg* installed to make MP3s, and it isn't on this machine.\n"
            "Install it (Windows: `winget install Gyan.FFmpeg`) and restart the bot.",
            parse_mode="Markdown",
        )
        return

    status = await update.message.reply_text("🎧 Downloading audio… this can take a moment.")
    music_dir = os.path.join(config.STORAGE_PATH, "Music")
    try:
        # Run the blocking download in a thread so the bot stays responsive.
        mp3_path, meta = await asyncio.to_thread(youtube.download_audio, url, music_dir)
    except youtube.DownloadError as exc:
        await status.edit_text(f"❌ Couldn't download that link:\n{exc}")
        return

    size = os.path.getsize(mp3_path)
    if size > TELEGRAM_SEND_LIMIT:
        await status.edit_text(
            f"⬇️ Downloaded “{meta['title']}”, but it's {size / 1024 / 1024:.1f} MB — "
            "over Telegram's 50 MB send limit, so I can't post it. The file is saved "
            f"locally at:\n{mp3_path}"
        )
        return

    target = _channel_target()
    chat_id = target if target is not None else update.effective_chat.id
    try:
        with open(mp3_path, "rb") as audio_file:
            sent = await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=meta["title"],
                performer=meta["artist"] or None,
                duration=meta["duration"] or None,
                caption=meta["webpage_url"],
            )
    except Forbidden:
        await status.edit_text(
            "❌ I'm not allowed to post to that channel. Add this bot to the channel "
            "as an *admin*, and check MUSIC_CHANNEL_ID in your .env.",
            parse_mode="Markdown",
        )
        return
    except BadRequest as exc:
        await status.edit_text(
            f"❌ Telegram rejected the send: {exc}.\nCheck that MUSIC_CHANNEL_ID is correct."
        )
        return

    # Archive it in the music table (reuse the file_id Telegram just gave us).
    file_id = sent.audio.file_id if sent.audio else None
    db.execute(
        """INSERT INTO music
           (file_id, title, artist, mood, tags, saved_filename, file_path, upload_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            file_id, meta["title"], meta["artist"], "", "youtube",
            os.path.basename(mp3_path), mp3_path,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    where = "your music channel" if target is not None else (
        "you (set MUSIC_CHANNEL_ID in .env to post to your channel instead)"
    )
    await status.edit_text(f"✅ “{meta['title']}” sent to {where} and added to your archive.")


@restricted
async def youtube_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when a plain message contains a YouTube link."""
    match = YOUTUBE_RE.search(update.message.text or "")
    if match:
        await _process_youtube(update, context, match.group(0))


@restricted
async def mp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicit '/mp3 <url>' form."""
    text = " ".join(context.args)
    match = YOUTUBE_RE.search(text)
    if not match:
        await update.message.reply_text("Usage: /mp3 <YouTube link>")
        return
    await _process_youtube(update, context, match.group(0))


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("musicadd", music_add)],
        states={
            M_FILE: [MessageHandler(
                filters.AUDIO | filters.VOICE | filters.Document.ALL, receive_audio)],
            M_TITLE: [
                CommandHandler("skip", skip_title),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_title),
            ],
            M_ARTIST: [
                CommandHandler("skip", skip_artist),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_artist),
            ],
            M_MOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_mood)],
            M_TAGS: [
                CommandHandler("skip", skip_tags),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_tags),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return [
        conv,
        CommandHandler("musicsearch", music_search),
        CommandHandler("playlist", playlist),
        CommandHandler("getmusic", get_music),
        CommandHandler("mp3", mp3_command),
        # Auto-detect a YouTube link in any (non-command) text message.
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(YOUTUBE_RE), youtube_message),
    ]
