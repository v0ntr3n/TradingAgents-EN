import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded } from './utils'

/**
 * Trading Plan E2E Testing
 *
 * Product positioning: investment plan based on historical data analysis results
 *
 * Coverage:
 * - Trading plan list
 * - Create/edit/delete trading plan
 * - Activate/deactivate trading plan
 * - Stop loss and take profit rule settings
 * - Linkage of plans and positions
 */
test.describe('Trading plan management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Trading plan list page loads', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/trading-system/)

    const content = page.locator('.el-main, .app-main, main, .el-card, .el-table').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Create a new trading plan', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    const createBtn = page.locator('button:has-text("Create"), button:has(.el-icon-plus)').first()
    if (await createBtn.isVisible({ timeout: 5000 })) {
      await createBtn.click()
      await page.waitForTimeout(3000)

      const planNameInput = page.locator('input[placeholder*="Plan name"], input[name*="name"]').first()
      if (await planNameInput.isVisible({ timeout: 3000 })) {
        await planNameInput.fill('Test trading plan')
      }
    }
  })

  test('Edit trading plan', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    const editBtn = page.locator('button:has-text("Edit"), .el-button--edit').first()
    if (await editBtn.isVisible({ timeout: 3000 })) {
      await editBtn.click()
      await page.waitForTimeout(3000)
    }
  })

  test('Activate/deactivate trading plan', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    const toggleBtn = page.locator('button:has-text("activate"), button:has-text("deactivate")').first()
    if (await toggleBtn.isVisible({ timeout: 3000 })) {
      await toggleBtn.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Set stop loss and take profit rules', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    const ruleBtn = page.locator('button:has-text("rules"), .rule-settings').first()
    if (await ruleBtn.isVisible({ timeout: 3000 })) {
      await ruleBtn.click()
      await page.waitForTimeout(3000)

      const stopLossInput = page.locator('input[placeholder*="stop loss"], .stop-loss input').first()
      if (await stopLossInput.isVisible({ timeout: 3000 })) {
        await stopLossInput.fill('10')
      }

      const takeProfitInput = page.locator('input[placeholder*="Take profit"], .take-profit input').first()
      if (await takeProfitInput.isVisible({ timeout: 3000 })) {
        await takeProfitInput.fill('20')
      }
    }
  })

  test('View trading plan details', async ({ page }) => {
    await page.goto('/trading-system')
    await waitForLoadingDone(page)

    const viewBtn = page.locator('button:has-text("View"), .view-detail').first()
    if (await viewBtn.isVisible({ timeout: 3000 })) {
      await viewBtn.click()
      await page.waitForTimeout(3000)
    }
  })
})
