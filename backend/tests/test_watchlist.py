"""Tests for the watchlist API."""

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
async def test_list_default_watchlist(client):
    r = await client.get("/api/watchlist")
    assert r.status_code == 200
    body = r.json()
    tickers = {e["ticker"] for e in body}
    assert {"AAPL", "GOOGL", "MSFT", "NFLX"}.issubset(tickers)
    for entry in body:
        assert entry["price"] > 0
        assert "session_change_pct" in entry


@pytest.mark.asyncio
async def test_add_ticker_returns_initial_entry(client):
    r = await client.post("/api/watchlist", json={"ticker": "pltr"})
    assert r.status_code == 201
    body = r.json()
    assert body["ticker"] == "PLTR"
    assert body["price"] == 100.0
    assert body["session_change_pct"] == 0.0


@pytest.mark.asyncio
async def test_add_ticker_persists(client):
    await client.post("/api/watchlist", json={"ticker": "PLTR"})
    r = await client.get("/api/watchlist")
    tickers = {e["ticker"] for e in r.json()}
    assert "PLTR" in tickers


@pytest.mark.asyncio
async def test_add_ticker_rejects_invalid(client):
    r = await client.post("/api/watchlist", json={"ticker": "BAD!"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_ticker(client):
    r = await client.delete("/api/watchlist/AAPL")
    assert r.status_code == 204
    r2 = await client.get("/api/watchlist")
    assert "AAPL" not in {e["ticker"] for e in r2.json()}


@pytest.mark.asyncio
async def test_delete_missing_ticker(client):
    r = await client.delete("/api/watchlist/ZZZZ")
    assert r.status_code == 404
