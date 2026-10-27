/**
 * Multi-data source synchronization related API
 */
import { ApiClient } from './request'

// Data source status interface
export interface DataSourceStatus {
  name: string
  priority: number
  available: boolean
  description: string
  token_source?: 'database' | 'env'  // Token Source (Tushare only)
}

// Synchronization status interface
export interface SyncStatus {
  job: string
  status: 'idle' | 'queued' | 'running' | 'success' | 'success_with_errors' | 'failed' | 'never_run'
  started_at?: string
  finished_at?: string
  total: number
  inserted: number
  updated: number
  errors: number
  last_trade_date?: string
  data_sources_used: string[]
  source_stats?: Record<string, Record<string, number>>
  message?: string
}

// Synchronous request parameters
export interface SyncRequest {
  force?: boolean
  preferred_sources?: string[]
}

// API response format
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data: T
}

// Basic test result interface
export interface BaseTestResult {
  success: boolean
  message: string
  count?: number
  date?: string
}

// Test results interface (simplified version)
export interface DataSourceTestResult {
  name: string
  priority: number
  available: boolean
  message: string
  token_source?: 'database' | 'env'  // Token Source (Tushare only)
}

// Use the recommended interface
export interface SyncRecommendations {
  primary_source?: {
    name: string
    priority: number
    reason: string
  }
  fallback_sources: Array<{
    name: string
    priority: number
  }>
  suggestions: string[]
  warnings: string[]
}

/**
 * Get data source status
 */
export const getDataSourcesStatus = (): Promise<ApiResponse<DataSourceStatus[]>> => {
  return ApiClient.get('/api/sync/multi-source/sources/status')
}

/**
 * Get the data source currently in use
 */
export const getCurrentDataSource = (): Promise<ApiResponse<{
  name: string
  priority: number
  description: string
  token_source?: 'database' | 'env'
  token_source_display?: string
}>> => {
  return ApiClient.get('/api/sync/multi-source/sources/current')
}

/**
 * Get sync status
 */
export const getSyncStatus = (): Promise<ApiResponse<SyncStatus>> => {
  return ApiClient.get('/api/sync/multi-source/status')
}

/**
 * Run basic stock information synchronization
 */
export const runStockBasicsSync = (params?: {
  force?: boolean
  preferred_sources?: string
}): Promise<ApiResponse<SyncStatus>> => {
  const queryParams = new URLSearchParams()
  if (params?.force) {
    queryParams.append('force', 'true')
  }
  if (params?.preferred_sources) {
    queryParams.append('preferred_sources', params.preferred_sources)
  }

  const url = `/api/sync/multi-source/stock_basics/run${queryParams.toString() ? '?' + queryParams.toString() : ''}`
  return ApiClient.post(url, undefined, {
  timeout: 15000 // The backend has been changed to return immediately after starting the task, and the frontend uses status polling.
  })
}

/**
 * Test data source connection
 * @param sourceName - Optionally, specify the name of the data source to test. If not specified, all data sources are tested
 */
export const testDataSources = (sourceName?: string): Promise<ApiResponse<{ test_results: DataSourceTestResult[] }>> => {
  const params = sourceName ? { source_name: sourceName } : {}
  return ApiClient.post('/api/sync/multi-source/test-sources', params, {
    timeout: 15000 // The test timeout is 15 seconds for a single data source and up to 30 seconds for multiple data sources.
  })
}

/**
 * Get sync suggestions
 */
export const getSyncRecommendations = (): Promise<ApiResponse<SyncRecommendations>> => {
  return ApiClient.get('/api/sync/multi-source/recommendations')
}

/**
 * Get sync history
 */
export const getSyncHistory = (params?: {
  page?: number
  page_size?: number
  status?: string
}): Promise<ApiResponse<{
  records: SyncStatus[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.page) {
    queryParams.append('page', params.page.toString())
  }
  if (params?.page_size) {
    queryParams.append('page_size', params.page_size.toString())
  }
  if (params?.status) {
    queryParams.append('status', params.status)
  }

  const url = `/api/sync/multi-source/history${queryParams.toString() ? '?' + queryParams.toString() : ''}`
  return ApiClient.get(url)
}

/**
 * Clear sync cache
 */
export const clearSyncCache = (): Promise<ApiResponse<{ cleared: boolean }>> => {
  return ApiClient.delete('/api/sync/multi-source/cache')
}

// Traditional single data source synchronization API (maintaining compatibility)
export const runSingleSourceSync = (): Promise<ApiResponse<any>> => {
  return ApiClient.post('/api/sync/stock_basics/run', undefined, {
    timeout: 15000 // The backend has been changed to return immediately after submitting the task
  })
}

export const getSingleSourceSyncStatus = (): Promise<ApiResponse<any>> => {
  return ApiClient.get('/api/sync/stock_basics/status')
}
