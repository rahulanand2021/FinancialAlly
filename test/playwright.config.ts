import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for FinAlly E2E tests.
 *
 * BASE_URL is read from the environment so the same suite runs against:
 *   - http://app:8000   when invoked inside docker-compose.test.yml
 *   - http://localhost:8000 when invoked on the host
 */
const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
