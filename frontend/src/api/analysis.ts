import { request, type ApiResponse } from './request'
import { ApiClient, type ApiResponse } from './request'
import { ApiClient } from './request'

// ============================================================================
// Module: analysis.ts
// ============================================================================

/**
 * stock analysis API
 */



// Analyze related type definitions
export interface AnalysisRequest {
  market_type: string
  stock_symbol: string
  analysis_date: string
  analysis_type: string
  data_sources: string[]
  analysis_depth: number
  include_news: boolean
  include_financials: boolean
  llm_provider?: string
  llm_model?: string
}

// Analysis engine type (consistent with the backend AnalysisEngine enumeration)
export type AnalysisEngineType = 'legacy' | 'unified' | 'v2'

// The request format expected by the backend
export interface SingleAnalysisRequest {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  parameters?: {
    market_type?: string
    analysis_date?: string
    research_depth?: string
    selected_analysts?: string[]
    custom_prompt?: string
    include_sentiment?: boolean
    include_risk?: boolean
    language?: string
    quick_analysis_model?: string
    deep_analysis_model?: string
    engine?: AnalysisEngineType
    workflow_id?: string
    enable_trace?: boolean
  }
}

export interface AnalysisProgress {
  analysis_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  current_step: string
  step_detail: string
  steps: AnalysisStep[]
  started_at: string
  updated_at: string
  estimated_completion?: string
}

export interface AnalysisStep {
  name: string
  title: string
  description: string
  status: 'pending' | 'active' | 'success' | 'error'
  started_at?: string
  completed_at?: string
  duration?: number
  error_message?: string
}

export interface AnalysisResult {
  analysis_id: string
  symbol?: string  // Main field: 6-digit stock code
  stock_symbol: string  // Compatible fields
  stock_code?: string  // Compatible fields (deprecated)
  stock_name: string
  market_type: string
  analysis_date: string
  analysis_type: string

  // Basic data
  current_price: number
  price_change: number
  price_change_percent: number
  volume: number
  market_cap?: number

  // Analyze results
  summary: string
  technical_analysis: string
  fundamental_analysis: string
  sentiment_analysis: string
  news_analysis?: string
  recommendation: string
  risk_assessment: string

  // Rating
  technical_score: number
  fundamental_score: number
  sentiment_score: number
  overall_score: number

  // metadata
  data_sources: string[]
  llm_provider: string
  llm_model: string
  analysis_duration: number
  token_usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    cost: number
  }

  created_at: string
  updated_at: string
}

export interface AnalysisHistory {
  total: number
  page: number
  page_size: number
  analyses: AnalysisResult[]
}

// stock analysis API
export const analysisApi = {
  // Start analysis
  startAnalysis(analysisRequest: AnalysisRequest): Promise<{ analysis_id: string; message: string }> {
    return request.post('/api/analysis/single', analysisRequest)
  },

  // Start a single stock study (using the format expected by the backend)
  startSingleAnalysis(analysisRequest: SingleAnalysisRequest): Promise<ApiResponse<any>> {
    return request.post('/api/analysis/single', analysisRequest)
  },

  // Pre-analysis: Check data source configuration and basic data synchronization status
  precheck(symbol?: string): Promise<ApiResponse<any>> {
    const params = symbol ? { symbol } : {}
    return request.get('/api/analysis/precheck', { params })
  },

  // Get task status
  getTaskStatus(taskId: string): Promise<ApiResponse<any>> {
    return request.get(`/api/analysis/tasks/${taskId}/status`)
  },

  // Get analysis progress
  getProgress(analysisId: string): Promise<AnalysisProgress> {
    return request.get(`/api/analysis/${analysisId}/progress`)
  },

  // Get analysis results
  getResult(analysisId: string): Promise<AnalysisResult> {
    return request.get(`/api/analysis/${analysisId}/result`)
  },

  // Stop analysis
  stopAnalysis(analysisId: string): Promise<{ message: string }> {
    return request.post(`/api/analysis/${analysisId}/stop`, {})
  },

  // Get analysis history (user dimension)
  getHistory(params?: {
    page?: number
    page_size?: number
    market_type?: string
    symbol?: string  // Main field: Stock code
    stock_code?: string  // Compatible fields (deprecated)
    start_date?: string
    end_date?: string
    status?: string
  }): Promise<any> {
    return request.get('/api/analysis/user/history', { params })
  },

  // Delete analysis results
  deleteAnalysis(analysisId: string): Promise<{ message: string }> {
    return request.delete(`/api/analysis/${analysisId}`)
  },

  // Export analysis results
  exportAnalysis(analysisId: string, format: 'pdf' | 'excel' | 'json' = 'pdf'): Promise<Blob> {
    return request.get(`/api/analysis/${analysisId}/export`, {
      params: { format },
      responseType: 'blob'
    })
  },

  // Batch Analysis (Option A: In-Process Execution Consistent with Single Stocks)
  startBatchAnalysis(batchRequest: {
    title: string
    description?: string
    symbols?: string[]  // Main field: List of stock codes
    stock_codes?: string[]  // Compatible fields (deprecated)
    parameters?: SingleAnalysisRequest['parameters']
  }): Promise<ApiResponse<{ batch_id: string; total_tasks: number; task_ids: string[]; mapping?: any[]; status: string }>>{
    return request.post('/api/analysis/batch', batchRequest)
  },

  // Get batch details (compatible with the original queue interface, if needed later)
  getBatch(batchId: string): Promise<any> {
    return request.get(`/api/analysis/batches/${batchId}`)
  },

  // Get task details (compatible with the original queue interface, if needed later)
  getTaskDetails(taskId: string): Promise<any> {
    return request.get(`/api/analysis/tasks/${taskId}/details`)
  },

  // Get task list (new version simple service)
  getTaskList(params?: { status?: string; limit?: number; offset?: number }): Promise<any>{
    return request.get('/api/analysis/tasks', { params })
  },

  // Get task results (new version of simple service)
  getTaskResult(taskId: string): Promise<any>{
    return request.get(`/api/analysis/tasks/${taskId}/result`)
  },

  // Mark task as failed
  markTaskAsFailed(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.post(`/api/analysis/tasks/${taskId}/mark-failed`, {})
  },

  // Delete task
  deleteTask(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.delete(`/api/analysis/tasks/${taskId}`)
  },

  // Recreate failed tasks
  retryTask(taskId: string): Promise<ApiResponse<{ task_id: string; message: string }>> {
    return request.post(`/api/analysis/tasks/${taskId}/retry`)
  },

  // Share analysis results
  shareAnalysis(analysisId: string, options: {
    expires_in?: number // Expiration time (seconds)
    password?: string   // access password
    public?: boolean    // Is it public?
  }): Promise<{ share_url: string; share_code: string }> {
    return request.post(`/api/analysis/${analysisId}/share`, options)
  },

  // Get basic stock information
  getStockInfo(symbol: string, market: string): Promise<{
    symbol: string
    name: string
    market: string
    current_price: number
    change: number
    change_percent: number
    volume: number
    market_cap?: number
    pe_ratio?: number
    pb_ratio?: number
    dividend_yield?: number
  }> {
    return request.get('/api/analysis/stock-info', {
      params: { symbol, market }
    })
  },

  // Search stocks
  searchStocks(query: string, market?: string): Promise<Array<{
    symbol: string
    name: string
    market: string
    type: string
  }>> {
    return request.get('/api/analysis/search', {
      params: { query, market }
    })
  },

  // Get popular stocks
  getPopularStocks(market?: string, limit: number = 10): Promise<Array<{
    symbol: string
    name: string
    market: string
    current_price: number
    change_percent: number
    volume: number
    analysis_count: number
  }>> {
    return request.get('/api/analysis/popular', {
      params: { market, limit }
    })
  },

  // Get analysis statistics
  getAnalysisStats(params?: {
    start_date?: string
    end_date?: string
    market_type?: string
  }): Promise<{
    total_analyses: number
    successful_analyses: number
    failed_analyses: number
    avg_duration: number
    total_tokens: number
    total_cost: number
    popular_stocks: Array<{
      symbol: string
      name: string
      count: number
    }>
    analysis_by_date: Array<{
      date: string
      count: number
    }>
    analysis_by_market: Array<{
      market: string
      count: number
    }>
  }> {
    return request.get('/api/analysis/stats', { params })
  }
}

// Analyze related constants
export const MARKET_TYPES = {
  CN: 'A shares'
} as const

export const ANALYSIS_TYPES = {
  BASIC: 'basic',
  DEEP: 'deep',
  TECHNICAL: 'technical',
  NEWS: 'news',
  COMPREHENSIVE: 'comprehensive'
} as const

/**
 * Data source constants
 *
 * NOTE: These constants are kept in sync with the backend DataSourceType enumeration
 * When adding a new data source, please first register it in the backend tradingagents/constants/data_sources.py
 */
export const DATA_SOURCES = {
  // cache data source
  MONGODB: 'mongodb',

  // China market data source
  TUSHARE: 'tushare',
  AKSHARE: 'akshare',
  BAOSTOCK: 'baostock',

  // Professional data source
  WIND: 'wind',
  CHOICE: 'choice',

  // Other data sources
  QUANDL: 'quandl',
  LOCAL_FILE: 'local_file',
  CUSTOM: 'custom'
} as const

// Analyze status constants
export const ANALYSIS_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed'
} as const

// step status constants
export const STEP_STATUS = {
  PENDING: 'pending',
  ACTIVE: 'active',
  SUCCESS: 'success',
  ERROR: 'error'
} as const

// Verification function
export const validateAnalysisRequest = (request: Partial<AnalysisRequest>): string[] => {
  const errors: string[] = []

  if (!request.market_type) errors.push('Please select market type')
  if (!request.stock_symbol) errors.push('Please enter stock code')
  if (!request.analysis_date) errors.push('Please select analysis date')
  if (!request.analysis_type) errors.push('Please select analysis type')
  if (!request.data_sources || request.data_sources.length === 0) {
    errors.push('Please select at least one data source')
  }

  // Validate ticker format
  if (request.stock_symbol) {
    const symbol = request.stock_symbol.trim().toUpperCase()
    if (!/^\d{6}$/.test(symbol)) {
      errors.push('A The stock code format is incorrect, it should be 6 digits')
    }
  }

  return errors
}

// format function
export const formatAnalysisType = (type: string): string => {
  const typeMap: Record<string, string> = {
    basic: 'Fundamental analysis',
    deep: 'In-depth analysis',
    technical: 'technical analysis',
    news: 'news analysis',
    comprehensive: 'comprehensive analysis'
  }
  return typeMap[type] ?? type
}

export const formatMarketType = (market: string): string => {
  const marketMap: Record<string, string> = {
    'US stocks': '🇺🇸 US stocks',
    'A shares': '🇨🇳 A shares',
    'Hong Kong stocks': '🇭🇰 Hong Kong stocks'
  }
  return marketMap[market] ?? market
}

export const formatDataSource = (source: string): string => {
  const sourceMap: Record<string, string> = {
    tushare: 'Tushare',
    akshare: 'AKShare'
  }
  return sourceMap[source] ?? source
}

/**
 * Get analysis history (current user)
 */
export const getAnalysisHistory = async (params: {
  page?: number
  page_size?: number
  status?: string
}) => {
  const response = await request.get('/api/analysis/user/history', { params })
  return response.data
}

/**
 * Get all task lists (not limited to users)
 */
export const getAllTasks = async (params: {
  limit?: number
  offset?: number
  status?: string
}) => {
  return request<{
    tasks: any[]
    total: number
    limit: number
    offset: number
  }>({
    url: '/api/analysis/tasks/all',
    method: 'GET',
    params
  })
}

// Utility function
export const getStockExamples = (): string[] => {
  return ['000001', '600519', '000002', '600036', '000858', '002415', '300059', '688981']
}

export const getStockPlaceholder = (): string => {
  return 'Enter the A-share code, such as 000001, 600519'
}

// ============================================================================
// Module: analysisProfiles.ts
// ============================================================================

// ── type definition ──

export interface AnalysisDimension {
  name: string
  description: string
  importance?: string
  data_source?: string
  weight?: number
}

export interface IndustryProfile {
  id?: string
  industry: string
  display_name: string
  analysis_dimensions: AnalysisDimension[]
  analysis_focus: string
  key_metrics: string[]
  comparable_companies: string[]
  source?: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface StockProfile {
  id?: string
  stock_symbol: string
  stock_name?: string
  industry?: string
  special_notes: string
  analysis_dimensions: AnalysisDimension[]
  is_active: boolean
  created_at?: string
  updated_at?: string
}

// ── Override evaluation type ──

export interface SourceRef {
  type: string
  type_label: string
  name: string
  detail: string
}

export interface ItemAssessment {
  name: string
  description: string
  requested_data_source: string
  coverage_status: 'directly_usable' | 'partially_usable' | 'external_required' | 'review_recommended'
  coverage_label: string
  recommended_action: string
  recommended_action_label: string
  matched_sources: SourceRef[]
  missing_requirements: string[]
  user_note: string
}

export interface CoverageSummary {
  overall_status: 'ready' | 'review_needed' | 'prune_needed'
  overall_label: string
  dimension_counts: Record<string, number>
  metric_counts: Record<string, number>
  recommendations: string[]
}

export interface CapabilitySnapshot {
  builtin_sources: { key: string; label: string; description: string }[]
  enabled_mcp_servers: { server_id: string; name: string; description: string; tool_count: number }[]
  active_skills: { tool_id: string; name: string; description: string }[]
  manual_import: { available: boolean; label: string; description: string }
  counts: { builtin_sources: number; enabled_mcp_servers: number; active_skills: number }
  notes: string[]
}

export interface GeneratePreview {
  profile: IndustryProfile
  coverage_summary: CoverageSummary
  capability_snapshot: CapabilitySnapshot
  dimension_assessments: ItemAssessment[]
  metric_assessments: ItemAssessment[]
  next_step_guidance: string[]
}

export interface GenerateIndustryOptions {
  user_request?: string
  existing_profile?: Partial<IndustryProfile>
}

// ── API interface ──

export const analysisProfilesApi = {
  // Industry configuration
  async listIndustries(isActive?: boolean): Promise<ApiResponse<IndustryProfile[]>> {
    const params: Record<string, any> = {}
    if (isActive !== undefined) params.is_active = isActive
    const res = await ApiClient.get('/api/analysis-profiles/industries', params)
    return res as ApiResponse<IndustryProfile[]>
  },

  async getIndustry(profileId: string): Promise<ApiResponse<IndustryProfile>> {
    return ApiClient.get(`/api/analysis-profiles/industries/${profileId}`)
  },

  async createIndustry(data: Partial<IndustryProfile>): Promise<ApiResponse<IndustryProfile>> {
    return ApiClient.post('/api/analysis-profiles/industries', data)
  },

  async updateIndustry(profileId: string, data: Partial<IndustryProfile>): Promise<ApiResponse<IndustryProfile>> {
    return ApiClient.put(`/api/analysis-profiles/industries/${profileId}`, data)
  },

  async deleteIndustry(profileId: string): Promise<ApiResponse<any>> {
    return ApiClient.delete(`/api/analysis-profiles/industries/${profileId}`)
  },

  async generateIndustry(industry: string, options?: GenerateIndustryOptions): Promise<ApiResponse<GeneratePreview>> {
    return ApiClient.post('/api/analysis-profiles/industries/generate', {
      industry,
      user_request: options?.user_request || '',
      existing_profile: options?.existing_profile || undefined,
    })
  },

  /** Get all actual industry names in the database (from stock_basic_info) */
  async getIndustryList(): Promise<ApiResponse<string[]>> {
    return ApiClient.get('/api/analysis-profiles/industry-list')
  },

  // Individual stock allocation
  async listStocks(industry?: string): Promise<ApiResponse<StockProfile[]>> {
    const params: Record<string, any> = {}
    if (industry) params.industry = industry
    const res = await ApiClient.get('/api/analysis-profiles/stocks', params)
    return res as ApiResponse<StockProfile[]>
  },

  async getStock(stockSymbol: string): Promise<ApiResponse<StockProfile>> {
    return ApiClient.get(`/api/analysis-profiles/stocks/${stockSymbol}`)
  }
}

// ============================================================================
// Module: preferences.ts
// ============================================================================

export interface PreferenceItem {
  preference_id: string
  name: string
  description: string
  risk_level: number
  decision_speed: string
  is_system: boolean
}

export const PreferencesApi = {
  async listSystem(): Promise<ApiResponse<PreferenceItem[]>> {
    return ApiClient.get('/api/v1/preferences')
  }
}

// ============================================================================
// Module: paper.ts
// ============================================================================

export interface CurrencyAmount {
  CNY: number
}

export interface PaperAccountSummary {
  cash: CurrencyAmount | number  // Support new and old formats
  realized_pnl: CurrencyAmount | number  // Support new and old formats
  positions_value: CurrencyAmount
  equity: CurrencyAmount | number  // Support new and old formats
  updated_at?: string
}

export interface PaperPositionItem {
  code: string
  quantity: number
  avg_cost: number
  last_price?: number | null
  market_value?: number
  unrealized_pnl?: number | null
}

export interface PaperOrderItem {
  user_id?: string
  code: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  amount: number
  status: 'filled' | 'rejected' | string
  created_at: string
  filled_at?: string
}

export interface GetAccountResponse {
  account: PaperAccountSummary
  positions: PaperPositionItem[]
}

export interface PlaceOrderPayload {
  code: string
  side: 'buy' | 'sell'
  quantity: number
  market?: string
  price?: number  // Optional: specify price
  analysis_id?: string
}

export interface QuoteInfo {
  code: string
  market: string
  current_price: number | null
  high: number | null
  low: number | null
}

export interface InitializeAccountRequest {
  initial_cash: CurrencyAmount
}

export interface ResetAccountRequest {
  initial_cash?: CurrencyAmount
}

export const paperApi = {
  async getAccount() {
    return ApiClient.get<GetAccountResponse>('/api/paper/account')
  },
  async placeOrder(data: PlaceOrderPayload) {
    return ApiClient.post<{ order: PaperOrderItem }>('/api/paper/order', data, { showLoading: true })
  },
  async getPositions() {
    return ApiClient.get<{ items: PaperPositionItem[] }>('/api/paper/positions')
  },
  async getOrders(limit = 50) {
    return ApiClient.get<{ items: PaperOrderItem[] }>(`/api/paper/orders`, { limit })
  },
  /**
   * Initialize account (set initial amount)
   * If the account already exists, positions and orders will be cleared and reset to the specified amount.
   * If the account does not exist, a new account will be created
   */
  async initializeAccount(data: InitializeAccountRequest) {
    return ApiClient.post<{ message: string; cash: CurrencyAmount; account: any }>('/api/paper/initialize', data, { showLoading: true })
  },
  /**
   * Reset account (supports custom initial amount)
   * If initial_cash is not provided, the default amount is used
   */
  async resetAccount(data?: ResetAccountRequest) {
    // Backend requirements confirm=true
    const params = new URLSearchParams()
    params.append('confirm', 'true')
    return ApiClient.post<{ message: string; cash: CurrencyAmount }>(
      `/api/paper/reset?${params.toString()}`,
      data || {},
      { showLoading: true }
    )
  },
  async getQuote(code: string, market?: string) {
    return ApiClient.get<QuoteInfo>(`/api/paper/quote/${code}`, { market })
  }
}
