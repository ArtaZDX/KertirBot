"""
Obsidian export.

An Obsidian vault is just a folder full of Markdown (.md) files, so "connecting"
the book archive to Obsidian means writing one Markdown note per book into your
vault. The note also EMBEDS the book file itself: the file is copied into the
vault (under Books/files/) and linked with an Obsidian embed, so PDFs and images
open/preview right inside Obsidian. Obsidian picks up new/changed files itself.

This is a ONE-WAY export (bot -> Obsidian). Editing a note inside Obsidian does
not change the bot's database. See the README for why, and for the two-way idea.

Enable it by setting OBSIDIAN_VAULT_PATH in your .env. If it is blank, every
function here is a safe no-op, so the rest of the bot keeps working unchanged.
"""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from config import OBSIDIAN_BOOKS_SUBFOLDER, OBSIDIAN_VAULT_PATH
from database import db

logger = logging.getLogger("personal_bot.obsidian")

# Characters that are illegal in file names on Windows/macOS/Linux. We keep
# spaces (Obsidian is happy with them) but strip these out.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# File types Obsidian can preview inline with an embed (![[...]]).
_EMBEDDABLE = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def is_enabled() -> bool:
    return bool(OBSIDIAN_VAULT_PATH)


def _books_dir() -> Path:
    return Path(OBSIDIAN_VAULT_PATH) / OBSIDIAN_BOOKS_SUBFOLDER


def _note_basename(title: str, book_id: int) -> str:
    """A stable, safe base name shared by the note and the copied file."""
    clean = _ILLEGAL.sub("", title or "Untitled").strip().rstrip(".")
    clean = clean[:80] or "Untitled"
    return f"{clean} (book-{book_id})"


def _split_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [t.lstrip("#") for t in raw.split() if t.strip()]


def _copy_attachment(book, books_dir: Path):
    """
    Copy the book's stored file into the vault so Obsidian can open it.
    Returns the attachment's file name (for the embed link), or None if there
    is no source file. Skips copying if an up-to-date copy already exists.
    """
    src = book["file_path"]
    if not src or not Path(src).exists():
        return None
    ext = Path(src).suffix
    name = _note_basename(book["title"], book["id"]) + ext
    dest_dir = books_dir / "files"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    # Re-copy only if missing or the source is newer/different size.
    if not dest.exists() or dest.stat().st_size != Path(src).stat().st_size:
        shutil.copy2(src, dest)
    return name


def _render(book, attachment) -> str:
    """Build the Markdown content (YAML frontmatter + body) for one book."""
    tags = _split_tags(book["tags"])
    tags_yaml = "[" + ", ".join(tags) + "]" if tags else "[]"

    def q(value: str) -> str:
        return '"' + (value or "").replace('"', "'") + '"'

    frontmatter = (
        "---\n"
        f"title: {q(book['title'])}\n"
        f"author: {q(book['author'])}\n"
        f"category: {q(book['category'])}\n"
        f"status: {q(book['status'])}\n"
        f"tags: {tags_yaml}\n"
        f"added: {book['upload_date'][:10]}\n"
        f"book_id: {book['id']}\n"
        "source: telegram-bot\n"
        "---\n\n"
    )

    body_tags = " ".join(f"#{t}" for t in tags)
    author_line = f"**Author:** {book['author']}\n" if book["author"] else ""
    notes = book["notes"] or "_No notes yet._"

    # The "File" section embeds (or links) the copied book file.
    if attachment:
        if Path(attachment).suffix.lower() in _EMBEDDABLE:
            file_section = f"## File\n\n![[{attachment}]]\n\n"
        else:
            file_section = f"## File\n\n[[{attachment}]]\n\n"
    else:
        file_section = f"_Stored file (not copied):_ `{book['file_path']}`\n\n"

    body = (
        f"# {book['title']}\n\n"
        f"{author_line}"
        f"**Status:** {book['status']}\n"
        f"**Category:** {book['category']}\n"
        f"**Added:** {book['upload_date'][:10]}\n"
        + (f"\n{body_tags}\n" if body_tags else "")
        + "\n"
        + file_section
        + "## Notes\n\n"
        f"{notes}\n\n"
        "---\n"
        f"_Exported from your Telegram bot on {datetime.now():%Y-%m-%d %H:%M}._\n"
    )
    return frontmatter + body


def export_book(book_id: int) -> bool:
    """Write/refresh the Obsidian note (and copy the file) for one book."""
    if not is_enabled():
        return False
    book = db.query_one("SELECT * FROM books WHERE id = ?", (book_id,))
    if not book:
        return False
    try:
        books_dir = _books_dir()
        books_dir.mkdir(parents=True, exist_ok=True)
        attachment = _copy_attachment(book, books_dir)
        path = books_dir / (_note_basename(book["title"], book["id"]) + ".md")
        path.write_text(_render(book, attachment), encoding="utf-8")
        return True
    except Exception:
        # Never let an export problem crash a bot command; just log it.
        logger.exception("Failed to export book %s to Obsidian", book_id)
        return False


def export_all() -> int:
    """Export every book. Returns how many notes were written."""
    if not is_enabled():
        return 0
    rows = db.query("SELECT id FROM books")
    return sum(1 for r in rows if export_book(r["id"]))
