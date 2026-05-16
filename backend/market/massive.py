from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from .base import MarketDataProvider, PriceCallback, PriceUpdate

logger = logging.getLogger(__name__)

BASE_URL = "https://api.massive.com"
POLL_INTERVAL = 15.0  # seconds; safe for the free tier (5 req/min cap)

SEED_PRICES: dict[str, float] = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 175.0,
    "NVDA": 875.0,
    "META": 500.0,
    "JPM": 200.0,
    "V": 275.0,
    "NFLX": 625.0,
}


def _extract_price(snap: dict) -> float:
    """
    Extract the best available price from a snapshot object.

    Priority:
      1. lastTrade.p  — most recent trade (real-time on paid plans)
      2. min.c        — most recent 1-minute bar close
      3. day.c        — current-day session close
      4. 0.0          — caller must handle missing price
    """
    last_trade = snap.get("lastTrade") or {}
    minute_bar = snap.get("min") or {}
    day = snap.get("day") or {}
    return last_trade.get("p") or minute_bar.get("c") or day.get("c") or 0.0


class MassiveMarketData(MarketDataProvider):
    """
    Polls the Massive (formerly Polygon.io) snapshot endpoint every 15 s.
    One HTTP request per poll cycle, regardless of watchlist size.
    """

    def __init__(self, api_key: str, poll_interval: float = POLL_INTERVAL) -> None:
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._tickers: set[str] = set()
        self._cache: dict[str, PriceUpdate] = {}
        self._subscribers: list[PriceCallback] = []
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def add_ticker(self, ticker: str) -> PriceUpdate:
        self._tickers.add(ticker)
        update = await self._fetch_single(ticker)
        self._cache[ticker] = update
        return update

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._cache.pop(ticker, None)

    def get_prices(self) -> dict[str, PriceUpdate]:
        return dict(self._cache)

    def subscribe(self, callback: PriceCallback) -> None:
        self._subscribers.append(callback)

    async def _poll_loop(self) -> None:
        while True:
            if self._tickers:
                try:
                    await self._poll_all()
                except Exception:
                    logger.exception("Massive poll error")
            await asyncio.sleep(self._poll_interval)

    async def _poll_all(self) -> None:
        """Fetch all active tickers in one API call and fan out callbacks."""
        tickers_param = ",".join(sorted(self._tickers))
        resp = await self._client.get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": tickers_param},
        )
        resp.raise_for_status()
        data = resp.json()

        now = datetime.now(timezone.utc)
        for snap in data.get("tickers", []):
            ticker = snap.get("ticker", "")
            if ticker not in self._tickers:
                continue

            price = _extract_price(snap)
            if price <= 0:
                continue

            prev_entry = self._cache.get(ticker)
            prev_price = prev_entry.price if prev_entry else price
            session_open = prev_entry.session_open if prev_entry else price

            direction = "flat"
            if price > prev_price:
                direction = "up"
            elif price < prev_price:
                direction = "down"

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 4),
                prev_price=round(prev_price, 4),
                session_open=round(session_open, 4),
                timestamp=now,
                direction=direction,
            )
            self._cache[ticker] = update
            for cb in self._subscribers:
                await cb(update)

    async def _fetch_single(self, ticker: str) -> PriceUpdate:
        """
        Fetch the current price for one ticker immediately (used by add_ticker).
        Falls back to SEED_PRICES on any error.
        """
        now = datetime.now(timezone.utc)
        seed = SEED_PRICES.get(ticker, 100.0)
        try:
            resp = await self._client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ticker},
            )
            resp.raise_for_status()
            snaps = resp.json().get("tickers", [])
            if snaps:
                price = _extract_price(snaps[0])
                if price > 0:
                    return PriceUpdate(
                        ticker=ticker,
                        price=round(price, 4),
                        prev_price=round(price, 4),
                        session_open=round(price, 4),
                        timestamp=now,
                        direction="flat",
                    )
        except Exception:
            logger.warning("Could not fetch price for %s from Massive; using seed", ticker)

        return PriceUpdate(
            ticker=ticker,
            price=seed,
            prev_price=seed,
            session_open=seed,
            timestamp=now,
            direction="flat",
        )
