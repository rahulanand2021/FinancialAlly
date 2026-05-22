# FinAlly Frontend

Next.js 15 + TypeScript + Tailwind CSS v4 frontend for the FinAlly AI trading workstation.

## Scripts

- `npm run dev` — start the dev server on http://localhost:3000
- `npm run build` — produce a static export in `out/`
- `npm test` — run unit tests with Vitest

## Configuration

`next.config.ts` sets `output: "export"` so the app builds to fully static HTML/JS that the FastAPI backend serves from `/`.

All API calls hit the same origin under `/api/*` (no CORS configuration required).
