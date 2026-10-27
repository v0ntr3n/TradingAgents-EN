/**
 * Database management API
 */

import { ApiClient } from './request'

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
