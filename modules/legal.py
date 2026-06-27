"""
Legal / Employment Tribunal archive.

  /legaladd                       guided: file -> category -> title -> tags -> date
  /legalfind <keyword>            search evidence, timeline, and witnesses
  /timelineadd 2024-03-15 text    add a dated event to the timeline
  /timeline                       show the full timeline (chronological)
  /witness Gerry                  show notes for a witness
  /witness Gerry <note...>        add a note for that witness
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
    "Contract", "Overtime", "Payslips", "Witnesses", "Emails",
    "ACAS", "Discrimination", "Hearing preparation", "Other",
]

E_FILE, E_CATEGORY, E_TITLE, E_TAGS, E_DATE = range(5)


@restricted
async def legal_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚖️ Send the evidence file or photo. /cancel to stop."
    )
    return E_FILE


async def receive_evidence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        if exceeds_download_limit(msg.document.file_size):
            await msg.reply_text(TOO_BIG_MESSAGE)
            return ConversationHandler.END
        file_id = msg.document.file_id
        original = msg.document.file_name or f"evidence_{file_id[:8]}"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        original = f"evidence_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    else:
        await msg.reply_text("Please send a file or photo.")
        return E_FILE
    context.user_data["ev"] = {"file_id": file_id, "original": original}
    buttons = [
        [InlineKeyboardButton(c, callback_data=f"legcat:{i}")]
        for i, c in enumerate(CATEGORIES)
    ]
    await msg.reply_text("Category:", reply_markup=InlineKeyboardMarkup(buttons))
    return E_CATEGORY


async def evidence_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split(":", 1)[1])
    context.user_data["ev"]["category"] = CATEGORIES[idx]
    await query.edit_message_text(f"Category: {CATEGORIES[idx]}\n\nShort title for this evidence?")
    return E_TITLE


async def evidence_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ev"]["title"] = update.message.text.strip()
    await update.message.reply_text("Tags? (or /skip)")
    return E_TAGS


async def evidence_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ev"]["tags"] = update.message.text.strip()
    await update.message.reply_text("Related date YYYY-MM-DD? (or /skip)")
    return E_DATE


async def evidence_tags_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ev"]["tags"] = ""
    await update.message.reply_text("Related date YYYY-MM-DD? (or /skip)")
    return E_DATE


async def evidence_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ev"]["related_date"] = update.message.text.strip()
    return await _save_evidence(update, context)


async def evidence_date_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ev"]["related_date"] = ""
    return await _save_evidence(update, context)


async def _save_evidence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ev = context.user_data.get("ev", {})
    data = await download_telegram_file(context.bot, ev["file_id"])
    saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_filename(ev['original'])}"
    path = storage.save(data, f"Legal/{ev.get('category', 'Other')}", saved_name)
    db.execute(
        """INSERT INTO legal_evidence
           (title, category, tags, related_date, description, saved_filename,
            file_path, upload_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            ev.get("title", ev["original"]), ev.get("category", "Other"),
            ev.get("tags", ""), ev.get("related_date", ""), "",
            saved_name, path, datetime.now().isoformat(timespec="seconds"),
        ),
    )
    context.user_data.pop("ev", None)
    await update.message.reply_text("✅ Evidence archived.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("ev", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


@restricted
async def legal_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = " ".join(context.args).strip()
    if not kw:
        await update.message.reply_text("Usage: /legalfind <keyword>")
        return
    like = f"%{kw}%"
    ev = db.query(
        "SELECT * FROM legal_evidence WHERE title LIKE ? OR category LIKE ? OR tags LIKE ? "
        "ORDER BY id DESC",
        (like, like, like),
    )
    tl = db.query(
        "SELECT * FROM legal_timeline WHERE description LIKE ? ORDER BY event_date", (like,)
    )
    wt = db.query("SELECT * FROM legal_witness WHERE name LIKE ? OR notes LIKE ?", (like, like))
    parts = []
    if ev:
        parts.append("📎 Evidence:\n" + "\n".join(
            f"  #{r['id']} {r['title']} ({r['category']})" for r in ev))
    if tl:
        parts.append("📜 Timeline:\n" + "\n".join(
            f"  {r['event_date']}: {r['description']}" for r in tl))
    if wt:
        parts.append("👤 Witnesses:\n" + "\n".join(
            f"  {r['name']}: {r['notes']}" for r in wt))
    await update.message.reply_text(
        "\n\n".join(parts) if parts else f"Nothing found for “{kw}”."
    )


@restricted
async def timeline_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /timelineadd YYYY-MM-DD <what happened>\n"
            "Example: /timelineadd 2024-03-15 Requested entry card"
        )
        return
    try:
        datetime.strptime(args[0], "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("First value must be a date: YYYY-MM-DD.")
        return
    db.execute(
        "INSERT INTO legal_timeline (event_date, description, created_date) VALUES (?,?,?)",
        (args[0], " ".join(args[1:]), datetime.now().isoformat(timespec="seconds")),
    )
    await update.message.reply_text("📜 Timeline event added.")


@restricted
async def timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query("SELECT * FROM legal_timeline ORDER BY event_date")
    if not rows:
        await update.message.reply_text("Timeline is empty. Add events with /timelineadd.")
        return
    await update.message.reply_text(
        "📜 Timeline:\n\n" + "\n".join(f"{r['event_date']}: {r['description']}" for r in rows)
    )


@restricted
async def witness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage:\n  /witness <name>           show notes\n"
            "  /witness <name> <note...>  add a note"
        )
        return
    name = args[0]
    if len(args) == 1:
        rows = db.query("SELECT * FROM legal_witness WHERE name LIKE ? ORDER BY id", (name,))
        if not rows:
            await update.message.reply_text(f"No notes for witness “{name}”.")
            return
        await update.message.reply_text(
            f"👤 {name}:\n\n" + "\n".join(f"• {r['notes']}" for r in rows)
        )
        return
    note = " ".join(args[1:])
    db.execute(
        "INSERT INTO legal_witness (name, notes, created_date) VALUES (?,?,?)",
        (name, note, datetime.now().isoformat(timespec="seconds")),
    )
    await update.message.reply_text(f"👤 Note added for witness {name}.")


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("legaladd", legal_add)],
        states={
            E_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, receive_evidence)],
            E_CATEGORY: [CallbackQueryHandler(evidence_category, pattern=r"^legcat:")],
            E_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, evidence_title)],
            E_TAGS: [
                CommandHandler("skip", evidence_tags_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, evidence_tags),
            ],
            E_DATE: [
                CommandHandler("skip", evidence_date_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, evidence_date),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return [
        conv,
        CommandHandler("legalfind", legal_find),
        CommandHandler("timelineadd", timeline_add),
        CommandHandler("timeline", timeline),
        CommandHandler("witness", witness),
    ]
