"""
Interface conformance tests — verifies that SimulatedMarketData satisfies
the full MarketDataProvider contract. These tests run against the simulator
(no network required) but document the contract both implementations must meet.
"""

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
    assert update.price > 0

    prices = provider.get_prices()
    assert "MSFT" in prices

    fired = []

    async def capture(u):
        fired.append(u)

    provider.subscribe(capture)
    await provider.start()
    await asyncio.sleep(0.6)
    await provider.stop()

    assert len(fired) >= 1

    await provider.remove_ticker("MSFT")
    assert "MSFT" not in provider.get_prices()


@pytest.mark.asyncio
async def test_add_returns_valid_price_update(provider):
    update = await provider.add_ticker("AAPL")
    assert update.ticker == "AAPL"
    assert isinstance(update.price, float)
    assert update.price > 0
    assert update.prev_price == update.price  # initial state: no previous price
    assert update.session_open == update.price
    assert update.direction == "flat"
    assert update.timestamp is not None


@pytest.mark.asyncio
async def test_cache_entry_exists_immediately_after_add(provider):
    """Verifies the race-condition guarantee: cache populated before return."""
    await provider.add_ticker("TSLA")
    prices = provider.get_prices()
    assert "TSLA" in prices
    assert prices["TSLA"].price > 0


@pytest.mark.asyncio
async def test_remove_purges_cache(provider):
    await provider.add_ticker("GOOGL")
    assert "GOOGL" in provider.get_prices()

    await provider.remove_ticker("GOOGL")
    assert "GOOGL" not in provider.get_prices()


@pytest.mark.asyncio
async def test_subscribe_and_receive_updates(provider):
    await provider.add_ticker("AAPL")

    updates = []

    async def on_update(u):
        updates.append(u)

    provider.subscribe(on_update)
    await provider.start()
    await asyncio.sleep(1.2)
    await provider.stop()

    assert len(updates) >= 2
    assert all(u.ticker == "AAPL" for u in updates)


@pytest.mark.asyncio
async def test_unsubscribe_removes_callback(provider):
    await provider.add_ticker("AAPL")

    updates = []

    async def on_update(u):
        updates.append(u)

    provider.subscribe(on_update)
    await provider.start()
    await asyncio.sleep(0.6)
    provider.unsubscribe(on_update)
    count = len(updates)
    await asyncio.sleep(0.6)
    await provider.stop()

    assert len(updates) == count  # no new updates after unsubscribe


@pytest.mark.asyncio
async def test_multiple_subscribers(provider):
    await provider.add_ticker("AAPL")

    received_a = []
    received_b = []

    async def cb_a(u):
        received_a.append(u)

    async def cb_b(u):
        received_b.append(u)

    provider.subscribe(cb_a)
    provider.subscribe(cb_b)
    await provider.start()
    await asyncio.sleep(1.2)
    await provider.stop()

    assert len(received_a) >= 2
    assert len(received_b) >= 2


@pytest.mark.asyncio
async def test_get_prices_is_snapshot(provider):
    await provider.add_ticker("AAPL")
    snapshot = provider.get_prices()
    assert isinstance(snapshot, dict)
    assert "AAPL" in snapshot


@pytest.mark.asyncio
async def test_start_stop_idempotent_stop(provider):
    await provider.add_ticker("AAPL")
    await provider.start()
    await asyncio.sleep(0.1)
    await provider.stop()
    await provider.stop()  # second stop should not raise
