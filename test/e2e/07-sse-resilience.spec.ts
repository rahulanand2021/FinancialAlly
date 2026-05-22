import { expect, test } from '@playwright/test';
import { connectionDot, waitForPrice, watchlistRow } from './helpers';

test.describe('SSE resilience', () => {
  test('connection indicator is green and prices keep updating', async ({ page }) => {
    await page.goto('/');

    await expect(connectionDot(page, 'Live')).toBeVisible();

    await waitForPrice(page, 'AAPL');

    const aapl = watchlistRow(page, 'AAPL');
    const initial = await aapl.innerText();

    await expect
      .poll(async () => (await aapl.innerText()) !== initial, { timeout: 20_000 })
      .toBe(true);
  });
});
