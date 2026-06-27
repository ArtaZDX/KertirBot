"""
Storage abstraction.

v1 saves files to local disk, organised into one sub-folder per category.

The rest of the app only uses the `storage` object's methods (save / delete),
so to add Google Drive, Dropbox, or S3 later you create a new class with the
same methods and swap which one is instantiated at the bottom of this file.
The metadata (file paths) lives in the database, so a future backend could
store a URL or object key in `file_path` instead of a local path.
"""

from pathlib import Path

from config import STORAGE_PATH
from services.security import safe_filename

# Telegram's Bot API only lets bots download files up to 20 MB via getFile.
# Anything larger raises "File is too big". We check message file sizes against
# this so we can warn the user immediately instead of failing at save time.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

TOO_BIG_MESSAGE = (
    "⚠️ That file is larger than 20 MB, which is the maximum a Telegram bot is "
    "allowed to download. Please send a smaller or compressed file.\n\n"
    "(Raising this limit requires running a self-hosted Telegram Bot API server — "
    "noted as a v2 option in the README.)"
)


def exceeds_download_limit(file_size) -> bool:
    """True if a Telegram file (by its reported size) is too big to download."""
    return bool(file_size and file_size > MAX_DOWNLOAD_BYTES)


class StorageBackend:
    """Interface that every storage backend must implement."""

    def save(self, data: bytes, subfolder: str, filename: str) -> str:
        raise NotImplementedError

    def delete(self, stored_path: str) -> bool:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, base: str):
        self.base = Path(base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _target(self, subfolder: str, filename: str) -> Path:
        # Both the sub-folder and the filename are sanitised, so the resolved
        # path can never climb above self.base (no path traversal).
        safe_sub = safe_filename(subfolder) if subfolder else ""
        safe_name = safe_filename(filename)
        target = (self.base / safe_sub / safe_name).resolve()
        if self.base != target and self.base not in target.parents:
            raise ValueError("Refusing to write outside the storage directory.")
        return target

    def save(self, data: bytes, subfolder: str, filename: str) -> str:
        target = self._target(subfolder, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        return str(target)

    def delete(self, stored_path: str) -> bool:
        if not stored_path:
            return False
        p = Path(stored_path).resolve()
        if (self.base == p or self.base in p.parents) and p.exists():
            p.unlink()
            return True
        return False


# The single backend the whole app uses. Swap this line to change backends.
storage: StorageBackend = LocalStorage(STORAGE_PATH)


async def download_telegram_file(bot, file_id: str) -> bytes:
    """Download a file the user sent us and return its raw bytes."""
    tg_file = await bot.get_file(file_id)
    data = await tg_file.download_as_bytearray()
    return bytes(data)
