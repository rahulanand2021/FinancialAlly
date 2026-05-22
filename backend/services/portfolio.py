"""Portfolio service: trade execution and state aggregation.

Exposed for both REST (routes/portfolio.py) and chat auto-execution (routes/chat.py)
so trade math lives in exactly one place.
"""

from __future__ import annotations

from typing import Any

import aiosqlite

from db import crud
from market import get_market_data_provider
from tasks.snapshots import compute_total_value


class TradeError(ValueError):
    """Raised when a trade fails validation (insufficient cash, shares, etc.)."""


async def _current_price(ticker: str) -> float:
    cache = get_market_data_provider().get_prices()
    update = cache.get(ticker)
    if update is None:
        update = await get_market_data_provider().add_ticker(ticker)
    return update.price


async def execute_trade(
    conn: aiosqlite.Connection,
    ticker: str,
    side: str,
    quantity: float,
) -> dict[str, Any]:
    """Execute a market order at the current cached price.

    Updates cash, positions (weighted avg cost on buys), records the trade,
    and snapshots the portfolio. Returns the inserted trade row.
    """
    ticker = ticker.strip().upper()
    side = side.lower()
    if side not in ("buy", "sell"):
        raise TradeError(f"side must be 'buy' or 'sell', got {side!r}")
    if quantity <= 0:
        raise TradeError("quantity must be positive")

    price = await _current_price(ticker)
    cash = await crud.get_cash_balance(conn)
    position = await crud.get_position(conn, ticker)

    if side == "buy":
        cost = price * quantity
        if cost > cash:
            raise TradeError(
                f"Insufficient cash: need {cost:.2f}, have {cash:.2f}"
            )
        if position is None:
            new_qty = quantity
            new_avg = price
        else:
            new_qty = position["quantity"] + quantity
            new_avg = (
                position["quantity"] * position["avg_cost"] + quantity * price
            ) / new_qty
        await crud.set_cash_balance(conn, cash - cost)
        await crud.upsert_position(conn, ticker, new_qty, new_avg)
    else:  # sell
        if position is None or position["quantity"] < quantity:
            owned = position["quantity"] if position else 0.0
            raise TradeError(
                f"Insufficient shares: trying to sell {quantity}, own {owned}"
            )
        proceeds = price * quantity
        new_qty = position["quantity"] - quantity
        await crud.set_cash_balance(conn, cash + proceeds)
        if new_qty <= 1e-9:
            await crud.delete_position(conn, ticker)
        else:
            await crud.upsert_position(conn, ticker, new_qty, position["avg_cost"])

    trade = await crud.insert_trade(conn, ticker, side, quantity, price)
    total = await compute_total_value(conn)
    await crud.insert_portfolio_snapshot(conn, total)
    return trade


async def get_portfolio_state(conn: aiosqlite.Connection) -> dict[str, Any]:
    """Return cash, total value, and positions with current prices and P&L."""
    cash = await crud.get_cash_balance(conn)
    positions = await crud.list_positions(conn)
    cache = get_market_data_provider().get_prices()

    enriched: list[dict[str, Any]] = []
    market_value = 0.0
    for pos in positions:
        cached = cache.get(pos["ticker"])
        current_price = cached.price if cached else pos["avg_cost"]
        cost_basis = pos["quantity"] * pos["avg_cost"]
        value = pos["quantity"] * current_price
        pnl = value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis else 0.0
        market_value += value
        enriched.append({
            "ticker": pos["ticker"],
            "quantity": pos["quantity"],
            "avg_cost": pos["avg_cost"],
            "current_price": current_price,
            "unrealized_pnl": round(pnl, 4),
            "unrealized_pnl_pct": round(pnl_pct, 4),
        })

    return {
        "cash_balance": cash,
        "total_value": round(cash + market_value, 4),
        "positions": enriched,
    }
