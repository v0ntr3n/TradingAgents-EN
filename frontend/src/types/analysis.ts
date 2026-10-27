// Analysis status enum
export enum AnalysisStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// Batch status enum
export enum BatchStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  PARTIAL_SUCCESS = 'partial_success',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// Analysis parameters
export interface AnalysisParameters {
  market_type: 'A shares'
  analysis_date?: string
  research_depth: 'fast' | 'Basics' | 'Standard' | 'Depth' | 'Comprehensive'
  selected_analysts: string[]
  custom_prompt?: string
  include_charts: boolean
  language: 'zh-CN' | 'en-US'
}

// Analyze results
export interface AnalysisResult {
  analysis_id: string
  summary?: string
  recommendation?: string
  confidence_score?: number
  risk_level?: string
  key_points: string[]
  detailed_analysis?: Record<string, any>
  charts: string[]
  tokens_used: number
  execution_time: number
  error_message?: string
}

// Analysis tasks
export interface AnalysisTask {
  id: string
  task_id: string
  batch_id?: string
  user_id: string
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name?: string
  status: AnalysisStatus
  priority: number
  progress: number
  
  // Timestamp
  created_at: string
  started_at?: string
  completed_at?: string
  
  // execution information
  worker_id?: string
  parameters: AnalysisParameters
  result?: AnalysisResult
  
  // Retry mechanism
  retry_count: number
  max_retries: number
  last_error?: string
}

// Analyze batches
export interface AnalysisBatch {
  id: string
  batch_id: string
  user_id: string
  title: string
  description?: string
  status: BatchStatus
  
  // Task statistics
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  cancelled_tasks: number
  progress: number
  
  // Timestamp
  created_at: string
  started_at?: string
  completed_at?: string
  
  // Configuration parameters
  parameters: AnalysisParameters
  
  // summary of results
  results_summary?: Record<string, any>
}

// Stock information (unify front-end and back-end field names)
export interface StockInfo {
  // Basic information
  symbol: string  // Main field: 6-digit stock code
  code?: string   // Compatible fields (deprecated)
  full_symbol?: string  // Complete code (such as 000001.SZ)
  name: string
  market: string
  industry?: string
  area?: string
  board?: string         // Sectors (Main Board, GEM, Science and Technology Innovation Board, etc.)
  exchange?: string      // Exchanges (Shanghai Stock Exchange, Shenzhen Stock Exchange, etc.)

  // Market value information (100 million yuan)
  total_mv?: number      // Total market capitalization
  circ_mv?: number       // Circulation market value

  // financial indicators
  pe?: number            // P/E ratio
  pb?: number            // price to book ratio
  pe_ttm?: number        // rolling price to earnings ratio
  pb_mrq?: number        // Latest price-to-book ratio
  roe?: number           // ROE(%)

  // transaction data
  close?: number         // closing price
  pct_chg?: number       // Increase or decrease(%)
  amount?: number        // Turnover
  turnover_rate?: number // turnover rate(%)
  volume_ratio?: number  // Quantity ratio

  // Technical indicators
  ma20?: number          // 20 daily moving average
  rsi14?: number         // RSI indicator
  kdj_k?: number         // KDJ-K
  kdj_d?: number         // KDJ-D
  kdj_j?: number         // KDJ-J
  dif?: number           // MACD-DIF
  dea?: number           // MACD-DEA
  macd_hist?: number     // MACD bar chart

  // Fundamental Diagnostics/Warnings
  factor_diagnostics?: Record<string, {
    data_quality_tier?: string
    field_name?: string
    display_name?: string
    data_quality_state?: string | null
    unavailable_reason?: string | null
    missing_inputs?: string[]
    report_period?: string | null
    comparison_period?: string | null
  }>
  factor_warnings?: Record<string, {
    warning_conditions: string[]
    warning_categories: Array<'fallback_used' | 'proxy_used' | 'low_sample_size' | 'precision_degraded'>
  }>
}

// Single Stock Research Request
export interface SingleAnalysisRequest {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  parameters?: AnalysisParameters
}

// Bulk research requests
export interface BatchAnalysisRequest {
  title: string
  description?: string
  symbols?: string[]  // Main field: List of stock codes
  stock_codes?: string[]  // Compatible fields (deprecated)
  parameters?: AnalysisParameters
}

// research task response
export interface AnalysisTaskResponse {
  task_id: string
  batch_id?: string
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name?: string
  status: AnalysisStatus
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  result?: AnalysisResult
}

// Study batch response
export interface AnalysisBatchResponse {
  batch_id: string
  title: string
  description?: string
  status: BatchStatus
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  parameters: AnalysisParameters
}

// Study historical query parameters
export interface AnalysisHistoryQuery {
  status?: AnalysisStatus
  start_date?: string
  end_date?: string
  symbol?: string  // Main field: Stock code
  stock_code?: string  // Compatible fields (deprecated)
  batch_id?: string
  page: number
  page_size: number
}

// Research historical responses
export interface AnalysisHistoryResponse {
  tasks: AnalysisTask[]
  batches: AnalysisBatch[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

// Task progress information
export interface TaskProgress {
  task_id: string
  status: AnalysisStatus
  progress: number
  message?: string
  updated_at: string
}

// Batch progress information
export interface BatchProgress {
  batch_id: string
  status: BatchStatus
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress: number
  updated_at: string
}

// Research Statistics
export interface AnalysisStats {
  total_analyses: number
  successful_analyses: number
  failed_analyses: number
  success_rate: number
  average_execution_time: number
  total_tokens_used: number
  daily_analyses: number
  monthly_analyses: number
}

// Queue status information
export interface QueueStatus {
  pending: number
  processing: number
  completed: number
  failed: number
  queue_size: number
}

// User queue status
export interface UserQueueStatus {
  pending: number
  processing: number
  concurrent_limit: number
  available_slots: number
}

// research report
export interface AnalysisReport {
  id: string
  task_id: string
  batch_id?: string
  title: string
  content: string
  format: 'html' | 'pdf' | 'markdown'
  created_at: string
  download_url?: string
}
