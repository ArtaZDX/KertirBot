"""
Security helpers.

  * `is_allowed` / `restricted` enforce the single-user allowlist.
  * `safe_filename` strips anything that could be used for path traversal or
    that is unsafe on Windows/Linux filesystems.
"""

import functools
import re
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import ALLOWED_USER_ID

# Characters we allow in a stored filename. Everything else is removed.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def is_allowed(user_id: int) -> bool:
    """True only for the configured owner. If ALLOWED_USER_ID is 0, nobody passes."""
    return ALLOWED_USER_ID != 0 and user_id == ALLOWED_USER_ID


def restricted(func):
    """
    Decorator for command/message handlers. Blocks anyone who is not the owner.

    Returning None from a ConversationHandler entry point means the conversation
    is simply not started, so unauthorised users can never enter a flow.
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user is None or not is_allowed(user.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ This is a private bot and you are not on its allowlist."
                )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper


def safe_filename(name: str) -> str:
    """
    Turn an arbitrary (possibly hostile) filename into something safe to store.

    Removes directory components, spaces, and unusual characters. The result can
    never contain '/', '\\', or '..', so it cannot escape its target folder.
    """
    name = Path(name).name              # drop any path part like ../../etc/passwd
    name = name.replace(" ", "_")
    name = _UNSAFE.sub("", name)
    name = name.strip("._")
    return (name or "file")[:120]
