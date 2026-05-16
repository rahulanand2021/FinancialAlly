from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Awaitable


@dataclass
class PriceUpdate:
    ticker: str
    price: float
    prev_price: float
    session_open: float
    timestamp: datetime
    direction: str  # "up" | "down" | "flat"


@dataclass
class TickerConfig:
    ticker: str
    seed_price: float = 100.0
    sigma: float = 0.02
    mu: float = 0.0001


PriceCallback = Callable[[PriceUpdate], Awaitable[None]]


class MarketDataProvider(ABC):
    """
    Live price feed for a dynamic watchlist of tickers.

    Lifecycle:
      1. Instantiate once (via the factory in __init__.py).
      2. Call start() at application startup.
      3. Add/remove tickers at any time.
      4. Call subscribe() to register async callbacks.
      5. Call stop() at application shutdown.

    Guarantees:
      - add_ticker() initialises a cache entry BEFORE returning.
      - remove_ticker() purges the cache entry atomically.
      - get_prices() is a synchronous snapshot.
      - Exceptions inside polling/tick cycles are caught and logged.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the background price update loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background loop and release resources."""

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
        if hasattr(self, "_subscribers"):
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass
