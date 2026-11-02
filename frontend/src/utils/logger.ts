/**
 * Environment-aware frontend logger (`frontend/src/utils/logger.ts`).
 * Silences debug/info logs in production builds.
 */

const isDev = typeof import.meta !== 'undefined' && Boolean((import.meta as any).env?.DEV)

export const logger = {
  debug(...args: unknown[]): void {
    if (isDev) {
      console.debug('[TradingAgents]', ...args)
    }
  },
  info(...args: unknown[]): void {
    if (isDev) {
      console.info('[TradingAgents]', ...args)
    }
  },
  warn(...args: unknown[]): void {
    console.warn('[TradingAgents]', ...args)
  },
  error(...args: unknown[]): void {
    console.error('[TradingAgents]', ...args)
  },
}

export default logger
