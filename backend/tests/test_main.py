"""Smoke tests for the FastAPI main application."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_path))
    import db.database as database
    database._initialized = False
    import market
    market._provider = None
    yield db_path
    tmpdir.cleanup()


@pytest.mark.asyncio
async def test_health_endpoint(temp_db):
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_lifespan_hydrates_watchlist(temp_db):
    from main import _hydrate_watchlist, lifespan, app
    from market import get_market_data_provider

    async with lifespan(app):
        cache = get_market_data_provider().get_prices()
        assert "AAPL" in cache
        assert "NFLX" in cache
