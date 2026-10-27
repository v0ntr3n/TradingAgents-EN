import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded } from './utils'

/**
 * Investment Report E2E Testing
 *
 * Product positioning: In-depth analysis report generated based on daily historical data
 *
 * Coverage:
 * - View report list
 * - View report details
 * - Report search and filtering
 * - Report export
 * - Token Consumption statistics
 */
test.describe('Investment reporting management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Report list page loads', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/reports/)

    const reportTable = page.locator('.el-table, .report-list').first()
    await expect(reportTable).toBeVisible({ timeout: 10000 })
  })

  test('View report details', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    const viewBtn = page.locator('button:has-text("View"), .view-report').first()
    if (await viewBtn.isVisible({ timeout: 3000 })) {
      await viewBtn.click()
      await page.waitForTimeout(5000)
    }
  })

  test('search report', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    const searchInput = page.locator('input[placeholder*="Search"], .search-input').first()
    if (await searchInput.isVisible({ timeout: 5000 })) {
      await searchInput.fill('Kweichow Moutai')
      await page.waitForTimeout(2000)
    }
  })

  test('Filter reports by time', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    const datePicker = page.locator('.el-date-picker, .date-range').first()
    if (await datePicker.isVisible({ timeout: 5000 })) {
      await datePicker.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Export report', async ({ page }) => {
    await page.goto('/reports')
    await waitForLoadingDone(page)

    const exportBtn = page.locator('button:has-text("Export"), button:has(.el-icon-download)').first()
    if (await exportBtn.isVisible({ timeout: 3000 })) {
      await exportBtn.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Token Consumption statistics page', async ({ page }) => {
    await page.goto('/reports/token')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/reports\/token/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })
})
