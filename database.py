"""
Database access layer.

This is intentionally a thin wrapper around sqlite3. The whole rest of the app
only calls `db.execute(...)`, `db.query(...)`, and `db.query_one(...)`, so when
you later move to PostgreSQL you only have to reimplement this class (e.g. with
psycopg) and keep the same method names.

A fresh connection is opened per call. That is simple and safe to use from the
bot's async handlers *and* from the background scheduler thread, which is what
matters most for a small personal bot.
"""

import sqlite3
from typing import Any, Iterable, Optional

from config import SQLITE_PATH


class Database:
    def __init__(self, path: str):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row  # rows behave like dicts: row["column"]
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run an INSERT/UPDATE/DELETE. Returns the new row id (for inserts)."""
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            return cur.lastrowid

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        """Run a SELECT and return all rows."""
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        """Run a SELECT and return the first row (or None)."""
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchone()


# Single shared instance used everywhere.
db = Database(SQLITE_PATH)


def init_db() -> None:
    """Create all tables if they do not already exist. Safe to run repeatedly."""
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id           TEXT,
                original_filename TEXT,
                saved_filename    TEXT,
                category          TEXT,
                tags              TEXT,
                description       TEXT,
                upload_date       TEXT,
                file_path         TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                remind_at    TEXT,            -- ISO 'YYYY-MM-DDTHH:MM:SS'
                text         TEXT,
                rtype        TEXT,            -- one-time | expiry | appointment
                status       TEXT,            -- pending | done
                alerts       TEXT,            -- JSON list of minutes-before, e.g. [0]
                alerts_sent  TEXT,            -- JSON list of offsets already fired
                created_date TEXT
            );

            CREATE TABLE IF NOT EXISTS books (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id        TEXT,
                title          TEXT,
                author         TEXT,
                category       TEXT,
                tags           TEXT,
                status         TEXT,          -- unread | reading | finished
                notes          TEXT,
                saved_filename TEXT,
                file_path      TEXT,
                upload_date    TEXT
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                amount       REAL,
                merchant     TEXT,
                category     TEXT,
                date         TEXT,            -- 'YYYY-MM-DD'
                notes        TEXT,
                receipt_path TEXT,
                created_date TEXT
            );

            CREATE TABLE IF NOT EXISTS legal_evidence (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                title          TEXT,
                category       TEXT,
                tags           TEXT,
                related_date   TEXT,
                description    TEXT,
                saved_filename TEXT,
                file_path      TEXT,
                upload_date    TEXT
            );

            CREATE TABLE IF NOT EXISTS legal_timeline (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date   TEXT,
                description  TEXT,
                created_date TEXT
            );

            CREATE TABLE IF NOT EXISTS legal_witness (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT,
                notes        TEXT,
                created_date TEXT
            );

            CREATE TABLE IF NOT EXISTS music (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id        TEXT,
                title          TEXT,
                artist         TEXT,
                mood           TEXT,
                tags           TEXT,
                saved_filename TEXT,
                file_path      TEXT,
                upload_date    TEXT
            );

            CREATE TABLE IF NOT EXISTS notes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT,
                content      TEXT,
                tags         TEXT,
                category     TEXT,
                created_date TEXT
            );
            """
        )
        conn.commit()
