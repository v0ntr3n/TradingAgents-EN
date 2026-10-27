/**
 * Stock symbol field compatibility tool function
 * 
 * Used to deal with compatibility issues in the front-end and back-end field standardization process
 */

/**
 * Get the stock code from the object (compatible with old and new fields)
 * @param obj Object containing a stock symbol
 * @returns Stock code (6 digits)
 */
export function getStockSymbol(obj: any): string {
  return obj?.symbol || obj?.stock_code || obj?.code || ''
}

/**
 * Get the full stock code (e.g. 000001.SZ) from the object
 * @param obj Object containing a stock symbol
 * @returns Full ticker
 */
export function getFullSymbol(obj: any): string {
  return obj?.full_symbol || obj?.symbol || obj?.stock_code || obj?.code || ''
}

/**
 * Create a ticker object containing compatible fields
 * @param symbol 6 stock code
 * @param fullSymbol Full code (optional)
 * @returns Object containing old and new fields
 */
export function createSymbolObject(symbol: string, fullSymbol?: string) {
  return {
    symbol,
    stock_code: symbol,  // Compatible fields
    code: symbol,        // Compatible fields
    ...(fullSymbol && { full_symbol: fullSymbol })
  }
}

/**
 * Standardized stock code list (duplication removal, compatibility with old and new fields)
 * @param symbols List of stock symbols (may contain old and new fields)
 * @returns Standardized code list
 */
export function normalizeSymbols(symbols: (string | { symbol?: string; stock_code?: string; code?: string })[]): string[] {
  const result = new Set<string>()
  
  for (const item of symbols) {
    if (typeof item === 'string') {
      if (item) result.add(item)
    } else if (item && typeof item === 'object') {
      const symbol = getStockSymbol(item)
      if (symbol) result.add(symbol)
    }
  }
  
  return Array.from(result)
}

/**
 * Validate ticker format
 * @param symbol Stock code
 * @param market Market type (optional)
 * @returns Is it valid?
 */
export function validateSymbol(symbol: string, market?: string): boolean {
  if (!symbol) return false
  
  const trimmed = symbol.trim()
  
  if (market === 'A shares' || market === 'CN') {
    // A Share: 6 digits
    return /^\d{6}$/.test(trimmed)
  }
  
  // When no market is specified, universal validation is attempted
  return /^\d{6}$/.test(trimmed) // A shares
}

/**
 * Formatting stock symbol display
 * @param symbol Stock code
 * @param market Market type (optional)
 * @returns Formatted code
 */
export function formatSymbol(symbol: string, _market?: string): string {
  if (!symbol) return ''
  
  return symbol.trim()
}

/**
 * Extract 6-digit code from complete code
 * @param fullSymbol Complete code (such as 000001.SZ)
 * @returns 6 bit code
 */
export function extractSymbol(fullSymbol: string): string {
  if (!fullSymbol) return ''
  
  // Remove market suffix (.SZ, .SH, .BJ, .HK etc.)
  return fullSymbol.split('.')[0]
}

/**
 * Infer market code from 6-digit code
 * @param symbol 6 stock code
 * @returns Market code (SZ/SH/BJ) or null
 */
export function inferMarketCode(symbol: string): string | null {
  if (!symbol || !/^\d{6}$/.test(symbol)) return null
  
  const code = symbol.substring(0, 3)
  
  // Shenzhen market
  if (['000', '001', '002', '003', '300', '301'].includes(code)) {
    return 'SZ'
  }
  
  // Shanghai market
  if (['600', '601', '603', '605', '688', '689'].includes(code)) {
    return 'SH'
  }
  
  // beijing market
  if (['430', '830', '870'].includes(code)) {
    return 'BJ'
  }
  
  return null
}

/**
 * Build a complete ticker
 * @param symbol 6 stock code
 * @param marketCode Market code (optional, automatically inferred if not provided)
 * @returns Complete code (such as 000001.SZ)
 */
export function buildFullSymbol(symbol: string, marketCode?: string): string {
  if (!symbol) return ''
  
  const market = marketCode || inferMarketCode(symbol)
  
  if (market) {
    return `${symbol}.${market}`
  }
  
  return symbol
}

/**
 * Batch convert ticker fields in objects
 * @param obj Object containing a stock symbol
 * @returns Converted object (contains old and new fields)
 */
export function normalizeStockObject<T extends Record<string, any>>(obj: T): T {
  if (!obj) return obj
  
  const symbol = getStockSymbol(obj)
  
  if (symbol) {
    return {
      ...obj,
      symbol,
      stock_code: symbol,  // Compatible fields
      code: symbol         // Compatible fields
    }
  }
  
  return obj
}

/**
 * Batch convert stock code fields in object array
 * @param arr object array
 * @returns converted array
 */
export function normalizeStockArray<T extends Record<string, any>>(arr: T[]): T[] {
  if (!Array.isArray(arr)) return arr
  
  return arr.map(item => normalizeStockObject(item))
}

