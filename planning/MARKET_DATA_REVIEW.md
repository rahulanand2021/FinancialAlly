# Market Data Backend — Code Review

**Reviewer**: Claude (Sonnet 4.6)
**Date**: 2026-05-16
**Scope**: `backend/market/`, `backend/routes/stream.py`, `backend/tests/`

---

## Test Results

```
35 passed in 20.01s
```

All tests pass. Coverage spans simulator lifecycle, Massive API (mocked via `respx`), interface conformance, subscriber/unsubscribe, direction tracking, session-open preservation, and error fallback paths.

---

## Overall Assessment

The implementation is clean, well-structured, and production-ready for its stated scope. The abstract interface, singleton factory, and provider swap are all implemented correctly. The GBM math is correct (proper Itô correction applied). The SSE fan-out pattern is solid. The test suite is thorough. There are no critical bugs. The issues below are a mix of spec deviations, code smells, and test gaps.

---

## Issues by Severity

### Moderate

**1. `DEFAULT_MU` deviates from spec (`simulator.py:45`)**

The design documents (`MARKET_DATA_DESIGN.md` §4.1 and `MARKET_SIMULATOR.md`) specify `DEFAULT_MU = 0.0001` for dynamically-added tickers. The implementation uses `DEFAULT_MU = 0.10` (10% annual drift). This is actually a more reasonable value (it matches the named tickers), but it contradicts the spec and could surprise anyone who reads the documentation and inspects the code.

**2. `CancelledError` swallowed in SSE generator (`routes/stream.py:49-50`)**

```python
except asyncio.CancelledError:
    provider.unsubscribe(on_price)
    # CancelledError NOT re-raised
```

In Python 3.8+, `CancelledError` is a `BaseException` and the asyncio documentation states it should be re-raised after cleanup so the cancellation can propagate. Swallowing it may interfere with framework-level task cancellation in some Starlette/FastAPI versions. The cleanup should be in a `finally` block:

```python
try:
    yield ": connected\n\n"
    while True:
        update = await queue.get()
        ...
        yield f"data: {json.dumps(payload)}\n\n"
finally:
    provider.unsubscribe(on_price)
```

This also ensures cleanup on non-`CancelledError` exceptions, which the current code misses entirely.

**3. `_make_update` double-mutation for event ticker (`simulator.py:164-173`)**

When a random market event fires, `_make_update` is called twice for the event ticker: once during the regular GBM step (which writes the new price to `self._prices`), and again in the list comprehension for the event. The second call uses `u.price` (the already-rounded GBM price) as the input, but the `prev_price` in that second update is taken from `self._prices` which was already mutated by the first call. This means the event update's `prev_price` reflects the post-GBM price rather than the true previous tick's price.

In practice the effect is negligible (GBM step is tiny), but the double side-effect is a subtle source of confusion. The cleaner approach is to compute the final price before calling `_make_update`, rather than patching via a list comprehension over already-computed updates.

---

### Minor

**4. `TickerConfig` dataclass is dead code (`base.py:22-26`)**

`TickerConfig` is defined per spec but never instantiated or referenced anywhere in the implementation. Either use it (as the per-ticker parameter container that `TICKER_PARAMS` dicts currently are) or remove it.

**5. `asyncio` imported but unused in `base.py`**

`import asyncio` appears at line 1 of `base.py`. No `asyncio` symbols are used in that file—`Awaitable` comes from `typing`. Remove the import.

**6. `conftest.py` `anyio_backend` fixture is unused**

The `anyio_backend = "asyncio"` fixture is only consumed by tests using the `anyio` pytest plugin. The test suite uses `pytest-asyncio` with `asyncio_mode = "auto"`, so this fixture does nothing. It can be removed.

**7. `test_prices_update_over_time` assertion is a no-op (`test_simulator.py:181`)**

```python
assert final_price != initial_price or True  # GBM can theoretically stay flat, so soft assert
```

The `or True` makes this always pass—it tests nothing. Remove the assertion or replace with a probabilistic guard (e.g., run 20 ticks and assert at least one price changed).

**8. Interface conformance tests only exercise `SimulatedMarketData` (`test_provider_interface.py`)**

The file's docstring says it documents "the contract both implementations must meet," but `MassiveMarketData` is never exercised here. Consider parameterizing the fixture with a `MassiveMarketData` instance backed by a `respx` mock, or add a parallel `test_massive_interface.py`.

**9. `reset_provider()` in `__init__.py` is undocumented**

`reset_provider()` is a useful test helper but is exported without documentation, and `__all__` only lists `get_market_data_provider`. Either add it to `__all__` with a docstring or mark it clearly as a testing-only function (e.g., name it `_reset_provider_for_testing`).

---

## Correctness Observations

### GBM Math

Correct. The exact discretisation `S(t+dt) = S(t) · exp((μ - σ²/2)·dt + σ·√dt·Z)` is used at `simulator.py:71`. The Itô correction `(μ - σ²/2)` is present. The `DT` computation (trading seconds per year) is correct and matches the documentation. The `max(…, 0.01)` floor ensures prices never go negative.

### Correlation Model

Correct. Cholesky decomposition is computed once at module load (`_CHOLESKY`). Correlated shocks are generated correctly with `_CHOLESKY @ z_full`. The 10×10 correlation matrix is positive definite (verified implicitly by `np.linalg.cholesky` not raising). Dynamically added tickers correctly draw independent shocks.

### Race-condition guarantee

Satisfied. Both providers ensure `add_ticker()` populates the cache before returning. Since asyncio is single-threaded and neither method yields after writing to `self._cache`, the cache entry is visible to any code that runs after `await provider.add_ticker(ticker)`.

### `_poll_all` error isolation

The `_poll_loop` wraps `_poll_all` in a `try/except Exception`, so any HTTP error, JSON parse error, or unexpected exception keeps the loop alive and the cache stale-but-valid. This is correct per the design's error handling policy.

### SSE queue fan-out

The `QueueFull` / drop-oldest strategy is correct. `on_price` uses `put_nowait` so it never blocks the tick loop. Subscriber registration happens before the `StreamingResponse` is returned. The `maxsize=200` is a reasonable bound (10 tickers × 2 ticks/s = 20 updates/s; 200 gives a 10-second buffer for a slow client before dropping starts).

---

## Missing Coverage

| Scenario | Status |
|---|---|
| SSE endpoint itself (`/api/stream/prices`) | No test |
| Concurrent `remove_ticker` during tick loop iteration | No test |
| `get_market_data_provider()` factory (env var selection) | No test |
| Market event fires (2% per tick) | No direct test; covered implicitly over 10-tick runs |
| Zero-price response from Massive skipped correctly | No test |
| `_poll_all` with ticker in response not in `self._tickers` | No test |

The SSE endpoint test gap is the most notable. It could be a simple FastAPI `TestClient` test that subscribes, receives one event, and verifies the JSON shape.

---

## Spec Conformance Summary

| Requirement | Status |
|---|---|
| Abstract base class with all methods | ✅ Matches spec |
| Singleton factory with env-var selection | ✅ Matches spec |
| GBM with Itô correction | ✅ Matches spec |
| Cholesky correlation for default 10 tickers | ✅ Matches spec |
| 2% random event per tick | ✅ Matches spec |
| Unknown ticker starts at $100 | ✅ Matches spec |
| `add_ticker` initialises cache before return | ✅ Matches spec |
| `session_open` preserved, never overwritten | ✅ Matches spec |
| Massive `_extract_price` priority order | ✅ Matches spec |
| Massive fallback to seed on error | ✅ Matches spec |
| SSE `": connected"` comment on open | ✅ Matches spec |
| SSE `QueueFull` drops oldest | ✅ Matches spec |
| `DEFAULT_MU` for unknown tickers | ❌ Spec: 0.0001, code: 0.10 |
| `TickerConfig` used for per-ticker params | ❌ Defined but unused |

---

## Recommended Actions (Priority Order)

1. **Fix `finally` in SSE generator** — swap `except CancelledError` for `finally` to ensure `unsubscribe` always fires.
2. **Resolve `DEFAULT_MU` discrepancy** — either update the spec to 0.10 (more sensible value) or update the code to 0.0001; add a comment explaining the choice.
3. **Remove `or True` from `test_prices_update_over_time`** — replace with a meaningful assertion or remove the test.
4. **Add SSE endpoint test** — verify the event shape, `": connected"` comment, and that `unsubscribe` is called on disconnect.
5. **Remove `TickerConfig`** or wire it into the simulator to replace the `TICKER_PARAMS` dict pattern.
6. **Remove unused `asyncio` import** from `base.py` and unused `anyio_backend` fixture from `conftest.py`.
