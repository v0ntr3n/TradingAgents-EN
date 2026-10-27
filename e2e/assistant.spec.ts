import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone } from './utils'

test.describe('Smart Assistant', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Smart assistant page loading', async ({ page }) => {
    await page.goto('/assistant')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/assistant/)

    // Page title
    const pageTitle = page.locator('h1:has-text("Smart Assistant")')
    await expect(pageTitle).toBeVisible({ timeout: 10000 })

    // top action button
    const newThreadBtn = page.locator('button:has-text("new theme")')
    await expect(newThreadBtn).toBeVisible({ timeout: 5000 })

    // input area
    const inputArea = page.locator('.input-area')
    await expect(inputArea).toBeVisible({ timeout: 5000 })
  })

  test('Smart Assistant - Quick Conversation', async ({ page }) => {
    test.setTimeout(120000) // 2 minutes timeout
    await page.goto('/assistant')
    await waitForLoadingDone(page)

    // 1. Create new topic
    const newThreadBtn = page.locator('button:has-text("new theme")').first()
    await newThreadBtn.click()
    await page.waitForTimeout(1000)

    // If there is a dialog box, fill in the topic name
    const dialogInput = page.locator('.el-message-box__input input, .el-message-box input').first()
    if (await dialogInput.isVisible({ timeout: 3000 })) {
      await dialogInput.fill('E2E test conversation')
      // Confirm creation (button text is"Create") 
      const confirmBtn = page.locator('.el-message-box button:has-text("Create")').first()
      await confirmBtn.click()
      await page.waitForTimeout(2000)
    }

    // 2. Make sure the topic is selected and the send button is enabled
    // Try selecting the first topic in the tree on the left
    const firstTreeNode = page.locator('.thread-tree .el-tree-node').first()
    await firstTreeNode.click()
    await page.waitForTimeout(1000)

    // 3. Enter question
    const textarea = page.locator('.input-area textarea').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })
    await textarea.fill('Hello, please briefly introduce yourself')
    await page.waitForTimeout(500)

    // 4. Click to send
    const sendBtn = page.locator('.send-btn').first()
    await expect(sendBtn).toBeEnabled({ timeout: 5000 })
    await sendBtn.click()

    // 5. Wait for assistant reply (streaming output)
    // User message appears
    const userMsg = page.locator('.message-user').first()
    await expect(userMsg).toBeVisible({ timeout: 30000 })

    // Wait for assistant to reply
    const assistantMsg = page.locator('.message-assistant').first()
    await expect(assistantMsg).toBeVisible({ timeout: 60000 })

    // 6. Verify that the reply has content
    const assistantContent = assistantMsg.locator('.message-text, .markdown-content').first()
    await expect(assistantContent).toBeVisible({ timeout: 10000 })
    const contentText = await assistantContent.textContent()
    expect(contentText?.length).toBeGreaterThan(10)
  })

  test('Smart Assistant - Topic List', async ({ page }) => {
    await page.goto('/assistant')
    await waitForLoadingDone(page)

    // Show subject bar
    const showThreadBtn = page.locator('button:has-text("Show subject bar")').first()
    if (await showThreadBtn.isVisible({ timeout: 3000 })) {
      await showThreadBtn.click()
      await page.waitForTimeout(1000)
    }

    // Topic tree or empty state
    const threadTree = page.locator('.thread-tree, .el-empty').first()
    await expect(threadTree).toBeVisible({ timeout: 5000 })
  })

  test('Smart Assistant - Assistant Settings Pop-up Window', async ({ page }) => {
    await page.goto('/assistant')
    await waitForLoadingDone(page)

    // Click Assistant Settings
    const settingsBtn = page.locator('button:has-text("Assistant settings")').first()
    await settingsBtn.click()
    await page.waitForTimeout(1000)

    // The settings dialog box appears (titled"Assistant settings"pop-up window)
    const dialog = page.locator('.el-dialog:has-text("Assistant settings"), .el-drawer:has-text("Assistant settings")').first()
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Close dialog
    const closeBtn = page.locator('.el-dialog__close, .el-drawer__close-btn').first()
    if (await closeBtn.isVisible({ timeout: 3000 })) {
      await closeBtn.click()
    }
  })
})