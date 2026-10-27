import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E Test configuration
 *
 * Preconditions:
 * 1. The backend service runs on http://localhost:8000
 * 2. The front-end dev server runs on http://localhost:3000
 *
 * run: npx playwright test
 * Run UI mode: npx playwright test --ui
 * View report: npx playwright show-report
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Serial execution to avoid test data conflicts
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // Single worker to avoid concurrency issues
  reporter: [
    ['html', { outputFolder: 'e2e-reports/html' }],
    ['list'],
  ],
  timeout: 60000, // 60 seconds timeout
  expect: {
    timeout: 10000,
  },
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3002',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
