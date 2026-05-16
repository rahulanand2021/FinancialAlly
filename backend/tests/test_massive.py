import asyncio

import httpx
import pytest
import respx

from market.massive import MassiveMarketData, BASE_URL, SEED_PRICES

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

MOCK_SNAPSHOT_NO_LAST_TRADE = {
    "tickers": [
        {
            "ticker": "GOOGL",
            "lastTrade": None,
            "day": {"c": 175.80},
            "min": {"c": 175.70},
        }
    ]
}

MOCK_SNAPSHOT_MULTI = {
    "tickers": [
        {
            "ticker": "AAPL",
            "lastTrade": {"p": 192.50},
            "day": {"c": 192.40},
            "min": None,
        },
        {
            "ticker": "MSFT",
            "lastTrade": {"p": 420.10},
            "day": {"c": 420.00},
            "min": None,
        },
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
    assert update.price == 192.5  # lastTrade.p takes priority


@pytest.mark.asyncio
async def test_add_ticker_falls_back_on_500():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(500)
        )
        provider = MassiveMarketData(api_key="test")
        update = await provider.add_ticker("AAPL")
        await provider.stop()

    assert update.price == SEED_PRICES["AAPL"]


@pytest.mark.asyncio
async def test_add_ticker_falls_back_for_unknown_ticker():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(500)
        )
        provider = MassiveMarketData(api_key="test")
        update = await provider.add_ticker("XYZZY")
        await provider.stop()

    assert update.price == 100.0  # default fallback


@pytest.mark.asyncio
async def test_add_ticker_uses_min_close_when_no_last_trade():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT_NO_LAST_TRADE)
        )
        provider = MassiveMarketData(api_key="test")
        update = await provider.add_ticker("GOOGL")
        await provider.stop()

    assert update.price == 175.70  # min.c takes priority over day.c


@pytest.mark.asyncio
async def test_remove_ticker_clears_cache():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test")
        await provider.add_ticker("AAPL")
        assert "AAPL" in provider.get_prices()

        await provider.remove_ticker("AAPL")
        await provider.stop()

    assert "AAPL" not in provider.get_prices()


@pytest.mark.asyncio
async def test_remove_nonexistent_ticker_no_error():
    provider = MassiveMarketData(api_key="test")
    await provider.remove_ticker("XYZZY")  # should not raise
    await provider.stop()


@pytest.mark.asyncio
async def test_poll_updates_cache_and_calls_subscribers():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test", poll_interval=0.1)
        await provider.add_ticker("AAPL")

        received = []

        async def capture(u):
            received.append(u)

        provider.subscribe(capture)
        await provider.start()
        await asyncio.sleep(0.35)  # ≥3 poll cycles at 0.1 s
        await provider.stop()

    assert len(received) >= 3


@pytest.mark.asyncio
async def test_poll_handles_api_error_gracefully():
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (add_ticker) fails
            return httpx.Response(500)
        # Poll calls also fail
        return httpx.Response(429)

    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(side_effect=side_effect)
        provider = MassiveMarketData(api_key="test", poll_interval=0.1)
        await provider.add_ticker("AAPL")  # falls back to seed
        await provider.start()
        await asyncio.sleep(0.35)  # poll cycles fail but don't crash
        await provider.stop()

    # Should still have the seed price from add_ticker fallback
    assert provider.get_prices()["AAPL"].price == SEED_PRICES["AAPL"]


@pytest.mark.asyncio
async def test_direction_tracking():
    # Two sequential poll responses with different prices
    prices = [192.50, 193.00]
    call_index = [0]

    def side_effect(request):
        price = prices[min(call_index[0], len(prices) - 1)]
        call_index[0] += 1
        return httpx.Response(
            200,
            json={
                "tickers": [
                    {"ticker": "AAPL", "lastTrade": {"p": price}, "day": None, "min": None}
                ]
            },
        )

    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(side_effect=side_effect)
        provider = MassiveMarketData(api_key="test", poll_interval=0.1)
        await provider.add_ticker("AAPL")  # gets 192.50

        received = []

        async def capture(u):
            received.append(u)

        provider.subscribe(capture)
        await provider.start()
        await asyncio.sleep(0.25)
        await provider.stop()

    # The second poll at 193.00 should show "up" direction
    up_updates = [u for u in received if u.direction == "up"]
    assert len(up_updates) >= 1


@pytest.mark.asyncio
async def test_session_open_preserved_across_polls():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test", poll_interval=0.1)
        initial = await provider.add_ticker("AAPL")
        session_open = initial.session_open

        await provider.start()
        await asyncio.sleep(0.35)
        await provider.stop()

    prices = provider.get_prices()
    assert prices["AAPL"].session_open == session_open


@pytest.mark.asyncio
async def test_get_prices_returns_copy():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/v2/snapshot/locale/us/markets/stocks/tickers").mock(
            return_value=httpx.Response(200, json=MOCK_SNAPSHOT)
        )
        provider = MassiveMarketData(api_key="test")
        await provider.add_ticker("AAPL")
        prices1 = provider.get_prices()
        prices2 = provider.get_prices()
        await provider.stop()

    assert prices1 is not prices2


@pytest.mark.asyncio
async def test_stop_without_start():
    provider = MassiveMarketData(api_key="test")
    await provider.stop()  # should not raise
