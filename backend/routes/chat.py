"""Chat REST endpoint: send a message, get an LLM reply, auto-execute actions.

Response shape: {message, actions[]} where each action carries per-action
status and detail (price, error, already_present). This supersedes the flat
trades/watchlist_changes shape originally sketched in PLAN.md §9 because it can
report per-action success/failure that the flat shape cannot.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import crud, get_db
from llm import HISTORY_LIMIT, build_portfolio_context, generate_response
from market import get_market_data_provider
from services import TradeError, execute_trade, get_portfolio_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


async def _build_history(conn: aiosqlite.Connection) -> list[dict[str, str]]:
    rows = await crud.list_recent_chat_messages(conn, limit=HISTORY_LIMIT)
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _watchlist_context(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    tickers = await crud.list_watchlist(conn)
    cache = get_market_data_provider().get_prices()
    entries: list[dict[str, Any]] = []
    for ticker in tickers:
        update = cache.get(ticker)
        if update is None:
            continue
        base = update.session_open or update.price
        pct = ((update.price - base) / base * 100.0) if base else 0.0
        entries.append({
            "ticker": ticker,
            "price": update.price,
            "session_change_pct": round(pct, 4),
        })
    return entries


async def _apply_trade(conn: aiosqlite.Connection, trade) -> dict[str, Any]:
    try:
        result = await execute_trade(conn, trade.ticker, trade.side, trade.quantity)
        return {
            "type": "trade",
            "status": "ok",
            "ticker": result["ticker"],
            "side": result["side"],
            "quantity": result["quantity"],
            "price": result["price"],
        }
    except TradeError as exc:
        return {
            "type": "trade",
            "status": "error",
            "ticker": trade.ticker.strip().upper(),
            "side": trade.side,
            "quantity": trade.quantity,
            "error": str(exc),
        }


async def _apply_watchlist_change(
    conn: aiosqlite.Connection, change
) -> dict[str, Any]:
    ticker = change.ticker.strip().upper()
    provider = get_market_data_provider()
    if change.action == "add":
        added = await crud.add_watchlist_ticker(conn, ticker)
        await provider.add_ticker(ticker)
        return {
            "type": "watchlist",
            "status": "ok",
            "action": "add",
            "ticker": ticker,
            "already_present": not added,
        }
    removed = await crud.remove_watchlist_ticker(conn, ticker)
    if removed:
        await provider.remove_ticker(ticker)
    return {
        "type": "watchlist",
        "status": "ok" if removed else "noop",
        "action": "remove",
        "ticker": ticker,
    }


@router.post("")
async def post_chat(
    body: ChatRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> dict[str, Any]:
    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    await crud.insert_chat_message(conn, "user", user_text)
    await conn.commit()

    state = await get_portfolio_state(conn)
    watchlist = await _watchlist_context(conn)
    context = build_portfolio_context(
        cash_balance=state["cash_balance"],
        total_value=state["total_value"],
        positions=state["positions"],
        watchlist=watchlist,
    )
    history = await _build_history(conn)

    reply = generate_response(user_text, context, history)

    actions: list[dict[str, Any]] = []
    for trade in reply.trades:
        actions.append(await _apply_trade(conn, trade))
    for change in reply.watchlist_changes:
        actions.append(await _apply_watchlist_change(conn, change))

    await crud.insert_chat_message(
        conn, "assistant", reply.message, actions=actions or None
    )

    return {"message": reply.message, "actions": actions}
