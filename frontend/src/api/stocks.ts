import { ApiClient } from './request'
import type { FactorDiagnosticPayload, FactorWarningPayload } from './screening'

export interface QuoteResponse {
  symbol: string  // Main field: 6-digit stock code
  code?: string   // Compatible fields (deprecated)
  full_symbol?: string  // Complete code (such as 000001.SZ)
  name?: string
  market?: string
  price?: number
  change_percent?: number
  amount?: number
  prev_close?: number
  turnover_rate?: number
  amplitude?: number  // Amplitude (substitution ratio)
  trade_date?: string
  updated_at?: string
}

export interface FundamentalsResponse {
  symbol: string  // Main field: 6-digit stock code
  code?: string   // Compatible fields (deprecated)
  full_symbol?: string  // Complete code (such as 000001.SZ)
  name?: string
  industry?: string
  market?: string
  sector?: string  // plate
  security_type?: string
  fund_type?: string
  track_index?: string
  fund_scale?: string | number
  fund_share?: string | number
  fund_share_date?: string
  management?: string
  custodian?: string
  management_fee?: string | number
  custodian_fee?: string | number
  unit_nav?: number
  accum_nav?: number
  nav_change_value?: number
  nav_growth_rate?: string | number
  market_price?: number
  premium_discount_rate?: string | number
  latest_nav_date?: string
  purchase_status?: string
  redemption_status?: string
  pe?: number
  pb?: number
  ps?: number      // 🔥 New: price-to-sales ratio
  pe_ttm?: number
  pb_mrq?: number
  ps_ttm?: number  // 🔥 New: Price to Sales Ratio (TTM)
  roe?: number
  roa?: number
  debt_ratio?: number  // 🔥 New: Debt ratio
  debt_to_assets?: number
  dividend_yield?: number
  dividend_yield_ttm?: number
  current_ratio?: number
  quick_ratio?: number
  cash_ratio?: number
  assets_to_eqt?: number
  gross_margin?: number
  netprofit_margin?: number
  revenue?: number
  revenue_ttm?: number
  net_income?: number
  net_profit?: number
  net_profit_ttm?: number
  oper_profit?: number
  total_profit?: number
  total_assets?: number
  total_liab?: number
  total_equity?: number
  n_cashflow_act?: number
  report_period?: string
  report_type?: string
  ann_date?: string
  financial_data_source?: string
  total_mv?: number
  circ_mv?: number
  turnover_rate?: number
  volume_ratio?: number
  pe_is_realtime?: boolean  // PE Is it real-time data?
  pe_source?: string        // PE Data source
  pe_updated_at?: string    // PE Update time
  factor_diagnostics?: Record<string, FactorDiagnosticPayload>
  factor_warnings?: Record<string, FactorWarningPayload>
  updated_at?: string
}

export interface KlineBar {
  time: string
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
  amount?: number
}

export interface KlineResponse {
  symbol: string  // Main field: 6-digit stock code
  code?: string   // Compatible fields (deprecated)
  period: 'day'|'week'|'month'|'5m'|'15m'|'30m'|'60m'
  limit: number
  adj: 'none'|'qfq'|'hfq'
  source?: string
  items: KlineBar[]
}

export interface NewsItem {
  title: string
  source: string
  time: string
  url: string
  type: 'news' | 'announcement'
}

export interface NewsResponse {
  symbol: string  // Main field: 6-digit stock code
  code?: string   // Compatible fields (deprecated)
  days: number
  limit: number
  include_announcements: boolean
  source?: string
  items: NewsItem[]
}

export interface DataValidationResponse {
  is_valid: boolean
  message: string
  missing_data: string[]
  details: Record<string, any>
}

export interface StockFinancialSummary {
  report_period?: string
  report_type?: string
  ann_date?: string
  data_source?: string
  revenue?: number
  revenue_ttm?: number
  oper_rev?: number
  net_income?: number
  net_profit?: number
  net_profit_ttm?: number
  oper_profit?: number
  total_profit?: number
  gross_margin?: number
  netprofit_margin?: number
  roe?: number
  roa?: number
  roe_waa?: number
  roe_dt?: number
  debt_to_assets?: number
  assets_to_eqt?: number
  current_ratio?: number
  quick_ratio?: number
  cash_ratio?: number
  total_assets?: number
  total_liab?: number
  total_equity?: number
  total_cur_assets?: number
  total_cur_liab?: number
  money_cap?: number
  accounts_receiv?: number
  inventories?: number
  fix_assets?: number
  n_cashflow_act?: number
  n_cashflow_inv_act?: number
  n_cashflow_fin_act?: number
  c_cash_equ_end_period?: number
  c_cash_equ_beg_period?: number
  updated_at?: string
}

export interface StockFinancialsResponse {
  code: string
  name?: string
  data_source?: string
  report_period?: string
  report_type?: string
  ann_date?: string
  summary: StockFinancialSummary
  factor_snapshot?: Record<string, number | string | null>
  factor_diagnostics?: Record<string, FactorDiagnosticPayload>
  factor_warnings?: Record<string, FactorWarningPayload>
  raw_data?: Record<string, any[]>
  available_fields: string[]
}

export const stocksApi = {
  /**
   * Get stock quotes
   * @param symbol 6 stock code
   */
  async getQuote(symbol: string) {
    return ApiClient.get<QuoteResponse>(`/api/stocks/${symbol}/quote`)
  },

  /**
   * Data verification
   * @param symbol Stock code
   * @param analysisDate Analysis date (YYYY-MM-DD)
   * @param marketType Market type (cn/hk/us)
   * @param options Validation options
   */
  async validateData(
    symbol: string,
    analysisDate?: string,
    marketType: string = 'cn',
    options?: {
      check_basic_info?: boolean
      check_historical_data?: boolean
      check_financial_data?: boolean
      check_realtime_quotes?: boolean
    }
  ) {
    const params = new URLSearchParams({
      symbol,
      market_type: marketType,
      ...(analysisDate && { analysis_date: analysisDate }),
      ...(options?.check_basic_info !== undefined && { check_basic_info: String(options.check_basic_info) }),
      ...(options?.check_historical_data !== undefined && { check_historical_data: String(options.check_historical_data) }),
      ...(options?.check_financial_data !== undefined && { check_financial_data: String(options.check_financial_data) }),
      ...(options?.check_realtime_quotes !== undefined && { check_realtime_quotes: String(options.check_realtime_quotes) })
    })
    return ApiClient.get<DataValidationResponse>(`/api/stock-sync/validate?${params.toString()}`)
  },

  /**
   * Get stock fundamental data
   * @param symbol 6 stock code
   */
  async getFundamentals(symbol: string) {
    return ApiClient.get<FundamentalsResponse>(`/api/stocks/${symbol}/fundamentals`)
  },

  /**
   * Get the latest financial details of a stock
   * @param symbol 6 stock code
   * @param options includeRaw: Whether to return raw_data grouping details
   */
  async getFinancials(symbol: string, options?: { source?: string; includeRaw?: boolean }) {
    return ApiClient.get<StockFinancialsResponse>(
      `/api/stocks/${symbol}/financials`,
      {
        ...(options?.source ? { source: options.source } : {}),
        ...(options?.includeRaw !== undefined ? { include_raw: String(options.includeRaw) } : {}),
      },
      { skipErrorHandler: true }
    )
  },

  /**
   * Get K-line data
   * @param symbol 6 stock code
   * @param period K line period
   * @param limit Number of data items
   * @param adj Restoration method
   */
  async getKline(symbol: string, period: KlineResponse['period'] = 'day', limit = 120, adj: KlineResponse['adj'] = 'none') {
    return ApiClient.get<KlineResponse>(`/api/stocks/${symbol}/kline`, { period, limit, adj })
  },

  /**
   * Get stock news
   * @param symbol 6 stock code
   * @param days days
   * @param limit Quantity limit
   * @param includeAnnouncements Whether to include announcements
   */
  async getNews(symbol: string, days = 30, limit = 50, includeAnnouncements = true) {
    return ApiClient.get<NewsResponse>(`/api/stocks/${symbol}/news`, { days, limit, include_announcements: includeAnnouncements })
  }
}

