"""
Receipt & expense tracker.

  /expense 12.50 Tesco food      quick add (amount, then merchant/notes)
  /receipt                       add an expense with a receipt photo (guided)
  /expenses June 2026            list expenses for a month
  /total June 2026               total for a month
  /export expenses               export everything to a CSV file
"""

import csv
import io
from datetime import datetime

from telegram import Update
from telegram.ext import (
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

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# Conversation states for /receipt
R_PHOTO, R_AMOUNT, R_MERCHANT = range(3)


def _month_range(args) -> tuple[str, str, str] | None:
    """Parse 'June 2026' -> ('2026-06-01', '2026-07-01', 'June 2026')."""
    if len(args) < 2:
        return None
    month = MONTHS.get(args[0].lower())
    if not month:
        return None
    try:
        year = int(args[1])
    except ValueError:
        return None
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), f"{args[0].title()} {year}"


@restricted
async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /expense <amount> <merchant / notes>\n"
            "Example: /expense 12.50 Tesco food\n"
            "To attach a receipt photo use /receipt."
        )
        return
    try:
        amount = float(args[0])
    except ValueError:
        await update.message.reply_text("The first value should be the amount, e.g. 12.50.")
        return
    rest = " ".join(args[1:]).strip()
    merchant = rest.split(" ", 1)[0] if rest else "Unknown"
    notes = rest
    db.execute(
        """INSERT INTO expenses
           (amount, merchant, category, date, notes, receipt_path, created_date)
           VALUES (?,?,?,?,?,?,?)""",
        (
            amount, merchant, "General", datetime.now().strftime("%Y-%m-%d"),
            notes, "", datetime.now().isoformat(timespec="seconds"),
        ),
    )
    await update.message.reply_text(f"💷 Logged £{amount:.2f} at {merchant}.")


# --- /receipt guided flow ---------------------------------------------------
@restricted
async def receipt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧾 Send the receipt photo (or /cancel).")
    return R_PHOTO


async def receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        file_id = msg.photo[-1].file_id
        original = f"receipt_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    elif msg.document:
        if exceeds_download_limit(msg.document.file_size):
            await msg.reply_text(TOO_BIG_MESSAGE)
            return ConversationHandler.END
        file_id = msg.document.file_id
        original = msg.document.file_name or "receipt"
    else:
        await msg.reply_text("Please send a photo or file.")
        return R_PHOTO
    data = await download_telegram_file(context.bot, file_id)
    saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_filename(original)}"
    context.user_data["receipt_path"] = storage.save(data, "Receipts", saved_name)
    await msg.reply_text("Amount? e.g. 12.50")
    return R_AMOUNT


async def receipt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["receipt_amount"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please send a number, e.g. 12.50")
        return R_AMOUNT
    await update.message.reply_text("Merchant / notes?")
    return R_MERCHANT


async def receipt_merchant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes = update.message.text.strip()
    merchant = notes.split(" ", 1)[0] if notes else "Unknown"
    db.execute(
        """INSERT INTO expenses
           (amount, merchant, category, date, notes, receipt_path, created_date)
           VALUES (?,?,?,?,?,?,?)""",
        (
            context.user_data.get("receipt_amount", 0.0), merchant, "General",
            datetime.now().strftime("%Y-%m-%d"), notes,
            context.user_data.get("receipt_path", ""),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    context.user_data.pop("receipt_path", None)
    context.user_data.pop("receipt_amount", None)
    await update.message.reply_text("🧾 Receipt and expense saved.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


@restricted
async def expenses_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rng = _month_range(context.args)
    if not rng:
        await update.message.reply_text("Usage: /expenses <Month> <Year>  e.g. /expenses June 2026")
        return
    start, end, label = rng
    rows = db.query(
        "SELECT * FROM expenses WHERE date >= ? AND date < ? ORDER BY date",
        (start, end),
    )
    if not rows:
        await update.message.reply_text(f"No expenses in {label}.")
        return
    lines = [f"£{r['amount']:.2f} • {r['merchant']} • {r['date']}" for r in rows]
    total = sum(r["amount"] for r in rows)
    await update.message.reply_text(
        f"🧾 {label}:\n\n" + "\n".join(lines) + f"\n\nTotal: £{total:.2f}"
    )


@restricted
async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rng = _month_range(context.args)
    if not rng:
        await update.message.reply_text("Usage: /total <Month> <Year>  e.g. /total June 2026")
        return
    start, end, label = rng
    row = db.query_one(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE date >= ? AND date < ?",
        (start, end),
    )
    await update.message.reply_text(f"💷 Total for {label}: £{row['s']:.2f}")


@restricted
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /export expenses  (the word 'expenses' is accepted for clarity)
    rows = db.query("SELECT * FROM expenses ORDER BY date")
    if not rows:
        await update.message.reply_text("No expenses to export.")
        return
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "amount", "merchant", "category", "date", "notes"])
    for r in rows:
        writer.writerow([r["id"], r["amount"], r["merchant"], r["category"], r["date"], r["notes"]])
    data = buffer.getvalue().encode("utf-8")
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=io.BytesIO(data),
        filename=f"expenses_{datetime.now():%Y%m%d}.csv",
        caption=f"{len(rows)} expenses exported.",
    )


def get_handlers() -> list:
    receipt_conv = ConversationHandler(
        entry_points=[CommandHandler("receipt", receipt_start)],
        states={
            R_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_photo)],
            R_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receipt_amount)],
            R_MERCHANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receipt_merchant)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    return [
        receipt_conv,
        CommandHandler("expense", expense),
        CommandHandler("expenses", expenses_list),
        CommandHandler("total", total),
        CommandHandler("export", export),
    ]
