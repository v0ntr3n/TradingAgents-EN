import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded } from './utils'

/**
 * Position management E2E test
 *
 * Product positioning: Portfolio management based on historical data
 *
 * Coverage:
 * - View position list
 * - Position profit analysis
 * - Position distribution chart
 * - Simulated trading (buy/sell/transaction record)
 * - Transaction review (win rate/profit and loss/transaction details)
 */
test.describe('Position management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Position list page loads', async ({ page }) => {
    await page.goto('/portfolio')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/portfolio/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Position income statistics', async ({ page }) => {
    await page.goto('/portfolio')
    await waitForLoadingDone(page)

    const totalAssets = page.locator(':text("total assets"), .total-assets').first()
    await expect(totalAssets).toBeVisible({ timeout: 10000 })
  })

  test('Position statistics card', async ({ page }) => {
    await page.goto('/portfolio')
    await waitForLoadingDone(page)

    const statCard = page.locator('.stat-card, .stat-value').first()
    await expect(statCard).toBeVisible({ timeout: 10000 })
  })

  test('Initiate analysis from a position', async ({ page }) => {
    await page.goto('/portfolio')
    await waitForLoadingDone(page)

    const analyzeBtn = page.locator('button:has-text("analysis"), .analyze-btn').first()
    if (await analyzeBtn.isVisible({ timeout: 5000 })) {
      await analyzeBtn.click()
      await page.waitForTimeout(3000)
    }
  })
})

test.describe('simulated trading', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Simulated trading page loading', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/paper/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Stock buying process', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    const buyTab = page.locator('text=buy, .buy-tab').first()
    if (await buyTab.isVisible({ timeout: 5000 })) {
      await buyTab.click()
    }

    const stockInput = page.locator('input[placeholder*="stocks"], input[name*="code"]').first()
    if (await stockInput.isVisible({ timeout: 3000 })) {
      await stockInput.fill('000001')
      await page.waitForTimeout(2000)
    }

    const amountInput = page.locator('input[placeholder*="Quantity"], input[name*="amount"]').first()
    if (await amountInput.isVisible({ timeout: 3000 })) {
      await amountInput.fill('100')
    }

    const submitBtn = page.locator('button:has-text("buy"), button[type="primary"]').first()
    if (await submitBtn.isVisible({ timeout: 3000 })) {
      await submitBtn.click()
      await page.waitForTimeout(3000)
    }
  })

  test('Selling Stock Process', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    const sellTab = page.locator('text=sell, .sell-tab').first()
    if (await sellTab.isVisible({ timeout: 5000 })) {
      await sellTab.click()
    }

    const stockSelector = page.locator('.stock-selector, .el-select').first()
    if (await stockSelector.isVisible({ timeout: 3000 })) {
      await stockSelector.click()
      await page.waitForTimeout(2000)
    }
  })

  test('View transaction history', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    const tradeHistoryTab = page.locator('text=transaction history, .history-tab').first()
    if (await tradeHistoryTab.isVisible({ timeout: 5000 })) {
      await tradeHistoryTab.click()
      await waitForTableLoaded(page)
    }
  })

  test('View position details', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    const positionTab = page.locator('text=Position, .position-tab').first()
    if (await positionTab.isVisible({ timeout: 5000 })) {
      await positionTab.click()
      await waitForTableLoaded(page)
    }
  })

  test('Asset overview', async ({ page }) => {
    await page.goto('/paper')
    await waitForLoadingDone(page)

    const assetOverview = page.locator('.asset-summary, .el-card:has-text("total assets")').first()
    await expect(assetOverview).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Transaction review', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('The review overview page loads', async ({ page }) => {
    await page.goto('/review')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/review/)

    const overview = page.locator('.review-overview, .el-card').first()
    await expect(overview).toBeVisible({ timeout: 10000 })
  })

  test('View transaction details', async ({ page }) => {
    await page.goto('/review')
    await waitForLoadingDone(page)

    const detailTab = page.locator('text=Transaction details, .detail-tab').first()
    if (await detailTab.isVisible({ timeout: 5000 })) {
      await detailTab.click()
      await waitForTableLoaded(page)
    }
  })

  test('View profit and loss analysis', async ({ page }) => {
    await page.goto('/review')
    await waitForLoadingDone(page)

    const profitTab = page.locator('text=Profit and loss, text=income, .profit-tab').first()
    if (await profitTab.isVisible({ timeout: 5000 })) {
      await profitTab.click()
      await page.waitForTimeout(3000)
    }
  })

  test('View win rate statistics', async ({ page }) => {
    await page.goto('/review')
    await waitForLoadingDone(page)

    // Switch to the simulated trading review tab to see the winning rate statistics
    await page.locator('.el-tabs__item').filter({ hasText: 'Simulated trading review' }).first().click()
    await page.waitForTimeout(3000)
    await waitForLoadingDone(page)

    const winRate = page.locator('.stat-label:has-text("winning rate"), :text("winning rate")').first()
    await expect(winRate).toBeVisible({ timeout: 10000 })
  })
})
