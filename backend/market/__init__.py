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


def reset_provider() -> None:
    """Reset the singleton (for testing only)."""
    global _provider
    _provider = None
