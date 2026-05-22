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

test.describe('Sell shares', () => {
  test('cash increases and position updates after selling AAPL', async ({ page }) => {
    await page.goto('/');
    await waitForPrice(page, 'AAPL');

    const startQty = await currentQty(page, 'AAPL');

    const trade = panel(page, 'Trade');
    const tickerInput = trade.getByPlaceholder('TICKER');
    const qtyInput = trade.locator('input[type="number"]');

    await tickerInput.fill('AAPL');
    await qtyInput.fill('3');
    await trade.getByRole('button', { name: 'Buy' }).click();

    await expect(positionRow(page, 'AAPL')).toBeVisible();
    await expect(positionQty(page, 'AAPL')).toHaveText(String(startQty + 3));

    const cash = cashValue(page);
    const cashAfterBuy = parseMoney(await cash.innerText());

    await tickerInput.fill('AAPL');
    await qtyInput.fill('1');
    await trade.getByRole('button', { name: 'Sell' }).click();

    await expect
      .poll(async () => parseMoney(await cash.innerText()))
      .toBeGreaterThan(cashAfterBuy);

    await expect(positionQty(page, 'AAPL')).toHaveText(String(startQty + 2));
  });
});
