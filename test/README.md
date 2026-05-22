# FinAlly E2E Tests

End-to-end Playwright suite covering the scenarios in PLAN.md §12.

## Run in Docker (matches CI)

```
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
```

The `app` service runs the FinAlly container with `LLM_MOCK=true`. The
`playwright` service waits for `/api/health` to return 200, then runs the
test suite against `http://app:8000`.

## Run locally against a running app

1. Start the app on port 8000 with `LLM_MOCK=true`.
2. From this directory:
   ```
   npm ci
   npx playwright install --with-deps
   npx playwright test
   ```

Set `BASE_URL` to override the default `http://localhost:8000`.

## Selector strategy

The frontend ships without `data-testid` attributes, so tests locate
elements via semantic markup (panel headings, placeholders, aria-labels,
roles, and table cells). All helpers live in `e2e/helpers.ts`. The DOM
contract the suite depends on:

| Element | How it's located |
|---|---|
| Panel | `<section>` containing an `<h2>` heading with the panel title |
| Watchlist row | `tbody tr` in the "Watchlist" panel containing the ticker cell |
| Position row | `tbody tr` in the "Positions" panel containing the ticker cell |
| Cash value | `<span>` after the header "Cash" label |
| Total value | `<span>` after the header "Total" label |
| Connection dot | header element with aria-label "Live" / "Reconnecting" / "Disconnected" |
| Add-ticker input | placeholder "ADD" in the Watchlist panel |
| Add-ticker button | button "+" in the Watchlist panel |
| Remove button | button with aria-label "Remove <TICKER>" |
| Trade ticker input | placeholder "TICKER" in the Trade panel |
| Trade quantity input | `input[type="number"]` in the Trade panel |
| Buy / Sell buttons | buttons "Buy" / "Sell" in the Trade panel |
| Heatmap | `svg rect` elements in the "Portfolio Heatmap" panel |
| Chat input | placeholder "Ask FinAlly..." in the "AI Assistant" panel |
| Chat send button | button "Send" in the "AI Assistant" panel |

If the frontend changes any of these labels/placeholders, update
`e2e/helpers.ts` to match.
