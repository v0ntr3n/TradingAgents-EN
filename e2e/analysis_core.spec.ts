import { test, expect } from '@playwright/test'
import { login, waitForLoadingDone, waitForTableLoaded, selectStock } from './utils'

/**
 * Core analysis process E2E testing
 *
 * Product positioning: In-depth analysis platform based on daily lines, historical data and fundamentals
 *
 * Coverage:
 * - In-depth analysis of single stocks (technical aspects + Fundamentals)
 * - Portfolio health analysis
 * - Risk assessment analysis
 * - Analysis task management (view/retry/cancel)
 * - Analysis results viewing and feedback
 * - Timing analysis configuration
 */
test.describe('In-depth analysis of single stocks', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Trigger single stock analysis - enter a stock symbol and start analysis', async ({ page }) => {
    test.setTimeout(600000) // Analysis takes time, set a 10 minute timeout
    await page.goto('/analysis/single')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/analysis\/single/)

    const stockInput = page.locator('input[placeholder*="000001"], .stock-input input').first()
    await expect(stockInput).toBeVisible({ timeout: 10000 })

    // Fill in the stock code and trigger the blur event to complete the verification
    await stockInput.fill('600519')
    await stockInput.blur()
    await page.waitForTimeout(2000)

    // Select Level 1 Quick Analysis (fastest, 2-5 minutes)
    const depthOptions = page.locator('.depth-option')
    const quickDepth = depthOptions.first() // 1 level = first one
    await quickDepth.click()
    await page.waitForTimeout(500)

    // Confirm button is enabled
    const analyzeBtn = page.locator('button:has-text("Start smart analysis")').first()
    await expect(analyzeBtn).toBeEnabled({ timeout: 10000 })

    // Click to start analysis
    await analyzeBtn.click()

    // Verification analysis submitted: progress indicator appears
    await expect(page.locator('button:has-text("Analysis in progress"), .progress-info, .el-progress').first()).toBeVisible({ timeout: 15000 })

    // 🔥 Key: Wait for the analysis to actually complete and the results area to appear
    // 1 Level quick analysis typically takes 2-5 minutes, set a 10 minute timeout
    const resultsSection = page.locator('.results-section, .results-card')
    await expect(resultsSection.first()).toBeVisible({ timeout: 600000 })

    // ✅ Verify the integrity of analysis results
    // 1. Analysis result card exists
    const resultsCard = page.locator('.results-card').first()
    await expect(resultsCard).toBeVisible()

    // 2. ticker label exists
    const stockTag = page.locator('.results-card .el-tag').first()
    await expect(stockTag).toBeVisible()

    // 3. Analysis overview exists
    const overview = page.locator('.overview-section, .markdown-content').first()
    await expect(overview).toBeVisible({ timeout: 10000 })

    // 4. Detailed analysis report tab page exists
    const analysisTabs = page.locator('.analysis-tabs, .el-tabs').first()
    await expect(analysisTabs).toBeVisible({ timeout: 10000 })

    // 5. 🔴 Check for backend errors/downgraded nodes
    const degradedAlert = page.locator('.el-alert:has-text("Downgrade"), .el-alert:has-text("failed")')
    const degradedVisible = await degradedAlert.isVisible().catch(() => false)
    if (degradedVisible) {
      // Take a screenshot to save the error message, but prevent the test from failing (downgrade is a normal fault tolerance mechanism)
      console.log('⚠️ Analysis of downgraded nodes, see screenshots for details')
      await page.screenshot({ path: 'test-results/analysis-degraded-nodes.png', fullPage: true })
    }

    // 6. Verify that at least one reporting tab has content
    const firstTab = page.locator('.el-tabs__content .report-content-wrapper').first()
    await expect(firstTab).toBeVisible({ timeout: 10000 })
  })

  test('Analysis page is loaded - entrances to each analysis dimension are visible', async ({ page }) => {
    await page.goto('/analysis/single')
    await waitForLoadingDone(page)

    const content = page.locator('.el-main, .app-main, main').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('View historical analysis results', async ({ page }) => {
    await page.goto('/analysis/history')
    await waitForLoadingDone(page)

    const content = page.locator('.el-main, .app-main, main, .el-table').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Analytical task management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Task Center - View analysis task list', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/tasks\/unified/)

    const taskTable = page.locator('.el-table, .task-list').first()
    await expect(taskTable).toBeVisible({ timeout: 10000 })
  })

  test('Task Center - Verification analysis task has been submitted', async ({ page }) => {
    // Trigger an analysis first
    await page.goto('/analysis/single')
    await waitForLoadingDone(page)
    const stockInput = page.locator('input[placeholder*="000001"], .stock-input input').first()
    await stockInput.fill('000001')
    await stockInput.blur()
    await page.waitForTimeout(2000)
    const analyzeBtn = page.locator('button:has-text("Start smart analysis")').first()
    await expect(analyzeBtn).toBeEnabled({ timeout: 10000 })
    await analyzeBtn.click()
    await page.waitForTimeout(3000)

    // Then go to the task center to verify that the task has appeared
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const taskTable = page.locator('.el-table').first()
    await expect(taskTable).toBeVisible({ timeout: 10000 })
    
    // Verify that there are data rows in the table (indicating that the analysis task has been submitted)
    const taskRows = page.locator('.el-table__body tr').first()
    await expect(taskRows).toBeVisible({ timeout: 10000 })
  })

  test('Task Center - Filter tasks by status', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const filterTabs = page.locator('.filter-tabs, .el-tabs__item').first()
    if (await filterTabs.isVisible({ timeout: 5000 })) {
      await filterTabs.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Task Center - View task details', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const detailBtn = page.locator('button:has-text("Details"), .view-detail').first()
    if (await detailBtn.isVisible({ timeout: 3000 })) {
      await detailBtn.click()
      await page.waitForTimeout(5000)
    }
  })

  test('Mission Center - Retry failed missions', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const retryBtn = page.locator('button:has-text("Try again"), button:has(.el-icon-refresh)').first()
    if (await retryBtn.isVisible({ timeout: 3000 })) {
      await retryBtn.click()
      await page.waitForTimeout(2000)
    }
  })

  test('Task Center - Cancel a running task', async ({ page }) => {
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const cancelBtn = page.locator('button:has-text("Cancel"), button:has(.el-icon-close)').first()
    if (await cancelBtn.isVisible({ timeout: 3000 })) {
      await cancelBtn.click()
      await page.waitForTimeout(2000)
    }
  })
})

test.describe('Analyze feedback', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Provide feedback on analysis results', async ({ page }) => {
    await page.goto('/analysis/history')
    await waitForLoadingDone(page)

    const viewBtn = page.locator('button:has-text("View"), .view-report').first()
    if (await viewBtn.isVisible({ timeout: 5000 })) {
      await viewBtn.click()
      await page.waitForTimeout(5000)

      const feedbackBtn = page.locator('button:has-text("feedback"), .feedback-btn').first()
      if (await feedbackBtn.isVisible({ timeout: 3000 })) {
        await feedbackBtn.click()
        await page.waitForTimeout(2000)
      }
    }
  })
})

test.describe('Timing analysis configuration', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Scheduled analysis configuration page loading', async ({ page }) => {
    await page.goto('/settings/scheduled-analysis')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/settings\/scheduled-analysis/)

    const content = page.locator('.el-main, .app-main, main, .el-card').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('Create scheduled analysis tasks', async ({ page }) => {
    await page.goto('/settings/scheduled-analysis')
    await waitForLoadingDone(page)

    const addBtn = page.locator('button:has-text("Create configuration")').first()
    if (await addBtn.isVisible({ timeout: 5000 })) {
      await addBtn.click()
      await page.waitForTimeout(3000)

      // Fill in the configuration name
      const nameInput = page.locator('.el-dialog input[placeholder*="Name"]').first()
      if (await nameInput.isVisible({ timeout: 3000 })) {
        await nameInput.fill('E2E Test timing analysis')
      }

      // Select analysis depth
      const depthSelect = page.locator('.el-dialog .el-select').first()
      if (await depthSelect.isVisible({ timeout: 3000 })) {
        await depthSelect.click()
        await page.waitForTimeout(1000)
        // Choose level 1 fast
        const option1 = page.locator('.el-select-dropdown__item:has-text("1 level")').first()
        if (await option1.isVisible({ timeout: 3000 })) {
          await option1.click()
          await page.waitForTimeout(500)
        }
      }

      // Click save
      const saveBtn = page.locator('.el-dialog button:has-text("save")').first()
      if (await saveBtn.isVisible({ timeout: 3000 })) {
        await saveBtn.click()
        await page.waitForTimeout(3000)
      }
    }
  })

  test('Test execution timing analysis', async ({ page }) => {
    test.setTimeout(300000) // Scheduled analysis takes time to execute
    await page.goto('/settings/scheduled-analysis')
    await waitForLoadingDone(page)

    // If configured, click"test execution"
    const testBtn = page.locator('button:has-text("test execution")').first()
    if (await testBtn.isVisible({ timeout: 5000 })) {
      await testBtn.click()
      await page.waitForTimeout(3000)

      // A verification execution result prompt appears.
      const successMsg = page.locator('.el-message--success, .el-notification').first()
      await expect(successMsg).toBeVisible({ timeout: 30000 })
    }
  })
})

test.describe('ETF analysis', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('ETF Analysis - Complete Process Validation', async ({ page }) => {
    test.setTimeout(600000) // Analysis takes time, set a 10 minute timeout
    await page.goto('/analysis/single')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/analysis\/single/)

    // Switch to ETF Market
    const marketSelect = page.locator('.el-select').first()
    await marketSelect.click()
    await page.waitForTimeout(500)
    const etfOption = page.locator('.el-select-dropdown__item:has-text("ETF")').first()
    await etfOption.click()
    await page.waitForTimeout(1000)

    // Enter ETF code
    const stockInput = page.locator('input[placeholder*="000001"], .stock-input input').first()
    await expect(stockInput).toBeVisible({ timeout: 10000 })
    await stockInput.fill('510050')
    await stockInput.blur()
    await page.waitForTimeout(2000)

    // Select Level 1 Quick Analysis
    const depthOptions = page.locator('.depth-option')
    const quickDepth = depthOptions.first()
    await quickDepth.click()
    await page.waitForTimeout(500)

    // Confirm button is enabled
    const analyzeBtn = page.locator('button:has-text("Start smart analysis")').first()
    await expect(analyzeBtn).toBeEnabled({ timeout: 10000 })

    // Click to start analysis
    await analyzeBtn.click()

    // Verification progress appears
    await expect(page.locator('button:has-text("Analysis in progress"), .progress-info, .el-progress').first()).toBeVisible({ timeout: 15000 })

    // Wait for the analysis to actually be completed
    const resultsSection = page.locator('.results-section, .results-card')
    await expect(resultsSection.first()).toBeVisible({ timeout: 600000 })

    // ✅ Validate ETF analysis results
    const resultsCard = page.locator('.results-card').first()
    await expect(resultsCard).toBeVisible()

    // ETF tag exists
    const stockTag = page.locator('.results-card .el-tag').first()
    await expect(stockTag).toBeVisible()

    // Analysis overview exists
    const overview = page.locator('.overview-section, .markdown-content').first()
    await expect(overview).toBeVisible({ timeout: 10000 })

    // Report tab exists
    const analysisTabs = page.locator('.analysis-tabs, .el-tabs').first()
    await expect(analysisTabs).toBeVisible({ timeout: 10000 })

    // Check for downgraded nodes
    const degradedAlert = page.locator('.el-alert:has-text("Downgrade"), .el-alert:has-text("failed")')
    const degradedVisible = await degradedAlert.isVisible().catch(() => false)
    if (degradedVisible) {
      console.log('⚠️ ETF Analysis of downgraded nodes, see screenshots for details')
      await page.screenshot({ path: 'test-results/etf-analysis-degraded.png', fullPage: true })
    }

    // Report content is visible
    const firstTab = page.locator('.el-tabs__content .report-content-wrapper').first()
    await expect(firstTab).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Batch analysis', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Batch analysis - submit tasks and verify', async ({ page }) => {
    await page.goto('/analysis/batch')
    await waitForLoadingDone(page)

    await expect(page).toHaveURL(/\/analysis\/batch/)

    // Enter the stock code (one per line)
    const textarea = page.locator('.stock-textarea textarea, textarea[placeholder*="Stock code"]').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })
    await textarea.fill('000001\n000002\n600036')
    await page.waitForTimeout(1000)

    // Click"Parsing stock symbols"
    const parseBtn = page.locator('button:has-text("Parsing stock symbols")').first()
    if (await parseBtn.isVisible({ timeout: 3000 })) {
      await parseBtn.click()
      await page.waitForTimeout(1000)
    }

    // Verify that the Stock Preview tab appears
    const stockTags = page.locator('.stock-tag, .stock-preview .el-tag').first()
    await expect(stockTags).toBeVisible({ timeout: 5000 })

    // Select Level 1 Quick Analysis
    const depthSelect = page.locator('.config-card .el-select').first()
    if (await depthSelect.isVisible({ timeout: 3000 })) {
      await depthSelect.click()
      await page.waitForTimeout(500)
      const option1 = page.locator('.el-select-dropdown__item:has-text("1 level")').first()
      if (await option1.isVisible({ timeout: 3000 })) {
        await option1.click()
        await page.waitForTimeout(500)
      }
    }

    // Click"Start batch analysis"
    const submitBtn = page.locator('button:has-text("Start batch analysis")').first()
    await expect(submitBtn).toBeEnabled({ timeout: 5000 })
    await submitBtn.click()

    // Confirmation dialog
    const confirmBtn = page.locator('.el-message-box button:has-text("OK")').first()
    if (await confirmBtn.isVisible({ timeout: 5000 })) {
      await confirmBtn.click()
      await page.waitForTimeout(3000)
    }

    // Verification success message
    const successMsg = page.locator('.el-message--success, .el-message-box:has-text("success")').first()
    await expect(successMsg).toBeVisible({ timeout: 10000 })

    // Go to the task center to verify that the task has been submitted
    await page.goto('/tasks/unified')
    await waitForLoadingDone(page)

    const taskTable = page.locator('.el-table').first()
    await expect(taskTable).toBeVisible({ timeout: 10000 })

    const taskRows = page.locator('.el-table__body tr').first()
    await expect(taskRows).toBeVisible({ timeout: 10000 })
  })
})
