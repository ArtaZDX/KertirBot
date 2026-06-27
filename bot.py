"""
Personal Telegram Bot — entry point.

Run with:  python bot.py

This file wires everything together:
  * validates configuration (token + your user id),
  * creates the database tables,
  * registers every module's handlers,
  * builds the main menu,
  * starts the reminder scheduler,
  * starts polling for messages.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
from database import init_db
from services.scheduler import setup_scheduler
from services.security import restricted

# Modules
from modules import backup, books, documents, expenses, legal, music, notes, reminders

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("personal_bot")


# --- Main menu --------------------------------------------------------------
MENU = [
    ("📁 Documents", "menu:docs"),
    ("📅 Reminders", "menu:rem"),
    ("📚 Books", "menu:books"),
    ("🧾 Expenses", "menu:exp"),
    ("⚖️ Legal Archive", "menu:legal"),
    ("🎵 Music", "menu:music"),
    ("📝 Notes", "menu:notes"),
    ("⚙️ Settings", "menu:settings"),
]

MENU_HELP = {
    "menu:docs": (
        "📁 *Documents*\n"
        "/save — store a document or photo\n"
        "/find <kw> — search\n"
        "/category <name> — list a category\n"
        "/recent — latest uploads\n"
        "/getfile <id> — download\n"
        "/deletefile — delete one"
    ),
    "menu:rem": (
        "📅 *Reminders*\n"
        "/remind YYYY-MM-DD HH:MM <text>\n"
        "/remindimportant … — 1w/1d/2h/on-time alerts\n"
        "/expiry YYYY-MM-DD <text> — passport/visa/MOT etc.\n"
        "/today  /week\n"
        "/done  /deletereminder"
    ),
    "menu:books": (
        "📚 *Books*\n"
        "/bookadd — add a book file\n"
        "/books — list all\n"
        "/booksearch <kw>\n"
        "/reading  /finished\n"
        "/booknote — set status + note\n"
        "/getbook <id> — download\n"
        "/booksync — export all books to Obsidian"
    ),
    "menu:exp": (
        "🧾 *Expenses*\n"
        "/expense 12.50 Tesco food — quick add\n"
        "/receipt — add with a photo\n"
        "/expenses June 2026 — list a month\n"
        "/total June 2026\n"
        "/export expenses — CSV"
    ),
    "menu:legal": (
        "⚖️ *Legal Archive*\n"
        "/legaladd — archive evidence\n"
        "/legalfind <kw>\n"
        "/timelineadd YYYY-MM-DD <event>\n"
        "/timeline\n"
        "/witness <name> [note]"
    ),
    "menu:music": (
        "🎵 *Music*\n"
        "/musicadd — add an audio file\n"
        "/musicsearch <kw>\n"
        "/playlist <mood>\n"
        "/getmusic <id>\n"
        "send a YouTube link (or /mp3 <url>) → MP3 to your channel"
    ),
    "menu:notes": (
        "📝 *Notes*\n"
        "/note <text>\n"
        "/notes <kw> — search (blank = recent)\n"
        "/getnote <id>\n"
        "/randomnote\n"
        "/deletenote"
    ),
    "menu:settings": (
        "⚙️ *Settings*\n"
        "/backup — zip the database + files\n"
        "/help — show this menu again\n\n"
        "This bot is private: only your Telegram ID can use it."
    ),
}


def _menu_markup() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in MENU]
    return InlineKeyboardMarkup(rows)


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to your personal vault.\nPick a section:",
        reply_markup=_menu_markup(),
    )


@restricted
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main menu:", reply_markup=_menu_markup())


async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = MENU_HELP.get(query.data, "Unknown section.")
    back = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu:back")]])
    if query.data == "menu:back":
        await query.edit_message_text("Main menu:", reply_markup=_menu_markup())
    else:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Handler error", exc_info=context.error)


def main() -> None:
    config.validate()
    init_db()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # General commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", menu))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CallbackQueryHandler(menu_click, pattern=r"^menu:"))

    # Feature modules
    for module in (documents, reminders, books, expenses, legal, music, notes, backup):
        for handler in module.get_handlers():
            application.add_handler(handler)

    application.add_error_handler(on_error)

    setup_scheduler(application)

    logger.info("Bot starting. Allowed user id: %s", config.ALLOWED_USER_ID)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
