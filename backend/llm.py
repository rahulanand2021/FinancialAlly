"""LLM integration for FinAlly chat assistant.

Calls openrouter/openai/gpt-oss-120b via LiteLLM with Cerebras as the
inference provider, requesting structured JSON output that may include
trades and watchlist changes to auto-execute.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from litellm import completion
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.

Your job:
- Analyze the user's portfolio composition, concentration risk, and unrealized P&L.
- Suggest trades with clear, data-driven reasoning.
- Execute trades when the user asks or agrees, by populating the `trades` field.
- Proactively manage the watchlist with the `watchlist_changes` field.
- Keep replies concise and grounded in the portfolio context provided below.

Rules:
- Use market orders only (instant fill at the current price).
- Only place trades the user has authorized or explicitly requested.
- Never invent prices or positions; rely on the supplied context.
- Always respond with a valid JSON object matching the required schema."""

MOCK_RESPONSE = {
    "message": (
        "I've reviewed your portfolio. You have $10,000 in cash and no open positions. "
        "I've added NVDA to your watchlist and bought 5 shares of AAPL to get you started."
    ),
    "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}],
    "watchlist_changes": [{"ticker": "NVDA", "action": "add"}],
}


class TradeAction(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistAction(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistAction] = Field(default_factory=list)


def _is_mock() -> bool:
    return os.getenv("LLM_MOCK", "").strip().lower() == "true"


def build_portfolio_context(
    cash_balance: float,
    total_value: float,
    positions: list[dict],
    watchlist: list[dict],
) -> str:
    """Render the user's portfolio + watchlist into a compact text block."""
    lines = [
        "=== PORTFOLIO CONTEXT ===",
        f"Cash balance: ${cash_balance:,.2f}",
        f"Total portfolio value: ${total_value:,.2f}",
        "",
        "Positions:",
    ]
    if not positions:
        lines.append("  (none)")
    else:
        for p in positions:
            lines.append(
                f"  {p['ticker']}: qty={p['quantity']:g}, "
                f"avg_cost=${p['avg_cost']:.2f}, "
                f"current=${p['current_price']:.2f}, "
                f"unrealized_pnl=${p['unrealized_pnl']:.2f} "
                f"({p['unrealized_pnl_pct']:+.2f}%)"
            )
    lines.append("")
    lines.append("Watchlist:")
    if not watchlist:
        lines.append("  (empty)")
    else:
        for w in watchlist:
            change = w.get("session_change_pct", 0.0)
            lines.append(
                f"  {w['ticker']}: ${w['price']:.2f} ({change:+.2f}% today)"
            )
    return "\n".join(lines)


def _build_messages(
    portfolio_context: str,
    history: list[dict],
    user_message: str,
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": portfolio_context},
        *history,
        {"role": "user", "content": user_message},
    ]


def generate_response(
    user_message: str,
    portfolio_context: str,
    history: list[dict],
) -> ChatResponse:
    """Call the LLM and return a parsed ChatResponse.

    Returns the fixed mock response when LLM_MOCK=true. On parse/transport
    errors, returns a ChatResponse with a graceful error message and no actions.
    """
    if _is_mock():
        return ChatResponse.model_validate(MOCK_RESPONSE)

    messages = _build_messages(portfolio_context, history, user_message)
    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=ChatResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
        raw = response.choices[0].message.content
        return ChatResponse.model_validate_json(raw)
    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        return ChatResponse(
            message=(
                "Sorry, I couldn't process that request right now. "
                "Please try again in a moment."
            ),
            trades=[],
            watchlist_changes=[],
        )


__all__ = [
    "ChatResponse",
    "TradeAction",
    "WatchlistAction",
    "MOCK_RESPONSE",
    "SYSTEM_PROMPT",
    "MODEL",
    "HISTORY_LIMIT",
    "build_portfolio_context",
    "generate_response",
]
