#!/usr/bin/env python3
"""
FinAlly Market Data Demo — live terminal dashboard.

Run from backend/:
    uv run python market_data_demo.py

Press Ctrl+C to exit.
"""

import asyncio
import os
import sys
from collections import deque
from datetime import datetime

# Allow running as a standalone script from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from market.simulator import SEED_PRICES, SimulatedMarketData

# ── configuration ─────────────────────────────────────────────────────────────

TICKERS = list(SEED_PRICES.keys())
SPARKLINE_LEN = 24          # price points kept per ticker
EVENT_LOG_LEN = 12          # lines in the event log
REFRESH_HZ    = 10          # UI redraws per second
EVENT_THRESHOLD = 0.005     # flag moves > 0.5% in a single tick as events

SPARK_CHARS = "▁▂▃▄▅▆▇█"

# ── helpers ───────────────────────────────────────────────────────────────────

def _sparkline(prices: deque) -> str:
    vals = list(prices)
    if len(vals) < 2:
        return "·" * len(vals)
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return "─" * len(vals)
    n = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[round((p - lo) / (hi - lo) * n)] for p in vals)


def _arrow(direction: str) -> str:
    return {"up": "▲", "down": "▼"}.get(direction, "●")


def _color(direction: str) -> str:
    return {"up": "green", "down": "red"}.get(direction, "white")


# ── state ─────────────────────────────────────────────────────────────────────

class DemoState:
    def __init__(self):
        from market.base import PriceUpdate
        self.latest:    dict[str, "PriceUpdate"] = {}
        self.history:   dict[str, deque]         = {t: deque(maxlen=SPARKLINE_LEN) for t in TICKERS}
        self.events:    deque[str]               = deque(maxlen=EVENT_LOG_LEN)
        self.tick_count = 0
        self.started_at = datetime.now()

    async def on_price(self, update) -> None:
        prev = self.latest.get(update.ticker)
        self.latest[update.ticker] = update

        if update.ticker in self.history:
            self.history[update.ticker].append(update.price)

        # Detect notable single-tick moves
        if prev:
            move = abs(update.price - prev.price) / prev.price
            if move >= EVENT_THRESHOLD:
                pct  = (update.price - prev.price) / prev.price * 100
                sign = "+" if pct > 0 else ""
                col  = "green" if pct > 0 else "red"
                ts   = update.timestamp.strftime("%H:%M:%S")
                self.events.appendleft(
                    f"[dim]{ts}[/dim]  "
                    f"[bold white]{update.ticker:<6}[/bold white]  "
                    f"[{col}]{_arrow(update.direction)} ${update.price:>8.2f}  {sign}{pct:+.2f}%[/{col}]  "
                    f"[bold yellow]⚡ EVENT[/bold yellow]"
                )

        self.tick_count += 1


# ── rendering ─────────────────────────────────────────────────────────────────

def _header(state: DemoState) -> Panel:
    elapsed = int((datetime.now() - state.started_at).total_seconds())
    t = Text(justify="center")
    t.append("  F I N A L L Y  ", style="bold yellow")
    t.append("Market Data Demo  ", style="bold white")
    t.append("● LIVE", style="bold green")
    t.append(f"   ticks: {state.tick_count}", style="dim")
    t.append(f"   uptime: {elapsed // 60:02d}:{elapsed % 60:02d}  ", style="dim")
    return Panel(t, border_style="yellow", style="on #0d1117", padding=(0, 1))


def _watchlist(state: DemoState) -> Panel:
    tbl = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold yellow",
        border_style="dim blue",
        expand=True,
        show_edge=True,
        padding=(0, 1),
    )
    tbl.add_column("TICKER",    style="bold white",  width=7)
    tbl.add_column("PRICE",     justify="right",     width=11)
    tbl.add_column("  ",        justify="center",    width=2)   # arrow
    tbl.add_column("SESSION %", justify="right",     width=10)
    tbl.add_column("PREV",      justify="right",     width=10)
    tbl.add_column("SPARKLINE " + "·" * SPARKLINE_LEN, min_width=SPARKLINE_LEN + 2)

    for ticker in TICKERS:
        u = state.latest.get(ticker)
        if u is None:
            tbl.add_row(ticker, "—", "—", "—", "—", "")
            continue

        col  = _color(u.direction)
        pct  = (u.price - u.session_open) / u.session_open * 100 if u.session_open else 0.0
        sign = "+" if pct >= 0 else ""
        spark = _sparkline(state.history[ticker]) if ticker in state.history else ""

        tbl.add_row(
            f"[bold]{ticker}[/bold]",
            f"[{col} bold]${u.price:>9.2f}[/{col} bold]",
            f"[{col} bold]{_arrow(u.direction)}[/{col} bold]",
            f"[{col}]{sign}{pct:.2f}%[/{col}]",
            f"[dim]${u.prev_price:.2f}[/dim]",
            f"[{col}]{spark}[/{col}]",
        )

    return Panel(
        tbl,
        title="[bold yellow]  Watchlist[/bold yellow]",
        border_style="blue dim",
        style="on #0d1117",
    )


def _event_log(state: DemoState) -> Panel:
    if not state.events:
        body = Text(
            "Waiting for events — moves >{:.0f}% per tick (~2% probability each 500 ms) …".format(
                EVENT_THRESHOLD * 100
            ),
            style="dim italic",
        )
    else:
        body = Text.from_markup("\n".join(state.events))

    return Panel(
        body,
        title="[bold yellow]  ⚡ Event Log[/bold yellow]",
        border_style="yellow dim",
        style="on #0d1117",
    )


def _build_layout(state: DemoState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header",    size=3),
        Layout(name="watchlist", ratio=3),
        Layout(name="events",    ratio=2),
    )
    layout["header"].update(_header(state))
    layout["watchlist"].update(_watchlist(state))
    layout["events"].update(_event_log(state))
    return layout


# ── main ──────────────────────────────────────────────────────────────────────

async def run() -> None:
    console = Console()
    state   = DemoState()
    sim     = SimulatedMarketData()

    console.print("[yellow]Starting simulator…[/yellow]")
    for ticker in TICKERS:
        update = await sim.add_ticker(ticker)
        state.latest[ticker] = update
        # Pre-fill history so sparklines aren't empty on launch
        for _ in range(SPARKLINE_LEN // 2):
            state.history[ticker].append(update.price)

    sim.subscribe(state.on_price)
    await sim.start()

    try:
        with Live(console=console, refresh_per_second=REFRESH_HZ, screen=True) as live:
            while True:
                live.update(_build_layout(state))
                await asyncio.sleep(1.0 / REFRESH_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        await sim.stop()
        console.print("\n[yellow]Simulator stopped. Goodbye![/yellow]")


if __name__ == "__main__":
    asyncio.run(run())
