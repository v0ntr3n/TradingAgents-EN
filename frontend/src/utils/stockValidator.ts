/**
 * Stock code format verification tool
 * Support code format verification for A-shares and ETFs
 */

export interface StockValidationResult {
  valid: boolean
  market?: 'A shares' | 'US stocks' | 'Hong Kong stocks' | 'ETF'
  message?: string
  normalizedCode?: string
}

/**
 * A Stock code format verification
 * Format: 6 digits
 * - 60xxxx: Shanghai Main Board
 * - 68xxxx: Science and Technology Innovation Board
 * - 00xxxx: Shenzhen motherboard
 * - 30xxxx: GEM
 * - 43xxxx/83xxxx/87xxxx/89xxxx/92xxxx: Beijing Exchange (920 is the unified number section starting from October 2025)
 */
export function validateAStock(code: string): StockValidationResult {
  // Remove spaces and special characters
  const cleanCode = code.trim().replace(/[^0-9]/g, '')
  
  // Must be 6 digits
  if (!/^\d{6}$/.test(cleanCode)) {
    return {
      valid: false,
      message: 'A Stock code must be 6 digits'
    }
  }
  
  // Authentication prefix
  const prefix = cleanCode.substring(0, 2)
  const validPrefixes = ['60', '68', '00', '30', '43', '83', '87', '89', '92']
  
  if (!validPrefixes.includes(prefix)) {
    return {
      valid: false,
      message: 'A The stock code prefix is incorrect (supported: starting with 60/68/00/30/43/83/87/89/92)'
    }
  }
  
  return {
    valid: true,
    market: 'A shares',
    normalizedCode: cleanCode
  }
}

/**
 * ETF Code format verification
 * Format: 6 digits, starting with 50/51/52 (Shanghai stock market) or 15/16 (Shenzhen stock market)
 */
export function validateETF(code: string): StockValidationResult {
  const cleanCode = code.trim().replace(/[^0-9]/g, '')
  if (!/^\d{6}$/.test(cleanCode)) {
    return { valid: false, message: 'ETF Code must be 6 digits' }
  }
  const prefix = cleanCode.substring(0, 2)
  const validPrefixes = ['50', '51', '52', '15', '16']
  if (!validPrefixes.includes(prefix)) {
    return { valid: false, message: 'ETF The code prefix is incorrect (supported: starting with 50/51/52/15/16)' }
  }
  return { valid: true, market: 'ETF', normalizedCode: cleanCode }
}

/**
 * U.S. stock code format verification
 * Format: 1-5 uppercase letters
 * Example:AAPL, MSFT, GOOGL, TSLA, BRK.B
 */
export function validateUSStock(code: string): StockValidationResult {
  // Remove spaces, keep letters and periods
  const cleanCode = code.trim().toUpperCase().replace(/[^A-Z.]/g, '')
  
  // Basic format: 1-5 letters, may include a period
  if (!/^[A-Z]{1,5}(\.[A-Z])?$/.test(cleanCode)) {
    return {
      valid: false,
      message: 'The US stock code format is incorrect (1-5 letters, such as: AAPL, BRK.B)'
    }
  }
  
  // It can t all be dots
  if (cleanCode.replace(/\./g, '').length === 0) {
    return {
      valid: false,
      message: 'US stock code cannot be empty'
    }
  }
  
  return {
    valid: true,
    market: 'US stocks',
    normalizedCode: cleanCode
  }
}

/**
 * Hong Kong stock code format verification
 * Format: 5 digits (may have 0 in front)
 * Example: 00700 (Tencent), 09988 (Alibaba), 01810 (Xiaomi)
 * Also supported are formats without leading 0s: 700, 9988,1810
 */
export function validateHKStock(code: string): StockValidationResult {
  // Remove spaces and special characters
  const cleanCode = code.trim().replace(/[^0-9]/g, '')
  
  // Must be 1-5 digits
  if (!/^\d{1,5}$/.test(cleanCode)) {
    return {
      valid: false,
      message: 'Hong Kong stock code must be 1-5 digits'
    }
  }
  
  // Convert to 5-bit format (padded with leading 0s)
  const normalizedCode = cleanCode.padStart(5, '0')
  
  return {
    valid: true,
    market: 'Hong Kong stocks',
    normalizedCode: normalizedCode
  }
}

/**
 * Automatically identify and verify stock symbol formats
 * @param code Stock code
 * @param marketHint Market tip (optional), if provided the market will be verified first
 */
export function validateStockCode(
  code: string,
  marketHint?: 'A shares' | 'ETF'
): StockValidationResult {
  if (!code || !code.trim()) {
    return {
      valid: false,
      message: 'Please enter stock code'
    }
  }
  
  const trimmedCode = code.trim()
  
  // If a market tip is provided, verify that market first
  if (marketHint) {
    switch (marketHint) {
      case 'A shares':
        return validateAStock(trimmedCode)
      case 'ETF':
        return validateETF(trimmedCode)
    }
  }
  
  // Automatic recognition: first determine whether they are all numbers
  const isNumeric = /^\d+$/.test(trimmedCode.replace(/[^0-9]/g, ''))
  
  if (isNumeric) {
    const cleanCode = trimmedCode.replace(/[^0-9]/g, '')
    
    // 6 digits -> Judge ETF (50/51/52/15/16) first, otherwise A shares
    if (cleanCode.length === 6) {
      const etfResult = validateETF(cleanCode)
      if (etfResult.valid) return etfResult
      return validateAStock(cleanCode)
    }
    
    return {
      valid: false,
      message: 'The numeric code length is incorrect (A shares must be 6 digits)'
    }
  }
  
  return {
    valid: false,
    message: 'Unrecognized ticker format'
  }
}

/**
 * Get stock symbol format instructions
 */
export function getStockCodeFormatHelp(market: 'A shares' | 'US stocks' | 'Hong Kong stocks' | 'ETF'): string {
  switch (market) {
    case 'A shares':
      return '6 digits, such as: 000001 (Ping An Bank), 600519 (Kweichow Moutai)'
    case 'US stocks':
      return '1-5 letters, such as: AAPL (Apple), TSLA (Tesla)'
    case 'Hong Kong stocks':
      return '1-5 digits, such as: 700 (Tencent), 9988 (Alibaba)'
    case 'ETF':
      return '6 Digits, such as: 510050 (Shanghai 50ETF), 159919 (CSI 300ETF)'
    default:
      return ''
  }
}

/**
 * Get stock symbol examples
 */
export function getStockCodeExamples(market: 'A shares' | 'US stocks' | 'Hong Kong stocks' | 'ETF'): string[] {
  switch (market) {
    case 'A shares':
      return ['000001', '600519', '000858', '300750', '920985']
    case 'ETF':
      return ['510050', '159919', '512690', '515000']
    case 'US stocks':
      return ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    case 'Hong Kong stocks':
      return ['00700', '09988', '01810', '03690']
    default:
      return []
  }
}

/**
 * Formatting stock symbol display
 * @param code original code
 * @param market market type
 */
export function formatStockCode(code: string, market: 'A shares' | 'ETF'): string {
  const validation = validateStockCode(code, market)
  return validation.normalizedCode || code
}

