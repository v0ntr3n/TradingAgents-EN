/**
 * Operation log API interface
 */

import { ApiClient } from './request'

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
import { formatDateTime as formatDateTimeUtil } from '@/utils/datetime'

export const formatDateTime = (timestamp: string | number): string => {
  return formatDateTimeUtil(timestamp)
}

// Default export
export default OperationLogsApi
