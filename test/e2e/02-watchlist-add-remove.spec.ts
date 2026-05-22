import { expect, test } from '@playwright/test';
import { panel, watchlistRow } from './helpers';

test.describe('Watchlist add/remove', () => {
  test('adds a new ticker and then removes it', async ({ page }) => {
    await page.goto('/');

    const newTicker = 'PLTR';
    const watchlist = panel(page, 'Watchlist');

    await watchlist.getByPlaceholder('ADD').fill(newTicker);
    await watchlist.getByRole('button', { name: '+' }).click();

    await expect(watchlistRow(page, newTicker)).toBeVisible();

    await watchlist.getByRole('button', { name: `Remove ${newTicker}` }).click();

    await expect(watchlistRow(page, newTicker)).toHaveCount(0);
  });
});
