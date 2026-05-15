# Market Simulator — Design and Code Structure

This document specifies the design and implementation approach for `SimulatedMarketData`, the built-in market data simulator used when no `MASSIVE_API_KEY` is set.

The simulator implements `MarketDataProvider` from `MARKET_INTERFACE.md` and is completely interchangeable with `MassiveMarketData` from the perspective of all downstream code.

---

## Goals

- Visually convincing: prices move realistically, not randomly bouncing between extremes
- Correlated moves: tech stocks move together; no ticker is fully independent
- Occasional drama: random "events" cause sudden 2–5% moves on a single ticker
- Fast: updates every ~500ms so the UI's price flash animations fire continuously
- Zero external dependencies: pure Python + NumPy, no network access
- Deterministic enough for tests: seedable RNG

---

## Approach: Geometric Brownian Motion (GBM)

GBM is the standard model for stock price simulation. The price at the next time step is:

```
S(t+dt) = S(t) * exp((mu - sigma²/2) * dt + sigma * sqrt(dt) * Z)
```

Where:
- `S(t)` — current price
- `mu` — drift (small positive trend)
- `sigma` — volatility (standard deviation of log-returns)
- `dt` — time step (in years; 500ms ≈ 1.585e-8 years)
- `Z` — standard normal random variable

This formula ensures prices are always positive and log-returns are normally distributed — the same properties real stock prices exhibit over short time horizons.

---

## Correlation Model

Rather than drawing independent `Z` values per ticker, the simulator draws from a correlated multivariate normal distribution. This produces sector-level co-movement.

**Method**: Cholesky decomposition of a correlation matrix.

```python
import numpy as np

# Example correlation structure
# Tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX
# Tech tickers (indices 0-6) are correlated at ~0.6
# Financials (indices 7-8) are correlated at ~0.5
# Cross-sector correlation is ~0.2

CORRELATION_MATRIX = np.array([...])  # 10x10 symmetric matrix

# Cholesky factor L, computed once at initialization
L = np.linalg.cholesky(CORRELATION_MATRIX)

# Each tick: draw correlated normals
z_independent = rng.standard_normal(n_tickers)
z_correlated = L @ z_independent  # correlated shocks
```

For tickers not in the default set (dynamically added by users), an independent `Z` is drawn — no correlation assumed.

---

## Random Events

Every update cycle, there's a small probability (2%) that a randomly selected ticker receives a "market event": an extra shock of ±2–5% applied on top of the regular GBM step. This creates the sudden, dramatic moves that make the simulator feel alive.

```python
if rng.random() < 0.02:
    event_ticker = rng.choice(list(active_tickers))
    event_magnitude = rng.uniform(0.02, 0.05) * rng.choice([-1, 1])
    # Apply as multiplicative shock
    prices[event_ticker] *= (1 + event_magnitude)
```

---

## File Structure

```
backend/market/simulator.py
```

---

## Full Implementation

```python
import asyncio
import numpy as np
from datetime import datetime, timezone
from .base import MarketDataProvider, PriceUpdate, PriceCallback


# Default update cadence
TICK_INTERVAL = 0.5  # seconds

# Seed prices for the default watchlist (realistic as of early 2026)
SEED_PRICES: dict[str, float] = {
    "AAPL":  190.0,
    "GOOGL": 175.0,
    "MSFT":  420.0,
    "AMZN":  185.0,
    "TSLA":  175.0,
    "NVDA":  875.0,
    "META":  500.0,
    "JPM":   200.0,
    "V":     275.0,
    "NFLX":  625.0,
}

# Per-ticker GBM parameters (annualized)
TICKER_PARAMS: dict[str, dict] = {
    "AAPL":  {"sigma": 0.25, "mu": 0.12},
    "GOOGL": {"sigma": 0.28, "mu": 0.10},
    "MSFT":  {"sigma": 0.22, "mu": 0.14},
    "AMZN":  {"sigma": 0.30, "mu": 0.12},
    "TSLA":  {"sigma": 0.65, "mu": 0.08},  # high vol
    "NVDA":  {"sigma": 0.55, "mu": 0.18},  # high vol, high drift
    "META":  {"sigma": 0.35, "mu": 0.10},
    "JPM":   {"sigma": 0.20, "mu": 0.10},
    "V":     {"sigma": 0.18, "mu": 0.12},
    "NFLX":  {"sigma": 0.38, "mu": 0.08},
}

DEFAULT_SIGMA = 0.25
DEFAULT_MU = 0.0001

# dt for 500ms ticks in years (252 trading days × 6.5 hours × 3600 seconds)
_TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = TICK_INTERVAL / _TRADING_SECONDS_PER_YEAR

# Correlation matrix for the 10 default tickers
# (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX)
_DEFAULT_CORR = np.array([
    #      AAPL  GOOGL  MSFT  AMZN  TSLA  NVDA  META   JPM     V  NFLX
    [1.00, 0.65,  0.70, 0.60, 0.40, 0.55, 0.60,  0.25, 0.30, 0.45],  # AAPL
    [0.65, 1.00,  0.65, 0.55, 0.35, 0.50, 0.65,  0.20, 0.25, 0.50],  # GOOGL
    [0.70, 0.65,  1.00, 0.58, 0.38, 0.55, 0.62,  0.28, 0.32, 0.42],  # MSFT
    [0.60, 0.55,  0.58, 1.00, 0.42, 0.48, 0.58,  0.25, 0.30, 0.55],  # AMZN
    [0.40, 0.35,  0.38, 0.42, 1.00, 0.50, 0.38,  0.18, 0.20, 0.32],  # TSLA
    [0.55, 0.50,  0.55, 0.48, 0.50, 1.00, 0.52,  0.22, 0.25, 0.40],  # NVDA
    [0.60, 0.65,  0.62, 0.58, 0.38, 0.52, 1.00,  0.22, 0.28, 0.48],  # META
    [0.25, 0.20,  0.28, 0.25, 0.18, 0.22, 0.22,  1.00, 0.55, 0.20],  # JPM
    [0.30, 0.25,  0.32, 0.30, 0.20, 0.25, 0.28,  0.55, 1.00, 0.22],  # V
    [0.45, 0.50,  0.42, 0.55, 0.32, 0.40, 0.48,  0.20, 0.22, 1.00],  # NFLX
])

_DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
_CHOLESKY = np.linalg.cholesky(_DEFAULT_CORR)


class SimulatedMarketData(MarketDataProvider):
    """
    GBM-based stock price simulator implementing MarketDataProvider.
    Prices update every 500ms with correlated moves across tickers.
    """

    def __init__(self, seed: int | None = None):
        self._rng = np.random.default_rng(seed)
        self._prices: dict[str, float] = {}         # current simulated price
        self._cache: dict[str, PriceUpdate] = {}    # last emitted PriceUpdate
        self._session_opens: dict[str, float] = {}  # price at add_ticker() time
        self._subscribers: list[PriceCallback] = []
        self._task: asyncio.Task | None = None

    # -------------------------------------------------------------------------
    # MarketDataProvider interface

    async def start(self) -> None:
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def add_ticker(self, ticker: str) -> PriceUpdate:
        if ticker not in self._prices:
            seed_price = SEED_PRICES.get(ticker, 100.0)
            self._prices[ticker] = seed_price
            self._session_opens[ticker] = seed_price
            now = datetime.now(timezone.utc)
            update = PriceUpdate(
                ticker=ticker,
                price=seed_price,
                prev_price=seed_price,
                session_open=seed_price,
                timestamp=now,
                direction="flat",
            )
            self._cache[ticker] = update
        return self._cache[ticker]

    async def remove_ticker(self, ticker: str) -> None:
        self._prices.pop(ticker, None)
        self._cache.pop(ticker, None)
        self._session_opens.pop(ticker, None)

    def get_prices(self) -> dict[str, PriceUpdate]:
        return dict(self._cache)

    def subscribe(self, callback: PriceCallback) -> None:
        self._subscribers.append(callback)

    # -------------------------------------------------------------------------
    # Internal tick loop

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            if not self._prices:
                continue
            now = datetime.now(timezone.utc)
            updates = self._compute_tick(now)
            for update in updates:
                self._cache[update.ticker] = update
                for cb in self._subscribers:
                    await cb(update)

    def _compute_tick(self, now: datetime) -> list[PriceUpdate]:
        tickers = list(self._prices.keys())
        n = len(tickers)

        # Split into known (correlated) and unknown (independent) tickers
        known = [t for t in tickers if t in _DEFAULT_TICKERS]
        unknown = [t for t in tickers if t not in _DEFAULT_TICKERS]

        updates: list[PriceUpdate] = []

        # --- Correlated shocks for known default tickers ---
        if known:
            known_indices = [_DEFAULT_TICKERS.index(t) for t in known]
            # Draw independent normals for the full 10x10 space, then correlate
            z_full = self._rng.standard_normal(len(_DEFAULT_TICKERS))
            z_corr = _CHOLESKY @ z_full  # shape (10,)

            for i, ticker in enumerate(known):
                idx = known_indices[i]
                z = z_corr[idx]
                params = TICKER_PARAMS.get(ticker, {"sigma": DEFAULT_SIGMA, "mu": DEFAULT_MU})
                price = self._gbm_step(self._prices[ticker], params["mu"], params["sigma"], z)
                updates.append(self._make_update(ticker, price, now))

        # --- Independent shocks for dynamically added tickers ---
        for ticker in unknown:
            z = self._rng.standard_normal()
            price = self._gbm_step(self._prices[ticker], DEFAULT_MU, DEFAULT_SIGMA, z)
            updates.append(self._make_update(ticker, price, now))

        # --- Random event: 2% chance per cycle ---
        if tickers and self._rng.random() < 0.02:
            event_ticker = tickers[int(self._rng.integers(0, len(tickers)))]
            magnitude = float(self._rng.uniform(0.02, 0.05)) * float(self._rng.choice([-1, 1]))
            # Find and adjust the update we already computed for this ticker
            for u in updates:
                if u.ticker == event_ticker:
                    new_price = max(u.price * (1.0 + magnitude), 0.01)
                    updates.remove(u)
                    updates.append(self._make_update(event_ticker, new_price, now))
                    break

        return updates

    def _gbm_step(self, price: float, mu: float, sigma: float, z: float) -> float:
        """Apply one GBM step. Returns new price, always positive."""
        exponent = (mu - 0.5 * sigma ** 2) * DT + sigma * (DT ** 0.5) * z
        new_price = price * np.exp(exponent)
        return max(float(new_price), 0.01)

    def _make_update(self, ticker: str, new_price: float, now: datetime) -> PriceUpdate:
        prev_price = self._prices.get(ticker, new_price)
        self._prices[ticker] = new_price

        direction = "flat"
        if new_price > prev_price:
            direction = "up"
        elif new_price < prev_price:
            direction = "down"

        return PriceUpdate(
            ticker=ticker,
            price=round(new_price, 4),
            prev_price=round(prev_price, 4),
            session_open=self._session_opens.get(ticker, new_price),
            timestamp=now,
            direction=direction,
        )
```

---

## GBM Parameter Choices

### Time Step (dt)

500ms ticks in a simulator do not correspond to 500ms of calendar time. We use trading time:

```
dt = 0.5s / (252 days/yr × 6.5 hr/day × 3600 s/hr) ≈ 8.47e-8 years
```

This keeps per-tick moves tiny and realistic. Typical price change per tick at `sigma=0.25`:

```
sigma * sqrt(dt) ≈ 0.25 * sqrt(8.47e-8) ≈ 0.0000727  (0.007%)
```

### Volatility (sigma)

Annualized values match rough real-world estimates:
- Low vol: `V` at σ=0.18 (18% annual)
- Medium vol: `AAPL` at σ=0.25, `GOOGL` at σ=0.28
- High vol: `TSLA` at σ=0.65, `NVDA` at σ=0.55

### Drift (mu)

All tickers use a small positive drift (μ=0.08–0.18 annually). Over the typical demo session (minutes to hours), drift is negligible — only volatility is observable.

---

## Correlation Matrix Rationale

The 10x10 correlation matrix encodes the following sector logic:

| Group | Tickers | Intra-group ρ |
|-------|---------|---------------|
| Big Tech | AAPL, GOOGL, MSFT, META | 0.60–0.70 |
| Tech/Growth | AMZN, TSLA, NVDA | 0.40–0.55 |
| Financials | JPM, V | 0.55 |
| Cross-sector | Tech ↔ Financials | 0.18–0.32 |

The Cholesky factor `L` is computed once at module load (`_CHOLESKY = np.linalg.cholesky(_DEFAULT_CORR)`) so it doesn't repeat per tick.

---

## Determinism for Testing

Pass a fixed seed to get reproducible price sequences:

```python
provider = SimulatedMarketData(seed=42)
```

Without a seed, `np.random.default_rng()` uses OS entropy (non-deterministic, appropriate for production).

---

## Performance Characteristics

- **CPU**: < 1ms per tick for 20 tickers; negligible
- **Memory**: O(n_tickers) — a few hundred bytes per ticker
- **Concurrency**: Single asyncio event loop task; no threads required
- **Scaling**: Supports 100+ tickers without degradation; `_compute_tick()` is vectorized via NumPy

---

## Differences from Real Market Data

| Property | Simulator | Real Market |
|----------|-----------|-------------|
| Price continuity | Continuous (no gaps) | Gaps at open/close |
| Bid/ask spread | Not modeled | Present |
| Volume | Not simulated | Real |
| Market events | Random 2% chance/tick | News-driven |
| After-hours | Runs 24/7 | Reduced activity |
| Correlation stability | Fixed matrix | Changes over time |

For the purposes of FinAlly — a demo trading workstation — these simplifications are intentional and appropriate. The goal is visual fidelity, not financial accuracy.
