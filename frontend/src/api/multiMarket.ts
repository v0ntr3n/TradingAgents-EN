/**
 * multi-market stocks API
 * Supports unified query interface for A-shares
 */
import request from './request'

export interface Market {
  code: string
  name: string
  name_en: string
  currency: string
  timezone: string
  trading_hours?: string
}

export interface StockInfo {
  code: string
  name: string
  name_en?: string
  market: string
  source: string
  total_mv?: number
  pe?: number
  pb?: number
  lot_size?: number
  currency?: string
  industry?: string
  sector?: string
  list_date?: string
  updated_at?: string
}

export interface StockQuote {
  code: string
  close?: number
  pct_chg?: number
  open?: number
  high?: number
  low?: number
  volume?: number
  amount?: number
  trade_date?: string
  currency?: string
  turnover_rate?: number
  amplitude?: number
}

export interface DailyQuote {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
}

/**
 * Get a list of supported markets
 */
export function getSupportedMarkets() {
  return request<{ markets: Market[] }>({
    url: '/api/markets',
    method: 'get'
  })
}

/**
 * Search for stocks (multi-market supported)
 */
export function searchStocks(market: string, query: string, limit: number = 20) {
  return request<{ stocks: StockInfo[]; total: number }>({
    url: `/api/markets/${market}/stocks/search`,
    method: 'get',
    params: { q: query, limit }
  })
}

/**
 * Get basic stock information
 */
export function getStockInfo(market: string, code: string, source?: string) {
  return request<StockInfo>({
    url: `/api/markets/${market}/stocks/${code}/info`,
    method: 'get',
    params: source ? { source } : undefined
  })
}

/**
 * Get real-time stock quotes
 */
export function getStockQuote(market: string, code: string) {
  return request<StockQuote>({
    url: `/api/markets/${market}/stocks/${code}/quote`,
    method: 'get'
  })
}

/**
 * Get stock historical K-line data
 */
export function getStockDailyQuotes(
  market: string,
  code: string,
  startDate?: string,
  endDate?: string,
  limit: number = 100
) {
  return request<{ code: string; market: string; quotes: DailyQuote[]; total: number }>({
    url: `/api/markets/${market}/stocks/${code}/daily`,
    method: 'get',
    params: {
      start_date: startDate,
      end_date: endDate,
      limit
    }
  })
}

