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
    """SSE endpoint that pushes price updates for the current watchlist."""
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
                    "ticker": update.ticker,
                    "price": round(update.price, 4),
                    "prev_price": round(update.prev_price, 4),
                    "session_open": round(update.session_open, 4),
                    "timestamp": update.timestamp.isoformat(),
                    "direction": update.direction,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            provider.unsubscribe(on_price)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
