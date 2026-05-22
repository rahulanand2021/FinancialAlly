"""Tests for the chat API: mock-mode end-to-end with auto-execution."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(monkeypatch):
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_path))
    monkeypatch.setenv("LLM_MOCK", "true")

    import db.database as database
    database._initialized = False
    import market
    market._provider = None

    from main import lifespan, app

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    tmpdir.cleanup()


@pytest.mark.asyncio
async def test_mock_chat_returns_message_and_executes_actions(client):
    r = await client.post("/api/chat", json={"message": "Get me started"})
    assert r.status_code == 200
    body = r.json()
    assert "I've reviewed your portfolio" in body["message"]

    actions = body["actions"]
    trade_actions = [a for a in actions if a["type"] == "trade"]
    wl_actions = [a for a in actions if a["type"] == "watchlist"]
    assert len(trade_actions) == 1
    assert trade_actions[0]["status"] == "ok"
    assert trade_actions[0]["ticker"] == "AAPL"
    assert trade_actions[0]["side"] == "buy"
    assert trade_actions[0]["quantity"] == 5
    assert trade_actions[0]["price"] > 0
    assert len(wl_actions) == 1
    assert wl_actions[0]["ticker"] == "NVDA"
    assert wl_actions[0]["action"] == "add"


@pytest.mark.asyncio
async def test_mock_chat_side_effects_persist(client):
    await client.post("/api/chat", json={"message": "hi"})

    portfolio = (await client.get("/api/portfolio")).json()
    assert portfolio["cash_balance"] < 10000.0
    assert any(p["ticker"] == "AAPL" and p["quantity"] == 5 for p in portfolio["positions"])

    watchlist = (await client.get("/api/watchlist")).json()
    assert any(w["ticker"] == "NVDA" for w in watchlist)


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client):
    r = await client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_chat_persists_history(client):
    await client.post("/api/chat", json={"message": "first"})

    from db import crud, get_db_path
    import aiosqlite

    conn = await aiosqlite.connect(get_db_path())
    conn.row_factory = aiosqlite.Row
    try:
        rows = await crud.list_recent_chat_messages(conn)
    finally:
        await conn.close()

    roles = [r["role"] for r in rows]
    assert "user" in roles and "assistant" in roles
    assistant_row = next(r for r in rows if r["role"] == "assistant")
    assert assistant_row["actions"] is not None
    assert any(a["type"] == "trade" for a in assistant_row["actions"])
