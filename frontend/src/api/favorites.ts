import { ApiClient } from './request'

export interface FavoriteItem {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name: string
  market: string
  board?: string
  exchange?: string
  added_at?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
  current_price?: number | null
  change_percent?: number | null
  volume?: number | null
}

export interface AddFavoriteReq {
  symbol?: string  // Main field: 6-digit stock code
  stock_code?: string  // Compatible fields (deprecated)
  stock_name: string
  market?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
}

export type FavoritesSyncTaskState = 'pending' | 'running' | 'success' | 'success_with_errors' | 'failed'

export interface FavoritesRealtimeSyncTaskSubmission {
  task_id: string
  task_type: 'favorites_realtime'
  status: FavoritesSyncTaskState
  message?: string | null
  created_at: string
}

export interface FavoritesRealtimeSyncTaskStatus extends FavoritesRealtimeSyncTaskSubmission {
  started_at?: string | null
  finished_at?: string | null
  result?: {
    total: number
    success_count: number
    failed_count: number
    symbols: string[]
    data_source: string
    message: string
  } | null
  error?: string | null
}

export const favoritesApi = {
  /**
   * Get list of favorites
   */
  list: () => ApiClient.get<FavoriteItem[]>('/api/favorites'),

  /**
   * Add to favorites
   * @param payload Collection information (need to include symbol or stock_code)
   */
  add: (payload: AddFavoriteReq) => ApiClient.post<{ message: string; symbol?: string; stock_code?: string }>('/api/favorites', payload),

  /**
   * Update collection
   * @param symbol Stock code (6 digits)
   * @param payload Update content
   */
  update: (symbol: string, payload: Partial<Pick<FavoriteItem, 'tags' | 'notes' | 'alert_price_high' | 'alert_price_low'>>) =>
    ApiClient.put<{ message: string; symbol?: string; stock_code?: string }>(`/api/favorites/${symbol}`, payload),

  /**
   * Delete favorite
   * @param symbol Stock code (6 digits)
   */
  remove: (symbol: string) => ApiClient.delete<{ message: string; symbol?: string; stock_code?: string }>(`/api/favorites/${symbol}`),

  /**
   * Check if it has been collected
   * @param symbol Stock code (6 digits)
   */
  check: (symbol: string) => ApiClient.get<{ symbol?: string; stock_code?: string; is_favorite: boolean }>(`/api/favorites/check/${symbol}`),

  /**
   * Get all tags
   */
  tags: () => ApiClient.get<string[]>('/api/favorites/tags'),

  /**
   * Synchronize real-time quotes of stock watchlists
   * @param data_source Data source (tushare/akshare)
   */
  syncRealtime: (data_source: string = 'tushare') =>
    ApiClient.post<FavoritesRealtimeSyncTaskSubmission>('/api/favorites/sync-realtime', { data_source }, {
      timeout: 15000
    }),

  getRealtimeSyncTaskStatus: (taskId: string) =>
    ApiClient.get<FavoritesRealtimeSyncTaskStatus>(`/api/favorites/sync-realtime/tasks/${taskId}`)
}

