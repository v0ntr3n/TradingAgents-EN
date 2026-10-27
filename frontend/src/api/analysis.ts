
/**
 * stock analysis API
 */

import { request, type ApiResponse } from './request'

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




