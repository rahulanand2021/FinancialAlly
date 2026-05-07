# FinAlly — Plan Review

**Reviewed:** 2026-05-07
**Reviewer:** Claude Code (claude-sonnet-4-6)
**Status of codebase:** No implementation exists yet. The repo contains only `planning/PLAN.md`, a `.env` file with an exposed API key, `.gitignore`, and `.claude/` configuration. All findings below are review of the *plan*, not running code.

---

## Summary

The plan is well-structured and architecturally sound for a capstone demo. The single-container, single-port approach with SSE and SQLite is the right level of simplicity. The main concerns are a committed secret in `.env`, several spec ambiguities that will cause agent disagreements during implementation, a few logical gaps in the database and API design, and missing `.env.example`.

---

## CRITICAL

### 1. Real API key committed to the repository

`D:\LLM\FinancialAlly\.env` is tracked in git (it appears in the initial commit) and contains a live `OPENROUTER_API_KEY`. The `.gitignore` lists `.env` but the file was committed before the rule was added.

The key must be rotated immediately and the commit history scrubbed or the key treated as permanently compromised. The `.env.example` file called for in the plan (Section 4) does not exist in the repo.

**Action required before any agent begins writing code:**
- Rotate the OpenRouter key.
- Remove `.env` from git history (`git filter-repo` or `git filter-branch`).
- Add `.env.example` with placeholder values.
- Confirm `.env` is in `.gitignore` and untracked.

---

## HIGH

### 2. LLM mock fixture will always fail on a fresh database

Section 9 (LLM Mock Mode) defines a fixed response that buys 5 shares of AAPL and adds NVDA to the watchlist. The E2E test assertion is: "cash reduced, AAPL position exists, NVDA on watchlist."

NVDA is already in the default seed watchlist (Section 7). An "add" action for a ticker that already exists must either be idempotent (no error, no duplicate) or return an error. The plan does not specify which. If the backend raises a constraint error on the duplicate insert, the mock E2E test will fail on a fresh database. The plan must explicitly state that watchlist "add" is idempotent.

### 3. Portfolio snapshot retention window mismatch

Section 7 says snapshots older than **7 days** are pruned. Section 8 says `GET /api/portfolio/history` returns the **last 24 hours**. These are two different windows. The plan never explains what happens to the 2–7 day data: it is stored but never exposed. This is probably an oversight — either the history endpoint should expose the full 7-day window, or the pruning window should match 24 hours. As written, agents will make different choices and the frontend chart will never show more than 24 hours regardless of retention.

### 4. `avg_cost` update logic for sells is unspecified

The `positions` table stores `avg_cost`. The plan specifies buy-side averaging implicitly (standard weighted average), but never describes how a partial sell affects `avg_cost`. Standard practice is that `avg_cost` stays unchanged on a sell (FIFO/LIFO is irrelevant for a single-cost-basis model). Agents implementing this without guidance may zero out or recalculate `avg_cost` incorrectly, breaking unrealized P&L display after a partial sell.

### 5. No `DELETE /api/watchlist/{ticker}` cache purge timing guarantee

Section 6 says: "When a ticker is removed from the watchlist, the cache entry is purged; it will no longer appear in the SSE stream starting from the **next push cycle**." But if a connected SSE client receives one more event for a removed ticker between the DELETE response and the next push cycle, the frontend must tolerate that gracefully. The plan says nothing about frontend handling of stale tickers in the SSE stream. This is a real edge case that should be documented.

### 6. `POST /api/watchlist` race condition partially addressed but incomplete

Section 6 says the backend initializes the price cache entry before returning the POST response to prevent a race condition. However, the SSE endpoint pushes all cached tickers; if a second SSE client connects between the DB insert and the cache init, it will receive the new ticker's first SSE push with `null` prices. The plan should state that cache init is atomic with the DB insert (same request handler, no async gap) to make the intent explicit for implementers.

---

## MEDIUM

### 7. Dockerfile uses `npm install` but the plan mandates no package manager guidance

Section 11 Dockerfile stage 1 says `npm install && npm run build`. The project mandates `uv` for Python but says nothing about whether `npm`, `pnpm`, or another Node package manager should be used. This is a minor inconsistency — the plan should either explicitly allow `npm` for the frontend or specify `pnpm` for consistency with modern Next.js tooling.

### 8. `session_open` is backend-session-scoped, not market-session-scoped

Section 6 defines `session_open` as "the first price seen for this ticker since the backend started." This means restarting the container mid-day resets the session open price, making the session change % meaningless or misleading. For a demo this is probably acceptable, but it should be called out explicitly so frontend agents do not label this field "Today's Open" in the UI — it is "Open since last restart."

### 9. `GET /api/portfolio/history` always returns 24 hours regardless of age

On a fresh database with no snapshots, the endpoint returns an empty array. The frontend P&L chart will be blank until snapshots accumulate. The plan does not specify what the chart should render in this empty state. Agents should add a spec for the empty state (e.g., show a single point at $10,000 at the current timestamp).

### 10. No ticker validation on `POST /api/watchlist`

The plan allows any string as a ticker symbol. The simulator accepts unknown tickers and starts them at $100. However, there is no mention of input sanitization — a ticker like `'; DROP TABLE watchlist; --` or a 500-character string could cause issues. The plan should specify maximum ticker length and character allowlist (e.g., uppercase A–Z, 1–5 characters) even for a demo.

### 11. Multi-stage Docker build does not specify where static files land

Section 11 says "Copy frontend build output into a static/ directory" but does not specify:
- Whether this is `/app/static/` or `/app/backend/static/`.
- What FastAPI mount path serves these files.
- How Next.js `output: 'export'` is configured (the `distDir` and `basePath` settings affect where the build output lands and whether asset paths work correctly).

The `next.config.js` `assetPrefix` and `trailingSlash` settings are also omitted. Missing these causes 404s on CSS/JS assets when served from FastAPI.

### 12. SSE endpoint has no heartbeat specification

Long-lived SSE connections are dropped by proxies, load balancers, and some browsers after 30–60 seconds of silence if there are no price changes. The plan does not specify a heartbeat/comment frame interval. For the simulator this is unlikely (prices change every 500ms), but for the Massive API on a slow poll interval (15s free tier), a proxy could close the connection. A spec comment like "send a `: keepalive` comment every 15 seconds" would prevent this.

### 13. `direction` field redundancy

The SSE event shape includes both `prev_price` and `direction`. `direction` is fully derivable from `price` vs `prev_price` on the client. This is not wrong, but it is redundant and adds maintenance surface. If `direction` is kept, the spec should clarify the rule for `"flat"` — is it `price == prev_price` exactly, or within some epsilon?

### 14. `backend/db/` directory naming conflicts with top-level `db/`

The plan uses `backend/db/` for schema SQL files and `db/` at the project root as the runtime SQLite volume mount. These names are confusingly similar. The boundary description in Section 4 is clear, but the directory structure diagram places `db/` under `backend/` as `backend/db/` — an agent reading quickly may conflate the two and write `finally.db` into `backend/db/` instead of `/app/db` inside the container. The Dockerfile COPY instructions must be explicit about this distinction.

---

## LOW / CLARITY

### 15. `cerebras-inference skill` vs `cerebras skill` naming

Section 9 says "use cerebras-inference skill" but the actual skill is registered as `cerebras` in `.claude/skills/cerebras/SKILL.md`. Agents reading the plan may search for a non-existent `cerebras-inference` skill and fail. Align the name in the plan with the actual registered skill name.

### 16. `reasoning_effort="low"` not mentioned in plan

The cerebras skill snippet uses `reasoning_effort="low"`. The plan section on LLM integration does not mention this parameter. For a chat assistant, `"low"` reasoning effort may produce lower-quality analysis. The plan should explicitly call out this parameter and its rationale (speed vs quality tradeoff).

### 17. `portfolio_snapshots` records after trade are not reflected in history endpoint without a page refresh

The plan says snapshots are recorded "immediately after each trade execution." The history endpoint returns snapshots from the database. If the frontend polls or re-fetches history only on load, the P&L chart won't update after a trade without a manual refresh. The plan does not specify whether the frontend should periodically re-poll `GET /api/portfolio/history` or whether a triggered update is expected. This should be specified.

### 18. No mention of CORS configuration for local development

The plan correctly notes that the static export avoids CORS in production (same origin). However, during frontend development (`next dev` on port 3000 vs backend on port 8000), developers will hit CORS errors. The plan should note that `fastapi.middleware.cors.CORSMiddleware` should allow `localhost:3000` in development mode, or that developers should use the Docker container for all testing.

### 19. Missing `.env.example`

The plan (Section 4) lists `.env.example` as a committed file but it does not exist in the repository. Agents implementing the project may skip creating it.

### 20. No mention of how trade quantity 0 or negative is handled

The trade endpoint accepts `quantity` as a REAL. The plan specifies a frontend minimum of 0.001 shares but does not specify backend validation. A POST with `quantity: 0` or `quantity: -5` should be rejected with a 422 response. This must be enforced server-side regardless of frontend constraints.

---

## Simplification Opportunities

- **`users_profile` table** is a single row for a single-user app. A simpler alternative is to store `cash_balance` in a key-value config table or as a single-column table with no `user_id` complexity. The `user_id` forward-compatibility argument is reasonable but adds cognitive overhead for no current benefit.
- **`chat_messages.actions` as JSON text** means querying executed trades from chat history requires JSON parsing in application code. If trade attribution to chat sessions is ever needed for display, a foreign key from `trades` to `chat_messages` would be cleaner. For demo purposes the JSON blob is fine.
- **`portfolio_snapshots` pruning on every insert** is simpler than a scheduled cleanup job, but it means a single heavy insert triggers a DELETE. For SQLite at this scale it is fine; the plan is correct to keep it simple.
- **The `id` UUID primary key on `watchlist` and `positions`** is unused by any API — all lookups are by `(user_id, ticker)`. A composite primary key `(user_id, ticker)` would eliminate the UUID column and the separate UNIQUE constraint, halving the index count on these tables.
