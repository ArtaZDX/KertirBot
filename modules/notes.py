"""
Personal notes / knowledge base.

  /note <text>        save a quick note (first line becomes the title)
  /notes <keyword>    search notes (no keyword = list recent)
  /randomnote         show a random note
  /deletenote         pick a note to delete
"""

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from database import db
from services.security import restricted


@restricted
async def note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.partition(" ")[2].strip()  # everything after /note
    if not text:
        await update.message.reply_text("Usage: /note <your note>\nTip: use #tags inside the text.")
        return
    title = text.split("\n", 1)[0][:60]
    tags = " ".join(w for w in text.split() if w.startswith("#"))
    db.execute(
        "INSERT INTO notes (title, content, tags, category, created_date) VALUES (?,?,?,?,?)",
        (title, text, tags, "General", datetime.now().isoformat(timespec="seconds")),
    )
    await update.message.reply_text("📝 Note saved.")


@restricted
async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = " ".join(context.args).strip()
    if kw:
        like = f"%{kw}%"
        rows = db.query(
            "SELECT * FROM notes WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? "
            "ORDER BY id DESC LIMIT 20",
            (like, like, like),
        )
        header = f"🔎 “{kw}”:"
    else:
        rows = db.query("SELECT * FROM notes ORDER BY id DESC LIMIT 15")
        header = "🗒 Recent notes:"
    if not rows:
        await update.message.reply_text("No matching notes.")
        return
    body = "\n".join(f"#{r['id']} {r['title']}" for r in rows)
    await update.message.reply_text(f"{header}\n\n{body}\n\nSend /getnote <id> to read one.")


@restricted
async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /getnote <id>")
        return
    row = db.query_one("SELECT * FROM notes WHERE id = ?", (context.args[0],))
    if not row:
        await update.message.reply_text("No note with that id.")
        return
    await update.message.reply_text(
        f"📝 #{row['id']} {row['title']}\n{row['created_date'][:10]}\n\n{row['content']}"
    )


@restricted
async def random_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = db.query_one("SELECT * FROM notes ORDER BY RANDOM() LIMIT 1")
    if not row:
        await update.message.reply_text("No notes yet. Add one with /note.")
        return
    await update.message.reply_text(f"🎲 #{row['id']} {row['title']}\n\n{row['content']}")


@restricted
async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM notes ORDER BY id DESC LIMIT 15")
    if not rows:
        await update.message.reply_text("No notes to delete.")
        return
    buttons = [
        [InlineKeyboardButton(f"🗑 #{r['id']} {r['title'][:30]}", callback_data=f"delnote:{r['id']}")]
        for r in rows
    ]
    await update.message.reply_text("Delete which note?", reply_markup=InlineKeyboardMarkup(buttons))


async def delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = query.data.split(":", 1)[1]
    db.execute("DELETE FROM notes WHERE id = ?", (nid,))
    await query.edit_message_text("🗑 Note deleted.")


def get_handlers() -> list:
    return [
        CommandHandler("note", note),
        CommandHandler("notes", notes),
        CommandHandler("getnote", get_note),
        CommandHandler("randomnote", random_note),
        CommandHandler("deletenote", delete_note),
        CallbackQueryHandler(delete_pick, pattern=r"^delnote:"),
    ]
