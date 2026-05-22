"""Tests for portfolio API: state, trade execution, history."""

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
async def test_fresh_portfolio(client):
    r = await client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == 10000.0
    assert body["positions"] == []
    assert body["total_value"] == 10000.0


@pytest.mark.asyncio
async def test_buy_creates_position_and_reduces_cash(client):
    r = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 5},
    )
    assert r.status_code == 200
    trade = r.json()
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 5

    state = (await client.get("/api/portfolio")).json()
    assert state["cash_balance"] < 10000.0
    assert len(state["positions"]) == 1
    pos = state["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 5
    assert pos["avg_cost"] == trade["price"]


@pytest.mark.asyncio
async def test_buy_more_recomputes_avg_cost(client):
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})

    state = (await client.get("/api/portfolio")).json()
    pos = next(p for p in state["positions"] if p["ticker"] == "AAPL")
    assert pos["quantity"] == 20
    assert pos["avg_cost"] > 0


@pytest.mark.asyncio
async def test_sell_partial(client):
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    r = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 4})
    assert r.status_code == 200

    state = (await client.get("/api/portfolio")).json()
    pos = next(p for p in state["positions"] if p["ticker"] == "AAPL")
    assert pos["quantity"] == 6


@pytest.mark.asyncio
async def test_sell_all_removes_position(client):
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 3})
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 3})

    state = (await client.get("/api/portfolio")).json()
    assert all(p["ticker"] != "AAPL" for p in state["positions"])


@pytest.mark.asyncio
async def test_buy_insufficient_cash(client):
    r = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "NVDA", "side": "buy", "quantity": 1000},
    )
    assert r.status_code == 400
    assert "Insufficient cash" in r.json()["detail"]


@pytest.mark.asyncio
async def test_sell_more_than_owned(client):
    r = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 1})
    assert r.status_code == 400
    assert "Insufficient shares" in r.json()["detail"]


@pytest.mark.asyncio
async def test_trade_invalid_quantity(client):
    r = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 0})
    assert r.status_code == 422  # pydantic validation


@pytest.mark.asyncio
async def test_history_returns_list(client):
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    r = await client.get("/api/portfolio/history")
    assert r.status_code == 200
    snapshots = r.json()
    assert len(snapshots) >= 1
    assert "timestamp" in snapshots[0]
    assert "total_value" in snapshots[0]


@pytest.mark.asyncio
async def test_pnl_reflects_avg_cost(client):
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5})
    state = (await client.get("/api/portfolio")).json()
    pos = next(p for p in state["positions"] if p["ticker"] == "AAPL")
    # Bought at current_price → P&L should be exactly 0 immediately
    assert abs(pos["unrealized_pnl"]) < 0.01
