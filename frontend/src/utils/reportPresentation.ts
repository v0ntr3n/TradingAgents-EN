export type ReportInfo = {
  name: string
  icon?: string
  description?: string
}

export const REPORT_INFO_MAP: Record<string, ReportInfo> = {
  // 🆕 Macro analyst team (2 a)
  'index_report': {
    name: '📊 Market Analyst',
    description: 'Analyze the market index based on multiple dimensions of technology, capital and fundamentals',
  },
  'sector_report': {
    name: '🏭 Sector Analyst',
    description: 'Hot sector rotation analysis and sector valuation positioning',
  },
  // Analyst Team (4 a)
  'market_report': {
    name: '📈 market analyst',
    description: 'Pure technical analysis based on K-line, moving average and trading volume',
  },
  'sentiment_report': {
    name: '💬 social media analyst',
    description: 'Emotional judgment based on news, public opinion, and capital flow',
  },
  'news_report': {
    name: '📰 news analyst',
    description: 'The impact of recent major news and announcements on the underlying',
  },
  'fundamentals_report': {
    name: '💰 fundamental analyst',
    description: 'Valuation, financial, growth fundamental analysis',
  },
  'chip_report': {
    name: '🧮 Chip distribution analyst',
    description: 'Analysis of profit ratio, chip concentration and cost distribution',
  },
  // research team (3 a)
  'bull_researcher': {
    name: '🐂 Positive Evidence Researcher',
    description: 'Research observations based on positive evidence',
  },
  'bear_researcher': {
    name: '🐻 cautious evidence researcher',
    description: 'Research observations based on careful evidence',
  },
  'research_team_decision': {
    name: '🔬 research integrator',
    description: 'Comprehensive observation and key data support of multi-scenario research',
  },
  // v2.0 straight out field
  'bull_report': {
    name: '🐂 positive evidence research',
    description: 'Research observations based on positive evidence',
  },
  'bear_report': {
    name: '🐻 careful evidence research',
    description: 'Research observations based on careful evidence',
  },
  // trading team (1 a)
  'trader_investment_plan': {
    name: '🧩 research integrator',
    description: 'Research briefing and research observation summary',
  },
  // risk management team (4 a)
  'risky_analyst': {
    name: '⚡ Highly Resilient Scenario Analyst',
    description: 'Analysis and research observation from the perspective of high elasticity',
  },
  'safe_analyst': {
    name: '🛡️ Defense Scenario Analyst',
    description: 'Risk assessment and research observation from a defense perspective',
  },
  'neutral_analyst': {
    name: '⚖️ Baseline Scenario Analyst',
    description: 'Objective analysis from a neutral perspective',
  },
  'risk_management_decision': {
    name: '👔 risk assessor',
    description: 'Overall risk assessment and governance opinions',
  },
  // v2.0 Risk perspective and assessment straight out of the field
  'risky_opinion': {
    name: '⚡ Highly resilient scenario analysis perspective',
    description: 'Risks and Opportunities from a Highly Resilient Scenario Perspective',
  },
  'safe_opinion': {
    name: '🛡️ Defense Scenario Analysis Perspective',
    description: 'Risk control opinions from the perspective of defense scenarios',
  },
  'neutral_opinion': {
    name: '⚖️ Baseline Scenario Analysis Perspective',
    description: 'Risks and Opportunities from a Neutral Perspective',
  },
  'risk_assessment': {
    name: '⚠️ risk review',
    description: 'Overall risk assessment of the target',
  },
  // final research conclusion (1 a)
  'final_trade_decision': {
    name: '🧾 Comprehensive research conclusion',
    description: 'Summarize the final research conclusions of each team',
  },
  // Compatible with old fields
  'investment_plan': {
    name: '🧾 research brief',
    description: 'Complete summary of research observations',
  },
  'investment_debate_state': {
    name: '🔬 Research Team Analysis (Old)',
    description: 'Research team multi-scenario research discussion',
  },
  'risk_debate_state': {
    name: '⚖️ Risk Team Analysis (Old)',
    description: 'Risk team multi-scenario research discussion',
  },
  'detailed_analysis': {
    name: '📄 Detailed analysis',
    description: 'Detailed raw analysis',
  },
}

export interface ManifestEntry {
  field: string
  display_name: string
  icon?: string
  description?: string
  category?: string
  order?: number
  is_primary?: boolean
  agent_id?: string
  has_content?: boolean
}

export function getReportName(key: string, manifestOrIsEtf?: ManifestEntry[] | boolean): string {
  const isEtf = typeof manifestOrIsEtf === 'boolean' ? manifestOrIsEtf : false
  const manifest = Array.isArray(manifestOrIsEtf) ? manifestOrIsEtf : undefined

  if (isEtf && key === 'fundamentals_report') {
    return '📊 ETF analysis'
  }
  // 1. Get it from manifest first display_name
  if (manifest) {
    const entry = manifest.find((m) => m.field === key)
    if (entry?.display_name) {
      const icon = entry.icon || ''
      return icon ? `${icon} ${entry.display_name}` : entry.display_name
    }
  }
  // 2. Fallback to hardcoding REPORT_INFO_MAP
  const info = REPORT_INFO_MAP[key]
  if (info?.name) {
    return info.name
  }
  // 3. The final tip: plain text formatting
  return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
}

export function getReportIcon(key: string, manifest?: ManifestEntry[]): string {
  // 1. Get it from manifest first icon
  if (manifest) {
    const entry = manifest.find((m) => m.field === key)
    if (entry?.icon) {
      return entry.icon
    }
  }
  // 2. Fallback to hardcoding REPORT_INFO_MAP
  const info = REPORT_INFO_MAP[key]
  if (!info?.name) {
    return ''
  }
  const match = info.name.match(/^(\S+)\s*/)
  return match?.[1] || ''
}

export function getReportDescription(key: string, manifest?: ManifestEntry[]): string {
  // 1. Get it from manifest first description
  if (manifest) {
    const entry = manifest.find((m) => m.field === key)
    if (entry?.description) {
      return entry.description
    }
  }
  // 2. Fallback to hardcoding REPORT_INFO_MAP
  return REPORT_INFO_MAP[key]?.description || ''
}
