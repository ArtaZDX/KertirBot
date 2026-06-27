"""
YouTube -> MP3 download service.

Wraps yt-dlp so the rest of the app only calls `download_audio(url, dest_dir)`.
Audio extraction to MP3 requires the **ffmpeg** executable to be installed and on
PATH; `ffmpeg_available()` lets callers check first and show a helpful message.

------------------------------------------------------------------------------
RESPONSIBLE USE — READ THIS
------------------------------------------------------------------------------
Downloading audio/video from YouTube can violate YouTube's Terms of Service and
copyright law. Only download content that you own, that is in the public domain
or Creative Commons licensed, or that you have explicit permission to download.
You (the operator of this bot) are solely responsible for how this is used.
------------------------------------------------------------------------------
"""

import glob
import os
import shutil

from yt_dlp import YoutubeDL

from config import FFMPEG_LOCATION


class DownloadError(Exception):
    """Raised when a download/extraction fails, with a user-friendly message."""


def ffmpeg_available() -> bool:
    """True if ffmpeg can be found on PATH or via the FFMPEG_LOCATION setting."""
    if shutil.which("ffmpeg") is not None:
        return True
    if FFMPEG_LOCATION and (
        os.path.isdir(FFMPEG_LOCATION) or os.path.isfile(FFMPEG_LOCATION)
    ):
        return True
    return False


def download_audio(url: str, dest_dir: str) -> tuple[str, dict]:
    """
    Download the best audio for `url` and convert it to MP3 in `dest_dir`.

    Returns (mp3_path, metadata). Runs synchronously (blocking) — call it from a
    worker thread (e.g. asyncio.to_thread) so it doesn't freeze the bot.
    """
    os.makedirs(dest_dir, exist_ok=True)

    options = {
        "format": "bestaudio/best",
        # Save as "<video id>.<ext>"; the postprocessor then makes "<id>.mp3".
        "outtmpl": os.path.join(dest_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,          # a link inside a playlist -> just that track
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    # If ffmpeg isn't on PATH, tell yt-dlp exactly where it is.
    if FFMPEG_LOCATION:
        options["ffmpeg_location"] = FFMPEG_LOCATION

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # yt-dlp raises many error types; normalise them
        raise DownloadError(str(exc)) from exc

    video_id = info.get("id", "audio")
    mp3_path = os.path.join(dest_dir, f"{video_id}.mp3")
    if not os.path.exists(mp3_path):
        # Fallback: locate whatever file ended up with that id.
        matches = glob.glob(os.path.join(dest_dir, f"{video_id}.*"))
        if not matches:
            raise DownloadError("Download finished but the audio file was not found.")
        mp3_path = matches[0]

    metadata = {
        "title": info.get("title") or video_id,
        "artist": info.get("artist") or info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "webpage_url": info.get("webpage_url") or url,
    }
    return mp3_path, metadata
