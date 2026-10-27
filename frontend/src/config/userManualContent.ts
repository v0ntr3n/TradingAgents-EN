/**
 * User manual content loader
 *
 * By Vite `?raw` The static import mechanism packages the Markdown manual under docs/02-user-guide/ into the front-end product.
 * Depending on whether it is currently in JD Cloud cooperation version mode, the corresponding manual content will be automatically selected.
 *
 * Documents involved:
 * - Standard version:docs/02-user-guide/user-manual-v3.0.md
 * - JD Cloud version:docs/02-user-guide/jdyun-user-manual-v3.0.md
 */

import { isJdyunMode } from '@/utils/config'

// Standard version user manual (lazy loading to avoid excessive first screen size)
const standardManualLoader = (): Promise<{ default: string }> =>
  import('../../../docs/02-user-guide/user-manual-v3.0.md?raw')

// JD Cloud cooperation version user manual (v3.0 uses the standard version manual after the merger, JD Cloud exclusive manual has been removed)
const jdyunManualLoader = (): Promise<{ default: string }> =>
  import('../../../docs/02-user-guide/user-manual-v3.0.md?raw')

/**
 * Get the user manual content in the current mode
 *
 * @returns Markdown format manual string
 */
export async function getUserManualContent(): Promise<string> {
  try {
    if (isJdyunMode()) {
      const mod = await jdyunManualLoader()
      return mod.default
    }
    const mod = await standardManualLoader()
    return mod.default
  } catch (err) {
    console.error('[userManual] Failed to load user manual:', err)
    return '# User manual failed to load\n\n Please try again later, or contact your administrator to obtain the latest version of the manual.'
  }
}

/**
 * Get the manual title in the current mode
 */
export function getUserManualTitle(): string {
  return isJdyunMode()
    ? 'TradingAgents-CN Pro JD Cloud Cooperation Edition User Manual'
    : 'TradingAgents-CN Pro v3.0 Complete user manual'
}

/**
 * Get a brief description of the manual in the current mode
 */
export function getUserManualDescription(): string {
  return isJdyunMode()
    ? 'Complete user guide for users of JD Cloud Cooperation Edition'
    : 'Complete user guide for new and advanced users'
}
