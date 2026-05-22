"""Portfolio REST endpoints."""

from __future__ import annotations

import logging
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import crud, get_db
from services import TradeError, execute_trade, get_portfolio_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0)
    side: Literal["buy", "sell"]


@router.get("")
async def get_portfolio(conn: aiosqlite.Connection = Depends(get_db)) -> dict:
    return await get_portfolio_state(conn)


@router.post("/trade")
async def trade(
    body: TradeRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> dict:
    try:
        return await execute_trade(conn, body.ticker, body.side, body.quantity)
    except TradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/history")
async def history(conn: aiosqlite.Connection = Depends(get_db)) -> list[dict]:
    return await crud.list_portfolio_snapshots(conn)
