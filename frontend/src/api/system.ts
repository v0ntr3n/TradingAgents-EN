import { ApiClient } from './request'
import type { 
  LoginForm, 
  RegisterForm, 
  LoginResponse, 
  RefreshTokenResponse,
  User,
  UserUpdatePayload,
  ChangePasswordForm
} from '@/types/auth'
import request from '@/api/request'
import { formatDateTime as formatDateTimeUtil } from '@/utils/datetime'
import { request } from './request'
import request, { ApiClient } from './request'
import type { ApiResponse } from './request'

// ============================================================================
// Module: auth.ts
// ============================================================================

export const authApi = {
  // Login
  login: (data: LoginForm) =>
    ApiClient.post<LoginResponse>('/api/auth/login', data, {
      skipAuth: true,  // Login requests do not require authentication
      skipAuthError: true  // Skip automatic handling of 401 errors
    }),

  // Register
  register: (data: RegisterForm) =>
    ApiClient.post('/api/auth/register', data, {
      skipAuth: true,  // Registration requests do not require authentication
      skipAuthError: true  // Skip automatic handling of 401 errors
    }),

  // Log out
  logout: () =>
    ApiClient.post('/api/auth/logout'),

  // Refresh Token
  refreshToken: (refreshToken: string) =>
    ApiClient.post<RefreshTokenResponse>('/api/auth/refresh', { refresh_token: refreshToken }),

  // Get user information
  getUserInfo: () =>
    ApiClient.get<User>('/api/auth/me'),

  // Obtain user permissions (not required for the open source version, admin has all permissions)
  // getUserPermissions: () =>
  //   ApiClient.get<UserPermissions>('/api/auth/permissions'),

  // Update user information
  updateUserInfo: (data: UserUpdatePayload) =>
    ApiClient.put<User>('/api/auth/me', data),

  // Change password
  changePassword: (data: ChangePasswordForm) =>
    ApiClient.post('/api/auth/change-password', data),

  // reset password
  resetPassword: (email: string) =>
    ApiClient.post('/api/auth/reset-password', { email }),

  // Verify email
  verifyEmail: (token: string) =>
    ApiClient.post('/api/auth/verify-email', { token }),

}

// ============================================================================
// Module: database.ts
// ============================================================================

/**
 * Database management API
 */



// Database status interface
export interface DatabaseStatus {
  mongodb: {
    connected: boolean
    host: string
    port: number
    database: string
    version?: string
    uptime?: number
    connections?: any
    memory?: any
    connected_at?: string
    error?: string
  }
  redis: {
    connected: boolean
    host: string
    port: number
    database: number
    version?: string
    uptime?: number
    memory_used?: number
    memory_peak?: number
    connected_clients?: number
    total_commands?: number
    error?: string
  }
}

// Database statistics interface
export interface DatabaseStats {
  total_collections: number
  total_documents: number
  total_size: number
  collections: Array<{
    name: string
    documents: number
    size: number
    storage_size: number
    indexes: number
    index_size: number
  }>
}

// Backup information interface
export interface BackupInfo {
  id: string
  name: string
  filename: string
  size: number
  collections: string[]
  created_at: string
  created_by?: string
}

// Connect test result interface
export interface ConnectionTestResult {
  mongodb: {
    success: boolean
    response_time_ms?: number
    message: string
    error?: string
  }
  redis: {
    success: boolean
    response_time_ms?: number
    message: string
    error?: string
  }
  overall: boolean
}

// Database management API
export const databaseApi = {
  // Get database status
  async getStatus(): Promise<DatabaseStatus> {
    const response = await ApiClient.get<DatabaseStatus>('/api/system/database/status')
    return response.data
  },

  // Get database statistics
  async getStats(): Promise<DatabaseStats> {
    const response = await ApiClient.get<DatabaseStats>('/api/system/database/stats')
    return response.data
  },

  // Test database connection
  testConnections(): Promise<{ success: boolean; message: string; data: ConnectionTestResult }> {
    return ApiClient.post('/api/system/database/test')
  },

  // Create backup
  createBackup(data: {
    name: string
    collections?: string[]
  }): Promise<{ success: boolean; message: string; data: BackupInfo }> {
    return ApiClient.post('/api/system/database/backup', data)
  },

  // Get backup list
  getBackups(): Promise<{ success: boolean; data: BackupInfo[] }> {
    return ApiClient.get('/api/system/database/backups')
  },

  // Delete backup
  deleteBackup(backupId: string): Promise<{ success: boolean; message: string }> {
    return ApiClient.delete(`/api/system/database/backups/${backupId}`)
  },

  // Import data
  importData(
    file: File,
    options: {
      collection: string
      format?: string
      overwrite?: boolean
    }
  ): Promise<{ success: boolean; message: string; data: any }> {
    const formData = new FormData()
    formData.append('file', file)

    // 🔥 Passing using URL parameters collection, format, overwrite
    // FastAPI When the File parameter is mixed with other parameters, other parameters need to be passed through Query.
    const params = new URLSearchParams({
      collection: options.collection,
      format: options.format || 'json',
      overwrite: String(options.overwrite || false)
    })

    console.log('📤 Import data request:', {
      filename: file.name,
      size: file.size,
      collection: options.collection,
      format: options.format,
      overwrite: options.overwrite
    })

    return ApiClient.post(`/api/system/database/import?${params.toString()}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // Export data
  exportData(options: {
    collections?: string[]
    format?: string
    sanitize?: boolean  // Whether to desensitize (clear sensitive fields, used for demonstration system)
  }): Promise<Blob> {
    return ApiClient.post('/api/system/database/export', options, {
      responseType: 'blob'
    }) as any
  },

  // Clean old data
  cleanupOldData(days: number = 30): Promise<{
    success: boolean
    message: string
    data: {
      deleted_count: number
      cleaned_collections: string[]
      cutoff_date: string
    }
  }> {
    return ApiClient.post(`/api/system/database/cleanup?days=${days}`)
  },

  // Clean up expired analysis results
  cleanupAnalysisResults(days: number = 30): Promise<{
    success: boolean
    message: string
    data: {
      deleted_count: number
      cleaned_collections: string[]
      cutoff_date: string
    }
  }> {
    return ApiClient.post(`/api/system/database/cleanup/analysis?days=${days}`)
  },

  // Clean operation log
  cleanupOperationLogs(days: number = 90): Promise<{
    success: boolean
    message: string
    data: {
      deleted_count: number
      cleaned_collections: string[]
      cutoff_date: string
    }
  }> {
    return ApiClient.post(`/api/system/database/cleanup/logs?days=${days}`)
  },

  // Get MongoDB connection information (used to generate backup/restore commands)
  async getConnectionInfo(): Promise<{
    success: boolean
    message: string
    data: {
      mongo_uri: string
      display_uri: string
      database_name: string
      host: string
      port: number
      has_auth: boolean
      install_dir: string
    }
  }> {
    const response = await ApiClient.get('/api/system/database/connection-info')
    return response
  }
}

// Utility function
export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

export const formatDateTime = (dateTime: string): string => {
  return new Date(dateTime).toLocaleString('zh-CN')
}

export const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  
  if (days > 0) {
    return `${days}day ${hours}hours ${minutes}minutes`
  } else if (hours > 0) {
    return `${hours}hours ${minutes}minutes`
  } else {
    return `${minutes}minutes`
  }
}

// ============================================================================
// Module: cache.ts
// ============================================================================

/**
 * Cache management API
 */


/**
 * cache statistics
 */
export interface CacheStats {
  totalFiles: number
  totalSize: number
  maxSize: number
  stockDataCount: number
  newsDataCount: number
  analysisDataCount: number
}

/**
 * Cache details item
 */
export interface CacheDetailItem {
  type: string
  symbol: string
  size: number
  created_at: string
  last_accessed: string
  hit_count: number
}

/**
 * Cache details response
 */
export interface CacheDetailsResponse {
  items: CacheDetailItem[]
  total: number
  page: number
  page_size: number
}

/**
 * Caching backend information
 */
export interface CacheBackendInfo {
  system: string
  primary_backend: string
  fallback_enabled: boolean
  mongodb_available?: boolean
  redis_available?: boolean
}

/**
 * Get cache statistics
 */
export function getCacheStats() {
  return request<CacheStats>({
    url: '/api/cache/stats',
    method: 'get'
  })
}

/**
 * Clear expired cache
 * @param days How many days old cache should be cleared?
 */
export function cleanupOldCache(days: number) {
  return request({
    url: '/api/cache/cleanup',
    method: 'delete',
    params: { days }
  })
}

/**
 * Clear all cache
 */
export function clearAllCache() {
  return request({
    url: '/api/cache/clear',
    method: 'delete'
  })
}

/**
 * Get cache details list
 * @param page Page number
 * @param pageSize Quantity per page
 */
export function getCacheDetails(page: number = 1, pageSize: number = 20) {
  return request<CacheDetailsResponse>({
    url: '/api/cache/details',
    method: 'get',
    params: { page, page_size: pageSize }
  })
}

/**
 * Get cache backend information
 */
export function getCacheBackendInfo() {
  return request<CacheBackendInfo>({
    url: '/api/cache/backend-info',
    method: 'get'
  })
}

// ============================================================================
// Module: logs.ts
// ============================================================================

/**
 * Log management API
 */



export interface LogFileInfo {
  name: string
  path: string
  size: number
  size_mb: number
  modified_at: string
  type: 'error' | 'webapi' | 'worker' | 'access' | 'other'
}

export interface LogContentResponse {
  filename: string
  lines: string[]
  stats: {
    total_lines: number
    filtered_lines: number
    error_count: number
    warning_count: number
    info_count: number
    debug_count: number
  }
}

export interface LogStatistics {
  total_files: number
  total_size_mb: number
  error_files: number
  recent_errors: string[]
  log_types: Record<string, number>
}

export interface LogReadRequest {
  filename: string
  lines?: number
  level?: 'ERROR' | 'WARNING' | 'INFO' | 'DEBUG'
  keyword?: string
  start_time?: string
  end_time?: string
}

export interface LogExportRequest {
  filenames?: string[]
  level?: 'ERROR' | 'WARNING' | 'INFO' | 'DEBUG'
  start_time?: string
  end_time?: string
  format?: 'zip' | 'txt'
}

export const LogsApi = {
  /**
   * Get a list of log files
   */
  listLogFiles(): Promise<LogFileInfo[]> {
    return ApiClient.get('/api/system/system-logs/files').then((response: any) => response.data ?? response)
  },

  /**
   * Read log file contents
   */
  readLogFile(request: LogReadRequest): Promise<LogContentResponse> {
    return ApiClient.post('/api/system/system-logs/read', request).then((response: any) => response.data ?? response)
  },

  /**
   * Export log file
   */
  async exportLogs(request: LogExportRequest): Promise<Blob> {
    const response = await ApiClient.post('/api/system/system-logs/export', request, {
      responseType: 'blob'
    })
    return response as unknown as Blob
  },

  /**
   * Get log statistics
   */
  getStatistics(days: number = 7): Promise<LogStatistics> {
    return ApiClient.get('/api/system/system-logs/statistics', { params: { days } }).then((response: any) => response.data ?? response)
  },

  /**
   * Delete log files
   */
  deleteLogFile(filename: string): Promise<{ success: boolean; message: string }> {
    return ApiClient.delete(`/api/system/system-logs/files/${filename}`)
  }
}

// ============================================================================
// Module: operationLogs.ts
// ============================================================================

/**
 * Operation log API interface
 */



// Operation log data type
export interface OperationLog {
  id: string
  user_id: string
  username: string
  action_type: string
  action: string
  details?: Record<string, any>
  success: boolean
  error_message?: string
  duration_ms?: number
  ip_address?: string
  user_agent?: string
  session_id?: string
  timestamp: string
  created_at: string
}

// Operation log query parameters
export interface OperationLogQuery {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  action_type?: string
  success?: boolean
  keyword?: string
}

// Operation log list response
export interface OperationLogListResponse {
  success: boolean
  data: {
    logs: OperationLog[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
  message: string
}

// Operation log statistics
export interface OperationLogStats {
  total_logs: number
  success_logs: number
  failed_logs: number
  success_rate: number
  action_type_distribution: Record<string, number>
  hourly_distribution: Array<{
    hour: string
    count: number
  }>
}

// Operation log statistics response
export interface OperationLogStatsResponse {
  success: boolean
  data: OperationLogStats
  message: string
}

// Create operation log request
export interface CreateOperationLogRequest {
  action_type: string
  action: string
  details?: Record<string, any>
  success?: boolean
  error_message?: string
  duration_ms?: number
  session_id?: string
}

// Clear log request
export interface ClearLogsRequest {
  days?: number
  action_type?: string
}

// Clear log response
export interface ClearLogsResponse {
  success: boolean
  data: {
    deleted_count: number
    filter: Record<string, any>
  }
  message: string
}

// Operation log API class
export class OperationLogsApi {
  /**
   * Get operation log list
   */
  static getOperationLogs(params: OperationLogQuery = {}): Promise<OperationLogListResponse> {
    const queryParams = new URLSearchParams()
    
    if (params.page) queryParams.append('page', params.page.toString())
    if (params.page_size) queryParams.append('page_size', params.page_size.toString())
    if (params.start_date) queryParams.append('start_date', params.start_date)
    if (params.end_date) queryParams.append('end_date', params.end_date)
    if (params.action_type) queryParams.append('action_type', params.action_type)
    if (params.success !== undefined) queryParams.append('success', params.success.toString())
    if (params.keyword) queryParams.append('keyword', params.keyword)
    
    const url = `/api/system/logs/list${queryParams.toString() ? '?' + queryParams.toString() : ''}`
    return ApiClient.get(url)
  }

  /**
   * Get operation log statistics
   */
  static getOperationLogStats(days: number = 30): Promise<OperationLogStatsResponse> {
    return ApiClient.get(`/api/system/logs/stats?days=${days}`)
  }

  /**
   * Get operation log details
   */
  static getOperationLogDetail(logId: string): Promise<{
    success: boolean
    data: OperationLog
    message: string
  }> {
    return ApiClient.get(`/api/system/logs/${logId}`)
  }

  /**
   * Create operation log
   */
  static createOperationLog(data: CreateOperationLogRequest): Promise<{
    success: boolean
    data: { log_id: string }
    message: string
  }> {
    return ApiClient.post('/api/system/logs/create', data)
  }

  /**
   * Clear operation log
   */
  static clearOperationLogs(data: ClearLogsRequest = {}): Promise<ClearLogsResponse> {
    return ApiClient.post('/api/system/logs/clear', data)
  }

  /**
   * The export operation log is CSV
   */
  static exportOperationLogsCSV(params: {
    start_date?: string
    end_date?: string
    action_type?: string
  } = {}): Promise<Blob> {
    const queryParams = new URLSearchParams()
    
    if (params.start_date) queryParams.append('start_date', params.start_date)
    if (params.end_date) queryParams.append('end_date', params.end_date)
    if (params.action_type) queryParams.append('action_type', params.action_type)
    
    const url = `/api/system/logs/export/csv${queryParams.toString() ? '?' + queryParams.toString() : ''}`
    return ApiClient.get(url, { responseType: 'blob' }) as any
  }
}

// Operation type constant
export const ActionTypes = {
  STOCK_ANALYSIS: 'stock_analysis',
  CONFIG_MANAGEMENT: 'config_management',
  CACHE_OPERATION: 'cache_operation',
  DATA_IMPORT: 'data_import',
  DATA_EXPORT: 'data_export',
  SYSTEM_SETTINGS: 'system_settings',
  USER_LOGIN: 'user_login',
  USER_LOGOUT: 'user_logout',
  USER_MANAGEMENT: 'user_management',  // 🔧 Add user management operation type
  DATABASE_OPERATION: 'database_operation',
  SCREENING: 'screening',
  REPORT_GENERATION: 'report_generation'
} as const

// Operation type name mapping
export const ActionTypeNames = {
  [ActionTypes.STOCK_ANALYSIS]: 'stock analysis',
  [ActionTypes.CONFIG_MANAGEMENT]: 'Configuration management',
  [ActionTypes.CACHE_OPERATION]: 'Caching operations',
  [ActionTypes.DATA_IMPORT]: 'Data import',
  [ActionTypes.DATA_EXPORT]: 'Data export',
  [ActionTypes.SYSTEM_SETTINGS]: 'System settings',
  [ActionTypes.USER_LOGIN]: 'User login',
  [ActionTypes.USER_LOGOUT]: 'User logout',
  [ActionTypes.USER_MANAGEMENT]: 'User management',  // 🔧 Add user management operation type name
  [ActionTypes.DATABASE_OPERATION]: 'Database operations',
  [ActionTypes.SCREENING]: 'stock screen',
  [ActionTypes.REPORT_GENERATION]: 'Report generation'
} as const

// Operation type label color mapping
export const ActionTypeTagColors = {
  [ActionTypes.STOCK_ANALYSIS]: 'primary',
  [ActionTypes.CONFIG_MANAGEMENT]: 'success',
  [ActionTypes.CACHE_OPERATION]: 'warning',
  [ActionTypes.DATA_IMPORT]: 'info',
  [ActionTypes.DATA_EXPORT]: 'info',
  [ActionTypes.SYSTEM_SETTINGS]: 'danger',
  [ActionTypes.USER_LOGIN]: 'success',
  [ActionTypes.USER_LOGOUT]: 'warning',
  [ActionTypes.USER_MANAGEMENT]: 'warning',  // 🔧 Add user management operation type color
  [ActionTypes.DATABASE_OPERATION]: 'primary',
  [ActionTypes.SCREENING]: 'info',
  [ActionTypes.REPORT_GENERATION]: 'primary'
} as const

// Convenience function
export const getActionTypeName = (actionType: string): string => {
  return ActionTypeNames[actionType as keyof typeof ActionTypeNames] || actionType
}

export const getActionTypeTagColor = (actionType: string): string => {
  return ActionTypeTagColors[actionType as keyof typeof ActionTypeTagColors] || 'info'
}

// Format time (import unified time formatting tool)


export const formatDateTime = (timestamp: string | number): string => {
  return formatDateTimeUtil(timestamp)
}

// Default export
export default OperationLogsApi

// ============================================================================
// Module: notifications.ts
// ============================================================================

export interface NotificationItem {
  id: string
  title: string
  content?: string
  type: 'analysis' | 'alert' | 'system'
  status: 'unread' | 'read'
  created_at: string
  link?: string
  source?: string
}

export interface NotificationListResponse {
  items: NotificationItem[]
  total?: number
  page?: number
  page_size?: number
}

export const notificationsApi = {
  async getUnreadCount(): Promise<{ success: boolean; data: { count: number } }> {
    // When the backend is not yet provided, the bottom line is 0
    try {
      return await request.get('/api/notifications/unread_count')
    } catch {
      return { success: true, data: { count: 0 } }
    }
  },

  async getList(params?: { status?: 'unread' | 'all'; page?: number; page_size?: number; type?: string }): Promise<{ success: boolean; data: NotificationListResponse }> {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.page) query.set('page', String(params.page))
    if (params?.page_size) query.set('page_size', String(params.page_size))
    if (params?.type) query.set('type', params.type)
    const url = query.toString() ? `/api/notifications?${query.toString()}` : '/api/notifications'
    try {
      return await request.get(url)
    } catch {
      return { success: true, data: { items: [], total: 0, page: params?.page ?? 1, page_size: params?.page_size ?? 20 } }
    }
  },

  async markRead(id: string): Promise<{ success: boolean }> {
    try {
      return await request.post(`/api/notifications/${id}/read`)
    } catch {
      return { success: true }
    }
  },

  async markAllRead(): Promise<{ success: boolean }> {
    try {
      return await request.post('/api/notifications/read_all')
    } catch {
      return { success: true }
    }
  }
}

// ============================================================================
// Module: scheduler.ts
// ============================================================================

/**
 * Related to scheduled tasks API
 */


// Pending execution records
export interface SuspendedExecution {
  execution_id: string
  progress: number
  processed_items?: number
  total_items?: number
  current_item?: string
  started_at?: string
  message?: string
}

export interface RunningExecution {
  execution_id: string
  progress: number
  processed_items?: number
  total_items?: number
  current_item?: string
  started_at?: string
  updated_at?: string
  message?: string
}

// Task status
export interface JobStatus {
  id: string  // The backend returns the id, not job_id
  name: string
  paused: boolean  // The backend returns paused, not enabled
  next_run_time?: string
  last_run_time?: string
  trigger?: string
  func?: string
  kwargs?: Record<string, unknown>
  display_name?: string
  description?: string
  has_suspended_execution?: boolean  // Is there any pending execution record?
  suspended_execution?: SuspendedExecution  // Pending execution record details
  has_running_execution?: boolean
  running_execution?: RunningExecution
}

// Task progress
export interface JobProgress {
  job_id: string
  execution_id?: string  // 🔥 Execution record ID, used to terminate the operation
  progress: number
  status: 'running' | 'cancelling' | 'suspended' | 'success' | 'failed' | 'cancelled' | 'unknown'
  message?: string
  current_item?: string
  total_items?: number
  processed_items?: number
  started_at?: string  // start time
  updated_at?: string   // Update time
}

export interface JobHistory {
  [key: string]: any
}

export interface JobExecution {
  [key: string]: any
}

export interface SchedulerStats {
  total_jobs: number
  running_jobs: number
  paused_jobs: number
  [key: string]: any
}

export type Job = JobStatus

// API response format
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data: T
}

/**
 * Get a list of all scheduled tasks
 */
export const getJobs = (): Promise<ApiResponse<JobStatus[]>> => {
  return ApiClient.get('/api/scheduler/jobs')
}

/**
 * Get task details
 */
export const getJobDetail = (jobId: string): Promise<ApiResponse<JobStatus>> => {
  return ApiClient.get(`/api/scheduler/jobs/${jobId}`)
}

/**
 * Get real-time progress of tasks
 */
export const getJobProgress = (jobId: string): Promise<ApiResponse<JobProgress>> => {
  return ApiClient.get(`/api/scheduler/jobs/${jobId}/progress`)
}

/**
 * Manually trigger tasks
 */
export const triggerJob = (jobId: string, options?: {
  force?: boolean
  incremental?: boolean  // Whether to incrementally synchronize (only historical data synchronization tasks are valid)
}): Promise<ApiResponse<void>> => {
  const params = new URLSearchParams()
  if (options?.force) {
    params.append('force', 'true')
  }
  if (options?.incremental !== undefined) {
    params.append('incremental', options.incremental ? 'true' : 'false')
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/trigger${queryString ? '?' + queryString : ''}`)
}

/**
 * Pause task
 */
export const pauseJob = (jobId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/pause`)
}

/**
 * recovery task
 */
export const resumeJob = (jobId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/resume`)
}

/**
 * Resumes suspended task execution (continues where it left off)
 */
export const resumeSuspendedExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/resume`)
}

/**
 * Cancel the pending task execution record (used when the user chooses to restart)
 */
export const cancelSuspendedExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/cancel`)
}

/**
 * Get scheduler statistics
 */
export const getSchedulerStats = (): Promise<ApiResponse<any>> => {
  return ApiClient.get('/api/scheduler/stats')
}

/**
 * Update task metadata (display name and description)
 */
export const updateJobMetadata = (
  jobId: string,
  metadata: {
    display_name?: string
    description?: string
  }
): Promise<ApiResponse<void>> => {
  return ApiClient.put(`/api/scheduler/jobs/${jobId}/metadata`, metadata)
}

/**
 * Rescheduling tasks (modifying CRON expression)
 */
export const rescheduleJob = (
  jobId: string,
  cron: string
): Promise<ApiResponse<void>> => {
  return ApiClient.put(`/api/scheduler/jobs/${jobId}/schedule`, { cron })
}

/**
 * Get task execution history (all tasks)
 */
export const getJobExecutions = (params?: {
  job_id?: string
  status?: string
  is_manual?: boolean
  limit?: number
  offset?: number
}): Promise<ApiResponse<{
  items: any[]
  total: number
  limit: number
  offset: number
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.job_id) queryParams.append('job_id', params.job_id)
  if (params?.status) queryParams.append('status', params.status)
  if (params?.is_manual !== undefined) queryParams.append('is_manual', String(params.is_manual))
  if (params?.limit) queryParams.append('limit', String(params.limit))
  if (params?.offset) queryParams.append('offset', String(params.offset))
  
  const queryString = queryParams.toString()
  return ApiClient.get(`/api/scheduler/executions${queryString ? '?' + queryString : ''}`)
}

/**
 * Get the execution history of a specified task
 */
export const getSingleJobExecutions = (
  jobId: string,
  params?: {
    status?: string
    is_manual?: boolean
    limit?: number
    offset?: number
  }
): Promise<ApiResponse<{
  items: any[]
  total: number
  limit: number
  offset: number
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.status) queryParams.append('status', params.status)
  if (params?.is_manual !== undefined) queryParams.append('is_manual', String(params.is_manual))
  if (params?.limit) queryParams.append('limit', String(params.limit))
  if (params?.offset) queryParams.append('offset', String(params.offset))
  
  const queryString = queryParams.toString()
  return ApiClient.get(`/api/scheduler/jobs/${jobId}/executions${queryString ? '?' + queryString : ''}`)
}

/**
 * Cancel execution logging (general, including pending executions)
 */
export const cancelExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/cancel`)
}

/**
 * Mark execution record as failed
 */
export const markExecutionFailed = (
  executionId: string,
  reason?: string
): Promise<ApiResponse<void>> => {
  const params = new URLSearchParams()
  if (reason) {
    params.append('reason', reason)
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/executions/${executionId}/mark-failed${queryString ? '?' + queryString : ''}`)
}

/**
 * Delete execution record
 */
export const deleteExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.delete(`/api/scheduler/executions/${executionId}`)
}

/**
 * Retry failed stocks (retry only retryable errors, skip errors with no data)
 * Suitable for historical data synchronization tasks (Tushare/AKShare)
 */
export const retryFailedSymbols = (
  executionId: string,
  options?: {
    start_date?: string  // Start date (optional, the date of the original task is used by default)
    end_date?: string     // End date (optional, the date of the original task is used by default)
    period?: 'daily' | 'weekly' | 'monthly'  // Data period, default daily
  }
): Promise<ApiResponse<{
  total_retried: number      // Total number of stocks to retry
  success_count: number      // Number of successes
  error_count: number        // Number of failures
  no_data_count: number     // No data count (skipped)
  retryable_errors_count: number  // Number of retryable errors
}>> => {
  const params = new URLSearchParams()
  if (options?.start_date) {
    params.append('start_date', options.start_date)
  }
  if (options?.end_date) {
    params.append('end_date', options.end_date)
  }
  if (options?.period) {
    params.append('period', options.period)
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/executions/${executionId}/retry-failed${queryString ? '?' + queryString : ''}`)
}

// ============================================================================
// Module: unifiedTasks.ts
// ============================================================================

/**
 * unified mission center API
 *
 * docking backend /api/v2/tasks/* endpoint
 * Supports all types of analysis tasks (stock analysis, position analysis, transaction review, etc.)
 */



export type TaskTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

// ==================== type definition ====================

/**
 * Task type enum
 */
export enum TaskType {
  STOCK_ANALYSIS = 'stock_analysis',
  ETF_ANALYSIS = 'etf_analysis',
  POSITION_ANALYSIS = 'position_analysis',
  TRADE_REVIEW = 'trade_review',
  PORTFOLIO_HEALTH = 'portfolio_health',
  RISK_ASSESSMENT = 'risk_assessment',
  MARKET_OVERVIEW = 'market_overview',
  SECTOR_ANALYSIS = 'sector_analysis'
}

/**
 * Task status enum
 */
export enum TaskStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  SUSPENDED = 'suspended'  // Pending status (unfinished tasks after service restart)
}

/**
 * task list item
 */
export interface TaskListItem {
  task_id: string
  task_type: TaskType
  status: TaskStatus
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  
  // Task parameters (for display)
  symbol?: string
  code?: string
  market?: string
}

/**
 * Mission details
 */
export interface TaskDetail {
  task_id: string
  user_id: string
  task_type: TaskType
  task_params: Record<string, any>
  workflow_id?: string
  engine_type: string
  preference_type: string
  status: TaskStatus
  progress: number
  current_step?: string
  result?: Record<string, any>
  created_at: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  retry_count: number
  max_retries: number
  tokens_used: number
  cost: number
  growth_context?: {
    memory_items_count: number
    suggestions_count: number
    memory_item_ids: string[]
    suggestion_ids: string[]
    extracted_at: string
    source_type: string
    source_id?: string
  } | null
}

/**
 * Task statistics
 */
export interface TaskStatistics {
  total: number
  pending: number
  processing: number
  completed: number
  failed: number
  cancelled: number
}

/**
 * Task list query parameters
 */
export interface TaskListParams {
  task_type?: TaskType
  status?: TaskStatus
  symbol?: string
  limit?: number
  skip?: number
}

// ==================== API method ====================

/**
 * Get task list
 */
export function getTaskList(params?: TaskListParams) {
  return ApiClient.get<{
    tasks: TaskListItem[]
    total: number
    limit: number
    skip: number
  }>('/api/v2/tasks/list', params)
}

/**
 * Get task statistics
 */
export function getTaskStatistics() {
  return ApiClient.get<TaskStatistics>('/api/v2/tasks/statistics')
}

/**
 * Get task details
 */
export function getTaskDetail(taskId: string) {
  return ApiClient.get<TaskDetail>(`/api/v2/tasks/${taskId}`)
}

/**
 * Cancel task
 */
export function cancelTask(taskId: string) {
  return ApiClient.delete<{ success: boolean; message: string }>(`/api/v2/tasks/${taskId}`)
}

/**
 * Resume a suspended task
 */
export function resumeTask(taskId: string) {
  return ApiClient.post<{ success: boolean; message: string }>(`/api/v2/tasks/${taskId}/resume`)
}

/**
 * Task type Chinese name mapping
 */
export const TaskTypeNames: Record<TaskType, string> = {
  [TaskType.STOCK_ANALYSIS]: 'stock analysis',
  [TaskType.ETF_ANALYSIS]: 'ETF analysis',
  [TaskType.POSITION_ANALYSIS]: 'Position analysis',
  [TaskType.TRADE_REVIEW]: 'Transaction review',
  [TaskType.PORTFOLIO_HEALTH]: 'Combination health',
  [TaskType.RISK_ASSESSMENT]: 'risk assessment',
  [TaskType.MARKET_OVERVIEW]: 'Market overview',
  [TaskType.SECTOR_ANALYSIS]: 'Sector analysis'
}

/**
 * Task status Chinese name mapping
 */
export const TaskStatusNames: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: 'Waiting',
  [TaskStatus.PROCESSING]: 'In progress',
  [TaskStatus.COMPLETED]: 'Completed',
  [TaskStatus.FAILED]: 'failed',
  [TaskStatus.CANCELLED]: 'Canceled',
  [TaskStatus.SUSPENDED]: 'Pending'
}

/**
 * Task status color mapping
 */
export const TaskStatusColors: Record<TaskStatus, TaskTagType> = {
  [TaskStatus.PENDING]: 'info',
  [TaskStatus.PROCESSING]: 'warning',
  [TaskStatus.COMPLETED]: 'success',
  [TaskStatus.FAILED]: 'danger',
  [TaskStatus.CANCELLED]: 'info',
  [TaskStatus.SUSPENDED]: 'warning'
}


// ==================== Dedicated to general research tasks API ====================

/**
 * Common research task list items
 */
export interface GeneralTaskListItem {
  task_id: string
  task_type: string
  status: string
  progress: number
  workflow_id?: string
  analysis_target: string
  research_depth?: string
  created_at?: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  current_step?: string
}

/**
 * Common research task query parameters
 */
export interface GeneralTaskListParams {
  workflow_id?: string
  date_start?: string
  date_end?: string
  keyword?: string
  status?: string
  limit?: number
  skip?: number
}

/**
 * Get a list of general research tasks
 */
export function getGeneralTaskList(params?: GeneralTaskListParams) {
  return ApiClient.get<{
    tasks: GeneralTaskListItem[]
    total: number
    limit: number
    skip: number
  }>('/api/v2/tasks/general/list', params)
}

/**
 * Get general research task statistics
 */
export function getGeneralTaskStatistics() {
  return ApiClient.get<{
    total: number
    completed: number
    failed: number
    processing: number
    pending: number
  }>('/api/v2/tasks/general/statistics')
}

/**
 * Chinese name of general research task status
 */
export const GeneralTaskStatusNames: Record<string, string> = {
  pending: 'Waiting',
  processing: 'In progress',
  completed: 'Completed',
  failed: 'failed',
  cancelled: 'Canceled',
  suspended: 'Pending'
}

/**
 * Common research task status colors
 */
export const GeneralTaskStatusColors: Record<string, TaskTagType> = {
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
  cancelled: 'info',
  suspended: 'warning'
}

// ============================================================================
// Module: update.ts
// ============================================================================

/**
 * System update API
 */


/** Build information */
export interface BuildInfo {
  build_type?: string
  version?: string
  build_date?: string
  git_commit?: string
  full_version?: string
}

/** Version information */
export interface VersionInfo {
  current_version: string
  build_info: BuildInfo
  update_channel?: string
  /** Docker environment */
  is_docker?: boolean
  /** Whether to support in-app updates (Windows portable version/installation version) */
  supports_in_app_update?: boolean
}

/** Update information */
export interface UpdateInfo {
  has_update: boolean
  latest_version: string
  package_type?: 'installer' | 'update'
  download_url: string
  file_size: number
  sha256: string
  release_notes: string
  release_date: string
  is_mandatory: boolean
  min_version: string
  /** The check failed (for example, the server cannot be connected) */
  check_failed?: boolean
  /** Error message */
  error_message?: string
}

/** Download progress */
export interface DownloadProgress {
  status: string       // idle | downloading | completed | failed | verify_failed
  version?: string
  total?: number
  downloaded?: number
  percent?: number
}

/** Get current version information */
export function getVersionInfo() {
  return request<VersionInfo>({
    url: '/api/system/update/info',
    method: 'get'
  })
}

/** Check for updates */
export function checkUpdate() {
  return request<UpdateInfo>({
    url: '/api/system/update/check',
    method: 'get'
  })
}

/** Get download progress */
export function getDownloadProgress() {
  return request<DownloadProgress>({
    url: '/api/system/update/progress',
    method: 'get'
  })
}

/** Start downloading update package */
export function downloadUpdate() {
  return request({
    url: '/api/system/update/download',
    method: 'post'
  })
}

/** Apply updates (service will restart) */
export function applyUpdate() {
  return request({
    url: '/api/system/update/apply',
    method: 'post'
  })
}

// ============================================================================
// Module: usage.ts
// ============================================================================

/**
 * usage statistics API
 */




export interface UsageRecord {
  id?: string
  timestamp: string
  provider: string
  model_name: string
  input_tokens: number
  output_tokens: number
  cost: number
  currency?: string
  session_id: string
  analysis_type: string
}

export interface UsageStatistics {
  total_requests: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost: number
  cost_by_currency: Record<string, number>
  by_provider: Record<string, any>
  by_model: Record<string, any>
  by_date: Record<string, any>
}

/**
 * Get usage records
 */
export function getUsageRecords(params?: {
  provider?: string
  model_name?: string
  start_date?: string
  end_date?: string
  limit?: number
}): Promise<ApiResponse<{ records: UsageRecord[]; total: number }>> {
  return ApiClient.get<{ records: UsageRecord[]; total: number }>(
    '/api/usage/records',
    params
  )
}

/**
 * Get usage statistics
 */
export function getUsageStatistics(params?: {
  days?: number
  provider?: string
  model_name?: string
}): Promise<ApiResponse<UsageStatistics>> {
  return ApiClient.get<UsageStatistics>(
    '/api/usage/statistics',
    params
  )
}

/**
 * Cost statistics by supplier
 */
export function getCostByProvider(days: number = 7) {
  return request({
    url: '/api/usage/cost/by-provider',
    method: 'get',
    params: { days }
  })
}

/**
 * Cost statistics by model
 */
export function getCostByModel(days: number = 7) {
  return request({
    url: '/api/usage/cost/by-model',
    method: 'get',
    params: { days }
  })
}

/**
 * Daily cost statistics
 */
export function getDailyCost(days: number = 7) {
  return request({
    url: '/api/usage/cost/daily',
    method: 'get',
    params: { days }
  })
}

/**
 * Delete old records
 */
export function deleteOldRecords(days: number = 90) {
  return request({
    url: '/api/usage/records/old',
    method: 'delete',
    params: { days }
  })
}
