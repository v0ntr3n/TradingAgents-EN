import type { StockInfo } from '@/types/analysis'
import type { FactorWarningPayload, WarningCategory } from '@/api/screening'
import { analysisApi } from '@/api/analysis'

// ============================================================================
// Module: factorPresentation.ts
// ============================================================================

type FactorTagType = 'warning' | 'danger' | 'info' | 'success'

interface FactorWarningEntry {
  key: string
  label: string
  tagType: FactorTagType
  conditions: string[]
}

interface FactorDiagnosticEntry {
  key: string
  label: string
  state: string
  reason: string
  missingInputs: string[]
  tagType: 'danger'
}

const warningCategoryMeta: Record<WarningCategory, { label: string; tagType: FactorTagType }> = {
  fallback_used: { label: 'Fallback calculation', tagType: 'warning' },
  proxy_used: { label: 'Proxy estimate', tagType: 'danger' },
  low_sample_size: { label: 'Too few samples', tagType: 'info' },
  precision_degraded: { label: 'Limited accuracy', tagType: 'warning' },
}

const diagnosticLabelMap: Record<string, string> = {
  piotroski_f_score: 'Financial quality score gap',
  altman_z_score: 'Financial Security Score Gap',
  beneish_m_score: 'Earnings manipulation risk gap',
}

const warningFieldLabelMap: Record<string, string> = {
  pe_ttm: 'Rolling P/E Retracement',
  pb: 'P/B retracement',
  pb_mrq: 'Latest price-to-book ratio estimates',
  ps_ttm: 'Rolling price-to-sales ratio retreat',
  dividend_yield: 'Dividend rate fallback',
  industry_pe_median: 'Industry valuation samples are too few',
  industry_pb_median: 'Industry valuation samples are too few',
  net_profit_ttm: 'Rolling net profit fallback',
  roic: 'Return on invested capital accuracy is limited',
  interest_coverage: 'Interest Coverage Ratio Rollback',
  inventory_turnover: 'Inventory turnover estimate',
  net_cash_position: 'Net Cash Position Estimate',
  fcf: 'Free Cash Flow Estimate',
}

const warningConditionDescriptionMap: Record<string, string> = {
  'pe_ttm fallback_to pe': 'The rolling price-to-earnings ratio lacks a direct value and has fallen back to using the price-to-earnings ratio caliber.',
  'pb fallback_to pb_mrq': 'The price-to-book ratio lacks a direct value and has fallen back to using the latest price-to-book ratio caliber.',
  'pb_mrq estimated_from market_cap_and_total_equity': 'The latest price-to-book ratio is estimated from total market capitalization and net assets.',
  'ps_ttm fallback_to ps': 'The rolling price-to-sales ratio lacks a direct value and has fallen back to using the price-to-sales ratio.',
  'dividend_yield fallback_to financial_field': 'The dividend rate lacks the market side field and has fallen back to using the financial field.',
  'industry_peer_sample_count < 5': 'The number of comparable samples in the industry is relatively small, and the stability of the horizontal reference is limited.',
  'net_profit_ttm fallback_to net_profit_or_net_income': 'The rolling net profit lacks a direct value and has fallen back to using the net profit caliber.',
  'roic money_cap_missing_assumed_zero': 'The monetary capital field is missing, and the return on invested capital is estimated using conservative assumptions.',
  'interest_coverage fallback_to raw_interest_expense': 'The interest expense field is incomplete and the interest coverage ratio has been rolled back to use the original interest expense.',
  'inventory_turnover cost_proxy_used': 'The operating cost field is missing, and the inventory turnover rate is estimated using a cost proxy instead.',
  'net_cash_position proxy_total_ncl_used': 'The long-term liability field is incomplete, and the net cash position is estimated using the agency approach.',
  'fcf conservative_proxy_used': 'Free cash flow is estimated using a conservative agency approach.',
}

const diagnosticStateLabelMap: Record<string, string> = {
  available: 'Available',
  missing_comparison_period: 'Missing comparison period',
  missing_required_inputs: 'Missing key input',
  invalid_denominator: 'Key denominator is invalid',
  calculation_blocked: 'Computing is protectively blocked',
  unknown: 'Status unknown',
}

export const getFactorWarningEntries = (row: StockInfo): FactorWarningEntry[] => {
  const warnings = row.factor_warnings || {}
  return Object.entries(warnings).map(([fieldName, payload]: [string, FactorWarningPayload]) => {
    const category = payload.warning_categories?.[0]
    const meta = category ? warningCategoryMeta[category] : null
    return {
      key: fieldName,
      label: warningFieldLabelMap[fieldName] || meta?.label || fieldName,
      tagType: meta?.tagType || 'info',
      conditions: (payload.warning_conditions || []).map(
        condition => warningConditionDescriptionMap[condition] || condition
      ),
    }
  })
}

export const getFactorDiagnosticEntries = (row: StockInfo): FactorDiagnosticEntry[] => {
  const diagnostics = row.factor_diagnostics || {}
  return Object.entries(diagnostics).map(([key, payload]: [string, any]) => ({
    key,
    label: diagnosticLabelMap[key] || key,
    state: diagnosticStateLabelMap[payload?.state] || payload?.state || 'Status unknown',
    reason: payload?.reason || '',
    missingInputs: payload?.missing_inputs || [],
    tagType: 'danger',
  }))
}

// ============================================================================
// Module: taskResult.ts
// ============================================================================

const META_KEYS = new Set([
  'analysis_id',
  'analysis_date',
  'created_at',
  'updated_at',
  'status',
  'source',
  'symbol',
  'stock_symbol',
  'stock_code',
  'stock_name',
  'market_type',
  'analysts',
  'research_depth',
  'execution_time',
  'tokens_used',
  'confidence_score',
  'risk_level',
  'task_id',
  'id'
])

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

const isApiEnvelope = (value: any) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return 'data' in value && ('success' in value || 'message' in value || 'code' in value || Object.keys(value).length === 1)
}

const hasNonEmptyValue = (value: any): boolean => {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.some(item => hasNonEmptyValue(item))
  if (typeof value === 'object') return Object.values(value).some(item => hasNonEmptyValue(item))
  return true
}

export const unwrapTaskResultResponse = (value: any) => {
  let current = value

  for (let depth = 0; depth < 3; depth += 1) {
    if (!isApiEnvelope(current)) {
      break
    }
    current = current.data
  }

  return current ?? null
}

export const hasTaskResultContent = (result: any) => {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return false

  const preferredKeys = [
    'summary',
    'recommendation',
    'reports',
    'decision',
    'state',
    'index_report',
    'sector_report',
    'market_report',
    'fundamentals_report',
    'final_trade_decision'
  ]

  if (preferredKeys.some(key => hasNonEmptyValue(result[key]))) {
    return true
  }

  return Object.entries(result).some(([key, value]) => !META_KEYS.has(key) && hasNonEmptyValue(value))
}

export const mergeTaskResult = (...sources: any[]) => {
  const merged: Record<string, any> = {}

  sources.forEach(source => {
    if (!source || typeof source !== 'object' || Array.isArray(source)) return

    Object.entries(source).forEach(([key, value]) => {
      if (value === undefined || value === null) return

      if (typeof value === 'string') {
        if (!merged[key] || String(merged[key]).trim().length === 0 || value.trim().length > String(merged[key]).trim().length) {
          merged[key] = value
        }
        return
      }

      if (Array.isArray(value)) {
        if (!Array.isArray(merged[key]) || merged[key].length === 0) {
          merged[key] = value
        }
        return
      }

      if (typeof value === 'object') {
        merged[key] = {
          ...(merged[key] || {}),
          ...value
        }
        return
      }

      merged[key] = value
    })
  })

  return merged
}

export const fetchTaskResultWithRetry = async (
  taskId: string,
  options?: {
    seedData?: any
    attempts?: number
    delayMs?: number
    isComplete?: (result: any) => boolean
  }
) => {
  const attempts = Math.max(1, options?.attempts ?? 4)
  const delayMs = Math.max(0, options?.delayMs ?? 800)
  const isComplete = options?.isComplete ?? hasTaskResultContent
  const seedData = unwrapTaskResultResponse(options?.seedData)

  let bestResult = mergeTaskResult(seedData)

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await analysisApi.getTaskResult(taskId)
      const apiResult = unwrapTaskResultResponse(response)
      bestResult = mergeTaskResult(bestResult, seedData, apiResult)

      if (isComplete(bestResult)) {
        return bestResult
      }
    } catch (error) {
      console.error(`Failed to obtain task results (page ${attempt + 1} times)`, error)
    }

    if (attempt < attempts - 1) {
      await delay(delayMs)
    }
  }

  return isComplete(bestResult) ? bestResult : seedData || bestResult || null
}

// ============================================================================
// Module: deliverableDownload.ts
// ============================================================================

/**
 * Deliverable file download interceptor (global)
 *
 * Background: Download link in smart assistant reply (/api/assistant/deliverables/*.xlsx) Yes
 * <a> tag, the browser navigates directly without the Authorization header (JWT is stored in localStorage, only
 * XHR/fetch will be carried), the link in the historical message will be clicked 401"Not logged in or your login has expired". 
 *
 * Solution: Document capture phase global delegation, intercept the click of this type of link, use fetch
 *  (Trigger browser download as blob after request (with JWT header).
 *   - Old links in historical messages (without signature)→ fetch bring JWT → Downloadable
 *   - New signature link (?exp=&sig=) → Follow this path and behave the same way
 *   - Not logged in/expired → Prompt user to log in again
 *
 * Global one-time binding, covering smart assistant homepage, floating assistant, stock details page, etc.
 * The position where markdown messages are rendered, and subsequent new entries do not need to be rewired.
 */

// Match the intelligent assistant deliverable download link (either relative path or absolute path)
const DELIVERABLE_HREF_PATTERN = /\/api\/assistant\/deliverables\//

/** Extract filename from Content-Disposition (supports RFC 5987 filename* with ordinary filename) */
function extractFilename(
  contentDisposition: string | null,
  fallbackHref: string
): string {
  if (contentDisposition) {
    // filename*=UTF-8''%E8%B5%9B... Priority (FastAPI uses this format for Chinese file names)
    const starMatch = contentDisposition.match(/filename\*=(?:UTF-8''|utf-8'')([^;]+)/i)
    if (starMatch) {
      try {
        return decodeURIComponent(starMatch[1].replace(/["']/g, '').trim())
      } catch {
        /* fallthrough */
      }
    }
    const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
    if (plainMatch) {
      try {
        return decodeURIComponent(plainMatch[1].trim())
      } catch {
        return plainMatch[1].trim()
      }
    }
  }
  // fallback: URL path final section
  try {
    const path = fallbackHref.split('?')[0]
    return decodeURIComponent(path.substring(path.lastIndexOf('/') + 1)) || 'download.xlsx'
  } catch {
    return 'download.xlsx'
  }
}

async function downloadDeliverable(href: string): Promise<void> {
  // Dynamic introduction avoids the hard dependence of the utils layer on pinia (the request.ts system is responsible for token expiration refresh,
  // Here, localStorage is read directly, keeping the same value chain as request.ts)
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()
  const token = authStore.token || localStorage.getItem('auth-token')

  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  try {
    const resp = await fetch(href, { headers, credentials: 'include' })

    if (resp.status === 401) {
      const { ElMessage } = await import('element-plus')
      ElMessage.error('Login has expired, please log in again and click download again')
      return
    }
    if (!resp.ok) {
      const { ElMessage } = await import('element-plus')
      ElMessage.error(`Download failed (HTTP ${resp.status}) , Please re-export and try again`)
      return
    }

    const blob = await resp.blob()
    const filename = extractFilename(resp.headers.get('content-disposition'), href)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('[deliverableDownload] Download failed:', err)
    const { ElMessage } = await import('element-plus')
    ElMessage.error('Download failed, please check the network and try again')
  }
}

let installed = false

/** Install global deliverable download interception (idempotent, called once at the application entry) */
export function setupDeliverableDownloadInterceptor(): void {
  if (installed) return
  installed = true

  document.addEventListener(
    'click',
    (event) => {
      // Interception during the capture phase, before browser navigation
      const target = event.target as HTMLElement | null
      const anchor = target?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!anchor) return

      const href = anchor.getAttribute('href') || ''
      if (!DELIVERABLE_HREF_PATTERN.test(href)) return

      event.preventDefault()
      event.stopPropagation()
      void downloadDeliverable(href)
    },
    true
  )
}
