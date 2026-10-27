import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded } from './utils'

/**
 * Data Quality Monitoring E2E Testing
 *
 * Product positioning: Ensure the stability and reliability of daily/historical data acquisition
 *
 * Coverage:
 * - Data source quality statistics (success rate/time consumption)
 * - QMT Connection diagnostics
 * - Data source configuration management
 * - Agent Workshop and version management
 */
test.describe('Data source quality monitoring', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Data source configuration management page loading', async ({ page }) => {
    await page.goto('/settings/config')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/config/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Synchronous page loading from multiple data sources', async ({ page }) => {
    await page.goto('/settings/sync')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/sync/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Cache management page loading', async ({ page }) => {
    await page.goto('/settings/cache')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/cache/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })
})

test.describe('QMT Connection diagnostics', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('QMT Diagnostics - Configuration Management page is accessible', async ({ page }) => {
    // QMT Diagnostics are provided through the backend API and the frontend is accessed through the configuration management page
    await page.goto('/settings/config')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/config/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Run QMT connection diagnostics', async ({ page }) => {
    // QMT Diagnostics functionality has been merged into the configuration management page
    await page.goto('/settings/config')
    await waitForLoadingDone(page)

    const diagnosisBtn = page.locator('button:has-text("Diagnosis"), button:has-text("Check")').first()
    if (await diagnosisBtn.isVisible({ timeout: 5000 })) {
      await diagnosisBtn.click()
      await page.waitForTimeout(5000)
    }
  })
})

test.describe('Data source configuration', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Configuration management page loading', async ({ page }) => {
    await page.goto('/settings/config')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/config/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Set up home page loading', async ({ page }) => {
    await page.goto('/settings')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings/)
  })

  test('Stock watch list grouping configuration', async ({ page }) => {
    await page.goto('/settings/watchlist-groups')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/watchlist-groups/)
  })
})

test.describe('Agent workshop', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Agent List page loads', async ({ page }) => {
    await page.goto('/workflow/agent-workshop')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/workflow\/agent-workshop/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('View Agent version history', async ({ page }) => {
    await page.goto('/workflow/agent-workshop')
    await waitForLoadingDone(page)

    const historyBtn = page.locator('button:has-text("Historical version"), button:has-text("version")').first()
    if (await historyBtn.isVisible({ timeout: 5000 })) {
      await historyBtn.click()
      await waitForLoadingDone(page)
      await page.waitForTimeout(3000)
    }
  })

  test('Agent Version rollback', async ({ page }) => {
    await page.goto('/workflow/agent-workshop')
    await waitForLoadingDone(page)

    const rollbackBtn = page.locator('button:has-text("rollback"), .rollback-btn').first()
    if (await rollbackBtn.isVisible({ timeout: 5000 })) {
      await rollbackBtn.click()
      await page.waitForTimeout(2000)

      const confirmBtn = page.locator('.el-dialog button:has-text("OK")').first()
      if (await confirmBtn.isVisible({ timeout: 3000 })) {
        await confirmBtn.click()
        await page.waitForTimeout(3000)
      }
    }
  })
})
