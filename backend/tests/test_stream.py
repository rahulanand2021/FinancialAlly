"""
Tests for the SSE /api/stream/prices route.

httpx.ASGITransport buffers the entire response body before returning, so it
cannot test infinite SSE generators via HTTP. Instead, we call stream_prices()
directly and drive the async generator ourselves — no HTTP layer needed.
"""

import asyncio
import json

import pytest

from market.simulator import SimulatedMarketData


def _patch_provider(provider):
    """Replace the provider reference in routes.stream for this test."""
    import routes.stream as stream_module
    stream_module.get_market_data_provider = lambda: provider


@pytest.mark.asyncio
async def test_sse_response_headers():
    """StreamingResponse is configured with correct media type and cache headers."""
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    _patch_provider(sim)

    from routes.stream import stream_prices

    response = await stream_prices()
    assert response.media_type == "text/event-stream"
    assert response.headers.get("cache-control") == "no-cache"
    assert response.headers.get("x-accel-buffering") == "no"


@pytest.mark.asyncio
async def test_sse_initial_connected_comment():
    """Generator yields ': connected\\n\\n' as the very first chunk."""
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    _patch_provider(sim)

    from routes.stream import stream_prices

    response = await stream_prices()
    gen = response.body_iterator

    first_chunk = await gen.__anext__()
    await gen.aclose()

    if isinstance(first_chunk, bytes):
        first_chunk = first_chunk.decode()
    assert ": connected" in first_chunk


@pytest.mark.asyncio
async def test_sse_event_json_shape():
    """After a price tick, the generator yields a data: line with all required fields."""
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    _patch_provider(sim)
    await sim.start()

    from routes.stream import stream_prices

    response = await stream_prices()
    gen = response.body_iterator

    # First chunk is always ": connected"
    await gen.__anext__()

    # Second chunk should be a price update within 2 ticks (≤ 1 s)
    raw = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await gen.aclose()
    await sim.stop()

    if isinstance(raw, bytes):
        raw = raw.decode()

    assert raw.startswith("data: ")
    payload = json.loads(raw[len("data: "):].strip())
    assert set(payload.keys()) >= {"ticker", "price", "prev_price", "session_open", "timestamp", "direction"}
    assert payload["ticker"] == "AAPL"
    assert isinstance(payload["price"], float)
    assert payload["price"] > 0
    assert payload["direction"] in ("up", "down", "flat")


@pytest.mark.asyncio
async def test_sse_unsubscribes_on_close():
    """Closing the generator calls unsubscribe via the finally block."""
    sim = SimulatedMarketData(seed=42)
    await sim.add_ticker("AAPL")
    _patch_provider(sim)

    assert len(sim._subscribers) == 0

    from routes.stream import stream_prices

    response = await stream_prices()
    gen = response.body_iterator

    # Consume first chunk so the generator is running and subscriber is active
    await gen.__anext__()
    assert len(sim._subscribers) == 1

    # aclose() triggers the finally block → unsubscribe
    await gen.aclose()
    await asyncio.sleep(0.05)

    assert len(sim._subscribers) == 0
