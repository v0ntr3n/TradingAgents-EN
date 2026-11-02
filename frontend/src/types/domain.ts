/**
 * Strict domain TypeScript interfaces for TradingAgents-EN (CARE-Agents).
 */

export type MarketRegimeLabel = 'bull' | 'bear' | 'sideways' | 'volatile'

export interface PosteriorDistribution {
  p_optimistic: number
  p_neutral: number
  p_cautious: number
  expected_move_bps: number
}

export interface AnalysisTask {
  task_id: string
  symbol: string
  market_type: 'cn' | 'hk' | 'us'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  created_at: string
  completed_at?: string
  posterior?: PosteriorDistribution
  summary?: string
  recommendation?: string
  reports?: Record<string, string>
}

export interface ScreeningResult {
  symbol: string
  name: string
  market: string
  close: number
  pct_chg: number
  pe_ttm: number | null
  pb_mrq: number | null
  roe_ttm: number | null
  total_mv: number | null
}

export interface PortfolioPosition {
  id: string
  symbol: string
  name: string
  quantity: number
  avg_cost: number
  current_price: number
  cost_basis: number
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  stop_loss_price?: number | null
  take_profit_price?: number | null
}

export interface AgentTraceEvent {
  event_id: string
  timestamp: string
  agent_name: string
  stage: 'specialist' | 'cbs_gate' | 'debate' | 'mwu_update' | 'execution'
  regime_label?: MarketRegimeLabel
  js_divergence?: number
  cbs_bps?: number
  message: string
}

export interface ModelCapability {
  model_id: string
  provider: string
  tier: string
  context_window: number
  input_cost_per_1m: number
  output_cost_per_1m: number
  supports_json_schema: boolean
}
