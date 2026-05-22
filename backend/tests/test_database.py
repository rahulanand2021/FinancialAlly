"""Tests for database initialization and seeding."""

from __future__ import annotations

import os

import aiosqlite
import pytest

from db import database as dbmod


@pytest.fixture(autouse=True)
async def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    await dbmod.close_db()
    yield db_file
    await dbmod.close_db()


async def test_init_db_creates_file_and_tables(isolated_db):
    await dbmod.init_db()
    assert isolated_db.exists()
    async with aiosqlite.connect(isolated_db) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            names = [r[0] for r in await cur.fetchall()]
    expected = {
        "chat_messages", "portfolio_snapshots", "positions",
        "trades", "users_profile", "watchlist",
    }
    assert expected.issubset(set(names))


async def test_seed_user_and_watchlist(isolated_db):
    await dbmod.init_db()
    async with aiosqlite.connect(isolated_db) as conn:
        async with conn.execute(
            "SELECT id, cash_balance FROM users_profile"
        ) as cur:
            users = await cur.fetchall()
        async with conn.execute(
            "SELECT ticker FROM watchlist ORDER BY ticker"
        ) as cur:
            tickers = [r[0] for r in await cur.fetchall()]

    assert len(users) == 1
    assert users[0][0] == "default"
    assert users[0][1] == 10000.0
    assert set(tickers) == set(dbmod.DEFAULT_WATCHLIST)


async def test_init_db_is_idempotent(isolated_db):
    await dbmod.init_db()
    await dbmod.close_db()
    await dbmod.init_db()
    async with aiosqlite.connect(isolated_db) as conn:
        async with conn.execute("SELECT COUNT(*) FROM watchlist") as cur:
            count = (await cur.fetchone())[0]
    assert count == len(dbmod.DEFAULT_WATCHLIST)


async def test_get_db_yields_connection(isolated_db):
    gen = dbmod.get_db()
    conn = await gen.__anext__()
    try:
        async with conn.execute("SELECT cash_balance FROM users_profile WHERE id='default'") as cur:
            row = await cur.fetchone()
        assert row["cash_balance"] == 10000.0
    finally:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
