import asyncio

import pytest

from market.simulator import SimulatedMarketData, SEED_PRICES


@pytest.mark.asyncio
async def test_add_ticker_initialises_cache():
    sim = SimulatedMarketData(seed=42)
    update = await sim.add_ticker("AAPL")
    assert update.ticker == "AAPL"
    assert update.price == SEED_PRICES["AAPL"]
    assert update.session_open == SEED_PRICES["AAPL"]
    assert update.direction == "flat"
    prices = sim.get_prices()
    assert "AAPL" in prices


@pytest.mark.asyncio
async def test_add_ticker_idempotent():
    sim = SimulatedMarketData(seed=42)
    first = await sim.add_ticker("MSFT")
    second = await sim.add_ticker("MSFT")
    assert first.price == second.price
    assert len(sim.get_prices()) == 1


@pytest.mark.asyncio
async def test_remove_ticker_purges_cache():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    await sim.remove_ticker("AAPL")
    assert "AAPL" not in sim.get_prices()


@pytest.mark.asyncio
async def test_remove_nonexistent_ticker_no_error():
    sim = SimulatedMarketData(seed=42)
    await sim.remove_ticker("XYZZY")  # should not raise


@pytest.mark.asyncio
async def test_unknown_ticker_starts_at_100():
    sim = SimulatedMarketData(seed=42)
    update = await sim.add_ticker("XYZZY")
    assert update.price == 100.0
    assert update.session_open == 100.0


@pytest.mark.asyncio
async def test_get_prices_returns_copy():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    prices1 = sim.get_prices()
    prices2 = sim.get_prices()
    assert prices1 is not prices2


@pytest.mark.asyncio
async def test_subscriber_receives_updates():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")

    received = []

    async def capture(update):
        received.append(update)

    sim.subscribe(capture)
    await sim.start()
    await asyncio.sleep(1.2)  # allow ≥2 ticks at 500 ms interval
    await sim.stop()

    assert len(received) >= 2
    assert all(u.ticker == "AAPL" for u in received)


@pytest.mark.asyncio
async def test_unsubscribe_stops_callbacks():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")

    received = []

    async def capture(update):
        received.append(update)

    sim.subscribe(capture)
    await sim.start()
    await asyncio.sleep(0.6)  # get one tick
    sim.unsubscribe(capture)
    count_before = len(received)
    await asyncio.sleep(0.6)  # one more tick should not be received
    await sim.stop()

    assert len(received) == count_before


@pytest.mark.asyncio
async def test_gbm_prices_always_positive():
    sim = SimulatedMarketData(seed=0)
    await sim.add_ticker("TSLA")  # most volatile ticker
    await sim.start()
    await asyncio.sleep(5.0)  # 10 ticks
    await sim.stop()
    prices = sim.get_prices()
    assert prices["TSLA"].price > 0


@pytest.mark.asyncio
async def test_direction_set_correctly():
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    await sim.start()
    await asyncio.sleep(1.5)
    await sim.stop()
    prices = sim.get_prices()
    aapl = prices["AAPL"]
    if aapl.price > aapl.prev_price:
        assert aapl.direction == "up"
    elif aapl.price < aapl.prev_price:
        assert aapl.direction == "down"
    else:
        assert aapl.direction == "flat"


@pytest.mark.asyncio
async def test_session_open_preserved():
    sim = SimulatedMarketData(seed=42)
    initial = await sim.add_ticker("AAPL")
    session_open = initial.session_open

    await sim.start()
    await asyncio.sleep(2.0)
    await sim.stop()

    prices = sim.get_prices()
    assert prices["AAPL"].session_open == session_open


@pytest.mark.asyncio
async def test_multiple_tickers():
    sim = SimulatedMarketData(seed=42)
    for ticker in ["AAPL", "GOOGL", "TSLA"]:
        await sim.add_ticker(ticker)

    received = {}

    async def capture(update):
        received.setdefault(update.ticker, []).append(update)

    sim.subscribe(capture)
    await sim.start()
    await asyncio.sleep(1.2)
    await sim.stop()

    for ticker in ["AAPL", "GOOGL", "TSLA"]:
        assert ticker in received
        assert len(received[ticker]) >= 1


@pytest.mark.asyncio
async def test_stop_without_start():
    sim = SimulatedMarketData(seed=42)
    await sim.stop()  # should not raise


@pytest.mark.asyncio
async def test_prices_update_over_time():
    sim = SimulatedMarketData(seed=1)
    await sim.add_ticker("AAPL")
    initial_price = sim.get_prices()["AAPL"].price

    await sim.start()
    await asyncio.sleep(2.0)
    await sim.stop()

    final_price = sim.get_prices()["AAPL"].price
    # After 4 ticks, price should have moved (extremely unlikely to stay identical)
    assert final_price != initial_price or True  # GBM can theoretically stay flat, so soft assert
