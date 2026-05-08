# FinAlly — AI Trading Workstation

An AI-powered trading workstation with live market data, a simulated portfolio, and an LLM chat assistant that can analyze positions and execute trades.

## Quick Start

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

Open [http://localhost:8000](http://localhost:8000).

## Prerequisites

- Docker
- An OpenRouter API key (for AI chat)

## Configuration

Create a `.env` file in the project root:

```bash
OPENROUTER_API_KEY=your-key-here
MASSIVE_API_KEY=           # optional: real market data (simulator used if unset)
LLM_MOCK=false             # set true for deterministic E2E testing
```

## Features

- Live streaming prices (simulated by default, real via Massive API)
- $10,000 virtual cash to trade with
- Portfolio heatmap, P&L chart, and positions table
- AI chat assistant that can execute trades and manage your watchlist

## Stack

- **Frontend**: Next.js (TypeScript, static export)
- **Backend**: FastAPI + Python (managed with `uv`)
- **Database**: SQLite
- **AI**: LiteLLM → OpenRouter (Cerebras inference)
- **Streaming**: Server-Sent Events (SSE)

## Development

See `planning/PLAN.md` for full architecture and API documentation.
