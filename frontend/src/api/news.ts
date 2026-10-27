import { ApiClient } from './request'

/**
 * News data interface
 */
export interface NewsItem {
  id?: string
  title: string
  content?: string
  summary?: string
  source?: string
  publish_time: string
  url?: string
  symbol?: string
  category?: string
  sentiment?: string
  importance?: number
  data_source?: string
}

/**
 * Latest news response
 */
export interface LatestNewsResponse {
  symbol?: string
  limit: number
  hours_back: number
  total_count: number
  news: NewsItem[]
}

/**
 * News query response
 */
export interface NewsQueryResponse {
  symbol: string
  hours_back: number
  total_count: number
  news: NewsItem[]
}

/**
 * News synchronization response
 */
export interface NewsSyncResponse {
  sync_type: string
  symbol?: string
  data_sources?: string[]
  hours_back: number
  max_news_per_source: number
}

/**
 * News API
 */
export const newsApi = {
  /**
   * Get the latest news
   * @param symbol Stock code, if empty, get market news
   * @param limit Return quantity limit
   * @param hours_back Lookback hours
   */
  async getLatestNews(symbol?: string, limit: number = 10, hours_back: number = 24) {
    const params: any = { limit, hours_back }
    if (symbol) {
      params.symbol = symbol
    }
    return ApiClient.get<LatestNewsResponse>('/api/news-data/latest', params)
  },

  /**
   * Check stock news
   * @param symbol Stock code
   * @param hours_back Lookback hours
   * @param limit Return quantity limit
   */
  async queryStockNews(symbol: string, hours_back: number = 24, limit: number = 20) {
    return ApiClient.get<NewsQueryResponse>(`/api/news-data/query/${symbol}`, {
      hours_back,
      limit
    })
  },

  /**
   * Synchronize market news (background task)
   * @param hours_back Lookback hours
   * @param max_news_per_source Maximum number of news per data source
   */
  async syncMarketNews(hours_back: number = 24, max_news_per_source: number = 50) {
    return ApiClient.post<NewsSyncResponse>('/api/news-data/sync/start', {
      symbol: null,
      data_sources: null,
      hours_back,
      max_news_per_source
    })
  }
}

