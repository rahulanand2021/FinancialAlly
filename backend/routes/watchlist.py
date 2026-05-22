"""Watchlist REST endpoints."""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import crud, get_db
from market import get_market_data_provider
from market.base import PriceUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)


class WatchlistEntry(BaseModel):
    ticker: str
    price: float
    prev_price: float
    session_open: float
    session_change_pct: float


def _to_entry(update: PriceUpdate) -> WatchlistEntry:
    base = update.session_open or update.price
    pct = ((update.price - base) / base * 100.0) if base else 0.0
    return WatchlistEntry(
        ticker=update.ticker,
        price=update.price,
        prev_price=update.prev_price,
        session_open=update.session_open,
        session_change_pct=round(pct, 4),
    )


@router.get("", response_model=list[WatchlistEntry])
async def list_watchlist(conn: aiosqlite.Connection = Depends(get_db)) -> list[WatchlistEntry]:
    tickers = await crud.list_watchlist(conn)
    provider = get_market_data_provider()
    cache = provider.get_prices()
    entries: list[WatchlistEntry] = []
    for ticker in tickers:
        update = cache.get(ticker)
        if update is None:
            update = await provider.add_ticker(ticker)
        entries.append(_to_entry(update))
    return entries


@router.post("", response_model=WatchlistEntry, status_code=201)
async def add_ticker(
    body: AddTickerRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> WatchlistEntry:
    ticker = body.ticker.strip().upper()
    if not ticker.isalnum():
        raise HTTPException(status_code=400, detail="Ticker must be alphanumeric")
    await crud.add_watchlist_ticker(conn, ticker)
    provider = get_market_data_provider()
    update = await provider.add_ticker(ticker)
    return _to_entry(update)


@router.delete("/{ticker}", status_code=204)
async def remove_ticker(
    ticker: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> None:
    ticker = ticker.strip().upper()
    removed = await crud.remove_watchlist_ticker(conn, ticker)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not on watchlist")
    await get_market_data_provider().remove_ticker(ticker)
