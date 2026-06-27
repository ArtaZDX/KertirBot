"""
Reminder system.

Commands:
  /remind 2026-08-12 18:30 Flight to Tehran   -> one-time, single alert
  /remindimportant 2026-08-12 18:30 Hearing   -> alerts 1 week / 1 day / 2h / on time
  /expiry 2026-09-01 Passport expires         -> date only (09:00), alerts 1w / 1d / on day
  /today        list today's pending reminders
  /week         list the next 7 days
  /done         mark a reminder complete
  /deletereminder  delete a reminder

A background job (services/scheduler.py) calls `check_due_reminders` every
minute and sends a message for each alert that has come due.
"""

import json
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import ALLOWED_USER_ID
from database import db
from services.security import restricted

# Alert offsets in minutes-before-the-event.
ALERTS_SINGLE = [0]
ALERTS_IMPORTANT = [10080, 1440, 120, 0]  # 1 week, 1 day, 2 hours, on time
ALERTS_EXPIRY = [10080, 1440, 0]          # 1 week, 1 day, on the day


def _parse(date_s: str, time_s: str) -> datetime:
    return datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")


def _create(remind_at: datetime, text: str, rtype: str, alerts: list[int]) -> int:
    return db.execute(
        """INSERT INTO reminders
           (remind_at, text, rtype, status, alerts, alerts_sent, created_date)
           VALUES (?,?,?,?,?,?,?)""",
        (
            remind_at.isoformat(timespec="seconds"),
            text,
            rtype,
            "pending",
            json.dumps(alerts),
            json.dumps([]),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


@restricted
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /remind YYYY-MM-DD HH:MM <text>\n"
            "Example: /remind 2026-08-12 18:30 Flight to Tehran"
        )
        return
    try:
        when = _parse(args[0], args[1])
    except ValueError:
        await update.message.reply_text("Could not read the date/time. Use YYYY-MM-DD HH:MM.")
        return
    text = " ".join(args[2:])
    rid = _create(when, text, "one-time", ALERTS_SINGLE)
    await update.message.reply_text(f"⏰ Reminder #{rid} set for {when:%Y-%m-%d %H:%M}.")


@restricted
async def remind_important(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /remindimportant YYYY-MM-DD HH:MM <text>\n"
            "Alerts at 1 week, 1 day, 2 hours before, and on time."
        )
        return
    try:
        when = _parse(args[0], args[1])
    except ValueError:
        await update.message.reply_text("Could not read the date/time. Use YYYY-MM-DD HH:MM.")
        return
    text = " ".join(args[2:])
    rid = _create(when, text, "appointment", ALERTS_IMPORTANT)
    await update.message.reply_text(
        f"⏰ Important reminder #{rid} set for {when:%Y-%m-%d %H:%M} "
        "(alerts 1w / 1d / 2h / on time)."
    )


@restricted
async def expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /expiry YYYY-MM-DD <text>\n"
            "Example: /expiry 2027-03-10 Passport expires"
        )
        return
    try:
        when = _parse(args[0], "09:00")
    except ValueError:
        await update.message.reply_text("Could not read the date. Use YYYY-MM-DD.")
        return
    text = " ".join(args[1:])
    rid = _create(when, text, "expiry", ALERTS_EXPIRY)
    await update.message.reply_text(
        f"📅 Expiry reminder #{rid} set for {when:%Y-%m-%d} (alerts 1 week / 1 day / on the day)."
    )


def _list(rows) -> str:
    icons = {"one-time": "⏰", "appointment": "📌", "expiry": "📅"}
    return "\n".join(
        f"{icons.get(r['rtype'], '•')} #{r['id']} {datetime.fromisoformat(r['remind_at']):%Y-%m-%d %H:%M}"
        f" — {r['text']}"
        for r in rows
    )


@restricted
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = db.query(
        "SELECT * FROM reminders WHERE status='pending' AND remind_at >= ? AND remind_at < ? "
        "ORDER BY remind_at",
        (start.isoformat(), end.isoformat()),
    )
    await update.message.reply_text(
        "📅 Today:\n\n" + _list(rows) if rows else "Nothing scheduled for today."
    )


@restricted
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    end = now + timedelta(days=7)
    rows = db.query(
        "SELECT * FROM reminders WHERE status='pending' AND remind_at >= ? AND remind_at < ? "
        "ORDER BY remind_at",
        (now.isoformat(), end.isoformat()),
    )
    await update.message.reply_text(
        "🗓 Next 7 days:\n\n" + _list(rows) if rows else "Nothing in the next 7 days."
    )


@restricted
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query(
        "SELECT * FROM reminders WHERE status='pending' ORDER BY remind_at LIMIT 15"
    )
    if not rows:
        await update.message.reply_text("No pending reminders.")
        return
    buttons = [
        [InlineKeyboardButton(f"✅ #{r['id']} {r['text'][:30]}", callback_data=f"remdone:{r['id']}")]
        for r in rows
    ]
    await update.message.reply_text(
        "Mark as done:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def done_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rid = query.data.split(":", 1)[1]
    db.execute("UPDATE reminders SET status='done' WHERE id = ?", (rid,))
    await query.edit_message_text("✅ Marked as done.")


@restricted
async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.query(
        "SELECT * FROM reminders WHERE status='pending' ORDER BY remind_at LIMIT 15"
    )
    if not rows:
        await update.message.reply_text("No pending reminders.")
        return
    buttons = [
        [InlineKeyboardButton(f"🗑 #{r['id']} {r['text'][:30]}", callback_data=f"remdel:{r['id']}")]
        for r in rows
    ]
    await update.message.reply_text(
        "Delete which reminder?", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rid = query.data.split(":", 1)[1]
    db.execute("DELETE FROM reminders WHERE id = ?", (rid,))
    await query.edit_message_text("🗑 Reminder deleted.")


def _offset_label(minutes: int) -> str:
    if minutes == 0:
        return "now"
    if minutes % 10080 == 0:
        return f"in {minutes // 10080} week(s)"
    if minutes % 1440 == 0:
        return f"in {minutes // 1440} day(s)"
    if minutes % 60 == 0:
        return f"in {minutes // 60} hour(s)"
    return f"in {minutes} minute(s)"


async def check_due_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called every minute by the job queue. Sends any alerts that are due."""
    now = datetime.now()
    rows = db.query("SELECT * FROM reminders WHERE status = 'pending'")
    for r in rows:
        remind_at = datetime.fromisoformat(r["remind_at"])
        alerts = json.loads(r["alerts"] or "[0]")
        sent = set(json.loads(r["alerts_sent"] or "[]"))
        changed = False
        for offset in alerts:
            if offset in sent:
                continue
            alert_time = remind_at - timedelta(minutes=offset)
            if alert_time <= now:
                when_txt = _offset_label(offset) if offset else "now"
                await context.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=(
                        f"🔔 Reminder ({r['rtype']}) — due {when_txt}:\n\n"
                        f"{r['text']}\n🕑 {remind_at:%Y-%m-%d %H:%M}"
                    ),
                )
                sent.add(offset)
                changed = True
        if changed:
            db.execute(
                "UPDATE reminders SET alerts_sent = ? WHERE id = ?",
                (json.dumps(sorted(sent)), r["id"]),
            )


def get_handlers() -> list:
    return [
        CommandHandler("remind", remind),
        CommandHandler("remindimportant", remind_important),
        CommandHandler("expiry", expiry),
        CommandHandler("today", today),
        CommandHandler("week", week),
        CommandHandler("done", done),
        CommandHandler("deletereminder", delete_reminder),
        CallbackQueryHandler(done_pick, pattern=r"^remdone:"),
        CallbackQueryHandler(delete_pick, pattern=r"^remdel:"),
    ]
