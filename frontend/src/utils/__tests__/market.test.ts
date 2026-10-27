import { describe, it, expect } from 'vitest'
import { getMarketByStockCode } from '../market'

describe('getMarketByStockCode', () => {
  describe('A Stock identification', () => {
    it('The 6-digit number should be recognized as A shares', () => {
      expect(getMarketByStockCode('000001')).toBe('A shares')
      expect(getMarketByStockCode('600519')).toBe('A shares')
      expect(getMarketByStockCode('300750')).toBe('A shares')
      expect(getMarketByStockCode('688981')).toBe('A shares')
    })
  })

  describe('boundary case', () => {
    it('should handle empty strings', () => {
      expect(getMarketByStockCode('')).toBe('A shares') // Return to A shares by default
    })
  })
})

