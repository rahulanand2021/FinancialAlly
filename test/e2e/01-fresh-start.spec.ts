import { expect, test } from '@playwright/test';
import {
  DEFAULT_TICKERS,
  cashValue,
  connectionDot,
  parseMoney,
  waitForPrice,
  watchlistRow,
} from './helpers';

test.describe('Fresh start', () => {
  test('shows default watchlist, $10k balance, and streaming prices', async ({ page }) => {
    await page.goto('/');

    for (const ticker of DEFAULT_TICKERS) {
      await expect(watchlistRow(page, ticker)).toBeVisible();
    }

    const cash = cashValue(page);
    await expect(cash).toBeVisible();
    expect(parseMoney(await cash.innerText())).toBeCloseTo(10000, 0);

    await waitForPrice(page, 'AAPL');

    await expect(connectionDot(page, 'Live')).toBeVisible();
  });
});
