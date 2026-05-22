import { expect, test } from '@playwright/test';
import { currentQty, panel, positionQty, positionRow, watchlistRow } from './helpers';

/**
 * Verifies the LLM_MOCK fixture from PLAN.md §9: any chat message triggers
 * a mock response that buys 5 AAPL shares and adds NVDA to the watchlist.
 * NVDA is already in the default watchlist (action returns already_present),
 * so we assert NVDA stays present plus the +5 AAPL buy and the fixture message.
 */
test.describe('AI chat (mocked)', () => {
  test('mock response executes AAPL buy and confirms NVDA on watchlist', async ({ page }) => {
    await page.goto('/');

    const startQty = await currentQty(page, 'AAPL');

    const chat = panel(page, 'AI Assistant');
    await chat.getByPlaceholder('Ask FinAlly...').fill('hello finally');
    await chat.getByRole('button', { name: 'Send' }).click();

    await expect(chat).toContainText(/I've reviewed your portfolio/i);

    await expect(positionRow(page, 'AAPL')).toBeVisible();
    await expect(positionQty(page, 'AAPL')).toHaveText(String(startQty + 5));

    await expect(watchlistRow(page, 'NVDA')).toBeVisible();
  });
});
