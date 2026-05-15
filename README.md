# FinAlly — AI Trading Workstation

A visually stunning AI-powered trading workstation with live market data, simulated portfolio trading, and an LLM chat assistant that can analyze positions and execute trades.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — $10,000 starting cash, market orders, instant fill
- **Watchlist** with sparkline mini-charts per ticker
- **Portfolio heatmap** (treemap) sized by weight, colored by P&L
- **AI chat assistant** that can execute trades and manage watchlist via natural language

## Quick Start

**macOS/Linux:**
```bash
cp .env.example .env         # add your OPENROUTER_API_KEY
./scripts/start_mac.sh
```

**Windows:**
```powershell
Copy-Item .env.example .env  # add your OPENROUTER_API_KEY
.\scripts\start_windows.ps1
```

Open [http://localhost:8000](http://localhost:8000).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM chat via OpenRouter (Cerebras) |
| `MASSIVE_API_KEY` | No | Real market data; simulator used if absent |
| `LLM_MOCK` | No | Set `true` for deterministic E2E test responses |

## Architecture

Single Docker container on port 8000:

- **Backend**: FastAPI (Python/uv), SQLite, SSE streaming
- **Frontend**: Next.js (TypeScript), static export served by FastAPI
- **AI**: LiteLLM → OpenRouter → Cerebras (fast inference, structured outputs)
- **Market data**: GBM simulator (default) or Massive API (optional)

## Tech Stack

Python · FastAPI · SQLite · Next.js · TypeScript · Tailwind CSS · Docker · LiteLLM
