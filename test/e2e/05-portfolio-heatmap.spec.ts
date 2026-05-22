import { expect, test } from '@playwright/test';
import { panel, positionRow, waitForPrice } from './helpers';

test.describe('Portfolio heatmap', () => {
  test('renders at least one rectangle after a position exists', async ({ page }) => {
    await page.goto('/');
    await waitForPrice(page, 'AAPL');

    const trade = panel(page, 'Trade');
    await trade.getByPlaceholder('TICKER').fill('AAPL');
    await trade.locator('input[type="number"]').fill('1');
    await trade.getByRole('button', { name: 'Buy' }).click();

    await expect(positionRow(page, 'AAPL')).toBeVisible();

    const heatmap = panel(page, 'Portfolio Heatmap');
    const rects = heatmap.locator('svg rect');
    await expect(rects.first()).toBeVisible();
    expect(await rects.count()).toBeGreaterThan(0);
  });
});
