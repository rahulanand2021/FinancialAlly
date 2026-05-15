# Market Data Interface — Unified Python API Design

This document defines the unified Python interface for retrieving stock prices in FinAlly. The same abstract base class is implemented twice: once backed by the Massive REST API and once by the built-in GBM simulator. All downstream code (SSE streaming, price cache, portfolio snapshot task) depends only on the abstract interface and is completely agnostic to the data source.

**Runtime selection**: If `MASSIVE_API_KEY` is set and non-empty in the environment, the backend uses `MassiveMarketData`. Otherwise it uses `SimulatedMarketData`. This selection happens once at startup in the application factory.

---

## Directory Layout

```
backend/
├── market/
│   ├── __init__.py          # exports: get_market_data_provider()
│   ├── base.py              # abstract base class + shared data models
│   ├── massive.py           # MassiveMarketData implementation
│   └── simulator.py         # SimulatedMarketData implementation
```

---

## Data Models

Defined in `backend/market/base.py`. These are plain dataclasses; no ORM, no Pydantic — they live only in memory.

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceUpdate:
    ticker: str
    price: float           # current/latest price
    prev_price: float      # price from the previous update cycle
    session_open: float    # first price seen this backend session (for session change %)
    timestamp: datetime    # when this price was recorded
    direction: str         # "up", "down", or "flat"


@dataclass
class TickerConfig:
    ticker: str
    seed_price: float = 100.0
    sigma: float = 0.02    # GBM volatility (used only by simulator)
    mu: float = 0.0001     # GBM drift (used only by simulator)
```

---

## Abstract Base Class

Defined in `backend/market/base.py`.

```python
import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Awaitable


PriceCallback = Callable[[PriceUpdate], Awaitable[None]]


class MarketDataProvider(ABC):
    """
    Provides a live price feed for a dynamic set of tickers.

    Lifecycle:
      1. Call start() once at application startup to begin the background polling loop.
      2. Add/remove tickers at any time via add_ticker() / remove_ticker().
      3. Register a callback with subscribe() to receive PriceUpdate objects.
      4. Call stop() on shutdown to cleanly cancel the background task.

    The provider guarantees:
      - add_ticker() immediately initializes a cache entry so no race condition exists
        when the SSE stream reads from the cache on the next push cycle.
      - remove_ticker() purges the cache entry; the ticker will not appear in the next
        push cycle.
      - get_prices() returns the current snapshot for all active tickers.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the background price update loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background loop and release resources."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> PriceUpdate:
        """
        Add a ticker to the active watchlist.
        Returns an immediate PriceUpdate for the new ticker (using seed price or
        the most recent API price). Must initialize the internal cache entry.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker and purge its cache entry."""

    @abstractmethod
    def get_prices(self) -> dict[str, PriceUpdate]:
        """
        Return the current in-memory price cache.
        Returns a dict mapping ticker -> PriceUpdate.
        This is a synchronous snapshot — callers must not mutate the returned dict.
        """

    @abstractmethod
    def subscribe(self, callback: PriceCallback) -> None:
        """
        Register a coroutine callback to be called on each price update cycle.
        The callback receives a single PriceUpdate per call.
        Multiple subscribers are supported.
        """
```

---

## Provider Factory

Defined in `backend/market/__init__.py`. Called once at FastAPI startup.

```python
import os
from .base import MarketDataProvider
from .massive import MassiveMarketData
from .simulator import SimulatedMarketData


_provider: MarketDataProvider | None = None


def get_market_data_provider() -> MarketDataProvider:
    """
    Returns the singleton provider, creating it on first call.
    Selection is based on MASSIVE_API_KEY environment variable.
    """
    global _provider
    if _provider is None:
        api_key = os.getenv("MASSIVE_API_KEY", "").strip()
        if api_key:
            _provider = MassiveMarketData(api_key=api_key)
        else:
            _provider = SimulatedMarketData()
    return _provider
```

**FastAPI integration** (in `backend/main.py`):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from market import get_market_data_provider
from db import init_db, get_watchlist_tickers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    provider = get_market_data_provider()
    # Seed with persisted watchlist tickers from DB
    for ticker in await get_watchlist_tickers():
        await provider.add_ticker(ticker)
    await provider.start()
    yield
    await provider.stop()


app = FastAPI(lifespan=lifespan)
```

---

## MassiveMarketData Implementation

Defined in `backend/market/massive.py`.

**Strategy**: Poll `GET /v2/snapshot/locale/us/markets/stocks/tickers` with all active tickers in one request. This is maximally efficient on the free tier (1 request per poll cycle regardless of watchlist size).

```python
import asyncio
import httpx
from datetime import datetime, timezone
from .base import MarketDataProvider, PriceUpdate, PriceCallback


POLL_INTERVAL = 15.0   # seconds — safe for the 5 req/min free tier
BASE_URL = "https://api.massive.com"

# Realistic seed prices for the default watchlist tickers
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0,
    "TSLA": 175.0, "NVDA": 875.0, "META": 500.0, "JPM": 200.0,
    "V": 275.0, "NFLX": 625.0,
}


class MassiveMarketData(MarketDataProvider):

    def __init__(self, api_key: str):
        self._api_key = api_key
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
        # Try to get current price; fall back to seed price immediately
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
                await self._poll_all()
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_all(self) -> None:
        tickers_param = ",".join(sorted(self._tickers))
        try:
            resp = await self._client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": tickers_param},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return  # skip cycle on any error; previous cache values remain valid

        now = datetime.now(timezone.utc)
        for snap in data.get("tickers", []):
            ticker = snap["ticker"]
            if ticker not in self._tickers:
                continue

            # Use lastTrade.p if available, else fall back to day.c
            last_trade = snap.get("lastTrade") or {}
            day = snap.get("day") or {}
            price = last_trade.get("p") or day.get("c") or 0.0

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
                price=price,
                prev_price=prev_price,
                session_open=session_open,
                timestamp=now,
                direction=direction,
            )
            self._cache[ticker] = update
            for cb in self._subscribers:
                await cb(update)

    async def _fetch_single(self, ticker: str) -> PriceUpdate:
        """Fetch price for one ticker (used by add_ticker to get immediate price)."""
        now = datetime.now(timezone.utc)
        seed = SEED_PRICES.get(ticker, 100.0)
        try:
            resp = await self._client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ticker},
            )
            resp.raise_for_status()
            data = resp.json()
            snaps = data.get("tickers", [])
            if snaps:
                snap = snaps[0]
                last_trade = snap.get("lastTrade") or {}
                day = snap.get("day") or {}
                price = last_trade.get("p") or day.get("c") or seed
                return PriceUpdate(
                    ticker=ticker,
                    price=price,
                    prev_price=price,
                    session_open=price,
                    timestamp=now,
                    direction="flat",
                )
        except Exception:
            pass
        # Fall back to seed price on API error
        return PriceUpdate(
            ticker=ticker,
            price=seed,
            prev_price=seed,
            session_open=seed,
            timestamp=now,
            direction="flat",
        )
```

---

## SimulatedMarketData Implementation

See `MARKET_SIMULATOR.md` for full design. Summary of how it satisfies the interface:

```python
class SimulatedMarketData(MarketDataProvider):
    """
    Drives prices with GBM at ~500ms intervals.
    Implements all methods of MarketDataProvider.
    add_ticker() immediately assigns a seed price and initializes the cache.
    """
```

---

## SSE Streaming Integration

The SSE endpoint reads from the provider's subscriber callback pattern.

```python
# backend/routes/stream.py
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from market import get_market_data_provider
from market.base import PriceUpdate

router = APIRouter()


@router.get("/api/stream/prices")
async def stream_prices():
    provider = get_market_data_provider()
    queue: asyncio.Queue[PriceUpdate] = asyncio.Queue()

    async def on_price(update: PriceUpdate) -> None:
        await queue.put(update)

    provider.subscribe(on_price)

    async def event_generator():
        try:
            while True:
                update = await queue.get()
                payload = {
                    "ticker": update.ticker,
                    "price": round(update.price, 4),
                    "prev_price": round(update.prev_price, 4),
                    "session_open": round(update.session_open, 4),
                    "timestamp": update.timestamp.isoformat(),
                    "direction": update.direction,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            provider._subscribers.remove(on_price)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

---

## Watchlist API Integration

When a ticker is added or removed via REST, the provider is updated immediately so the cache stays consistent with the SSE stream.

```python
# backend/routes/watchlist.py (excerpt)
from market import get_market_data_provider

@router.post("/api/watchlist")
async def add_to_watchlist(body: AddTickerRequest, db: DB):
    ticker = body.ticker.upper()
    # ... validate ticker, check uniqueness in DB ...
    await db.insert_watchlist(ticker)
    provider = get_market_data_provider()
    update = await provider.add_ticker(ticker)
    return {
        "ticker": ticker,
        "price": update.price,
        "prev_price": update.prev_price,
        "session_open": update.session_open,
        "session_change_pct": 0.0,
    }

@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, db: DB):
    ticker = ticker.upper()
    await db.delete_watchlist(ticker)
    provider = get_market_data_provider()
    await provider.remove_ticker(ticker)
    return {"ok": True}
```

---

## Invariants and Guarantees

| Invariant | How it's enforced |
|-----------|-------------------|
| No race between add_ticker and SSE stream | `add_ticker()` is awaited before returning the HTTP response; cache entry exists before next push cycle |
| Removed ticker disappears from stream | `remove_ticker()` deletes the cache entry and removes from the ticker set atomically |
| Provider selected once | Module-level singleton via `_provider` global in `__init__.py` |
| API errors don't crash the stream | Exceptions in `_poll_all()` and `_fetch_single()` are caught; stale cache values persist |
| Session open is preserved across restarts | `session_open` is set on first `add_ticker()` call and never overwritten |
