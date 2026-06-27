"""
Backup.

  /backup   creates a zip containing the SQLite database and every uploaded
            file, saves it under data/backups/, and sends it to you in chat.

Telegram bots can only send files up to ~50 MB. If your archive grows beyond
that, the zip is still written to disk and you are told where to find it.
"""

import os
import zipfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import BACKUP_PATH, SQLITE_PATH, STORAGE_PATH
from services.security import restricted

TELEGRAM_MAX_BYTES = 50 * 1024 * 1024


def make_backup() -> Path:
    """Create the backup zip and return its path."""
    name = f"backup_{datetime.now():%Y%m%d_%H%M%S}.zip"
    out_path = Path(BACKUP_PATH) / name
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(SQLITE_PATH):
            z.write(SQLITE_PATH, arcname="vault.db")
        for root, _dirs, files in os.walk(STORAGE_PATH):
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, STORAGE_PATH)
                z.write(full, arcname=os.path.join("files", rel))
    return out_path


@restricted
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Creating backup…")
    out_path = make_backup()
    size = out_path.stat().st_size
    if size <= TELEGRAM_MAX_BYTES:
        with open(out_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=out_path.name,
                caption=f"Backup • {size / 1024:.0f} KB",
            )
    else:
        await update.message.reply_text(
            f"✅ Backup created but it is too large to send via Telegram "
            f"({size / 1024 / 1024:.1f} MB).\nSaved at:\n{out_path}"
        )


def get_handlers() -> list:
    return [CommandHandler("backup", backup)]
