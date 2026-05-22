"""SQLite database connection and lazy initialization for FinAlly."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10000.0
DEFAULT_WATCHLIST = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_initialized = False


def get_db_path() -> Path:
    """Resolve the SQLite file path.

    Honors FINALLY_DB_PATH for tests; otherwise uses <project_root>/db/finally.db
    where <project_root> is the parent of the backend/ directory.
    """
    override = os.getenv("FINALLY_DB_PATH")
    if override:
        return Path(override)
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "db" / "finally.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _is_empty(conn: aiosqlite.Connection) -> bool:
    """Return True if the users_profile table is empty (or missing)."""
    try:
        async with conn.execute("SELECT COUNT(*) FROM users_profile") as cur:
            row = await cur.fetchone()
            return (row[0] if row else 0) == 0
    except aiosqlite.OperationalError:
        return True


async def _apply_schema(conn: aiosqlite.Connection) -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    await conn.executescript(sql)


async def _seed(conn: aiosqlite.Connection) -> None:
    now = _utcnow()
    await conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
    )
    for ticker in DEFAULT_WATCHLIST:
        await conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now),
        )


async def init_db() -> None:
    """Create the schema and seed default data if the database is fresh.

    Idempotent: safe to call multiple times. Runs at most once per process.
    """
    global _initialized
    if _initialized:
        return
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await _apply_schema(conn)
        if await _is_empty(conn):
            await _seed(conn)
        await conn.commit()
    _initialized = True


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI dependency that yields an aiosqlite connection.

    Ensures the schema is initialized on first use, returns rows as Row objects,
    and commits on success.
    """
    await init_db()
    conn = await aiosqlite.connect(get_db_path())
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        await conn.commit()
    finally:
        await conn.close()


async def close_db() -> None:
    """Reset the initialization flag (for tests)."""
    global _initialized
    _initialized = False
