/**
 * Position research API
 */
import { ApiClient } from './request'

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

