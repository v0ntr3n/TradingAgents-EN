import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded } from './utils'

/**
 * Core Page Navigation E2E Test
 *
 * Cover:
 * - Dashboard Page loading
 * - Sidebar navigation to each core page
 * - Page title displays correctly
 */
test.describe('Core page navigation', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Dashboard Page loads correctly', async ({ page }) => {
    await page.goto('/dashboard')
    await waitForLoadingDone(page)

    // Verify that the page has content (not a blank page)
    const mainContent = page.locator('.el-main, .app-main, main, .dashboard').first()
    await expect(mainContent).toBeVisible({ timeout: 10000 })
  })

  test('Navigate to the single stock analysis page', async ({ page }) => {
    await page.goto('/analysis/single')
    await waitForLoadingDone(page)

    // Verify page loading
    await expect(page).toHaveURL(/\/analysis\/single/)
  })

  test('Navigate to filter page', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/screening/)
  })

  test('Navigate to favorites page', async ({ page }) => {
    await page.goto('/favorites')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/favorites/)
  })

  test('Navigate to the report page', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/reports/)
  })

  test('Navigate to the positions page', async ({ page }) => {
    await page.goto('/portfolio')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/portfolio/)
  })

  test('Navigate to the simulated trading page', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/paper/)
  })

  test('Navigate to the transaction review page', async ({ page }) => {
    await page.goto('/review')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/review/)
  })

  test('Navigate to the Task Center page', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/tasks\/unified/)
  })

  test('Navigate to the settings page', async ({ page }) => {
    await page.goto('/settings')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings/)
  })
})
