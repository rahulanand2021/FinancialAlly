import { expect, test } from '@playwright/test';
import {
  cashValue,
  currentQty,
  panel,
  parseMoney,
  positionQty,
  positionRow,
  waitForPrice,
} from './helpers';

test.describe('Buy shares', () => {
  test('cash decreases and position appears after buying AAPL', async ({ page }) => {
    await page.goto('/');
    await waitForPrice(page, 'AAPL');

    const startQty = await currentQty(page, 'AAPL');
    const cash = cashValue(page);
    const startCash = parseMoney(await cash.innerText());

    const trade = panel(page, 'Trade');
    await trade.getByPlaceholder('TICKER').fill('AAPL');
    await trade.locator('input[type="number"]').fill('2');
    await trade.getByRole('button', { name: 'Buy' }).click();

    await expect(positionRow(page, 'AAPL')).toBeVisible();
    await expect(positionQty(page, 'AAPL')).toHaveText(String(startQty + 2));

    await expect
      .poll(async () => parseMoney(await cash.innerText()))
      .toBeLessThan(startCash);
  });
});
