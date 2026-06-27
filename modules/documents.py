"""
Document Vault.

Flow for saving:
  /save -> send a file/photo -> pick a category (buttons) -> optional
  description/tags -> the file is downloaded, stored, and indexed in SQLite.

Other commands: /find, /category, /recent, /getfile, /deletefile.
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
from services.security import restricted, safe_filename
from services.storage import (
    TOO_BIG_MESSAGE,
    download_telegram_file,
    exceeds_download_limit,
    storage,
)

CATEGORIES = [
    "Tax",
    "Passport / Visa / Immigration",
    "Employment",
    "Legal / Tribunal",
    "Bank",
    "NHS / Medical letters",
    "Tenancy / Housing",
    "Car / MOT / Insurance",
    "Certificates",
    "Other",
]

# Conversation states
FILE, CATEGORY, CUSTOM_CAT, DESC = range(4)


@restricted
async def save_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📎 Send me the document or photo you want to save.\nSend /cancel to stop."
    )
    return FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        if exceeds_download_limit(msg.document.file_size):
            await msg.reply_text(TOO_BIG_MESSAGE)
            return ConversationHandler.END
        file_id = msg.document.file_id
        original = msg.document.file_name or f"document_{file_id[:8]}"
    elif msg.photo:
        file_id = msg.photo[-1].file_id  # highest resolution
        original = f"photo_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    else:
        await msg.reply_text("Please send a document or a photo.")
        return FILE

    context.user_data["doc"] = {"file_id": file_id, "original": original}

    buttons = [
        [InlineKeyboardButton(c, callback_data=f"doccat:{i}")]
        for i, c in enumerate(CATEGORIES)
    ]
    buttons.append([InlineKeyboardButton("✏️ Type my own", callback_data="doccat:custom")])
    await msg.reply_text("Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))
    return CATEGORY


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":", 1)[1]
    if data == "custom":
        await query.edit_message_text("Type the category name:")
        return CUSTOM_CAT
    context.user_data["doc"]["category"] = CATEGORIES[int(data)]
    await query.edit_message_text(
        f"Category: {CATEGORIES[int(data)]}\n\n"
        "Send a short description and #tags, or /skip."
    )
    return DESC


async def custom_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["doc"]["category"] = update.message.text.strip()
    await update.message.reply_text("Send a short description and #tags, or /skip.")
    return DESC


async def with_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["doc"]["description"] = update.message.text.strip()
    return await _finalize(update, context)


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["doc"]["description"] = ""
    return await _finalize(update, context)


async def _finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = context.user_data.get("doc", {})
    category = doc.get("category", "Other")
    data = await download_telegram_file(context.bot, doc["file_id"])
    saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_filename(doc['original'])}"
    path = storage.save(data, category, saved_name)

    # Tags = any #hashtags found in the description; description = the full text.
    description = doc.get("description", "")
    tags = " ".join(w for w in description.split() if w.startswith("#"))

    db.execute(
        """INSERT INTO documents
           (file_id, original_filename, saved_filename, category, tags,
            description, upload_date, file_path)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            doc["file_id"],
            doc["original"],
            saved_name,
            category,
            tags,
            description,
            datetime.now().isoformat(timespec="seconds"),
            path,
        ),
    )
    context.user_data.pop("doc", None)
    await update.message.reply_text(
        f"✅ Saved “{doc['original']}” under *{category}*.", parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("doc", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# --- Read / search commands -------------------------------------------------
def _format_rows(rows) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"#{r['id']} • {r['original_filename']}\n"
            f"    {r['category']} • {r['upload_date'][:10]}"
        )
    return "\n".join(lines)


@restricted
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("Usage: /find <keyword>")
        return
    like = f"%{keyword}%"
    rows = db.query(
        """SELECT * FROM documents
           WHERE original_filename LIKE ? OR category LIKE ?
              OR tags LIKE ? OR description LIKE ?
           ORDER BY id DESC LIMIT 20""",
        (like, like, like, like),
    )
    if not rows:
        await update.message.reply_text("No matching documents.")
        return
    await update.message.reply_text(
        f"🔎 Results for “{keyword}”:\n\n{_format_rows(rows)}\n\nUse /getfile <id> to download."
    )


@restricted
async def by_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = " ".join(context.args).strip()
    if not cat:
        await update.message.reply_text("Usage: /category <name>  e.g. /category Tax")
        return
    rows = db.query(
        "SELECT * FROM documents WHERE category LIKE ? ORDER BY id DESC LIMIT 30",
        (f"%{cat}%",),
    )
    if not rows:
        await update.message.reply_text(f"No documents in category “{cat}”.")
        return
    await update.message.reply_text(
        f"📁 {cat}:\n\n{_format_rows(rows)}\n\nUse /getfile <id> to download."
    )


@restricted
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM documents ORDER BY id DESC LIMIT 10")
    if not rows:
        await update.message.reply_text("No documents saved yet. Use /save to add one.")
        return
    await update.message.reply_text(f"🕑 Recent uploads:\n\n{_format_rows(rows)}")


@restricted
async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /getfile <id>")
        return
    row = db.query_one("SELECT * FROM documents WHERE id = ?", (context.args[0],))
    if not row:
        await update.message.reply_text("No document with that id.")
        return
    # Re-send the original Telegram file by its file_id (fast, no re-upload).
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=row["file_id"],
        caption=f"{row['original_filename']} • {row['category']}",
    )


@restricted
async def deletefile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM documents ORDER BY id DESC LIMIT 10")
    if not rows:
        await update.message.reply_text("Nothing to delete.")
        return
    buttons = [
        [InlineKeyboardButton(f"🗑 #{r['id']} {r['original_filename'][:30]}",
                              callback_data=f"deldoc:{r['id']}")]
        for r in rows
    ]
    await update.message.reply_text(
        "Select a document to delete:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    doc_id = query.data.split(":", 1)[1]
    row = db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not row:
        await query.edit_message_text("Already gone.")
        return
    buttons = [[
        InlineKeyboardButton("✅ Yes, delete", callback_data=f"deldocyes:{doc_id}"),
        InlineKeyboardButton("Cancel", callback_data="deldocno"),
    ]]
    await query.edit_message_text(
        f"Delete “{row['original_filename']}”? This removes the file and its record.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "deldocno":
        await query.edit_message_text("Cancelled.")
        return
    doc_id = query.data.split(":", 1)[1]
    row = db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if row:
        storage.delete(row["file_path"])
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await query.edit_message_text("🗑 Deleted.")


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("save", save_start)],
        states={
            FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, receive_file)],
            CATEGORY: [CallbackQueryHandler(choose_category, pattern=r"^doccat:")],
            CUSTOM_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_category)],
            DESC: [
                CommandHandler("skip", skip_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, with_description),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return [
        conv,
        CommandHandler("find", find),
        CommandHandler("category", by_category),
        CommandHandler("recent", recent),
        CommandHandler("getfile", getfile),
        CommandHandler("deletefile", deletefile),
        CallbackQueryHandler(delete_pick, pattern=r"^deldoc:"),
        CallbackQueryHandler(delete_confirm, pattern=r"^(deldocyes:|deldocno$)"),
    ]
