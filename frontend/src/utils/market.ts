// Standardization of market parameters: V3.0 focuses on A shares, Hong Kong and US stocks have been suspended
export const normalizeMarketForAnalysis = (market: any): string => {
  const raw = String(market ?? '').trim()
  const upper = raw.toUpperCase()
  const cn = raw
  const isETF = ['ETF', 'On-exchange funds'].includes(cn) || upper === 'ETF'
  const isA = [
    'A shares', 'motherboard', 'GEM', 'Science and Technology Innovation Board', 'Small and medium board', 'Shanghai Stock Exchange', 'Shenzhen City', 'Shanghai Stock Exchange', 'Shenzhen Stock Exchange', 'Beijing Exchange'
  ].includes(cn) || ['CN', 'SH', 'SZ', 'SSE', 'SZSE'].includes(upper)
  if (isETF) return 'ETF'
  if (isA) return 'A shares'
  // By default, it is processed as A shares
  return 'A shares'
}

/**
 * Convert exchange symbol to market type
 * @param exchangeCode exchange code (e.g. "sz", "sh", "hk", "us") 
 * @returns market type ("A shares", "Hong Kong stocks", "US stocks") 
 */
export const exchangeCodeToMarket = (exchangeCode: string): string => {
  const code = String(exchangeCode ?? '').toLowerCase().trim()

  // A stock exchange code
  if (['sz', 'sh', 'bj', 'sse', 'szse', 'bse'].includes(code)) {
    return 'A shares'
  }

  // Return to A shares by default
  return 'A shares'
}

/**
 * Determine market type based on stock code
 * @param stockCode Stock code
 * @returns market type ("A shares", "Hong Kong stocks", "US stocks", "ETF") 
 */
export const getMarketByStockCode = (stockCode: string): string => {
  const code = String(stockCode ?? '').trim().toUpperCase()

  // 6 Digits: Determine ETF first, otherwise A shares
  if (/^\d{6}$/.test(code)) {
    const prefix = code.substring(0, 2)
    if (['50', '51', '52', '56', '58', '15', '16', '18'].includes(prefix)) {
      return 'ETF'
    }
    return 'A shares'
  }

  // Return to A shares by default
  return 'A shares'
}

export default {
  normalizeMarketForAnalysis,
  exchangeCodeToMarket,
  getMarketByStockCode
}

