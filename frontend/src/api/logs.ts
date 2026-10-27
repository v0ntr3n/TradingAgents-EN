/**
 * Log management API
 */

import { ApiClient } from './request'

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

