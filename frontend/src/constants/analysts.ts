/**
 * Analyst Configuration Constants
 */

export interface Analyst {
  id: string
  name: string
  description: string
  icon?: string
}

// List of analysts supported by the system
export const ANALYSTS: Analyst[] = [
  // Individual stock analysts
  {
    id: 'market',
    name: 'Market Analyst',
    description: 'Analyze stock price trends and technical indicators (MA/MACD/RSI/Bollinger Bands) to generate technical analysis reports',
    icon: 'TrendCharts'
  },
  {
    id: 'fundamentals',
    name: 'Fundamentals Analyst',
    description: 'Analyze company financial condition, business model, and competitive advantages',
    icon: 'DataAnalysis'
  },
  {
    id: 'news',
    name: 'News Analyst',
    description: 'Analyze the impact of relevant news, announcements, and market events',
    icon: 'Document'
  },
  {
    id: 'social',
    name: 'Social Media Analyst',
    description: 'Analyze social media sentiment, investor psychology, and public opinion trends',
    icon: 'ChatDotRound'
  },
  // 🆕 Macro analysts
  {
    id: 'index_analyst',
    name: 'Market Index Analyst',
    description: 'Analyze broad market index trends, market environment, and systemic risks',
    icon: 'PieChart'
  },
  {
    id: 'sector_analyst',
    name: 'Sector Analyst',
    description: 'Analyze industry trends, sector rotation, and peer comparisons',
    icon: 'Grid'
  },
  // ETF Analyst (ETF market only)
  {
    id: 'etf',
    name: 'ETF Analyst',
    description: 'Analyze ETF net asset value (NAV), tracking error, and holdings structure',
    icon: 'DataAnalysis'
  }
]

// Analyst name list (used for form options)
export const ANALYST_NAMES = ANALYSTS.map(analyst => analyst.name)

// Default selected analysts
export const DEFAULT_ANALYSTS = ['Market Analyst', 'Fundamentals Analyst']

// Get analyst info by name
export const getAnalystByName = (name: string): Analyst | undefined => {
  return ANALYSTS.find(analyst => analyst.name === name)
}

// Get analyst info by ID
export const getAnalystById = (id: string): Analyst | undefined => {
  return ANALYSTS.find(analyst => analyst.id === id)
}

// Validate whether an analyst name is valid
export const isValidAnalyst = (name: string): boolean => {
  return ANALYST_NAMES.includes(name) || Object.prototype.hasOwnProperty.call(ANALYST_NAME_TO_ID_MAP, name)
}

// Mapping from analyst display name (both English and legacy Chinese) to ID
export const ANALYST_NAME_TO_ID_MAP: Record<string, string> = {
  // Legacy Chinese names (preserved for backward compatibility)
  '大盘分析师': 'index_analyst',
  '板块分析师': 'sector_analyst',
  '市场分析师': 'market',
  '基本面分析师': 'fundamentals',
  '新闻分析师': 'news',
  '社媒分析师': 'social',
  '社交媒体分析师': 'social',
  'ETF分析师': 'etf',
  // English names
  'Market Index Analyst': 'index_analyst',
  'Sector Analyst': 'sector_analyst',
  'Market Analyst': 'market',
  'Fundamentals Analyst': 'fundamentals',
  'News Analyst': 'news',
  'Social Media Analyst': 'social',
  'ETF Analyst': 'etf'
}

// Convert analyst names to IDs
export const convertAnalystNamesToIds = (names: string[]): string[] => {
  return names.map(name => ANALYST_NAME_TO_ID_MAP[name] || name)
}

// Convert analyst IDs to display names
export const convertAnalystIdsToNames = (ids: string[]): string[] => {
  const idToNameMap = Object.fromEntries(
    Object.entries(ANALYST_NAME_TO_ID_MAP).map(([name, id]) => [id, name])
  )
  return ids.map(id => idToNameMap[id] || id)
}

// Mapping from model name to provider
export const MODEL_TO_PROVIDER_MAP: Record<string, string> = {
  // Alibaba Cloud Bailian (DashScope)
  'qwen-turbo': 'dashscope',
  'qwen-plus': 'dashscope',
  'qwen-max': 'dashscope',
  'qwen-plus-latest': 'dashscope',
  'qwen-max-longcontext': 'dashscope',

  // OpenAI
  'gpt-3.5-turbo': 'openai',
  'gpt-4': 'openai',
  'gpt-4-turbo': 'openai',
  'gpt-4o': 'openai',
  'gpt-4o-mini': 'openai',

  // Google
  'gemini-pro': 'google',
  'gemini-2.0-flash': 'google',
  'gemini-2.0-flash-thinking-exp': 'google',

  // DeepSeek
  'deepseek-chat': 'deepseek',
  'deepseek-coder': 'deepseek',

  // Zhipu AI
  'glm-4': 'zhipu',
  'glm-3-turbo': 'zhipu',
  'chatglm3-6b': 'zhipu'
}

// Get provider by model name
export const getProviderByModel = (modelName: string): string => {
  return MODEL_TO_PROVIDER_MAP[modelName] || 'dashscope' // Default to Alibaba Cloud Bailian (DashScope)
}
