import type { StockInfo } from '@/types/analysis'
import type { FactorWarningPayload, WarningCategory } from '@/api/screening'

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