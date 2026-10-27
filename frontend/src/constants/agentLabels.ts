/**
 * Display label mappings for Agent types and names
 * Used in dropdowns, tables, and other UI displays
 */

/** v1.0 and below, hidden from display */
export const v1AgentTypes = [
  'analysts',
  'researchers',
  'debators',
  'managers',
  'trader',
  'reviewers',
  'position_analysis',
]

export const agentTypeMap: Record<string, string> = {
  analysts_v2: 'Independent Analysts v2.0',
  researchers_v2: 'Bullish/Cautious Evidence Researchers v2.0',
  debators_v2: 'Multi-Scenario Risk Research v2.0',
  managers_v2: 'Research/Risk Assessors v2.0',
  trader_v2: 'Research Integrator v2.0',
  reviewers_v2: 'Trade Review Analysis v2.0',
  position_analysis_v2: 'Position Analysis v2.0',
  post_processors_v2: 'Post-Processors v2.0',
  // Alias without _v2 suffix in database, unified display label
  post_processors: 'Post-Processors v2.0',
  // Agent Workshop
  universal: 'Custom Agent',
}

export const agentNameMap: Record<string, string> = {
  fundamentals_analyst_v2: 'Fundamentals Analyst v2.0',
  market_analyst_v2: 'Market Analyst v2.0',
  news_analyst_v2: 'News Analyst v2.0',
  social_analyst_v2: 'Social Media Analyst v2.0',
  sector_analyst_v2: 'Sector Analyst v2.0',
  index_analyst_v2: 'Market Index Analyst v2.0',
  bull_researcher_v2: 'Bullish Evidence Researcher v2.0',
  bear_researcher_v2: 'Cautious Evidence Researcher v2.0',
  research_manager_v2: 'Research Integrator v2.0',
  risk_manager_v2: 'Risk Assessor v2.0',
  trader_v2: 'Research Integrator v2.0',
  risky_analyst_v2: 'High-Beta Scenario Analyst v2.0',
  safe_analyst_v2: 'Defensive Scenario Analyst v2.0',
  neutral_analyst_v2: 'Baseline Scenario Analyst v2.0',
  timing_analyst_v2: 'Timing Assessor v2.0',
  position_analyst_v2: 'Position Assessor v2.0',
  emotion_analyst_v2: 'Sentiment Researcher v2.0',
  attribution_analyst_v2: 'Attribution Researcher v2.0',
  review_manager_v2: 'Review Summarizer v2.0',
  pa_technical_v2: 'Technical Researcher v2.0',
  pa_fundamental_v2: 'Fundamental Researcher v2.0',
  pa_risk_v2: 'Risk Assessor v2.0',
  pa_advisor_v2: 'Position Researcher v2.0',
  chip_distribution_analyst_v2: 'Chip Distribution Analyst v2.0',
  etf_analyst_v2: 'ETF Analyst v2.0',
  data_preparer_v2: 'Data Preparer v2.0',
  report_generator_v2: 'Report Generator v2.0',
}

export const labelAgentType = (v?: string) => (v && agentTypeMap[v]) || v || '-'
export const labelAgentName = (v?: string) => (v && agentNameMap[v]) || v || '-'

/** agent_id → agent_type, used for Prompt Design Assistant chat API */
export const agentIdToTypeMap: Record<string, string> = {
  // v2
  market_analyst_v2: 'analysts_v2',
  fundamentals_analyst_v2: 'analysts_v2',
  news_analyst_v2: 'analysts_v2',
  social_analyst_v2: 'analysts_v2',
  sector_analyst_v2: 'analysts_v2',
  index_analyst_v2: 'analysts_v2',
  etf_analyst_v2: 'analysts_v2',
  chip_distribution_analyst_v2: 'analysts_v2',
  data_preparer_v2: 'analysts_v2',
  bull_researcher_v2: 'researchers_v2',
  bear_researcher_v2: 'researchers_v2',
  research_manager_v2: 'managers_v2',
  risk_manager_v2: 'managers_v2',
  trader_v2: 'trader_v2',
  risky_analyst_v2: 'debators_v2',
  safe_analyst_v2: 'debators_v2',
  neutral_analyst_v2: 'debators_v2',
  timing_analyst_v2: 'reviewers_v2',
  position_analyst_v2: 'reviewers_v2',
  emotion_analyst_v2: 'reviewers_v2',
  attribution_analyst_v2: 'reviewers_v2',
  review_manager_v2: 'reviewers_v2',
  pa_technical_v2: 'position_analysis_v2',
  pa_fundamental_v2: 'position_analysis_v2',
  pa_risk_v2: 'position_analysis_v2',
  pa_advisor_v2: 'position_analysis_v2',
  report_generator_v2: 'post_processors_v2',
  // v1 (compatible with legacy workflows)
  market_analyst: 'analysts_v2',
  fundamentals_analyst: 'analysts_v2',
  news_analyst: 'analysts_v2',
  social_analyst: 'analysts_v2',
  sector_analyst: 'analysts_v2',
  index_analyst: 'analysts_v2',
  bull_researcher: 'researchers_v2',
  bear_researcher: 'researchers_v2',
  research_manager: 'managers_v2',
  risk_manager: 'managers_v2',
  trader: 'trader_v2',
  risky_analyst: 'debators_v2',
  safe_analyst: 'debators_v2',
  neutral_analyst: 'debators_v2',
  timing_analyst: 'reviewers_v2',
  position_analyst: 'reviewers_v2',
  emotion_analyst: 'reviewers_v2',
  attribution_analyst: 'reviewers_v2',
  review_manager: 'reviewers_v2',
  pa_technical: 'position_analysis_v2',
  pa_fundamental: 'position_analysis_v2',
  pa_risk: 'position_analysis_v2',
  pa_advisor: 'position_analysis_v2',
}

export const resolveAgentType = (agentId?: string) =>
  (agentId && agentIdToTypeMap[agentId]) || 'analysts_v2'

/** Keep only v2.0 and above types */
export const filterV2AgentTypes = (types: string[]) =>
  types.filter((t) => !v1AgentTypes.includes(t))
