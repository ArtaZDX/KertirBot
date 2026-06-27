"""
Book & PDF library.

  /bookadd   -> send file -> title -> author -> category -> tags -> saved (unread)
  /books     list all
  /booksearch <keyword>
  /reading   list books currently being read
  /finished  list finished books
  /booknote  attach/replace a note and set reading status
"""

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import db
from services import obsidian
from services.security import restricted, safe_filename
from services.storage import (
    TOO_BIG_MESSAGE,
    download_telegram_file,
    exceeds_download_limit,
    storage,
)

TITLE, AUTHOR, CATEGORY, TAGS = range(4)
# A second conversation for adding a note.
NOTE_PICK, NOTE_TEXT = range(10, 12)


@restricted
async def book_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Send the book file (PDF / EPUB / doc). /cancel to stop."
    )
    return TITLE  # we actually wait for the file first; see receive below


async def receive_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("Please send the book as a file.")
        return TITLE
    if exceeds_download_limit(doc.file_size):
        await update.message.reply_text(TOO_BIG_MESSAGE)
        return ConversationHandler.END
    context.user_data["book"] = {
        "file_id": doc.file_id,
        "original": doc.file_name or f"book_{doc.file_id[:8]}",
    }
    await update.message.reply_text("Title?")
    return AUTHOR


async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["title"] = update.message.text.strip()
    await update.message.reply_text("Author? (or /skip)")
    return CATEGORY


async def set_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["author"] = update.message.text.strip()
    await update.message.reply_text("Category? e.g. Study, Fiction, Reference")
    return TAGS


async def skip_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["author"] = ""
    await update.message.reply_text("Category? e.g. Study, Fiction, Reference")
    return TAGS


# One more state is needed after the tags prompt. Defined here so set_category
# (above) can refer to it by name.
TAGS_DONE = 4


async def set_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["category"] = update.message.text.strip()
    await update.message.reply_text("Tags? (space separated, or /skip)")
    return TAGS_DONE


async def set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["tags"] = update.message.text.strip()
    return await _save_book(update, context)


async def skip_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["book"]["tags"] = ""
    return await _save_book(update, context)


async def _save_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = context.user_data.get("book", {})
    data = await download_telegram_file(context.bot, b["file_id"])
    saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_filename(b['original'])}"
    path = storage.save(data, "Books", saved_name)
    book_id = db.execute(
        """INSERT INTO books
           (file_id, title, author, category, tags, status, notes,
            saved_filename, file_path, upload_date)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            b["file_id"], b.get("title", b["original"]), b.get("author", ""),
            b.get("category", "Other"), b.get("tags", ""), "unread", "",
            saved_name, path, datetime.now().isoformat(timespec="seconds"),
        ),
    )
    context.user_data.pop("book", None)
    extra = " (also saved to Obsidian)" if obsidian.export_book(book_id) else ""
    await update.message.reply_text(f"✅ Added “{b.get('title')}” (status: unread).{extra}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("book", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def _format(rows) -> str:
    icons = {"unread": "⚪", "reading": "📖", "finished": "✅"}
    out = []
    for r in rows:
        author = f" — {r['author']}" if r["author"] else ""
        out.append(f"{icons.get(r['status'], '•')} #{r['id']} {r['title']}{author}")
    return "\n".join(out)


@restricted
async def books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM books ORDER BY id DESC LIMIT 30")
    await update.message.reply_text(
        "📚 Library:\n\n" + _format(rows) + "\n\nUse /getbook <id> to download."
        if rows else "No books yet. Use /bookadd."
    )


@restricted
async def book_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = " ".join(context.args).strip()
    if not kw:
        await update.message.reply_text("Usage: /booksearch <keyword>")
        return
    like = f"%{kw}%"
    rows = db.query(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR tags LIKE ? "
        "OR category LIKE ? ORDER BY id DESC",
        (like, like, like, like),
    )
    await update.message.reply_text(
        f"🔎 “{kw}”:\n\n" + _format(rows) if rows else "No matching books."
    )


@restricted
async def reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM books WHERE status='reading' ORDER BY id DESC")
    await update.message.reply_text(
        "📖 Currently reading:\n\n" + _format(rows) if rows else "Not reading anything."
    )


@restricted
async def finished(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM books WHERE status='finished' ORDER BY id DESC")
    await update.message.reply_text(
        "✅ Finished:\n\n" + _format(rows) if rows else "No finished books yet."
    )


@restricted
async def get_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /getbook <id>")
        return
    row = db.query_one("SELECT * FROM books WHERE id = ?", (context.args[0],))
    if not row:
        await update.message.reply_text("No book with that id.")
        return
    await context.bot.send_document(
        chat_id=update.effective_chat.id, document=row["file_id"],
        caption=f"{row['title']} ({row['status']})",
    )


# --- /booknote: pick a book, set status, write a note -----------------------
@restricted
async def booknote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM books ORDER BY id DESC LIMIT 15")
    if not rows:
        await update.message.reply_text("No books yet. Use /bookadd.")
        return ConversationHandler.END
    buttons = [
        [InlineKeyboardButton(f"#{r['id']} {r['title'][:30]}", callback_data=f"booknote:{r['id']}")]
        for r in rows
    ]
    await update.message.reply_text(
        "Which book?", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return NOTE_PICK


async def booknote_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["booknote_id"] = query.data.split(":", 1)[1]
    buttons = [[
        InlineKeyboardButton("⚪ unread", callback_data="bstatus:unread"),
        InlineKeyboardButton("📖 reading", callback_data="bstatus:reading"),
        InlineKeyboardButton("✅ finished", callback_data="bstatus:finished"),
    ]]
    await query.edit_message_text(
        "Set reading status, then send your note text:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return NOTE_TEXT


async def booknote_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status = query.data.split(":", 1)[1]
    db.execute(
        "UPDATE books SET status = ? WHERE id = ?",
        (status, context.user_data.get("booknote_id")),
    )
    await query.edit_message_text(f"Status set to {status}. Now send the note text (or /skip).")
    return NOTE_TEXT


async def booknote_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    book_id = context.user_data.get("booknote_id")
    db.execute(
        "UPDATE books SET notes = ? WHERE id = ?",
        (update.message.text.strip(), book_id),
    )
    context.user_data.pop("booknote_id", None)
    if book_id:
        obsidian.export_book(book_id)  # keep the Obsidian note in sync
    await update.message.reply_text("📝 Note saved.")
    return ConversationHandler.END


async def booknote_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    book_id = context.user_data.pop("booknote_id", None)
    if book_id:
        obsidian.export_book(book_id)  # status may have changed; refresh the note
    await update.message.reply_text("Done.")
    return ConversationHandler.END


@restricted
async def book_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not obsidian.is_enabled():
        await update.message.reply_text(
            "Obsidian export is off. Set OBSIDIAN_VAULT_PATH in your .env, "
            "restart the bot, then run /booksync again."
        )
        return
    await update.message.reply_text("📓 Exporting all books to Obsidian…")
    count = obsidian.export_all()
    await update.message.reply_text(f"✅ Wrote {count} book note(s) to your Obsidian vault.")


def get_handlers() -> list:
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("bookadd", book_add)],
        states={
            TITLE: [MessageHandler(filters.Document.ALL, receive_book)],
            AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_title)],
            CATEGORY: [
                CommandHandler("skip", skip_author),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_author),
            ],
            TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_category)],
            TAGS_DONE: [
                CommandHandler("skip", skip_tags),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_tags),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    note_conv = ConversationHandler(
        entry_points=[CommandHandler("booknote", booknote_start)],
        states={
            NOTE_PICK: [CallbackQueryHandler(booknote_pick, pattern=r"^booknote:")],
            NOTE_TEXT: [
                CallbackQueryHandler(booknote_status, pattern=r"^bstatus:"),
                CommandHandler("skip", booknote_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booknote_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return [
        add_conv,
        note_conv,
        CommandHandler("books", books),
        CommandHandler("booksearch", book_search),
        CommandHandler("reading", reading),
        CommandHandler("finished", finished),
        CommandHandler("getbook", get_book),
        CommandHandler("booksync", book_sync),
    ]
