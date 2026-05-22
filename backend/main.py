"""FinAlly FastAPI application.

Wires together the market data provider, SSE/REST routes, database initialization,
the portfolio snapshot loop, and the Next.js static export.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import crud, get_db_path, init_db
from market import get_market_data_provider
from routes.chat import router as chat_router
from routes.portfolio import router as portfolio_router
from routes.stream import router as stream_router
from routes.watchlist import router as watchlist_router
from tasks.snapshots import snapshot_loop

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

load_dotenv(PROJECT_ROOT / ".env")


async def _hydrate_watchlist() -> None:
    """Seed the market data cache from the persisted watchlist."""
    provider = get_market_data_provider()
    conn = await aiosqlite.connect(get_db_path())
    conn.row_factory = aiosqlite.Row
    try:
        tickers = await crud.list_watchlist(conn)
    finally:
        await conn.close()
    for ticker in tickers:
        await provider.add_ticker(ticker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    await init_db()
    provider = get_market_data_provider()
    await _hydrate_watchlist()
    await provider.start()
    snapshot_task = asyncio.create_task(snapshot_loop())
    logger.info("FinAlly backend started")
    try:
        yield
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        await provider.stop()
        logger.info("FinAlly backend stopped")


app = FastAPI(title="FinAlly", lifespan=lifespan)

app.include_router(stream_router)
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _mount_static() -> None:
    """Serve the Next.js static export with SPA-style fallback to index.html."""
    if not STATIC_DIR.exists():
        logger.warning("Static directory %s not found; UI routes will 404", STATIC_DIR)
        return

    app.mount("/_next", StaticFiles(directory=STATIC_DIR / "_next"), name="next-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        html_candidate = STATIC_DIR / f"{full_path}.html"
        if html_candidate.is_file():
            return FileResponse(html_candidate)
        return FileResponse(STATIC_DIR / "index.html")


_mount_static()
