/**
 * Transaction review API
 */
import { ApiClient } from './request'

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

