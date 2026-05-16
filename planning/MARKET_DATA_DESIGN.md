# Market Data Backend — Implementation Design

This document is the implementation reference for all market data functionality in FinAlly. It synthesises `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, and `MASSIVE_API.md` into a single, code-complete guide that a developer (or agent) can follow to produce the `backend/market/` module from scratch.

---

## 1. Directory Layout

```
backend/
├── market/
│   ├── __init__.py       # singleton factory: get_market_data_provider()
│   ├── base.py           # PriceUpdate, TickerConfig, MarketDataProvider ABC
│   ├── simulator.py      # SimulatedMarketData — GBM-based, no network
│   └── massive.py        # MassiveMarketData — Massive (Polygon.io) REST API
├── routes/
│   ├── stream.py         # GET /api/stream/prices  (SSE)
│   └── watchlist.py      # GET/POST/DELETE /api/watchlist
└── main.py               # FastAPI app + lifespan wiring
```

All market data code lives in `backend/market/`. Nothing outside that package imports `simulator.py` or `massive.py` directly — only the abstract interface and the factory function are public.

---

## 2. Shared Data Models — `backend/market/base.py`

Pure dataclasses. No Pydantic, no ORM. These live only in memory; the database stores snapshots separately.

```python
# backend/market/base.py
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Awaitable


# ---------------------------------------------------------------------------
# Data models

@dataclass
class PriceUpdate:
    ticker: str
    price: float        # latest trade price
    prev_price: float   # price from the immediately preceding update cycle
    session_open: float # first price recorded for this ticker this backend session
    timestamp: datetime # UTC timestamp of this update
    direction: str      # "up" | "down" | "flat"


@dataclass
class TickerConfig:
    ticker: str
    seed_price: float = 100.0
    sigma: float = 0.02   # annualised GBM volatility (simulator only)
    mu: float = 0.0001    # annualised GBM drift     (simulator only)


# ---------------------------------------------------------------------------
# Callback type

PriceCallback = Callable[[PriceUpdate], Awaitable[None]]


# ---------------------------------------------------------------------------
# Abstract base class

class MarketDataProvider(ABC):
    """
    Live price feed for a dynamic watchlist of tickers.

    Lifecycle
    ---------
    1. Instantiate once (via the factory in __init__.py).
    2. Call start() at application startup — begins the background loop.
    3. Add / remove tickers at any time; the cache updates immediately.
    4. Call subscribe() to register async callbacks that receive each PriceUpdate.
    5. Call stop() at application shutdown.

    Guarantees
    ----------
    - add_ticker() initialises a cache entry BEFORE returning, so there is no
      window in which the SSE stream could reference a ticker with no price.
    - remove_ticker() purges the cache entry atomically; the ticker disappears
      from the next push cycle.
    - get_prices() is a synchronous snapshot; callers must not mutate it.
    - Any exception inside a polling/tick cycle is caught and logged; the cache
      retains stale-but-valid values and the stream continues uninterrupted.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the background price update loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background loop and release resources (e.g. HTTP client)."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> PriceUpdate:
        """
        Register a ticker and return an immediate PriceUpdate.

        For the simulator: seeds from SEED_PRICES or $100.
        For Massive: attempts a live fetch; falls back to seed price on error.
        Always initialises the internal cache before returning.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Unregister a ticker and delete its cache entry."""

    @abstractmethod
    def get_prices(self) -> dict[str, PriceUpdate]:
        """Return a shallow copy of the current price cache (ticker → PriceUpdate)."""

    @abstractmethod
    def subscribe(self, callback: PriceCallback) -> None:
        """Register an async callback invoked for every PriceUpdate emitted."""

    def unsubscribe(self, callback: PriceCallback) -> None:
        """Remove a previously registered callback. No-op if not found."""
        # Concrete implementations maintain self._subscribers; provide a default.
        if hasattr(self, "_subscribers"):
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass
```

### Why dataclasses and not Pydantic?

`PriceUpdate` objects exist only in memory and are created thousands of times per minute. Dataclasses have negligible construction overhead. Pydantic models are appropriate at the API boundary (request/response validation); these are internal.

---

## 3. Provider Factory — `backend/market/__init__.py`

Module-level singleton. The factory is called at startup; all subsequent callers get the same instance.

```python
# backend/market/__init__.py
import os
from .base import MarketDataProvider
from .massive import MassiveMarketData
from .simulator import SimulatedMarketData

__all__ = ["get_market_data_provider"]

_provider: MarketDataProvider | None = None


def get_market_data_provider() -> MarketDataProvider:
    """
    Return the singleton MarketDataProvider.

    Selection rule (evaluated once on first call):
      - MASSIVE_API_KEY set and non-empty  →  MassiveMarketData
      - otherwise                          →  SimulatedMarketData
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

**Important**: never call `get_market_data_provider()` during module import — only inside request handlers or the lifespan context. Import-time calls would fire before the `.env` file is loaded.

---

## 4. Simulator — `backend/market/simulator.py`

Full implementation of `SimulatedMarketData`. Zero network dependencies; prices driven by Geometric Brownian Motion with correlated shocks.

### 4.1 Constants and seed data

```python
# backend/market/simulator.py
from __future__ import annotations

import asyncio
import logging
import numpy as np
from datetime import datetime, timezone

from .base import MarketDataProvider, PriceCallback, PriceUpdate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing

TICK_INTERVAL = 0.5          # seconds between price updates
# Convert 500 ms to a fraction of a trading year so GBM drift/vol are
# expressed in annualised terms (industry convention).
_TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600   # ≈ 5,896,800 s/yr
DT = TICK_INTERVAL / _TRADING_SECONDS_PER_YEAR  # ≈ 8.48e-8 yr

# ---------------------------------------------------------------------------
# Default watchlist: seed prices (realistic early-2026 values)

SEED_PRICES: dict[str, float] = {
    "AAPL":  190.0,
    "GOOGL": 175.0,
    "MSFT":  420.0,
    "AMZN":  185.0,
    "TSLA":  175.0,
    "NVDA":  875.0,
    "META":  500.0,
    "JPM":   200.0,
    "V":     275.0,
    "NFLX":  625.0,
}

# Per-ticker GBM parameters (annualised).
# sigma = annualised volatility, mu = annualised drift.
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.25, "mu": 0.12},
    "GOOGL": {"sigma": 0.28, "mu": 0.10},
    "MSFT":  {"sigma": 0.22, "mu": 0.14},
    "AMZN":  {"sigma": 0.30, "mu": 0.12},
    "TSLA":  {"sigma": 0.65, "mu": 0.08},   # high vol
    "NVDA":  {"sigma": 0.55, "mu": 0.18},   # high vol, high drift
    "META":  {"sigma": 0.35, "mu": 0.10},
    "JPM":   {"sigma": 0.20, "mu": 0.10},
    "V":     {"sigma": 0.18, "mu": 0.12},
    "NFLX":  {"sigma": 0.38, "mu": 0.08},
}

DEFAULT_SIGMA = 0.25
DEFAULT_MU    = 0.10

# ---------------------------------------------------------------------------
# Correlation matrix for the 10 default tickers
# Order: AAPL GOOGL MSFT AMZN TSLA NVDA META JPM V NFLX

_DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

_DEFAULT_CORR = np.array([
    #      AAPL  GOOGL  MSFT  AMZN  TSLA  NVDA  META   JPM     V  NFLX
    [1.00, 0.65,  0.70, 0.60, 0.40, 0.55, 0.60,  0.25, 0.30, 0.45],  # AAPL
    [0.65, 1.00,  0.65, 0.55, 0.35, 0.50, 0.65,  0.20, 0.25, 0.50],  # GOOGL
    [0.70, 0.65,  1.00, 0.58, 0.38, 0.55, 0.62,  0.28, 0.32, 0.42],  # MSFT
    [0.60, 0.55,  0.58, 1.00, 0.42, 0.48, 0.58,  0.25, 0.30, 0.55],  # AMZN
    [0.40, 0.35,  0.38, 0.42, 1.00, 0.50, 0.38,  0.18, 0.20, 0.32],  # TSLA
    [0.55, 0.50,  0.55, 0.48, 0.50, 1.00, 0.52,  0.22, 0.25, 0.40],  # NVDA
    [0.60, 0.65,  0.62, 0.58, 0.38, 0.52, 1.00,  0.22, 0.28, 0.48],  # META
    [0.25, 0.20,  0.28, 0.25, 0.18, 0.22, 0.22,  1.00, 0.55, 0.20],  # JPM
    [0.30, 0.25,  0.32, 0.30, 0.20, 0.25, 0.28,  0.55, 1.00, 0.22],  # V
    [0.45, 0.50,  0.42, 0.55, 0.32, 0.40, 0.48,  0.20, 0.22, 1.00],  # NFLX
], dtype=np.float64)

# Computed once at module load — reused every tick.
_CHOLESKY: np.ndarray = np.linalg.cholesky(_DEFAULT_CORR)
```

### 4.2 GBM math

The core price step uses the exact GBM discretisation:

```
S(t+dt) = S(t) · exp( (μ - σ²/2)·dt  +  σ·√dt·Z )
```

Where `Z ~ N(0,1)`. The `(μ - σ²/2)` Itô correction ensures the expected value of `S(t+dt)` is `S(t)·exp(μ·dt)` (not inflated by Jensen's inequality).

```python
def _gbm_step(price: float, mu: float, sigma: float, z: float) -> float:
    """One GBM tick. Returns new price, guaranteed > 0."""
    exponent = (mu - 0.5 * sigma ** 2) * DT + sigma * (DT ** 0.5) * z
    return max(float(price * np.exp(exponent)), 0.01)
```

**Typical magnitude at σ=0.25, dt=8.48e-8 yr**:

```
σ·√dt ≈ 0.25 · √(8.48e-8) ≈ 7.28e-5
```

So each tick moves the price by roughly ±0.007% — imperceptible individually but visually smooth over hundreds of ticks per minute.

### 4.3 Correlation model

Correlated shocks via Cholesky decomposition:

```python
# Draw 10 independent standard normals
z_independent = rng.standard_normal(10)        # shape (10,)

# Multiply by the Cholesky factor to introduce correlation
z_correlated = _CHOLESKY @ z_independent       # shape (10,)

# z_correlated[i] is used for _DEFAULT_TICKERS[i]
```

`_CHOLESKY` is computed once (`np.linalg.cholesky(_DEFAULT_CORR)`) at module import. Dynamically added tickers (not in the default 10) draw independent `z` values — no correlation assumed.

### 4.4 Full class

```python
class SimulatedMarketData(MarketDataProvider):
    """
    GBM-driven price simulator. Updates every 500 ms.
    Pass seed= for deterministic sequences (useful in tests).
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)
        self._prices: dict[str, float] = {}          # current simulated price
        self._session_opens: dict[str, float] = {}   # price at add_ticker() time
        self._cache: dict[str, PriceUpdate] = {}     # last emitted PriceUpdate
        self._subscribers: list[PriceCallback] = []
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # MarketDataProvider interface

    async def start(self) -> None:
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def add_ticker(self, ticker: str) -> PriceUpdate:
        if ticker not in self._prices:
            seed_price = SEED_PRICES.get(ticker, 100.0)
            self._prices[ticker] = seed_price
            self._session_opens[ticker] = seed_price
            update = PriceUpdate(
                ticker=ticker,
                price=seed_price,
                prev_price=seed_price,
                session_open=seed_price,
                timestamp=datetime.now(timezone.utc),
                direction="flat",
            )
            self._cache[ticker] = update
        return self._cache[ticker]

    async def remove_ticker(self, ticker: str) -> None:
        self._prices.pop(ticker, None)
        self._session_opens.pop(ticker, None)
        self._cache.pop(ticker, None)

    def get_prices(self) -> dict[str, PriceUpdate]:
        return dict(self._cache)

    def subscribe(self, callback: PriceCallback) -> None:
        self._subscribers.append(callback)

    # ------------------------------------------------------------------
    # Internal tick loop

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            if not self._prices:
                continue
            try:
                now = datetime.now(timezone.utc)
                updates = self._compute_tick(now)
                for update in updates:
                    self._cache[update.ticker] = update
                    for cb in self._subscribers:
                        await cb(update)
            except Exception:
                logger.exception("Simulator tick error")

    def _compute_tick(self, now: datetime) -> list[PriceUpdate]:
        tickers = list(self._prices.keys())

        known   = [t for t in tickers if t in _DEFAULT_TICKERS]
        unknown = [t for t in tickers if t not in _DEFAULT_TICKERS]
        updates: list[PriceUpdate] = []

        # Correlated shocks for the default 10-ticker set
        if known:
            z_full = self._rng.standard_normal(len(_DEFAULT_TICKERS))
            z_corr = _CHOLESKY @ z_full   # correlated shocks
            for ticker in known:
                idx = _DEFAULT_TICKERS.index(ticker)
                params = TICKER_PARAMS[ticker]
                new_price = _gbm_step(
                    self._prices[ticker], params["mu"], params["sigma"], float(z_corr[idx])
                )
                updates.append(self._make_update(ticker, new_price, now))

        # Independent shocks for dynamically added tickers
        for ticker in unknown:
            z = float(self._rng.standard_normal())
            new_price = _gbm_step(self._prices[ticker], DEFAULT_MU, DEFAULT_SIGMA, z)
            updates.append(self._make_update(ticker, new_price, now))

        # Random market event: 2% probability per tick, one ticker
        if tickers and self._rng.random() < 0.02:
            event_ticker = tickers[int(self._rng.integers(0, len(tickers)))]
            magnitude = float(self._rng.uniform(0.02, 0.05))
            sign      = float(self._rng.choice(np.array([-1.0, 1.0])))
            # Patch the update we already computed for this ticker
            updates = [
                self._make_update(event_ticker, max(u.price * (1.0 + sign * magnitude), 0.01), now)
                if u.ticker == event_ticker else u
                for u in updates
            ]

        return updates

    def _make_update(self, ticker: str, new_price: float, now: datetime) -> PriceUpdate:
        prev_price = self._prices.get(ticker, new_price)
        self._prices[ticker] = new_price
        direction = "flat"
        if new_price > prev_price:
            direction = "up"
        elif new_price < prev_price:
            direction = "down"
        return PriceUpdate(
            ticker=ticker,
            price=round(new_price, 4),
            prev_price=round(prev_price, 4),
            session_open=self._session_opens.get(ticker, new_price),
            timestamp=now,
            direction=direction,
        )


def _gbm_step(price: float, mu: float, sigma: float, z: float) -> float:
    exponent = (mu - 0.5 * sigma ** 2) * DT + sigma * (DT ** 0.5) * z
    return max(float(price * np.exp(exponent)), 0.01)
```

### 4.5 GBM parameter reference

| Ticker | σ (annual) | μ (annual) | Character |
|--------|-----------|-----------|-----------|
| V      | 0.18      | 0.12      | Stable, slow mover |
| JPM    | 0.20      | 0.10      | Financials, moderate |
| MSFT   | 0.22      | 0.14      | Large-cap tech |
| AAPL   | 0.25      | 0.12      | Large-cap tech |
| GOOGL  | 0.28      | 0.10      | Large-cap tech |
| AMZN   | 0.30      | 0.12      | High-growth |
| META   | 0.35      | 0.10      | Social media |
| NFLX   | 0.38      | 0.08      | Growth, event-driven |
| NVDA   | 0.55      | 0.18      | High vol, high drift |
| TSLA   | 0.65      | 0.08      | Very high vol |
| (other)| 0.25      | 0.10      | Default fallback |

All values are annualised. Over a typical demo session (< 1 hour), drift is negligible — only volatility is visually observable.

---

## 5. Massive API Provider — `backend/market/massive.py`

Polls `GET /v2/snapshot/locale/us/markets/stocks/tickers` once per cycle using `httpx.AsyncClient`. All watchlist tickers are fetched in a single request.

### 5.1 Constants

```python
# backend/market/massive.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from .base import MarketDataProvider, PriceCallback, PriceUpdate

logger = logging.getLogger(__name__)

BASE_URL      = "https://api.massive.com"
POLL_INTERVAL = 15.0   # seconds; safe for the free tier (5 req/min cap)

# Seed prices used as fallback when the API is unavailable at add_ticker() time
SEED_PRICES: dict[str, float] = {
    "AAPL":  190.0,
    "GOOGL": 175.0,
    "MSFT":  420.0,
    "AMZN":  185.0,
    "TSLA":  175.0,
    "NVDA":  875.0,
    "META":  500.0,
    "JPM":   200.0,
    "V":     275.0,
    "NFLX":  625.0,
}
```

### 5.2 Full class

```python
class MassiveMarketData(MarketDataProvider):
    """
    Polls the Massive (formerly Polygon.io) snapshot endpoint every 15 s.
    One HTTP request per poll cycle, regardless of watchlist size.
    """

    def __init__(self, api_key: str, poll_interval: float = POLL_INTERVAL) -> None:
        self._api_key       = api_key
        self._poll_interval = poll_interval
        self._tickers: set[str]               = set()
        self._cache:   dict[str, PriceUpdate] = {}
        self._subscribers: list[PriceCallback] = []
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )

    # ------------------------------------------------------------------
    # MarketDataProvider interface

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
        # Attempt a live price fetch; fall back to seed on any error
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

    # ------------------------------------------------------------------
    # Polling loop

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

            prev_entry   = self._cache.get(ticker)
            prev_price   = prev_entry.price        if prev_entry else price
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
        now  = datetime.now(timezone.utc)
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
    day        = snap.get("day") or {}
    return (
        last_trade.get("p") or
        minute_bar.get("c") or
        day.get("c") or
        0.0
    )
```

### 5.3 Rate limit strategy

| Plan | req/min | Recommended `poll_interval` |
|------|---------|-----------------------------|
| Free | 5 | 15 s (default) |
| Starter $29/mo | unlimited | 3–5 s |
| Developer $79/mo | unlimited | 2–3 s |
| Advanced $199/mo | unlimited | 1–2 s |

One snapshot request covers all watchlist tickers, so the free tier comfortably supports 10+ tickers at 15-second intervals.

### 5.4 Outside-market-hours behaviour

The snapshot endpoint returns the last known prices when the market is closed. The `updated` nanosecond timestamp in the raw response can be used to detect stale data, but FinAlly does not currently expose this to the UI. The Massive provider still polls and fans out updates — the prices will simply be static (direction = "flat") until the market reopens.

---

## 6. FastAPI Wiring — `backend/main.py`

The lifespan context manager initialises the database, seeds the provider with persisted watchlist tickers, starts the background loop, then shuts it down cleanly.

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from market import get_market_data_provider
from db import init_db, get_watchlist_tickers
from routes.stream    import router as stream_router
from routes.watchlist import router as watchlist_router
from routes.portfolio import router as portfolio_router
from routes.chat      import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Ensure schema + seed data exist
    await init_db()

    # 2. Wire up market data provider
    provider = get_market_data_provider()
    for ticker in await get_watchlist_tickers():
        await provider.add_ticker(ticker)
    await provider.start()

    yield

    # 3. Graceful shutdown
    await provider.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(stream_router)
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(chat_router)

# Serve the Next.js static export
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

---

## 7. SSE Streaming Endpoint — `backend/routes/stream.py`

Each connected client gets its own `asyncio.Queue`. The SSE generator blocks on `queue.get()` and yields one SSE frame per `PriceUpdate`. The subscriber is registered when the request opens and removed when it closes (via `CancelledError`).

```python
# backend/routes/stream.py
import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from market import get_market_data_provider
from market.base import PriceUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/stream/prices")
async def stream_prices():
    provider = get_market_data_provider()
    queue: asyncio.Queue[PriceUpdate] = asyncio.Queue(maxsize=200)

    async def on_price(update: PriceUpdate) -> None:
        try:
            queue.put_nowait(update)
        except asyncio.QueueFull:
            # Client is too slow; drop oldest item and enqueue new one
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            queue.put_nowait(update)

    provider.subscribe(on_price)

    async def event_generator():
        try:
            # Send an initial comment so the browser EventSource fires "open"
            yield ": connected\n\n"
            while True:
                update = await queue.get()
                payload = {
                    "ticker":       update.ticker,
                    "price":        round(update.price, 4),
                    "prev_price":   round(update.prev_price, 4),
                    "session_open": round(update.session_open, 4),
                    "timestamp":    update.timestamp.isoformat(),
                    "direction":    update.direction,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            provider.unsubscribe(on_price)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
```

**SSE event shape** (one JSON object per `data:` line):

```json
{
  "ticker":       "AAPL",
  "price":        192.3412,
  "prev_price":   191.8034,
  "session_open": 189.5000,
  "timestamp":    "2026-05-16T14:22:01.123456+00:00",
  "direction":    "up"
}
```

**Frontend usage**:

```typescript
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const update = JSON.parse(e.data);
  // update.ticker, update.price, update.direction, etc.
};
```

EventSource automatically reconnects on disconnect. The `": connected"` SSE comment above fires the `open` event immediately, enabling the frontend connection-status indicator.

---

## 8. Watchlist API Integration — `backend/routes/watchlist.py`

The provider must be notified when the watchlist changes so the cache stays consistent with the SSE stream.

```python
# backend/routes/watchlist.py (excerpt — key provider interactions shown)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import (
    get_watchlist,
    insert_watchlist_ticker,
    delete_watchlist_ticker,
    ticker_in_watchlist,
)
from market import get_market_data_provider

router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str


@router.get("/api/watchlist")
async def get_watchlist_route():
    """Return all watched tickers with their latest prices."""
    provider = get_market_data_provider()
    prices   = provider.get_prices()
    rows     = await get_watchlist()   # list[str] of tickers from DB

    result = []
    for ticker in rows:
        p = prices.get(ticker)
        if p is None:
            # Ticker in DB but not yet in provider cache — should not happen in
            # normal operation (lifespan seeds them all), but handle defensively.
            p = await provider.add_ticker(ticker)
        session_change_pct = (
            (p.price - p.session_open) / p.session_open * 100.0
            if p.session_open > 0 else 0.0
        )
        result.append({
            "ticker":             ticker,
            "price":              round(p.price, 4),
            "prev_price":         round(p.prev_price, 4),
            "session_open":       round(p.session_open, 4),
            "session_change_pct": round(session_change_pct, 4),
        })
    return result


@router.post("/api/watchlist", status_code=201)
async def add_ticker_route(body: AddTickerRequest):
    """Add a ticker to the watchlist. Returns its initial price."""
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker is required")
    if await ticker_in_watchlist(ticker):
        raise HTTPException(status_code=409, detail=f"{ticker} is already on the watchlist")

    # 1. Persist to DB
    await insert_watchlist_ticker(ticker)

    # 2. Register with provider — this initialises the cache entry immediately
    #    so the SSE stream has a valid price before the HTTP response returns.
    provider = get_market_data_provider()
    update   = await provider.add_ticker(ticker)

    session_change_pct = (
        (update.price - update.session_open) / update.session_open * 100.0
        if update.session_open > 0 else 0.0
    )
    return {
        "ticker":             ticker,
        "price":              round(update.price, 4),
        "prev_price":         round(update.prev_price, 4),
        "session_open":       round(update.session_open, 4),
        "session_change_pct": round(session_change_pct, 4),
    }


@router.delete("/api/watchlist/{ticker}", status_code=200)
async def remove_ticker_route(ticker: str):
    """Remove a ticker from the watchlist."""
    ticker = ticker.strip().upper()
    if not await ticker_in_watchlist(ticker):
        raise HTTPException(status_code=404, detail=f"{ticker} not found on watchlist")

    await delete_watchlist_ticker(ticker)
    provider = get_market_data_provider()
    await provider.remove_ticker(ticker)
    return {"ok": True}
```

### Race-condition guarantee

```
Client                Backend
  │                      │
  │  POST /api/watchlist  │
  │ ──────────────────→  │
  │                      │  insert_watchlist_ticker("PYPL")
  │                      │  provider.add_ticker("PYPL")     ← cache["PYPL"] set HERE
  │                      │  return {"ticker": "PYPL", "price": 100.0, ...}
  │ ←──────────────────  │
  │                      │
  │  GET /api/stream/prices (next push cycle, 500 ms later)
  │ ←──────────────────  │  {"ticker": "PYPL", ...}  ← cache entry already exists
```

`add_ticker()` is awaited synchronously before the HTTP response is sent. By the time the client receives the 201 and sets up any UI state, the provider cache already contains the new ticker.

---

## 9. Portfolio Snapshot Background Task

The portfolio snapshot task reads from the provider's cache to compute total portfolio value. It is independent of the market data module itself — it calls `get_prices()` and queries the DB for positions.

```python
# backend/tasks/snapshots.py
import asyncio
import logging
from datetime import datetime, timezone

from db import get_positions, get_cash_balance, insert_portfolio_snapshot
from market import get_market_data_provider

logger = logging.getLogger(__name__)
SNAPSHOT_INTERVAL = 30  # seconds


async def run_snapshot_task() -> None:
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        try:
            await take_snapshot()
        except Exception:
            logger.exception("Snapshot task error")


async def take_snapshot(user_id: str = "default") -> None:
    """Compute and persist total portfolio value right now."""
    provider  = get_market_data_provider()
    prices    = provider.get_prices()
    positions = await get_positions(user_id)
    cash      = await get_cash_balance(user_id)

    holdings_value = sum(
        pos["quantity"] * prices[pos["ticker"]].price
        for pos in positions
        if pos["ticker"] in prices
    )
    total_value = cash + holdings_value

    await insert_portfolio_snapshot(
        user_id=user_id,
        total_value=total_value,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
```

Wire the task into the lifespan alongside the provider:

```python
# backend/main.py  (lifespan, updated)
from tasks.snapshots import run_snapshot_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    provider = get_market_data_provider()
    for ticker in await get_watchlist_tickers():
        await provider.add_ticker(ticker)
    await provider.start()

    snapshot_task = asyncio.create_task(run_snapshot_task())

    yield

    snapshot_task.cancel()
    await provider.stop()
```

---

## 10. Error Handling Policy

| Scenario | Behaviour |
|----------|-----------|
| Massive API returns 429 | `raise_for_status()` raises; caught in `_poll_loop`; previous cache values persist; next attempt after `poll_interval` |
| Massive API returns 403 | Same as above; logged as ERROR (misconfigured key) |
| Network timeout | `httpx.TimeoutException` caught; same result |
| `_fetch_single` fails at add_ticker | Falls back to `SEED_PRICES` or $100.00; no exception propagated to caller |
| Simulator NumPy error | Caught in `_tick_loop`; logged; no crash |
| Slow SSE client | `QueueFull` drops oldest item; client continues receiving (may miss a tick) |
| Client disconnects SSE | `CancelledError` fires in generator; `unsubscribe(on_price)` called; no memory leak |

---

## 11. Testing

### Unit tests for the simulator

```python
# backend/tests/test_simulator.py
import asyncio
import pytest
from market.simulator import SimulatedMarketData

@pytest.mark.asyncio
async def test_add_ticker_initialises_cache():
    sim = SimulatedMarketData(seed=42)
    update = await sim.add_ticker("AAPL")
    assert update.ticker == "AAPL"
    assert update.price == 190.0         # seed price
    assert update.session_open == 190.0
    assert update.direction == "flat"
    prices = sim.get_prices()
    assert "AAPL" in prices

@pytest.mark.asyncio
async def test_remove_ticker_purges_cache():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    await sim.remove_ticker("AAPL")
    assert "AAPL" not in sim.get_prices()

@pytest.mark.asyncio
async def test_subscriber_receives_updates():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")

    received = []
    async def capture(update):
        received.append(update)

    sim.subscribe(capture)
    await sim.start()
    await asyncio.sleep(1.2)   # allow ≥2 ticks at 500 ms interval
    await sim.stop()

    assert len(received) >= 2
    assert all(u.ticker == "AAPL" for u in received)

@pytest.mark.asyncio
async def test_gbm_prices_always_positive():
    sim = SimulatedMarketData(seed=0)
    await sim.add_ticker("TSLA")   # most volatile ticker
    await sim.start()
    await asyncio.sleep(5.0)       # 10 ticks
    await sim.stop()
    prices = sim.get_prices()
    assert prices["TSLA"].price > 0

@pytest.mark.asyncio
async def test_unknown_ticker_starts_at_100():
    sim = SimulatedMarketData(seed=42)
    update = await sim.add_ticker("XYZZY")
    assert update.price == 100.0
```

### Unit tests for Massive client (httpx mock)

```python
# backend/tests/test_massive.py
import asyncio
import pytest
import respx
import httpx
from market.massive import MassiveMarketData, BASE_URL

MOCK_SNAPSHOT = {
    "tickers": [
        {
            "ticker": "AAPL",
            "lastTrade": {"p": 192.50},
            "day": {"c": 192.40},
            "min": {"c": 192.45},
        }
    ]
}

@pytest.mark.asyncio
async def test_add_ticker_fetches_live_price():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test")
        update = await provider.add_ticker("AAPL")
        await provider.stop()

    assert update.ticker == "AAPL"
    assert update.price == 192.5    # lastTrade.p takes priority

@pytest.mark.asyncio
async def test_add_ticker_falls_back_on_error():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(500)
        )
        provider = MassiveMarketData(api_key="test")
        update = await provider.add_ticker("AAPL")
        await provider.stop()

    assert update.price == 190.0   # SEED_PRICES["AAPL"]

@pytest.mark.asyncio
async def test_poll_updates_cache_and_calls_subscribers():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test", poll_interval=0.1)
        await provider.add_ticker("AAPL")

        received = []
        async def capture(u): received.append(u)
        provider.subscribe(capture)

        await provider.start()
        await asyncio.sleep(0.35)   # ≥3 poll cycles at 0.1 s
        await provider.stop()

    assert len(received) >= 3
```

### Interface conformance test (runs both implementations)

```python
# backend/tests/test_provider_interface.py
import asyncio
import pytest
from market.simulator import SimulatedMarketData

@pytest.fixture
def provider():
    return SimulatedMarketData(seed=99)

@pytest.mark.asyncio
async def test_full_lifecycle(provider):
    update = await provider.add_ticker("MSFT")
    assert update.ticker == "MSFT"

    prices = provider.get_prices()
    assert "MSFT" in prices

    fired = []
    provider.subscribe(lambda u: fired.append(u) or asyncio.sleep(0))

    await provider.start()
    await asyncio.sleep(0.6)
    await provider.stop()

    assert len(fired) >= 1

    await provider.remove_ticker("MSFT")
    assert "MSFT" not in provider.get_prices()
```

---

## 12. Dependency Declaration

Add to `backend/pyproject.toml`:

```toml
[project]
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "httpx>=0.27.0",
    "numpy>=1.26.0",
    # massive SDK is optional — only needed if MASSIVE_API_KEY is set
    # "massive>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
]
```

`numpy` is a required dependency because the simulator uses it even in the default (no-API-key) configuration. The `massive` SDK is commented out — raw `httpx` calls are used instead, which avoids an opaque dependency and keeps the free-tier logic explicit.

---

## 13. Summary of Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single abstract base class | All downstream code (SSE, watchlist routes, snapshot task) is provider-agnostic; swapping simulator↔Massive requires only an env var change |
| Subscriber callback pattern for SSE | Each SSE client gets its own queue; there is no shared mutable list of queues inside the provider; unsubscribe is trivial |
| `add_ticker` returns `PriceUpdate` immediately | Eliminates the race condition where the frontend receives a ticker with no price — the HTTP response itself carries the initial price |
| `session_open` set at `add_ticker` time, never overwritten | Correct session change % across the whole backend session, even if the price oscillates back to its starting point |
| Exceptions swallowed inside poll/tick loops | A transient API error or NaN from GBM should not crash the SSE stream or lose subscriptions; stale cache is always preferable to a 500 |
| `QueueFull` drops oldest item for slow SSE clients | A slow client should not block or slow down all other subscribers; dropping a tick is harmless for a price display |
| Module-level singleton via `_provider` global | The factory is called from multiple request handlers; Python's GIL makes this safe without a lock |
