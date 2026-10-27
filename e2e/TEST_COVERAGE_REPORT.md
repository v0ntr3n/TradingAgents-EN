# E2E Test Coverage Report

## Product Positioning

**Deep analysis platform based on daily bars, historical data, and fundamentals**

---

## Test File Structure

```
e2e/
├── auth.spec.ts              # Authentication flow (5 tests)
├── navigation.spec.ts        # Page navigation (9 tests)
├── analysis.spec.ts          # Analysis flow (4 tests)
├── analysis_core.spec.ts     # Core analysis flow (11 tests)
├── screening.spec.ts         # Smart stock screening (10 tests)
├── portfolio.spec.ts         # Portfolio management (14 tests)
├── reports.spec.ts           # Investment reports (6 tests)
├── trading_plan.spec.ts      # Trading plans (6 tests)
├── data_quality.spec.ts      # Data quality monitoring (12 tests)
└── utils.ts                  # Utility functions
```

**Total: 77 test cases across 9 test files**

---

## Test Scenario Categories

### P0 - Core Features (Must Pass)

#### 1. Authentication Flow (auth.spec.ts)
- ✅ Login page loads
- ✅ Login with valid credentials
- ✅ Login fails with invalid password
- ✅ Unauthenticated access to protected routes
- ✅ Public page access

#### 2. Core Analysis Flow (analysis_core.spec.ts)
- ✅ Trigger single-stock deep analysis
- ✅ Analysis page loads
- ✅ View historical analysis results
- ✅ Analysis task management (list/filter/details/retry/cancel)
- ✅ Analysis feedback rating
- ✅ Scheduled analysis configuration

#### 3. Smart Stock Screening (screening.spec.ts)
- ✅ Multi-condition combined filtering (PE/PB/ROE)
- ✅ Industry sector filtering
- ✅ Sort screening results
- ✅ Save screening criteria
- ✅ Moving average filtering
- ✅ Volume filtering
- ✅ Watchlist management (add/list/group/trigger analysis)

#### 4. Portfolio Management (portfolio.spec.ts)
- ✅ Portfolio list loads
- ✅ Portfolio return statistics
- ✅ Portfolio allocation charts
- ✅ Trigger analysis from portfolio
- ✅ Paper trading (buy/sell/trade history/position details/asset overview)
- ✅ Trade review (overview/trade details/PnL analysis/win rate statistics)

---

### P1 - Important Features

#### 5. Investment Reports (reports.spec.ts)
- ✅ Report list loads
- ✅ View report details
- ✅ Search reports
- ✅ Filter reports by date
- ✅ Export reports
- ✅ Token consumption statistics

#### 6. Trading Plans (trading_plan.spec.ts)
- ✅ Trading plan list loads
- ✅ Create new trading plan
- ✅ Edit trading plan
- ✅ Activate/deactivate trading plan
- ✅ Configure stop-loss and take-profit rules
- ✅ View trading plan details

---

### P2 - Infrastructure

#### 7. Data Quality Monitoring (data_quality.spec.ts)
- ✅ Data source quality statistics page loads
- ✅ Data source success rate display
- ✅ Data source latency statistics
- ✅ QMT diagnostics page loads
- ✅ Run QMT connection diagnostics
- ✅ Configuration management page loads
- ✅ Settings home page loads
- ✅ Watchlist group configuration
- ✅ Agent list page loads
- ✅ View Agent version history
- ✅ Agent version rollback

#### 8. Page Navigation (navigation.spec.ts)
- ✅ Dashboard page loads
- ✅ Navigate to Single-Stock Analysis page
- ✅ Navigate to Screening page
- ✅ Navigate to Watchlist/Favorites page
- ✅ Navigate to Reports page
- ✅ Navigate to Portfolio page
- ✅ Navigate to Paper Trading page
- ✅ Navigate to Trade Review page
- ✅ Navigate to Task Center page
- ✅ Navigate to Settings page

---

## Test Coverage Matrix

| Module | Test File | Test Count | Priority |
|---------|---------|---------|-------|
| Authentication Flow | auth.spec.ts | 5 | P0 |
| Page Navigation | navigation.spec.ts | 9 | P2 |
| Analysis Flow | analysis.spec.ts | 4 | P0 |
| Core Analysis Flow | analysis_core.spec.ts | 11 | P0 |
| Smart Stock Screening | screening.spec.ts | 10 | P0 |
| Portfolio Management | portfolio.spec.ts | 14 | P0 |
| Investment Reports | reports.spec.ts | 6 | P1 |
| Trading Plans | trading_plan.spec.ts | 6 | P1 |
| Data Quality Monitoring | data_quality.spec.ts | 12 | P2 |
| **Total** | **9 files** | **77 tests** | - |

---

## Running Tests

```bash
# List all tests
npx playwright test --list

# Run all tests
npx playwright test

# Run a specific test file
npx playwright test analysis_core.spec.ts

# Run tests matching a title pattern
npx playwright test -g "Single-stock deep analysis"

# Run in UI mode
npx playwright test --ui

# Generate HTML report
npx playwright test --reporter=html

# View report
npx playwright show-report
```

---

## Test Design Principles

### 1. Focus on Core Analysis Capabilities
- Single-stock deep analysis workflow
- Multi-condition stock screening
- Integration between portfolio management and analysis
- Analysis report generation and viewing

### 2. Ensure Data Quality
- Data source quality monitoring
- QMT connection diagnostics
- Data source configuration management

### 3. Complete User Journey
- Authentication → Screening → Analysis → Portfolio → Reports → Review
- Covers the daily workflow of investors and researchers

### 4. Exclude Real-Time Tick Quotes
- Does not include minute-level real-time tick data tests
- Does not include call auction data tests
- Focuses on daily bar and historical data analysis

---

## Test Helper Utilities

### Provided by `utils.ts`

- `login()` - Login flow
- `ensureLoggedIn()` - Ensure user is logged in
- `waitForLoadingDone()` - Wait for loading state to finish
- `waitForTableLoaded()` - Wait for table to load
- `getElMessage()` - Retrieve Element Plus message notification
- `selectStock()` - Select a stock
- `waitForModalClose()` - Wait for modal dialog to close
- `clickConfirm()` - Click confirm button
- `clickCancel()` - Click cancel button
- `waitForSidebarMenu()` - Wait for sidebar menu
- `navigateBySidebar()` - Navigate via sidebar
- `waitForTableData()` - Wait for table data
- `verifyPageTitle()` - Verify page title
- `randomWait()` - Random wait delay

---

## Continuous Integration

Recommended CI/CD pipeline stages:

1. **Every Commit**: Run P0 core feature tests
2. **Daily Build**: Run all tests
3. **Pre-Release**: Run the full test suite and generate reports

```yaml
# GitHub Actions Example
- name: Run E2E Tests
  run: |
    npm run build
    npm run test:e2e
    
- name: Upload Test Results
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: playwright-report/
```

---

## Next Steps for Optimization

1. **Add Data Validation Tests**
   - Verify data completeness of analysis results
   - Verify accuracy of report contents

2. **Performance Testing**
   - Large-batch stock screening performance
   - Complex analysis task performance

3. **Compatibility Testing**
   - Cross-browser compatibility
   - Responsive adaptation across screen sizes

4. **Regression Testing**
   - Automated regression for critical business workflows
   - Data consistency verification

---

**Report Generated**: 2026-06-22  
**Test Framework**: Playwright  
**Total Test Cases**: 77
