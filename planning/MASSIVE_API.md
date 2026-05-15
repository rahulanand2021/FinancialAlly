# Massive API (formerly Polygon.io) — Stock Price Data

Massive.com (rebranded from Polygon.io on October 30, 2025) provides real-time and historical U.S. stock market data via REST APIs, WebSocket streams, and flat files. This document covers the REST endpoints relevant to FinAlly: fetching current prices and previous-day OHLCV for multiple tickers.

## Key Facts

- **Base URL**: `https://api.massive.com` (legacy `https://api.polygon.io` still resolves)
- **Python SDK**: `pip install -U massive` (formerly `polygon-api-client`)
- **Free tier**: 5 API calls per minute, unlimited on paid tiers
- **Existing Polygon.io API keys continue to work unchanged**

---

## Authentication

The API key is accepted two ways:

### Option 1 — Authorization Header (preferred)
```
Authorization: Bearer YOUR_API_KEY
```

### Option 2 — Query Parameter
```
GET /v2/snapshot/locale/us/markets/stocks/tickers?apiKey=YOUR_API_KEY
```

The Python SDK handles auth automatically when initialized with `api_key=`.

---

## Relevant Endpoints

### 1. Full Market Snapshot (primary endpoint for FinAlly)

Retrieves current price data for one or many tickers in a single request. This is the most efficient endpoint for a watchlist.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

**Query Parameters**

| Parameter    | Type    | Required | Description |
|--------------|---------|----------|-------------|
| `tickers`    | string  | No       | Comma-separated list of tickers, e.g. `AAPL,TSLA,GOOG`. Omit for all ~10,000+ tickers. |
| `include_otc`| boolean | No       | Include OTC securities. Default: `false` |
| `apiKey`     | string  | No*      | API key (use header auth instead) |

**Response Shape**

```json
{
  "count": 2,
  "status": "OK",
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.54,
      "todaysChangePerc": 0.82,
      "updated": 1605192894630916600,
      "fmv": null,
      "day": {
        "o": 186.10,
        "h": 188.44,
        "l": 185.83,
        "c": 187.64,
        "v": 52341200,
        "vw": 187.12
      },
      "prevDay": {
        "o": 185.00,
        "h": 186.90,
        "l": 184.20,
        "c": 186.10,
        "v": 48120000,
        "vw": 185.71
      },
      "min": {
        "o": 187.50,
        "h": 187.80,
        "l": 187.40,
        "c": 187.64,
        "v": 85000,
        "vw": 187.58,
        "t": 1684428600000,
        "n": 124,
        "av": 52341200
      },
      "lastTrade": {
        "p": 187.64,
        "s": 200,
        "t": 1605192894630916600,
        "x": 4
      },
      "lastQuote": {
        "P": 187.65,
        "S": 3,
        "p": 187.64,
        "s": 8,
        "t": 1605192959994246100
      }
    }
  ]
}
```

**Field Reference**

| Field | Description |
|-------|-------------|
| `day.c` | Current day close (most recent price during market hours) |
| `day.o` / `h` / `l` | Session open / high / low |
| `day.v` | Day volume |
| `day.vw` | Day volume-weighted average price |
| `prevDay.c` | Previous trading day close |
| `min.c` | Most recent minute bar close |
| `min.t` | Minute bar timestamp (milliseconds Unix) |
| `lastTrade.p` | Price of last trade |
| `lastTrade.s` | Size (shares) of last trade |
| `todaysChange` | Absolute price change vs. previous close |
| `todaysChangePerc` | Percentage change vs. previous close |
| `updated` | Nanosecond timestamp of last update |
| `fmv` | Fair Market Value (Business plan only) |

**Data Reset Schedule**: Snapshot data clears daily at 3:30 AM EST and repopulates as early as 4:00 AM EST.

---

### 2. Previous Day Bar (EOD)

Fetches the previous trading day's OHLCV for a single ticker.

```
GET /v2/aggs/ticker/{ticker}/prev
```

**Path Parameters**

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `ticker`  | string | Yes      | Case-sensitive ticker symbol, e.g. `AAPL` |

**Query Parameters**

| Parameter  | Type    | Required | Description |
|------------|---------|----------|-------------|
| `adjusted` | boolean | No       | Adjust for splits. Default: `true` |

**Response Shape**

```json
{
  "adjusted": true,
  "queryCount": 1,
  "request_id": "6a7e466379af0a71039d60cc78e72282",
  "results": [
    {
      "T": "AAPL",
      "o": 115.55,
      "h": 117.59,
      "l": 114.13,
      "c": 115.97,
      "v": 131704427,
      "vw": 116.3058,
      "t": 1605042000000
    }
  ],
  "resultsCount": 1,
  "status": "OK",
  "ticker": "AAPL"
}
```

**Note**: For multiple tickers, call this endpoint once per ticker. With a free-tier limit of 5 req/min, batch these carefully — at 10 tickers you need 10 seconds minimum.

---

### 3. Aggregate Bars (OHLCV over time range)

Fetches OHLCV candles for a ticker over a date range. Useful for charting history.

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
```

**Example**: 1-minute bars for AAPL for a single day
```
GET /v2/aggs/ticker/AAPL/range/1/minute/2026-05-09/2026-05-09
```

**Path Parameters**

| Parameter    | Type    | Description |
|--------------|---------|-------------|
| `ticker`     | string  | Ticker symbol |
| `multiplier` | integer | Size of the timespan (e.g. `1`, `5`, `15`) |
| `timespan`   | string  | `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year` |
| `from`       | string  | Start date `YYYY-MM-DD` or Unix ms timestamp |
| `to`         | string  | End date `YYYY-MM-DD` or Unix ms timestamp |

**Query Parameters**

| Parameter    | Type    | Description |
|--------------|---------|-------------|
| `adjusted`   | boolean | Adjust for splits. Default: `true` |
| `sort`       | string  | `asc` (default) or `desc` |
| `limit`      | integer | Max results per page (default 5000, max 50000) |

**Response Shape**

```json
{
  "ticker": "AAPL",
  "status": "OK",
  "queryCount": 390,
  "resultsCount": 390,
  "adjusted": true,
  "results": [
    {
      "o": 186.10,
      "h": 186.40,
      "l": 185.90,
      "c": 186.20,
      "v": 1234500,
      "vw": 186.15,
      "t": 1605042000000,
      "n": 2341
    }
  ]
}
```

---

### 4. Last Trade

Fetches the most recent trade for a single ticker (real-time on paid plans).

```
GET /v2/last/trade/{ticker}
```

**Response**: Returns `price` (`p`), `size` (`s`), `timestamp` (`t`), and `exchange` (`x`).

---

## Python SDK Usage

### Installation

```bash
pip install -U massive
```

Or add to `pyproject.toml`:
```toml
[project]
dependencies = ["massive>=1.0.0"]
```

### Initialization

```python
from massive import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")
```

### Fetching snapshot for a watchlist

```python
from massive import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")

tickers = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]

# Fetch all in one request
snapshots = client.get_snapshot_all("stocks", tickers=tickers)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.day.c:.2f}  ({snap.todays_change_perc:+.2f}%)")
```

### Fetching aggregate bars (for charting)

```python
aggs = []
for bar in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="minute",
    from_="2026-05-09",
    to="2026-05-09",
    limit=50000,
):
    aggs.append(bar)
```

### Fetching previous day OHLCV

```python
prev = client.get_previous_close("AAPL")
print(f"Previous close: ${prev.results[0].c:.2f}")
```

### Raw HTTP (no SDK)

```python
import httpx

API_KEY = "YOUR_API_KEY"
BASE_URL = "https://api.massive.com"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Snapshot for multiple tickers
params = {"tickers": "AAPL,GOOGL,MSFT"}
resp = httpx.get(
    f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers",
    headers=headers,
    params=params,
)
data = resp.json()

for ticker_snap in data["tickers"]:
    print(ticker_snap["ticker"], ticker_snap["day"]["c"])
```

---

## Rate Limits and Polling Strategy

| Plan   | Requests/min | Recommended Poll Interval |
|--------|-------------|--------------------------|
| Free   | 5           | 15 seconds               |
| Starter ($29/mo) | Unlimited | 2–5 seconds   |
| Developer ($79/mo) | Unlimited | 2–5 seconds |
| Advanced ($199/mo) | Unlimited | 1–2 seconds |

**Free tier strategy**: Use the snapshot endpoint with a comma-separated list of all watchlist tickers in a single request. One request every 15 seconds stays safely under the 5/min cap, leaving headroom for other API calls.

**Polling pattern for FinAlly**:
```python
# One API call covers all 10+ tickers — efficient use of the free tier
tickers_param = ",".join(watchlist_tickers)
response = httpx.get(
    f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers",
    headers={"Authorization": f"Bearer {API_KEY}"},
    params={"tickers": tickers_param},
    timeout=10.0,
)
```

---

## Error Handling

```python
import httpx

try:
    resp = httpx.get(url, headers=headers, params=params, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
except httpx.TimeoutException:
    # Retry after backoff
    pass
except httpx.HTTPStatusError as e:
    if e.response.status_code == 429:
        # Rate limited — back off
        pass
    elif e.response.status_code == 403:
        # Invalid API key
        pass
```

**Common status codes**:
- `200 OK` — success
- `403 Forbidden` — invalid or missing API key
- `429 Too Many Requests` — rate limit exceeded
- `404 Not Found` — unknown ticker or endpoint

---

## Market Hours

The snapshot endpoint returns stale data outside market hours but is still usable. The `updated` nanosecond timestamp tells you when the data was last refreshed. Pre-market and after-hours data availability depends on your plan tier.
