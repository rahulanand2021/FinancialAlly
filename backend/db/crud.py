"""Async CRUD helpers for FinAlly.

All functions take an aiosqlite.Connection (typically yielded by get_db()).
The caller owns the connection lifecycle; these helpers do not commit.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import aiosqlite

from .database import DEFAULT_USER_ID

SNAPSHOT_RETENTION_DAYS = 7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# --- users_profile -----------------------------------------------------------

async def get_cash_balance(conn: aiosqlite.Connection, user_id: str = DEFAULT_USER_ID) -> float:
    async with conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return float(row["cash_balance"]) if row else 0.0


async def set_cash_balance(
    conn: aiosqlite.Connection, balance: float, user_id: str = DEFAULT_USER_ID
) -> None:
    await conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (balance, user_id),
    )


# --- watchlist ---------------------------------------------------------------

async def list_watchlist(
    conn: aiosqlite.Connection, user_id: str = DEFAULT_USER_ID
) -> list[str]:
    async with conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (user_id,),
    ) as cur:
        return [row["ticker"] for row in await cur.fetchall()]


async def add_watchlist_ticker(
    conn: aiosqlite.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Add ticker to the watchlist. Returns True if newly added, False if it already existed."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, ticker.upper(), _utcnow()),
    )
    return cur.rowcount > 0


async def remove_watchlist_ticker(
    conn: aiosqlite.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Remove ticker from the watchlist. Returns True if a row was deleted."""
    cur = await conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    )
    return cur.rowcount > 0


# --- positions ---------------------------------------------------------------

async def list_positions(
    conn: aiosqlite.Connection, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_position(
    conn: aiosqlite.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any] | None:
    async with conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_position(
    conn: aiosqlite.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Insert or update a position row. Caller computes the new avg_cost."""
    await conn.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (_new_id(), user_id, ticker.upper(), quantity, avg_cost, _utcnow()),
    )


async def delete_position(
    conn: aiosqlite.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> None:
    await conn.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker.upper()),
    )


# --- trades ------------------------------------------------------------------

async def insert_trade(
    conn: aiosqlite.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Record a trade. Returns the inserted row as a dict."""
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    trade_id = _new_id()
    executed_at = _utcnow()
    await conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade_id, user_id, ticker.upper(), side, quantity, price, executed_at),
    )
    return {
        "id": trade_id,
        "user_id": user_id,
        "ticker": ticker.upper(),
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": executed_at,
    }


async def list_trades(
    conn: aiosqlite.Connection,
    limit: int | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, ticker, side, quantity, price, executed_at FROM trades "
        "WHERE user_id = ? ORDER BY executed_at DESC"
    )
    params: tuple[Any, ...] = (user_id,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (user_id, limit)
    async with conn.execute(sql, params) as cur:
        return [dict(row) for row in await cur.fetchall()]


# --- portfolio_snapshots -----------------------------------------------------

async def insert_portfolio_snapshot(
    conn: aiosqlite.Connection, total_value: float, user_id: str = DEFAULT_USER_ID
) -> None:
    """Insert a snapshot and prune records older than SNAPSHOT_RETENTION_DAYS."""
    await conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, total_value, _utcnow()),
    )
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS)).isoformat()
    await conn.execute(
        "DELETE FROM portfolio_snapshots WHERE user_id = ? AND recorded_at < ?",
        (user_id, cutoff),
    )


async def list_portfolio_snapshots(
    conn: aiosqlite.Connection,
    since: datetime | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, Any]]:
    """Return snapshots ordered oldest -> newest. Defaults to the last 24 hours."""
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
    async with conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ? AND recorded_at >= ? ORDER BY recorded_at",
        (user_id, since.isoformat()),
    ) as cur:
        return [
            {"timestamp": row["recorded_at"], "total_value": row["total_value"]}
            for row in await cur.fetchall()
        ]


# --- chat_messages -----------------------------------------------------------

async def insert_chat_message(
    conn: aiosqlite.Connection,
    role: str,
    content: str,
    actions: dict[str, Any] | list[Any] | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    if role not in ("user", "assistant"):
        raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
    message_id = _new_id()
    created_at = _utcnow()
    actions_json = json.dumps(actions) if actions is not None else None
    await conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, user_id, role, content, actions_json, created_at),
    )
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": created_at,
    }


async def list_recent_chat_messages(
    conn: aiosqlite.Connection,
    limit: int = 20,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, Any]]:
    """Return the most recent messages ordered oldest -> newest (chronological)."""
    async with conn.execute(
        "SELECT id, role, content, actions, created_at FROM chat_messages "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ) as cur:
        rows = [dict(row) for row in await cur.fetchall()]
    rows.reverse()
    for row in rows:
        row["actions"] = json.loads(row["actions"]) if row["actions"] else None
    return rows
