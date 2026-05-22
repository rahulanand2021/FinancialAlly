import { expect, Locator, Page } from '@playwright/test';

export const DEFAULT_TICKERS = [
  'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA',
  'NVDA', 'META', 'JPM', 'V', 'NFLX',
];

/**
 * Panels are rendered as <section> elements whose <h2> holds the title.
 * Scope lookups to a panel so identical text in other panels never collides.
 */
export function panel(page: Page, title: string): Locator {
  return page.locator('section').filter({ has: page.getByRole('heading', { name: title }) });
}

/** A watchlist <tr> identified by its ticker cell. */
export function watchlistRow(page: Page, ticker: string): Locator {
  return panel(page, 'Watchlist').locator('tbody tr').filter({
    has: page.getByRole('cell', { name: ticker, exact: true }),
  });
}

/** A positions-table <tr> identified by its ticker cell. */
export function positionRow(page: Page, ticker: string): Locator {
  return panel(page, 'Positions').locator('tbody tr').filter({
    has: page.getByRole('cell', { name: ticker, exact: true }),
  });
}

/**
 * The quantity cell of a position row. Columns are
 * Sym | Qty | Avg | Last | P&L | P&L%, so quantity is the 2nd cell.
 */
export function positionQty(page: Page, ticker: string): Locator {
  return positionRow(page, ticker).locator('td').nth(1);
}

/** Current held quantity for a ticker via the API (0 if no position). */
export async function currentQty(page: Page, ticker: string): Promise<number> {
  const portfolio = await page.evaluate(async () => {
    const res = await fetch('/api/portfolio');
    return res.json();
  });
  const pos = (portfolio.positions ?? []).find(
    (p: { ticker: string }) => p.ticker === ticker,
  );
  return pos ? Number(pos.quantity) : 0;
}

/**
 * Cash balance value. Header renders <span>Cash</span><span>$amount</span>;
 * the value is the span immediately after the "Cash" label.
 */
export function cashValue(page: Page): Locator {
  return page
    .locator('header span', { hasText: /^Cash$/ })
    .locator('xpath=following-sibling::span[1]');
}

/** Total portfolio value, sibling of the "Total" label in the header. */
export function totalValue(page: Page): Locator {
  return page
    .locator('header span', { hasText: /^Total$/ })
    .locator('xpath=following-sibling::span[1]');
}

/**
 * Connection status dot. Header gives it an aria-label of
 * "Live" | "Reconnecting" | "Disconnected".
 */
export function connectionDot(
  page: Page,
  label: 'Live' | 'Reconnecting' | 'Disconnected',
): Locator {
  return page.locator('header').getByLabel(label);
}

/** Wait until the watchlist row for a ticker shows a numeric price. */
export async function waitForPrice(page: Page, ticker: string): Promise<void> {
  const row = watchlistRow(page, ticker);
  await expect(row).toBeVisible();
  await expect(row).toContainText(/\d+\.\d{2}/);
}

/** Parse "$10,000.00" -> 10000. */
export function parseMoney(text: string): number {
  const cleaned = text.replace(/[^0-9.\-]/g, '');
  return parseFloat(cleaned);
}
