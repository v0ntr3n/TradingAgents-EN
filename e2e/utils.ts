/**
 * E2E Test common utility functions
 */
import type { Page } from '@playwright/test'

/**
 * Default test account
 */
export const TEST_USER = {
  username: 'admin',
  password: 'admin123',
}

/**
 * Login process: Visit the login page, fill in the form, check the agreement, and submit login
 * Automatically jump to after successful login dashboard
 */
export async function login(page: Page): Promise<void> {
  await page.goto('/login')

  // Wait for the login form to load
  await page.waitForSelector('.login-card', { timeout: 10000 })

  // Fill in username and password
  await page.locator('.el-form-item').filter({ hasText: 'Username' }).locator('input').fill(TEST_USER.username)
  await page.locator('.el-form-item').filter({ hasText: 'Password' }).locator('input').fill(TEST_USER.password)

  // Check"I have read and agree"Protocol checkbox
  const agreementCheckbox = page.locator('.agreement-check .el-checkbox')
  await agreementCheckbox.click()
  await page.waitForTimeout(500)

  // Click the login button
  await page.locator('button:has-text("Login")').first().click()

  // Waiting to jump to dashboard or other authenticated page
  await page.waitForURL(url => !url.toString().includes('/login'), { timeout: 15000 })
}

/**
 * Make sure you are logged in, if not logged in then log in first
 */
export async function ensureLoggedIn(page: Page): Promise<void> {
  const token = await page.evaluate(() => localStorage.getItem('auth-token'))
  if (!token) {
    await login(page)
  }
}

/**
 * Wait for Element Plus loading mask to disappear
 */
export async function waitForLoadingDone(page: Page): Promise<void> {
  const loadingMask = page.locator('.el-loading-mask')
  if (await loadingMask.isVisible({ timeout: 1000 }).catch(() => false)) {
    await loadingMask.waitFor({ state: 'hidden', timeout: 30000 })
  }
}

/**
 * Wait for the Element Plus table to finish loading
 */
export async function waitForTableLoaded(page: Page): Promise<void> {
  await page.waitForSelector('table', { timeout: 10000 })
  await waitForLoadingDone(page)
}

/**
 * Get the message prompt text of Element Plus
 */
export async function getElMessage(page: Page): Promise<string | null> {
  const message = page.locator('.el-message__content')
  if (await message.isVisible({ timeout: 2000 }).catch(() => false)) {
    return message.textContent()
  }
  return null
}

/**
 * Select a stock symbol (autocomplete scenario)
 */
export async function selectStock(page: Page, stockCode: string): Promise<void> {
  const input = page.locator('input[placeholder*="000001"], input[placeholder*="stocks"], input[placeholder*="code"], .stock-input input').first()
  await input.fill(stockCode)
  await page.waitForTimeout(1500)
  
  const dropdownOption = page.locator('.el-select-dropdown__item, .el-autocomplete-suggestion li').first()
  if (await dropdownOption.isVisible({ timeout: 3000 })) {
    await dropdownOption.click()
  }
}

/**
 * Wait for the modal to close
 */
export async function waitForModalClose(page: Page): Promise<void> {
  const modal = page.locator('.el-modal')
  if (await modal.isVisible({ timeout: 1000 })) {
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
  }
}

/**
 * Click the OK button (Processing Element Plus dialog box)
 */
export async function clickConfirm(page: Page): Promise<void> {
  const confirmBtn = page.locator('.el-dialog__footer button:has-text("OK"), .el-dialog__footer button[type="primary"]').first()
  if (await confirmBtn.isVisible({ timeout: 3000 })) {
    await confirmBtn.click()
    await waitForModalClose(page)
  }
}

/**
 * Click the Cancel button (Processing Element Plus dialog box)
 */
export async function clickCancel(page: Page): Promise<void> {
  const cancelBtn = page.locator('.el-dialog__footer button:has-text("Cancel")').first()
  if (await cancelBtn.isVisible({ timeout: 3000 })) {
    await cancelBtn.click()
    await waitForModalClose(page)
  }
}

/**
 * Wait for the sidebar menu to expand
 */
export async function waitForSidebarMenu(page: Page): Promise<void> {
  await page.waitForSelector('.el-menu, .sidebar-menu', { timeout: 10000 })
}

/**
 * Navigate to specified page (via sidebar)
 */
export async function navigateBySidebar(page: Page, menuText: string): Promise<void> {
  await waitForSidebarMenu(page)
  const menuItem = page.locator(`.el-menu-item:has-text("${menuText}"), .sidebar-item:has-text("${menuText}")`).first()
  if (await menuItem.isVisible({ timeout: 5000 })) {
    await menuItem.click()
    await waitForLoadingDone(page)
  }
}

/**
 * Wait for table data to load
 */
export async function waitForTableData(page: Page): Promise<void> {
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await waitForLoadingDone(page)
}

/**
 * Verify page title
 */
export async function verifyPageTitle(page: Page, title: string): Promise<void> {
  const pageTitle = page.locator('h1, .page-title, .el-page-header__title').first()
  await expect(pageTitle).toHaveText(title, { timeout: 10000 })
}

/**
 * Random waiting (simulating user thinking time)
 */
export async function randomWait(minMs: number = 500, maxMs: number = 2000): Promise<void> {
  const waitTime = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs
  await new Promise(resolve => setTimeout(resolve, waitTime))
}
