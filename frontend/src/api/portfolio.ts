import { ApiClient } from './request'
import type { ApiResponse } from './request'

// ============================================================================
// Module: portfolio.ts
// ============================================================================

/**
 * Position research API
 */


// ==================== type definition ====================

/** Position data source */
export type PositionSource = 'real' | 'paper' | 'all'

/** Position items */
export interface PositionItem {
  id: string
  code: string
  name?: string
  market: string
  currency: string
  quantity: number
  cost_price: number
  /** The original average buying price (unchanged when reducing positions, used for investment evaluation); if not, it is the same as cost_price */
  original_avg_cost?: number | null
  /** Original cost price (actual transaction price without restoration of rights) */
  original_cost_price?: number | null
  /** Price restoration mark:null/undefined=Before restoration (default),"none"=Original unrestored rights */
  price_adjust_type?: string | null
  current_price?: number
  market_value?: number
  unrealized_pnl?: number
  unrealized_pnl_pct?: number
  buy_date?: string
  industry?: string
  notes?: string
  source: string
  created_at: string
  updated_at: string
}

/** Historical position items (transaction summary) */
export interface HistoryPositionItem {
  id: string
  code: string
  name?: string
  market: string
  currency: string
  total_buy_qty: number       // Cumulative purchase quantity
  total_sell_qty: number      // Cumulative sales quantity
  avg_buy_price: number       // average buying price
  avg_sell_price: number      // average selling price
  first_buy_date?: string     // First purchase date
  last_trade_date?: string    // last transaction date
  realized_pnl: number        // Realized profit and loss
}

/** Add position request */
export interface PositionCreatePayload {
  code: string
  name?: string
  market?: string
  quantity: number
  cost_price: number
  buy_date?: string
  notes?: string
}

/** QMT Position coverage synchronization request */
export interface QMTPositionImportPayload {
  account_id: string
  account_type?: string
}

export interface QMTPositionSyncPreview {
  account_id: string
  account_type: string
  will_replace_position_count: number
  will_clear_change_count: number
  local_cash: number | null
  local_total_assets: number | null
  qmt_position_count: number
  qmt_importable_count: number
  qmt_cash: number | null
  qmt_market_value: number | null
  qmt_total_asset: number | null
  will_sync_cash: boolean
  cash_currency: string
  sync_note: string
}

export interface QMTPositionSyncResult {
  success_count: number
  failed_count: number
  errors: Array<{ code: string; error: string }>
  account_id: string
  account_type: string
  queried_count: number
  imported_count: number
  deleted_positions: number
  deleted_changes: number
  restored_cash: Record<string, number>
  replace_existing: boolean
  cash_synced: boolean
  synced_currency?: string | null
  synced_cash?: number | null
  qmt_market_value?: number | null
  qmt_total_asset?: number | null
  sync_note?: string
}

/** Update position request */
export interface PositionUpdatePayload {
  name?: string
  quantity?: number
  cost_price?: number
  buy_date?: string
  notes?: string
}

/** Industry distribution */
export interface IndustryDistribution {
  industry: string
  value: number
  percentage: number
  count: number
}

/** Position statistics */
export interface PortfolioStats {
  total_positions: number
  total_value: number
  total_cost: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  industry_distribution: IndustryDistribution[]
  market_distribution: Record<string, number>
}

/** Position snapshot */
export interface PositionSnapshot {
  code: string
  name?: string
  market: string
  quantity: number
  cost_price: number
  current_price?: number
  market_value?: number
  unrealized_pnl?: number
  unrealized_pnl_pct?: number
  industry?: string
  holding_days?: number
}

/** Combined Snapshot */
export interface PortfolioSnapshot {
  total_positions: number
  total_value: number
  total_cost: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  positions: PositionSnapshot[]
}

/** concentration analysis */
export interface ConcentrationAnalysis {
  top1_pct: number
  top3_pct: number
  top5_pct: number
  hhi_index: number
  industry_count: number
}

/** AI Analyze results */
export interface AIAnalysisResult {
  summary: string
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]
  detailed_report?: string
}

/** research report */
export interface PortfolioAnalysisReport {
  analysis_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  health_score?: number
  risk_level?: string
  portfolio_snapshot: PortfolioSnapshot
  industry_distribution: IndustryDistribution[]
  concentration_analysis: ConcentrationAnalysis
  ai_analysis: AIAnalysisResult
  execution_time?: number
  error_message?: string
  created_at: string
}

/** research request */
export interface AnalysisRequestPayload {
  include_paper?: boolean
  research_depth?: string
}

// ==================== Single Stock Position Research Types ====================

/** Single Stock Research Request Parameters */
export interface PositionAnalysisParams {
  research_depth?: string
  include_add_position?: boolean
  target_profit_pct?: number
  // Related to the total amount of funds (for risk analysis)
  total_capital?: number          // Total amount of investment funds
  max_position_pct?: number       // Maximum position ratio of a single stock (%), default 30
  max_loss_pct?: number           // Maximum acceptable loss ratio (%), default 10
}

/** price target */
export interface PriceTargets {
  stop_loss_price?: number
  stop_loss_pct?: number
  take_profit_price?: number
  take_profit_pct?: number
  breakeven_price?: number
}

/** Position risk indicators */
export interface PositionRiskMetrics {
  position_pct?: number           // Position proportion (%)
  position_value?: number         // Position market value
  max_loss_amount?: number        // Maximum possible loss amount
  max_loss_impact_pct?: number    // Impact of maximum loss on total funds (%)
  available_add_amount?: number   // Amount that can be added to the position
  risk_level?: 'low' | 'medium' | 'high' | 'critical'  // risk level
  risk_summary?: string           // Risk overview
}

export interface PositionUserView {
  conclusion: string
  position_context: string
  key_points: string[]
  risk_focus: string[]
  watch_items: string[]
  uncertainty_note: string
}

export interface PositionAppendixSection {
  key: string
  title: string
  content: string
}

/** Single stock position research results */
export interface PositionAnalysisResult {
  analysis_id: string
  task_id?: string
  position_id: string
  code: string
  name?: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  action: string
  action_reason: string
  confidence: number
  price_targets: PriceTargets | Record<string, never>
  risk_assessment: string
  opportunity_assessment: string
  detailed_analysis: string
  user_view?: PositionUserView
  appendix_sections?: PositionAppendixSection[]
  suggested_quantity?: number | null
  suggested_amount?: number | null
  risk_metrics?: PositionRiskMetrics  // Risk indicators (calculated based on total funds)
  execution_time?: number
  error_message?: string
  created_at: string
}

// ==================== API method ====================

export const portfolioApi = {
  /** Get position list */
  async getPositions(source: PositionSource = 'all') {
    return ApiClient.get<{ items: PositionItem[]; total: number }>(
      '/api/portfolio/positions',
      { source }
    )
  },

  /** Get historical positions (records of cleared positions) */
  async getHistoryPositions(params?: { source?: string; limit?: number; skip?: number }) {
    return ApiClient.get<{ items: HistoryPositionItem[]; total: number; limit: number; skip: number }>(
      '/api/portfolio/positions/history',
      params || {}
    )
  },

  /** Add position */
  async addPosition(data: PositionCreatePayload) {
    return ApiClient.post<PositionItem>('/api/portfolio/positions', data, { showLoading: true })
  },

  /** Update positions */
  async updatePosition(positionId: string, data: PositionUpdatePayload) {
    return ApiClient.put<PositionItem>(`/api/portfolio/positions/${positionId}`, data, { showLoading: true })
  },

  /** Delete position */
  async deletePosition(positionId: string) {
    return ApiClient.delete(`/api/portfolio/positions/${positionId}`, { showLoading: true })
  },

  /** Import positions in batches */
  async importPositions(positions: PositionCreatePayload[]) {
    return ApiClient.post<{ success_count: number; failed_count: number; errors: any[] }>(
      '/api/portfolio/positions/import',
      { positions },
      { showLoading: true }
    )
  },

  /** Preview of simultaneous positions covered from QMT */
  async previewQmtPositionImport(data: QMTPositionImportPayload) {
    return ApiClient.post<QMTPositionSyncPreview>(
      '/api/portfolio/positions/import/qmt/preview',
      data,
      { showLoading: true }
    )
  },

  /** Read-only query and import positions from QMT */
  async importPositionsFromQmt(data: QMTPositionImportPayload) {
    return ApiClient.post<QMTPositionSyncResult>(
      '/api/portfolio/positions/import/qmt',
      data,
      { showLoading: true }
    )
  },

  /** Get position statistics */
  async getStatistics() {
    return ApiClient.get<PortfolioStats>('/api/portfolio/statistics')
  },

  /** Initiate position research */
  async analyzePortfolio(params?: AnalysisRequestPayload) {
    return ApiClient.post<PortfolioAnalysisReport>('/api/portfolio/analysis', params || {}, { showLoading: true })
  },

  /** Get research history */
  async getAnalysisHistory(page = 1, pageSize = 10) {
    return ApiClient.get<{ items: PortfolioAnalysisReport[]; total: number; page: number; page_size: number }>(
      '/api/portfolio/analysis/history',
      { page, page_size: pageSize }
    )
  },

  /** Get study details */
  async getAnalysisDetail(analysisId: string) {
    return ApiClient.get<PortfolioAnalysisReport>(`/api/portfolio/analysis/${analysisId}`)
  },

  // ==================== Single stock position research ====================

  /** Get individual position details */
  async getPositionDetail(positionId: string) {
    return ApiClient.get<PositionItem>(`/api/portfolio/positions/${positionId}`)
  },

  /** Initiate single stock position research (single record) */
  async analyzePosition(positionId: string, params?: PositionAnalysisParams) {
    return ApiClient.post<PositionAnalysisResult>(
      `/api/portfolio/positions/${positionId}/analysis`,
      params || {},
      { showLoading: true }
    )
  },

  /** Analyze positions by ticker (asynchronous mode, returns task ID immediately) */
  /** Check Single Stock Research Report Cache Status */
  async checkStockAnalysisCache(code: string, market: string) {
    return ApiClient.post<{
      has_cache: boolean
      cache_age_hours: number | null
      cache_age_minutes: number | null
      source: string | null
      task_id: string | null
      created_at: string | null
    }>(
      '/api/portfolio/positions/check-cache',
      { code, market }
    )
  },

  async analyzePositionByCode(code: string, market: string, params?: PositionAnalysisParams) {
    return ApiClient.post<{
      analysis_id: string
      code: string
      market: string
      status: string
      message: string
      created_at: string
    }>(
      '/api/portfolio/positions/analyze-by-code',
      { code, market, ...params },
      { showLoading: false }  // Loading is not displayed because it is an asynchronous task.
    )
  },

  /** Get research task status and results */
  async getPositionAnalysisStatus(analysisId: string) {
    return ApiClient.get<PositionAnalysisResult & { summary?: any }>(
      `/api/portfolio/positions/analysis/${analysisId}`
    )
  },

  /** Get the latest research reports by stock symbol */
  async getLatestPositionAnalysis(code: string, market: string, source: PositionSource = 'real') {
    return ApiClient.get<PositionAnalysisResult & { summary?: any } | null>(
      `/api/portfolio/positions/analysis-by-code/${code}`,
      { market, source }
    )
  },

  /** Get single stock research history */
  async getPositionAnalysisHistory(positionId: string, page = 1, pageSize = 10, source: PositionSource = 'real') {
    return ApiClient.get<{ items: PositionAnalysisResult[]; total: number; page: number; page_size: number }>(
      `/api/portfolio/positions/${positionId}/analysis/history`,
      { page, page_size: pageSize, source }
    )
  },

  /** Delete position research report */
  async deletePositionAnalysis(analysisId: string) {
    return ApiClient.delete<{ message: string }>(`/api/portfolio/positions/analysis/${analysisId}`)
  },

  // ==================== Capital account API ====================

  /** Get a funding account */
  async getAccount() {
    return ApiClient.get<RealAccount>('/api/portfolio/account')
  },

  /** Get account summary (including position market value and income) */
  async getAccountSummary() {
    return ApiClient.get<AccountSummary>('/api/portfolio/account/summary')
  },

  /** Initialize capital account */
  async initializeAccount(initial_capital: number, currency = 'CNY') {
    return ApiClient.post<RealAccount>('/api/portfolio/account/initialize', {
      initial_capital,
      currency
    })
  },

  /** Deposit */
  async deposit(amount: number, currency = 'CNY', description?: string) {
    return ApiClient.post<RealAccount>('/api/portfolio/account/deposit', {
      transaction_type: 'deposit',
      amount,
      currency,
      description
    })
  },

  /** Withdraw funds */
  async withdraw(amount: number, currency = 'CNY', description?: string) {
    return ApiClient.post<RealAccount>('/api/portfolio/account/withdraw', {
      transaction_type: 'withdraw',
      amount,
      currency,
      description
    })
  },

  /** Update account settings */
  async updateAccountSettings(settings: AccountSettingsParams) {
    return ApiClient.put<RealAccount>('/api/portfolio/account/settings', settings)
  },

  /** Get fund transaction records */
  async getTransactions(currency?: string, limit = 50) {
    return ApiClient.get<{ items: CapitalTransaction[]; total: number }>(
      '/api/portfolio/account/transactions',
      { currency, limit }
    )
  },

  // ==================== Position change record API ====================

  /** Get position change records */
  async getPositionChanges(params?: PositionChangeQueryParams) {
    return ApiClient.get<{ items: PositionChange[]; total: number; limit: number; skip: number }>(
      '/api/portfolio/position-changes',
      params || {}
    )
  },

  /** Modify single transaction records (quantity, unit price, used to correct entry errors) */
  async updatePositionChange(changeId: string, data: { quantity: number; price: number; trade_time?: string }) {
    return ApiClient.put<{ message: string; quantity: number; cost_price: number }>(
      `/api/portfolio/position-changes/${changeId}`,
      data
    )
  },

  /** Delete a single change record */
  async deletePositionChange(changeId: string) {
    return ApiClient.delete<{ message: string; quantity: number; cost_price: number }>(
      `/api/portfolio/position-changes/${changeId}`
    )
  },

  /** Reset the entire position (delete all change records and positions of the stock) */
  async resetPosition(code: string, market?: string) {
    return ApiClient.post<{ message: string; deleted_changes: number; position_deleted: boolean }>(
      '/api/portfolio/positions/reset',
      undefined,
      { params: { code, market: market || 'CN' } }
    )
  },

  /** Clear all positions (delete all positions and change records of this user) */
  async resetAllPositions() {
    return ApiClient.post<{ message: string; deleted_changes: number; deleted_positions: number }>(
      '/api/portfolio/positions/reset-all'
    )
  },

  /** Execute position operations (increase positions, reduce positions, dividends, split shares, combine shares, adjust costs) */
  async operatePosition(data: PositionOperationPayload) {
    return ApiClient.post<PositionOperationResult>(
      '/api/portfolio/positions/operate',
      data,
      { showLoading: true }
    )
  }
}

// ==================== Position operation type definition ====================

/** Position operation type */
export type PositionOperationType = 'add' | 'reduce' | 'dividend' | 'split' | 'merge' | 'adjust'

/** Position operation request */
export interface PositionOperationPayload {
  operation_type: PositionOperationType
  code: string
  market?: string
  quantity?: number
  price?: number
  dividend_amount?: number
  ratio?: string
  new_cost_price?: number
  operation_date?: string
  notes?: string
}

/** Position operation results */
export interface PositionOperationResult {
  message: string
  new_quantity?: number
  new_cost_price?: number
  sell_amount?: number
  profit?: number
  profit_pct?: number
  dividend_amount?: number
}

// ==================== Capital account type definition ====================

/** Capital account */
export interface RealAccount {
  user_id: string
  cash: Record<string, number>
  initial_capital: Record<string, number>
  total_deposit: Record<string, number>
  total_withdraw: Record<string, number>
  settings: {
    default_market: string
    max_position_pct: number
    max_loss_pct: number
  }
  created_at: string
  updated_at: string
}

/** Account summary */
export interface AccountSummary {
  cash: Record<string, number>
  initial_capital: Record<string, number>
  total_deposit: Record<string, number>
  total_withdraw: Record<string, number>
  net_capital: Record<string, number>
  positions_value: Record<string, number>
  total_assets: Record<string, number>
  profit: Record<string, number>
  profit_pct: Record<string, number>
  settings: Record<string, any>
}

/** Fund transaction records */
export interface CapitalTransaction {
  id: string
  user_id: string
  transaction_type: 'initial' | 'deposit' | 'withdraw' | 'dividend' | 'adjustment'
  amount: number
  currency: string
  balance_before: number
  balance_after: number
  description?: string
  created_at: string
}

/** Account setting parameters */
export interface AccountSettingsParams {
  max_position_pct?: number
  max_loss_pct?: number
  default_market?: string
}

// ==================== Position change record type definition ====================

/** Position change type */
export type PositionChangeType = 'buy' | 'add' | 'reduce' | 'sell' | 'adjust'

/** Position change record */
export interface PositionChange {
  id: string
  user_id: string
  position_id?: string
  code: string
  name: string
  market: string
  currency: string
  change_type: PositionChangeType
  quantity_before: number
  cost_price_before: number
  cost_value_before: number
  quantity_after: number
  cost_price_after: number
  cost_value_after: number
  quantity_change: number
  cash_change: number
  trade_price?: number
  realized_profit?: number
  description?: string
  trade_time?: string  // Transaction time (the time when the actual transaction occurs, manually entered by the user)
  created_at: string   // record creation time
}

/** Position change query parameters */
export interface PositionChangeQueryParams {
  code?: string
  market?: string
  change_type?: PositionChangeType
  limit?: number
  skip?: number
}

// ============================================================================
// Module: review.ts
// ============================================================================

/**
 * Transaction review API
 */


// ==================== type definition ====================

/** Review type */
export type ReviewType = 'single_trade' | 'complete_trade' | 'periodic'

/** Review status */
export type ReviewStatus = 'pending' | 'processing' | 'completed' | 'failed'

/** Trading direction */
export type TradeSide = 'buy' | 'sell'

/** transaction history */
export interface TradeRecord {
  trade_id: string
  code: string
  market: string
  side: TradeSide
  quantity: number
  price: number
  amount: number
  pnl: number
  commission: number
  timestamp: string
  change_type?: string
  quantity_after?: number
  created_at?: string
}

/** Transaction information summary */
export interface TradeInfo {
  code: string
  name?: string
  market: string
  trades: TradeRecord[]
  total_buy_quantity: number
  total_sell_quantity: number
  avg_buy_price: number
  avg_sell_price: number
  total_buy_amount: number
  total_sell_amount: number
  total_commission: number
  realized_pnl: number
  realized_pnl_pct: number
  unrealized_pnl?: number  // 🆕 Floating profit and loss (when holding a position)
  unrealized_pnl_pct?: number  // 🆕 Floating profit and loss percentage (when the position is held)
  current_price?: number  // 🆕 Current price (when the position is open)
  is_holding?: boolean  // 🆕 Are you still holding a position?
  remaining_quantity?: number  // 🆕 Remaining position quantity
  first_buy_date?: string
  last_sell_date?: string
  holding_days: number
}

/** Market data snapshot */
export interface MarketSnapshot {
  period_high?: number
  period_high_date?: string
  period_low?: number
  period_low_date?: string
  buy_date_open?: number
  buy_date_high?: number
  buy_date_low?: number
  buy_date_close?: number
  sell_date_open?: number
  sell_date_high?: number
  sell_date_low?: number
  sell_date_close?: number
  optimal_buy_price?: number
  optimal_buy_date?: string
  optimal_sell_price?: number
  optimal_sell_date?: string
  kline_data?: Array<{
    date: string
    open: number
    high: number
    low: number
    close: number
    volume: number
  }>
}

/** AI Review analysis results */
export interface AITradeReview {
  overall_score: number
  timing_score?: number
  position_score?: number
  discipline_score?: number
  emotion_score?: number
  attribution_score?: number
  summary: string
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]  // Compatible field names, actually displayed as review improvement items
  timing_analysis?: string
  position_analysis?: string
  emotion_analysis?: string
  attribution_analysis?: string
  actual_pnl?: number
  optimal_pnl?: number
  missed_profit?: number
  avoided_loss?: number
  plan_adherence?: string  // Plan execution status
  plan_deviation?: string   // Deviation instructions
}

/** Review report */
export interface TradeReviewReport {
  review_id: string
  task_id?: string
  review_type: ReviewType
  status: ReviewStatus
  source?: 'paper' | 'position' | 'real'
  error_message?: string
  trade_info: TradeInfo
  market_snapshot: MarketSnapshot
  ai_review: AITradeReview
  is_case_study: boolean
  tags: string[]
  execution_time?: number
  created_at: string
  trading_system_id?: string  // Associated trading plans ID
  trading_system_name?: string  // Associated trading plan name
}

/** Review list items */
export interface ReviewListItem {
  review_id: string
  review_type: ReviewType
  code?: string
  name?: string
  realized_pnl: number
  overall_score: number
  status: ReviewStatus
  is_case_study: boolean
  created_at: string
}

/** Transaction statistics */
export interface TradingStatistics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_profit: number
  avg_loss: number
  profit_loss_ratio: number
  max_single_profit: number
  max_single_loss: number
  total_commission: number
}

/** Stocks that can be reviewed */
export interface ReviewableStock {
  code: string
  name?: string
  market?: string
  status?: 'completed' | 'holding'  // completed=Transaction completed, holding=In position
  buy_count: number
  sell_count: number
  total_pnl: number
  total_buy_amount?: number
  total_sell_amount?: number
  last_trade_time?: string
}

// ==================== Request type ====================

/** Create review request */
export interface CreateTradeReviewRequest {
  trade_ids: string[]
  review_type?: ReviewType
  code?: string
  source?: 'real' | 'paper'  // Data source: user positions or simulated positions
  trading_system_id?: string  // Associated trading plans ID
  workflow_id?: string  // Associated workflows ID
  use_workflow?: boolean  // Whether to use workflow engine (v2.0)
}

/** Save case request */
export interface SaveAsCaseRequest {
  review_id: string
  tags?: string[]
  source?: 'paper' | 'position' | 'real'  // data source: paper(simulated trading) or position(Position operation)
}

/** Review history filter parameters */
export interface ReviewHistoryFilter {
  page?: number
  pageSize?: number
  code?: string
  startDate?: string
  endDate?: string
  reviewType?: ReviewType
  source?: 'paper' | 'position'  // data source: paper(simulated trading) or position(Position operation)
}

/** Reviewable transaction filtering parameters */
export interface ReviewableTradesFilter {
  code?: string
  startDate?: string
  endDate?: string
  page?: number
  pageSize?: number
}

/** Periodic review cycle type */
export type PeriodType = 'week' | 'month' | 'quarter' | 'year'

/** Create a staged review request */
export interface CreatePeriodicReviewRequest {
  period_type: PeriodType
  start_date: string
  end_date: string
  source?: 'paper' | 'position'  // data source: paper(simulated trading) or position(Position operation)
}

/** AI Phased review results */
export interface AIPeriodicReview {
  overall_score: number
  summary: string
  trading_style: string
  common_mistakes: string[]
  improvement_areas: string[]  // Review and improvement directions
  action_plan: string[]  // Compatible field name, actually displayed as subsequent observation items
  best_trade?: string
  worst_trade?: string
}

/** transaction summary item */
export interface TradeSummaryItem {
  code: string
  name?: string
  side: string
  quantity: number
  price: number
  pnl: number
  pnl_pct: number
  timestamp: string
}

/** Periodic review report */
export interface PeriodicReviewReport {
  review_id: string
  period_type: PeriodType
  period_start: string
  period_end: string
  statistics: TradingStatistics
  trades_summary: TradeSummaryItem[]
  ai_review: AIPeriodicReview
  status: ReviewStatus
  execution_time?: number
  created_at: string
}

/** Periodic review list items */
export interface PeriodicReviewListItem {
  review_id: string
  period_type: PeriodType
  period_start: string
  period_end: string
  source?: 'paper' | 'position'
  total_trades: number
  total_pnl: number
  win_rate: number
  overall_score: number
  status: ReviewStatus
  created_at: string
}

// ==================== API method ====================

export const reviewApi = {
  /** Create a transaction review */
  async createTradeReview(data: CreateTradeReviewRequest) {
    return ApiClient.post<TradeReviewReport>('/api/review/trade', data, {
      showLoading: true,
      timeout: 30000,  // 30 seconds timeout (the backend returns the task ID immediately, without waiting for the task to complete)
      retryCount: 0     // Disable retries to avoid repeated analysis
    })
  },

  /** Get the review history list and support filtering */
  async getReviewHistory(filter: ReviewHistoryFilter = {}) {
    const { page = 1, pageSize = 10, code, startDate, endDate, reviewType, source } = filter
    return ApiClient.get<{ items: ReviewListItem[]; total: number; page: number; page_size: number }>(
      '/api/review/trade/history',
      {
        page,
        page_size: pageSize,
        code,
        start_date: startDate,
        end_date: endDate,
        review_type: reviewType,
        source
      }
    )
  },

  /** Get review details */
  async getReviewDetail(reviewId: string) {
    return ApiClient.get<TradeReviewReport>(`/api/review/trade/${reviewId}`)
  },

  /** Save as case */
  async saveAsCase(data: SaveAsCaseRequest) {
    return ApiClient.post<{ message: string }>('/api/review/case', data, { showLoading: true })
  },

  /** Get case library */
  async getCases(params: { page?: number; pageSize?: number; source?: 'paper' | 'position' } = {}) {
    const { page = 1, pageSize = 10, source } = params
    const queryParams: Record<string, any> = { page, page_size: pageSize }
    if (source) {
      queryParams.source = source
    }
    return ApiClient.get<{ items: ReviewListItem[]; total: number; page: number; page_size: number }>(
      '/api/review/cases',
      queryParams
    )
  },

  /** Delete from case library */
  async deleteCase(reviewId: string) {
    return ApiClient.delete<{ message: string }>(`/api/review/case/${reviewId}`, { showLoading: true })
  },

  /** Delete review record */
  async deleteReview(reviewId: string) {
    return ApiClient.delete<{ message: string }>(`/api/review/trade/${reviewId}`, { showLoading: true })
  },

  /** Get transaction statistics */
  async getTradingStatistics(startDate?: string, endDate?: string) {
    return ApiClient.get<TradingStatistics>('/api/review/statistics', {
      start_date: startDate,
      end_date: endDate
    })
  },

  /** Obtain a list of transactions that can be reviewed and support filtering */
  async getReviewableTrades(filter: ReviewableTradesFilter = {}) {
    const { code, startDate, endDate, page = 1, pageSize = 20 } = filter
    return ApiClient.get<{
      items: TradeRecord[]
      total: number
      page: number
      page_size: number
      completed_stocks: ReviewableStock[]
      all_stocks: ReviewableStock[]  // All traded stocks (including buy-only ones)
    }>('/api/review/reviewable-trades', {
      code,
      start_date: startDate,
      end_date: endDate,
      page,
      page_size: pageSize
    })
  },

  /** Get all transactions for a stock */
  async getTradesByCode(code: string, source: 'real' | 'paper' = 'real') {
    return ApiClient.get<{
      code: string
      trades: TradeRecord[]
      summary: {
        total_trades: number
        total_buy_quantity: number
        total_sell_quantity: number
        total_pnl: number
        is_closed: boolean
      }
    }>(`/api/review/trades-by-code/${code}`, { source })
  },

  // ==================== Periodic review ====================

  /** Create a staged review */
  async createPeriodicReview(data: CreatePeriodicReviewRequest) {
    return ApiClient.post<PeriodicReviewReport>('/api/review/periodic', data, {
      showLoading: true,
      timeout: 600000,  // 600 Second timeout (10 minutes)
      retryCount: 0     // Disable retries to avoid repeated analysis
    })
  },

  /** Get periodic review history */
  async getPeriodicReviewHistory(page = 1, pageSize = 10, source?: 'paper' | 'position') {
    const params: Record<string, any> = { page, page_size: pageSize }
    if (source) {
      params.source = source
    }
    return ApiClient.get<{ items: PeriodicReviewListItem[]; total: number; page: number; page_size: number }>(
      '/api/review/periodic/history',
      params
    )
  },

  /** Get details of periodic review */
  async getPeriodicReviewDetail(reviewId: string) {
    return ApiClient.get<PeriodicReviewReport>(`/api/review/periodic/${reviewId}`)
  },

  /** Get review summary by stock code (for stock details page) */
  async getTradeReviewSummary(code: string) {
    return ApiClient.get<ReviewSummary>(`/api/review/summary`, { code })
  }
}

/** Review summary type (used on the stock details page) */
interface ReviewSummary {
  has: boolean
  task_id?: string
  completed_at?: string
  summary?: string
  recommendation?: string
  risk_level?: string
  confidence_score?: number | null
  trade_count?: number | null
}

// ============================================================================
// Module: favorites.ts
// ============================================================================

export interface FavoriteItem {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name: string
  market: string
  board?: string
  exchange?: string
  added_at?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
  current_price?: number | null
  change_percent?: number | null
  volume?: number | null
}

export interface AddFavoriteReq {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name: string
  market?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
}

export type FavoritesSyncTaskState = 'pending' | 'running' | 'success' | 'success_with_errors' | 'failed'

export interface FavoritesRealtimeSyncTaskSubmission {
  task_id: string
  task_type: 'favorites_realtime'
  status: FavoritesSyncTaskState
  message?: string | null
  created_at: string
}

export interface FavoritesRealtimeSyncTaskStatus extends FavoritesRealtimeSyncTaskSubmission {
  started_at?: string | null
  finished_at?: string | null
  result?: {
    total: number
    success_count: number
    failed_count: number
    symbols: string[]
    data_source: string
    message: string
  } | null
  error?: string | null
}

export const favoritesApi = {
  /**
   * Get list of favorites
   */
  list: () => ApiClient.get<FavoriteItem[]>('/api/favorites'),

  /**
   * Add to favorites
   * @param payload Collection information (need to include symbol or stock_code)
   */
  add: (payload: AddFavoriteReq) => ApiClient.post<{ message: string; symbol?: string; stock_code?: string }>('/api/favorites', payload),

  /**
   * Update collection
   * @param symbol Stock code (6 digits)
   * @param payload Update content
   */
  update: (symbol: string, payload: Partial<Pick<FavoriteItem, 'tags' | 'notes' | 'alert_price_high' | 'alert_price_low'>>) =>
    ApiClient.put<{ message: string; symbol?: string; stock_code?: string }>(`/api/favorites/${symbol}`, payload),

  /**
   * Delete favorite
   * @param symbol Stock code (6 digits)
   */
  remove: (symbol: string) => ApiClient.delete<{ message: string; symbol?: string; stock_code?: string }>(`/api/favorites/${symbol}`),

  /**
   * Check if it has been collected
   * @param symbol Stock code (6 digits)
   */
  check: (symbol: string) => ApiClient.get<{ symbol?: string; stock_code?: string; is_favorite: boolean }>(`/api/favorites/check/${symbol}`),

  /**
   * Get all tags
   */
  tags: () => ApiClient.get<string[]>('/api/favorites/tags'),

  /**
   * Synchronize real-time quotes of stock watchlists
   * @param data_source Data source (tushare/akshare)
   */
  syncRealtime: (data_source: string = 'tushare') =>
    ApiClient.post<FavoritesRealtimeSyncTaskSubmission>('/api/favorites/sync-realtime', { data_source }, {
      timeout: 15000
    }),

  getRealtimeSyncTaskStatus: (taskId: string) =>
    ApiClient.get<FavoritesRealtimeSyncTaskStatus>(`/api/favorites/sync-realtime/tasks/${taskId}`)
}

// ============================================================================
// Module: tags.ts
// ============================================================================

export interface TagItem {
  id: string
  name: string
  color: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface CreateTagDto {
  name: string
  color?: string
  sort_order?: number
}

export interface UpdateTagDto {
  name?: string
  color?: string
  sort_order?: number
}

export const tagsApi = {
  async list(): Promise<ApiResponse<TagItem[]>> {
    return await ApiClient.get<TagItem[]>('/api/tags')
  },
  async create(payload: CreateTagDto): Promise<ApiResponse<TagItem>> {
    return await ApiClient.post<TagItem>('/api/tags', payload)
  },
  async update(id: string, payload: UpdateTagDto): Promise<ApiResponse<{ id: string }>> {
    return await ApiClient.put<{ id: string }>(`/api/tags/${id}`, payload)
  },
  async remove(id: string): Promise<ApiResponse<{ id: string }>> {
    return await ApiClient.delete<{ id: string }>(`/api/tags/${id}`)
  }
}

// ============================================================================
// Module: tradingSystem.ts
// ============================================================================

/**
 * Trading plan API (community version empty shell)
 *
 * This file is generated by the publish pipeline (scripts/publish_community.py):
 * The trading plan has Pro capability (trading_plan_check gate control), and the community version interface returns empty data.
 * Reference component (position review/operation history pop-up window"Related party transaction plan"dropdown) naturally degrades to an empty list.
 */

/** Minimum type of trading plan (only declare the fields used by the community version reference component; style is required to be consistent with the Pro original type) */
export interface TradingSystem {
  id?: string
  name: string
  style: string
  is_active?: boolean
}

export interface TradingSystemsResponse {
  data: { systems: TradingSystem[] }
}

/** Get the list of trading plans (community version: always empty) */
export const getTradingSystems = async (): Promise<TradingSystemsResponse> => ({
  data: { systems: [] }
})
