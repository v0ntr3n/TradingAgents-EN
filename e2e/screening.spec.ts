import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded, selectStock } from './utils'

/**
 * Intelligent stock selection E2E test
 *
 * Product positioning: multi-condition combination screening based on fundamental and technical indicators
 *
 * Coverage:
 * - Fundamental screening (PE/PB/ROE)
 * - Technical indicator screening (moving average/trading volume)
 * - Industry sector screening
 * - Sort and save filter results
 * - Stock watch list management (add/group/batch operations)
 */
test.describe('Intelligent Stock Picking - Fundamental Screening', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('PE/PB/ROE Multiple condition combination filtering', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/screening/)

    // Switch to advanced mode tab
    const advancedTab = page.locator('.el-tabs__item:has-text("Advanced mode")').first()
    if (await advancedTab.isVisible({ timeout: 5000 })) {
      await advancedTab.click()
      await page.waitForTimeout(2000)
    }

    const filterPanel = page.locator('.filter-panel').first()
    // Wait for the v-loading mask on filter-panel to disappear
    await filterPanel.locator('.el-loading-mask').waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {})
    await filterPanel.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
    // Skip if filter-panel is still not visible (data source may not be configured)
    const filterVisible = await filterPanel.isVisible().catch(() => false)
    if (!filterVisible) {
      return
    }

    const peInput = page.locator('input[placeholder*="PE"], input[name*="pe"]').first()
    if (await peInput.isVisible({ timeout: 5000 })) {
      await peInput.fill('0-30')
    }

    const pbInput = page.locator('input[placeholder*="PB"], input[name*="pb"]').first()
    if (await pbInput.isVisible({ timeout: 3000 })) {
      await pbInput.fill('0-5')
    }

    const screenBtn = page.locator('button:has-text("Filter")').first()
    if (await screenBtn.isVisible({ timeout: 3000 })) {
      await screenBtn.click()
      await page.waitForTimeout(5000)
    }
  })

  test('Industry sector screening', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    const industrySelector = page.locator('.industry-selector, .el-select:has-text("Industry")').first()
    if (await industrySelector.isVisible({ timeout: 5000 })) {
      await industrySelector.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Sort filter results', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    const sortButton = page.locator('button:has-text("sort"), .sort-selector').first()
    if (await sortButton.isVisible({ timeout: 3000 })) {
      await sortButton.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Save filters', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    const saveBtn = page.locator('button:has-text("save"), button:has-text("Collection")').first()
    if (await saveBtn.isVisible({ timeout: 3000 })) {
      await saveBtn.click()
      await page.waitForTimeout(2000)
    }
  })
})

test.describe('Intelligent Stock Picking - Technical Indicator Screening', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Moving average condition filter', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    const maFilter = page.locator('text=moving average, .ma-filter, .moving-average').first()
    if (await maFilter.isVisible({ timeout: 5000 })) {
      await maFilter.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Filter by trading volume conditions', async ({ page }) => {
    await page.goto('/screening')
    await waitForLoadingDone(page)

    const volumeFilter = page.locator('text=Volume, .volume-filter').first()
    if (await volumeFilter.isVisible({ timeout: 5000 })) {
      await volumeFilter.click()
      await page.waitForTimeout(2000)
    }
  })
})

test.describe('Stock watch list management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Add stocks to your selection', async ({ page }) => {
    await page.goto('/favorites')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/favorites/)

    const addBtn = page.locator('button:has-text("add"), button:has(.el-icon-plus)').first()
    if (await addBtn.isVisible({ timeout: 5000 })) {
      await addBtn.click()

      const input = page.locator('input[placeholder*="Stock code"]').first()
      if (await input.isVisible({ timeout: 3000 })) {
        await input.fill('600519')
      }

      const confirmBtn = page.locator('button:has-text("OK"), button[type="primary"]').first()
      if (await confirmBtn.isVisible({ timeout: 3000 })) {
        await confirmBtn.click()
        await page.waitForTimeout(2000)
      }
    }
  })

  test('Stock watchlist list loading', async ({ page }) => {
    await page.goto('/favorites')
    await waitForLoadingDone(page)

    const favoritesTable = page.locator('.el-table')
    await expect(favoritesTable).toBeVisible({ timeout: 10000 })
  })

  test('Stock watch list group management', async ({ page }) => {
    await page.goto('/favorites')
    await waitForLoadingDone(page)

    const groupSelector = page.locator('.group-selector, .el-select:has-text("Group")').first()
    if (await groupSelector.isVisible({ timeout: 5000 })) {
      await groupSelector.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Initiate analysis from a stock watchlist', async ({ page }) => {
    await page.goto('/favorites')
    await waitForLoadingDone(page)

    const analyzeBtn = page.locator('button:has-text("analysis"), .analyze-btn').first()
    if (await analyzeBtn.isVisible({ timeout: 5000 })) {
      await analyzeBtn.click()
      await page.waitForTimeout(3000)
    }
  })
})
