import { test, expect } from '@playwright/test'
import { login, TEST_USER } from './utils'

/**
 * Certification Process E2E Testing
 *
 * Cover:
 * - Login page loads
 * - Login successful with correct credentials
 * - Login failed with incorrect credentials
 * - If you are not logged in and access the protected route, you will be redirected to the login page.
 * - Log out
 */
test.describe('Certification process', () => {
  test('The login page should load correctly', async ({ page }) => {
    await page.goto('/login')

    // Verify that the login form element exists
    await expect(page.locator('input[type="text"], input[placeholder*="Username"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.locator('button:has-text("Login"), button[type="submit"]')).toBeVisible()
  })

  test('Log in successfully with correct credentials and jump to Dashboard', async ({ page }) => {
    await login(page)

    // Verify jump to dashboard
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })

    // Verify that localStorage contains token
    const token = await page.evaluate(() => localStorage.getItem('auth-token'))
    expect(token).toBeTruthy()
  })

  test('Login failed with wrong password', async ({ page }) => {
    await page.goto('/login')

    const usernameInput = page.locator('input[placeholder*="Username"], input[type="text"]').first()
    const passwordInput = page.locator('input[type="password"]').first()
    await usernameInput.fill(TEST_USER.username)
    await passwordInput.fill('wrong_password')

    // Check the agreement (Element Plus checkbox requires clicking label)
    const agreementLabel = page.locator('.el-checkbox:has-text("Agree")').first()
    if (await agreementLabel.isVisible({ timeout: 3000 }).catch(() => false)) {
      await agreementLabel.click()
    }

    await page.locator('button:has-text("Login"), button[type="submit"]').first().click()

    // Wait for the request to complete
    await page.waitForTimeout(3000)

    // You should still be on the login page (the wrong password will not jump)
    await expect(page).toHaveURL(/\/login/)
  })

  test('If you are not logged in and access the protected route, you should be redirected to the login page.', async ({ page }) => {
    // Clear login status
    await page.goto('/login')
    await page.evaluate(() => {
      localStorage.clear()
    })

    // Access pages that require authentication
    await page.goto('/dashboard')

    // Should jump to login page
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })

  test('Public pages can be accessed without logging in', async ({ page }) => {
    // About page is public
    await page.goto('/about')
    // Should not jump to login page
    await expect(page).not.toHaveURL(/\/login/)
  })
})
