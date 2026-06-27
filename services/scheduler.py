"""
Scheduler wiring.

python-telegram-bot ships a JobQueue (backed by APScheduler), so we don't need
an extra dependency. We simply ask it to run the reminder checker every minute.
The actual checking logic lives in modules/reminders.py.
"""

from telegram.ext import Application

from modules.reminders import check_due_reminders


def setup_scheduler(application: Application) -> None:
    job_queue = application.job_queue
    # Run 10 seconds after startup, then every 60 seconds.
    job_queue.run_repeating(check_due_reminders, interval=60, first=10)
