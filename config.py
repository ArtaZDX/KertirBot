"""
Central configuration.

All secrets and paths are loaded from the environment (a `.env` file in
development). Nothing sensitive is hard-coded here.

To migrate to PostgreSQL later, set DATABASE_URL and update database.py to
branch on it. The rest of the app only talks to the Database class, so this is
the only place that needs to change.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file if present.
load_dotenv()

# Project root (the folder that contains this file).
BASE_DIR = Path(__file__).resolve().parent

# --- Secrets / identity -----------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0") or "0")

# --- Database ---------------------------------------------------------------
# For v1 we use SQLite. DATABASE_URL is reserved for a future PostgreSQL move.
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "vault.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "")  # e.g. postgresql://user:pass@host/db

# --- File storage -----------------------------------------------------------
STORAGE_PATH = os.getenv("STORAGE_PATH", str(BASE_DIR / "data" / "files"))
BACKUP_PATH = os.getenv("BACKUP_PATH", str(BASE_DIR / "data" / "backups"))

# --- Obsidian export (optional) ---------------------------------------------
# Path to your Obsidian vault folder. Leave blank to disable Obsidian export.
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")
# Sub-folder inside the vault where book notes are written.
OBSIDIAN_BOOKS_SUBFOLDER = os.getenv("OBSIDIAN_BOOKS_SUBFOLDER", "Books")

# --- Music channel (optional) -----------------------------------------------
# Where YouTube->MP3 downloads are posted. Either a numeric id like
# "-1001234567890" or a public "@channelusername". The bot must be a member/admin
# of that channel. Leave blank to send the MP3 to your own chat instead.
MUSIC_CHANNEL_ID = os.getenv("MUSIC_CHANNEL_ID", "")

# Optional explicit path to the ffmpeg binary or its folder (needed for MP3).
# Leave blank if ffmpeg is already on your system PATH.
FFMPEG_LOCATION = os.getenv("FFMPEG_LOCATION", "")

# Make sure the folders we rely on exist before anything else runs.
for _p in (Path(SQLITE_PATH).parent, Path(STORAGE_PATH), Path(BACKUP_PATH)):
    Path(_p).mkdir(parents=True, exist_ok=True)


def validate() -> None:
    """Fail fast with a clear message if required settings are missing."""
    problems = []
    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN is not set.")
    if ALLOWED_USER_ID == 0:
        problems.append("ALLOWED_USER_ID is not set (the bot would be open to everyone).")
    if problems:
        raise SystemExit(
            "Configuration error:\n  - " + "\n  - ".join(problems)
            + "\n\nCopy .env.example to .env and fill in the values."
        )
