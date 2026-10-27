/**
 * Cache management API
 */
import request from '@/api/request'

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

