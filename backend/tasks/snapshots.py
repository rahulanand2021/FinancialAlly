"""Background task that records portfolio value snapshots every 30 seconds."""

from __future__ import annotations

import asyncio
import logging

import aiosqlite

from db import crud, get_db_path, init_db
from market import get_market_data_provider

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 30.0


async def compute_total_value(conn: aiosqlite.Connection) -> float:
    """Cash plus mark-to-market value of all positions using the latest price cache."""
    cash = await crud.get_cash_balance(conn)
    positions = await crud.list_positions(conn)
    if not positions:
        return cash
    prices = get_market_data_provider().get_prices()
    market_value = 0.0
    for pos in positions:
        cached = prices.get(pos["ticker"])
        price = cached.price if cached else pos["avg_cost"]
        market_value += pos["quantity"] * price
    return cash + market_value


async def _record_snapshot() -> None:
    await init_db()
    conn = await aiosqlite.connect(get_db_path())
    conn.row_factory = aiosqlite.Row
    try:
        total = await compute_total_value(conn)
        await crud.insert_portfolio_snapshot(conn, total)
        await conn.commit()
    finally:
        await conn.close()


async def snapshot_loop() -> None:
    """Run forever, recording a snapshot every SNAPSHOT_INTERVAL seconds."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        try:
            await _record_snapshot()
        except Exception:
            logger.exception("Portfolio snapshot failed")
