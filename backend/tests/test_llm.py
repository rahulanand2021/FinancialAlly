"""Unit tests for the LLM module — mock mode and context construction."""

from __future__ import annotations

import os

import pytest

from llm import (
    MOCK_RESPONSE,
    ChatResponse,
    build_portfolio_context,
    generate_response,
)


def test_mock_mode_returns_fixed_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    response = generate_response("hello", "ctx", [])
    assert isinstance(response, ChatResponse)
    assert response.message == MOCK_RESPONSE["message"]
    assert len(response.trades) == 1
    assert response.trades[0].ticker == "AAPL"
    assert response.trades[0].side == "buy"
    assert response.trades[0].quantity == 5
    assert len(response.watchlist_changes) == 1
    assert response.watchlist_changes[0].ticker == "NVDA"
    assert response.watchlist_changes[0].action == "add"


def test_build_portfolio_context_includes_key_fields():
    positions = [
        {
            "ticker": "AAPL",
            "quantity": 10,
            "avg_cost": 180.0,
            "current_price": 190.0,
            "unrealized_pnl": 100.0,
            "unrealized_pnl_pct": 5.55,
        }
    ]
    watchlist = [{"ticker": "GOOGL", "price": 175.5, "session_change_pct": 1.2}]
    ctx = build_portfolio_context(
        cash_balance=8200.0,
        total_value=10100.0,
        positions=positions,
        watchlist=watchlist,
    )
    assert "Cash balance: $8,200.00" in ctx
    assert "Total portfolio value: $10,100.00" in ctx
    assert "AAPL" in ctx and "avg_cost=$180.00" in ctx
    assert "GOOGL" in ctx and "$175.50" in ctx


def test_build_portfolio_context_handles_empty():
    ctx = build_portfolio_context(10000.0, 10000.0, [], [])
    assert "(none)" in ctx
    assert "(empty)" in ctx


def test_chat_response_defaults_empty_actions():
    resp = ChatResponse(message="hi")
    assert resp.trades == []
    assert resp.watchlist_changes == []
