from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import numpy as np

from .base import MarketDataProvider, PriceCallback, PriceUpdate

logger = logging.getLogger(__name__)

TICK_INTERVAL = 0.5  # seconds between price updates

_TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # ≈ 5,896,800 s/yr
DT = TICK_INTERVAL / _TRADING_SECONDS_PER_YEAR  # ≈ 8.48e-8 yr

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

TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL": {"sigma": 0.25, "mu": 0.12},
    "GOOGL": {"sigma": 0.28, "mu": 0.10},
    "MSFT": {"sigma": 0.22, "mu": 0.14},
    "AMZN": {"sigma": 0.30, "mu": 0.12},
    "TSLA": {"sigma": 0.65, "mu": 0.08},
    "NVDA": {"sigma": 0.55, "mu": 0.18},
    "META": {"sigma": 0.35, "mu": 0.10},
    "JPM": {"sigma": 0.20, "mu": 0.10},
    "V": {"sigma": 0.18, "mu": 0.12},
    "NFLX": {"sigma": 0.38, "mu": 0.08},
}

DEFAULT_SIGMA = 0.25
DEFAULT_MU = 0.10

_DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

_DEFAULT_CORR = np.array(
    [
        #      AAPL  GOOGL  MSFT  AMZN  TSLA  NVDA  META   JPM     V  NFLX
        [1.00, 0.65, 0.70, 0.60, 0.40, 0.55, 0.60, 0.25, 0.30, 0.45],  # AAPL
        [0.65, 1.00, 0.65, 0.55, 0.35, 0.50, 0.65, 0.20, 0.25, 0.50],  # GOOGL
        [0.70, 0.65, 1.00, 0.58, 0.38, 0.55, 0.62, 0.28, 0.32, 0.42],  # MSFT
        [0.60, 0.55, 0.58, 1.00, 0.42, 0.48, 0.58, 0.25, 0.30, 0.55],  # AMZN
        [0.40, 0.35, 0.38, 0.42, 1.00, 0.50, 0.38, 0.18, 0.20, 0.32],  # TSLA
        [0.55, 0.50, 0.55, 0.48, 0.50, 1.00, 0.52, 0.22, 0.25, 0.40],  # NVDA
        [0.60, 0.65, 0.62, 0.58, 0.38, 0.52, 1.00, 0.22, 0.28, 0.48],  # META
        [0.25, 0.20, 0.28, 0.25, 0.18, 0.22, 0.22, 1.00, 0.55, 0.20],  # JPM
        [0.30, 0.25, 0.32, 0.30, 0.20, 0.25, 0.28, 0.55, 1.00, 0.22],  # V
        [0.45, 0.50, 0.42, 0.55, 0.32, 0.40, 0.48, 0.20, 0.22, 1.00],  # NFLX
    ],
    dtype=np.float64,
)

_CHOLESKY: np.ndarray = np.linalg.cholesky(_DEFAULT_CORR)


def _gbm_step(price: float, mu: float, sigma: float, z: float) -> float:
    """One GBM tick using the exact discretisation. Returns new price, guaranteed > 0."""
    exponent = (mu - 0.5 * sigma**2) * DT + sigma * (DT**0.5) * z
    return max(float(price * np.exp(exponent)), 0.01)


class SimulatedMarketData(MarketDataProvider):
    """
    GBM-driven price simulator. Updates every 500 ms.
    Pass seed= for deterministic sequences (useful in tests).
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)
        self._prices: dict[str, float] = {}
        self._session_opens: dict[str, float] = {}
        self._cache: dict[str, PriceUpdate] = {}
        self._subscribers: list[PriceCallback] = []
        self._task: asyncio.Task | None = None

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
        known = [t for t in tickers if t in _DEFAULT_TICKERS]
        unknown = [t for t in tickers if t not in _DEFAULT_TICKERS]
        updates: list[PriceUpdate] = []

        if known:
            z_full = self._rng.standard_normal(len(_DEFAULT_TICKERS))
            z_corr = _CHOLESKY @ z_full
            for ticker in known:
                idx = _DEFAULT_TICKERS.index(ticker)
                params = TICKER_PARAMS[ticker]
                new_price = _gbm_step(
                    self._prices[ticker], params["mu"], params["sigma"], float(z_corr[idx])
                )
                updates.append(self._make_update(ticker, new_price, now))

        for ticker in unknown:
            z = float(self._rng.standard_normal())
            new_price = _gbm_step(self._prices[ticker], DEFAULT_MU, DEFAULT_SIGMA, z)
            updates.append(self._make_update(ticker, new_price, now))

        if tickers and self._rng.random() < 0.02:
            event_ticker = tickers[int(self._rng.integers(0, len(tickers)))]
            magnitude = float(self._rng.uniform(0.02, 0.05))
            sign = float(self._rng.choice(np.array([-1.0, 1.0])))
            updates = [
                self._make_update(event_ticker, max(u.price * (1.0 + sign * magnitude), 0.01), now)
                if u.ticker == event_ticker
                else u
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
