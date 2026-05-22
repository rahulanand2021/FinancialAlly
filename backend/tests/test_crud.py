"""Tests for CRUD helper functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from db import crud
from db import database as dbmod


@pytest.fixture
async def conn(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    await dbmod.close_db()
    await dbmod.init_db()
    c = await aiosqlite.connect(db_file)
    c.row_factory = aiosqlite.Row
    try:
        yield c
        await c.commit()
    finally:
        await c.close()
        await dbmod.close_db()


# --- cash --------------------------------------------------------------------

async def test_cash_balance_default(conn):
    assert await crud.get_cash_balance(conn) == 10000.0


async def test_set_cash_balance(conn):
    await crud.set_cash_balance(conn, 7432.10)
    assert await crud.get_cash_balance(conn) == 7432.10


# --- watchlist ---------------------------------------------------------------

async def test_seeded_watchlist(conn):
    tickers = await crud.list_watchlist(conn)
    assert set(tickers) == set(dbmod.DEFAULT_WATCHLIST)


async def test_add_and_remove_watchlist(conn):
    assert await crud.add_watchlist_ticker(conn, "pltr") is True
    tickers = await crud.list_watchlist(conn)
    assert "PLTR" in tickers
    assert await crud.add_watchlist_ticker(conn, "PLTR") is False
    assert await crud.remove_watchlist_ticker(conn, "PLTR") is True
    assert "PLTR" not in await crud.list_watchlist(conn)
    assert await crud.remove_watchlist_ticker(conn, "PLTR") is False


# --- positions ---------------------------------------------------------------

async def test_upsert_get_delete_position(conn):
    assert await crud.get_position(conn, "AAPL") is None
    await crud.upsert_position(conn, "AAPL", 10.0, 180.0)
    pos = await crud.get_position(conn, "AAPL")
    assert pos["quantity"] == 10.0 and pos["avg_cost"] == 180.0

    await crud.upsert_position(conn, "AAPL", 15.0, 185.0)
    pos = await crud.get_position(conn, "AAPL")
    assert pos["quantity"] == 15.0 and pos["avg_cost"] == 185.0

    await crud.upsert_position(conn, "MSFT", 5.0, 410.0)
    positions = await crud.list_positions(conn)
    assert [p["ticker"] for p in positions] == ["AAPL", "MSFT"]

    await crud.delete_position(conn, "AAPL")
    assert await crud.get_position(conn, "AAPL") is None


# --- trades ------------------------------------------------------------------

async def test_insert_and_list_trades(conn):
    t1 = await crud.insert_trade(conn, "AAPL", "buy", 5.0, 190.0)
    t2 = await crud.insert_trade(conn, "MSFT", "sell", 2.0, 410.0)
    assert t1["id"] != t2["id"]

    trades = await crud.list_trades(conn)
    assert len(trades) == 2
    # ordered DESC by executed_at
    assert trades[0]["ticker"] == "MSFT"

    limited = await crud.list_trades(conn, limit=1)
    assert len(limited) == 1


async def test_insert_trade_rejects_bad_side(conn):
    with pytest.raises(ValueError):
        await crud.insert_trade(conn, "AAPL", "short", 1.0, 100.0)


# --- portfolio_snapshots -----------------------------------------------------

async def test_snapshot_insert_and_list(conn):
    await crud.insert_portfolio_snapshot(conn, 10000.0)
    await crud.insert_portfolio_snapshot(conn, 10100.0)
    snaps = await crud.list_portfolio_snapshots(conn)
    assert len(snaps) == 2
    assert snaps[0]["total_value"] == 10000.0


async def test_snapshot_prunes_old_records(conn):
    old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    await conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        ("old-id", "default", 9000.0, old_time),
    )
    await crud.insert_portfolio_snapshot(conn, 10000.0)
    snaps_recent = await crud.list_portfolio_snapshots(conn)
    assert all(s["total_value"] != 9000.0 for s in snaps_recent)

    async with conn.execute(
        "SELECT COUNT(*) FROM portfolio_snapshots WHERE id = 'old-id'"
    ) as cur:
        count = (await cur.fetchone())[0]
    assert count == 0


# --- chat_messages -----------------------------------------------------------

async def test_chat_messages_roundtrip(conn):
    await crud.insert_chat_message(conn, "user", "hi")
    await crud.insert_chat_message(
        conn, "assistant", "hello", actions={"trades": [{"ticker": "AAPL"}]}
    )
    messages = await crud.list_recent_chat_messages(conn)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["actions"] == {"trades": [{"ticker": "AAPL"}]}
    assert messages[0]["actions"] is None


async def test_chat_messages_limit_and_order(conn):
    for i in range(25):
        await crud.insert_chat_message(conn, "user", f"msg-{i}")
    recent = await crud.list_recent_chat_messages(conn, limit=5)
    assert len(recent) == 5
    # oldest -> newest within the trailing window
    assert recent[0]["content"] == "msg-20"
    assert recent[-1]["content"] == "msg-24"


async def test_chat_invalid_role(conn):
    with pytest.raises(ValueError):
        await crud.insert_chat_message(conn, "system", "nope")
