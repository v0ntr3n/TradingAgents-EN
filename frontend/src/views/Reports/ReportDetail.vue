<template>
  <div class="report-detail">
    <!-- Loading status -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <!-- Report content -->
    <div v-else-if="report" class="report-content">
      <!-- Report header -->
      <el-card class="report-header" shadow="never">
        <div class="header-content">
          <div class="title-section">
            <h1 class="report-title">
              <el-icon><Document /></el-icon>
              {{ report.stock_name || report.stock_symbol }} research report
            </h1>
            <div class="report-meta">
              <el-tag type="primary">{{ report.stock_symbol }}</el-tag>
              <el-tag v-if="report.stock_name && report.stock_name !== report.stock_symbol" type="info">{{ report.stock_name }}</el-tag>
              <el-tag type="success">{{ getStatusText(report.status) }}</el-tag>
              <span class="meta-item">
                <el-icon><Calendar /></el-icon>
                {{ formatTime(report.created_at) }}
              </span>
              <span class="meta-item">
                <el-icon><User /></el-icon>
                {{ formatAnalysts(report.analysts) }}
              </span>
              <span v-if="report.model_info && report.model_info !== 'Unknown'" class="meta-item">
                <el-icon><Cpu /></el-icon>
                <el-tooltip :content="getModelDescription(report.model_info)" placement="top">
                  <el-tag type="info" style="cursor: help;">{{ report.model_info }}</el-tag>
                </el-tooltip>
              </span>
              <span v-if="report.research_depth" class="meta-item">
                <el-icon><DataAnalysis /></el-icon>
                <el-tooltip :content="getResearchDepthDescription(report.research_depth)" placement="top">
                  <el-tag type="warning" style="cursor: help;">Depth: {{ report.research_depth }}</el-tag>
                </el-tooltip>
              </span>
            </div>
          </div>
          
          <div class="action-section">
            <el-dropdown trigger="click" @command="downloadReport">
              <el-button type="primary">
                <el-icon><Download /></el-icon>
                Download report
                <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="markdown">
                    <el-icon><document /></el-icon> Markdown
                  </el-dropdown-item>
                  <el-dropdown-item command="docx">
                    <el-icon><document /></el-icon> Word Documentation
                  </el-dropdown-item>
                  <el-dropdown-item command="pdf">
                    <el-icon><document /></el-icon> PDF
                  </el-dropdown-item>
                  <el-dropdown-item command="json" divided>
                    <el-icon><document /></el-icon> JSON (raw data)
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button @click="goBack">
              <el-icon><Back /></el-icon>
              Return
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- Risk warning -->
      <div class="risk-disclaimer">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <div class="disclaimer-content">
              <el-icon class="disclaimer-icon"><WarningFilled /></el-icon>
              <div class="disclaimer-text">
                <p style="margin: 0 0 8px 0;"><strong>⚠️ Important Risk Warnings and Disclaimers</strong></p>
                <ul style="margin: 0; padding-left: 20px; line-height: 1.8;">
                  <li><strong>Platform nature:</strong>This platform is an AI-assisted analysis technology learning platform, focusing on the application verification and technical learning of AI technology in the fields of securities and ETF analysis.</li>
                  <li><strong>Analysis purpose:</strong>All analysis conclusions are only used to learn and verify AI-assisted analysis technology and are not used as real trading guidance or investment basis.</li>
                  <li><strong>Non-investment advice:</strong>All analysis results, ratings, and recommendations are only for technical verification reference and do not constitute any buying and selling advice or the basis for investment decisions.</li>
                  <li><strong>Data limitations:</strong>The analysis is based on historical data and public information, which may be delayed, incomplete or inaccurate, and cannot predict future market trends.</li>
                  <li><strong>Investment risks:</strong>Both stock and ETF investments are subject to various risks such as market risk, liquidity risk, policy risk, etc., which may result in loss of principal.</li>
                  <li><strong>Independent decision-making:</strong>Investors should make investment decisions independently based on their own risk tolerance, investment objectives and financial status.</li>
                  <li><strong>Responsibility statement:</strong>Any investment decisions and consequences arising from the use of this platform are the sole responsibility of the user, and this platform does not assume any responsibility.</li>
                </ul>
              </div>
            </div>
          </template>
        </el-alert>
      </div>

      <!-- research brief -->
      <el-card v-if="summaryDisplayContent" class="summary-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><InfoFilled /></el-icon>
            <span>research brief</span>
          </div>
        </template>
        <div class="summary-content markdown-content" v-html="renderMarkdown(summaryDisplayContent)"></div>
      </el-card>

      <TaskGrowthPanel
        v-if="growthTaskId"
        class="growth-card"
        :task-id="growthTaskId"
      />

      <!-- reporting module -->
      <el-card class="modules-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Files /></el-icon>
            <span>Detailed research report</span>
          </div>
        </template>
        
        <el-tabs v-model="activeModule" type="border-card">
          <el-tab-pane
            v-for="moduleName in detailedModuleNames"
            :key="moduleName"
            :label="getModuleDisplayName(moduleName)"
            :name="moduleName"
          >
            <div class="module-content">
              <div v-if="getModuleContent(report.reports[moduleName])" class="markdown-content">
                <div v-html="renderMarkdown(getModuleContent(report.reports[moduleName]) || '')"></div>
              </div>
              <div v-else class="json-content">
                <pre>{{ JSON.stringify(report.reports[moduleName], null, 2) }}</pre>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <!-- error status -->
    <div v-else class="error-container">
      <el-result
        icon="error"
        title="Report loading failed"
        sub-title="Please check if the report ID is correct or try again later"
      >
        <template #extra>
          <el-button type="primary" @click="goBack">Return to list</el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { configApi, type LLMConfig } from '@/api/config'
import TaskGrowthPanel from '@/components/growth/TaskGrowthPanel.vue'
import {
  Document,
  Calendar,
  User,
  Download,
  Back,
  InfoFilled,
  Files,
  WarningFilled,
  DataAnalysis,
  Cpu,
  ArrowDown
} from '@element-plus/icons-vue'
import { ApiClient } from '@/api/request'
import { marked } from 'marked'

interface ReportDecision {
  action?: string
  analysis_view?: string
}

interface ReportDetailData {
  id: string | number
  analysis_id?: string | number
  task_id?: string
  stock_symbol: string
  stock_name?: string
  status: string
  created_at: string
  analysts: string[]
  model_info?: string
  research_depth?: number
  recommendation?: string
  reports: Record<string, any>
  confidence_score?: number
  risk_level?: string
  key_points?: string[]
  summary?: string
  task_type?: string
  decision?: ReportDecision
  report_manifest?: Array<{
    field: string
    display_name: string
    category?: string
    order: number
    is_primary?: boolean
  }>
}

// routing and authentication
const route = useRoute()
const router = useRouter()

// Configure marked for more complete Markdown support
marked.setOptions({ breaks: true, gfm: true })

// Responsive data
const loading = ref(true)
const report = ref<ReportDetailData | null>(null)
const activeModule = ref('')
const llmConfigs = ref<LLMConfig[]>([]) // Store all model configurations
const growthTaskId = computed(() => report.value?.task_id || null)

const analystNameMap: Record<string, string> = {
  index_analyst: 'Market Analyst',
  index_analyst_v2: 'Market Analyst',
  sector_analyst: 'Sector Analyst',
  sector_analyst_v2: 'Sector Analyst',
  market_analyst: 'market analyst',
  market_analyst_v2: 'market analyst',
  fundamentals_analyst: 'fundamental analyst',
  fundamentals_analyst_v2: 'fundamental analyst',
  etf_analyst: 'ETF analyst',
  etf_analyst_v2: 'ETF analyst',
  news_analyst: 'news analyst',
  news_analyst_v2: 'news analyst',
  social_analyst: 'social media analyst',
  social_analyst_v2: 'social media analyst',
  sentiment_analyst: 'social media analyst',
  bull_researcher: 'Optimistic Scenario Researcher',
  bull_researcher_v2: 'Optimistic Scenario Researcher',
  bear_researcher: 'Prudential Scenario Researcher',
  bear_researcher_v2: 'Prudential Scenario Researcher',
  research_manager: 'research manager',
  research_manager_v2: 'research manager',
  trader: 'research integrator',
  trader_v2: 'research integrator',
  risky_analyst: 'Highly Resilient Scenario Analyst',
  risky_analyst_v2: 'Highly Resilient Scenario Analyst',
  safe_analyst: 'Defense Scenario Analyst',
  safe_analyst_v2: 'Defense Scenario Analyst',
  neutral_analyst: 'Baseline Scenario Analyst',
  neutral_analyst_v2: 'Baseline Scenario Analyst',
  risk_manager: 'risk assessor',
  risk_manager_v2: 'risk assessor',
  market: 'market analyst',
  fundamentals: 'fundamental analyst',
  etf: 'ETF analyst',
  news: 'news analyst',
  social: 'social media analyst',
  sentiment: 'social media analyst',
  technical: 'market analyst',
  'Market Index Analyst': 'Market Analyst',
  'Industry sector analyst': 'Sector Analyst',
  'Market Technical Analyst': 'market analyst',
  'news events analyst': 'news analyst',
  'market sentiment analyst': 'social media analyst',
  'multi-investigator': 'Optimistic Scenario Researcher',
  'short researcher': 'Prudential Scenario Researcher',
  'activist analyst': 'Highly Resilient Scenario Analyst',
  'conservative analyst': 'Defense Scenario Analyst',
  'neutral analyst': 'Baseline Scenario Analyst'
}

const moduleDisplayNameMap: Record<string, string> = {
  index_report: '📊 Market Analyst',
  sector_report: '🏭 Sector Analyst',
  market_report: '📈 market analyst',
  sentiment_report: '💬 social media analyst',
  news_report: '📰 news analyst',
  fundamentals_report: '💰 fundamental analyst',
  bull_researcher: '🐂 Positive Evidence Researcher',
  bull_report: '🐂 positive evidence research',
  bear_researcher: '🐻 cautious evidence researcher',
  bear_report: '🐻 careful evidence research',
  research_team_decision: '🔬 research integrator',
  trader_investment_plan: '🧩 research integrator',
  risky_analyst: '⚡ Highly Resilient Scenario Analyst',
  risky_opinion: '⚡ Highly elastic scenario research observations',
  safe_analyst: '🛡️ Defense Scenario Analyst',
  safe_opinion: '🛡️ Defense Scenario Research Observations',
  neutral_analyst: '⚖️ Baseline Scenario Analyst',
  neutral_opinion: '⚖️ Baseline Scenario Research Observations',
  risk_management_decision: '👔 risk assessor',
  risk_assessment: '⚠️ risk review',
  investment_plan: '🧾 research brief',
  final_trade_decision: '🧾 Comprehensive research conclusion',
  investment_debate_state: '🔬 Research Team Analysis (Old)',
  risk_debate_state: '⚖️ Risk Team Analysis (Old)',
  detailed_analysis: '📄 Detailed analysis'
}

const manifestDisplayNameAliasMap: Record<string, string> = {
  'Market analysis v2': '📊 Market Analyst',
  'Market Analyst v2': '📊 Market Analyst',
  'Sector analysis v2': '🏭 Sector Analyst',
  'Sector Analyst v2': '🏭 Sector Analyst',
  'market analysis v2': '📈 market analyst',
  'market analyst v2': '📈 market analyst',
  'Market technical analysis': '📈 market analyst',
  'fundamental analysis v2': '💰 fundamental analyst',
  'fundamental analyst v2': '💰 fundamental analyst',
  'news analysis v2': '📰 news analyst',
  'news analyst v2': '📰 news analyst',
  'News event analysis': '📰 news analyst',
  'Public opinion analysis v2': '💬 social media analyst',
  'social media analyst v2': '💬 social media analyst',
  'Market Sentiment Analysis': '💬 social media analyst',
  'Research Manager Analysis': '🔬 research integrator',
  'research manager v2': '🔬 research integrator',
  'research manager': '🔬 research integrator',
  'trader plan': '🧩 research integrator',
  'trader v2': '🧩 research integrator',
  'trader': '🧩 research integrator',
  'research integrator v2': '🧩 research integrator',
  'research integrator': '🧩 research integrator',
  'activist analyst': '⚡ Highly Resilient Scenario Analyst',
  'activist analyst v2': '⚡ Highly Resilient Scenario Analyst',
  'conservative analyst': '🛡️ Defense Scenario Analyst',
  'conservative analyst v2': '🛡️ Defense Scenario Analyst',
  'neutral analyst': '⚖️ Baseline Scenario Analyst',
  'neutral analyst v2': '⚖️ Baseline Scenario Analyst',
  'risk manager': '👔 risk assessor',
  'risk manager v2': '👔 risk assessor',
  'risk manager': '👔 risk assessor',
  'risk manager v2': '👔 risk assessor',
  'risk assessment': '⚠️ risk review',
  'Final analysis results': '🧾 Comprehensive research conclusion'
}

// Get model configuration list
const fetchLLMConfigs = async () => {
  try {
    const response = await configApi.getSystemConfig()
    llmConfigs.value = Array.isArray(response?.llm_configs) ? response.llm_configs : []
  } catch (error) {
    console.error('Failed to get model configuration:', error)
  }
}

// Get report details
const fetchReportDetail = async () => {
  loading.value = true
  try {
    const reportId = route.params.id as string

    const result = await ApiClient.get<any>(`/api/reports/${reportId}/detail`)

    if (result.success) {
      report.value = result.data

      // Set the default activated modules (skip the research briefing and prioritize the first detailed research report)
      const reports = result.data.reports || {}
      const availableModules = Object.keys(reports)

      const manifest = Array.isArray(result.data.report_manifest) ? result.data.report_manifest : []
      const firstManifestModule = manifest.length > 0
        ? [...manifest]
            .sort((a, b) => a.order - b.order)
            .map(item => item.field)
            .find((field: string) => availableModules.includes(field))
        : undefined

      const orderedDetailedModules = moduleOrder.filter(name => {
        if (!availableModules.includes(name)) {
          return false
        }

        return name !== 'trader_investment_plan'
      })

      // Prioritize according to report_manifest, and then fall back to the detailed module order.
      const firstModule = (firstManifestModule && firstManifestModule !== 'trader_investment_plan')
        ? firstManifestModule
        : orderedDetailedModules[0]
      if (firstModule) {
        activeModule.value = firstModule
      } else if (availableModules.length > 0) {
        const firstDetailedModule = availableModules.find(name => name !== 'trader_investment_plan')
        activeModule.value = firstDetailedModule || ''
      }
    } else {
      throw new Error(result.message || 'Failed to get report details')
    }
  } catch (error) {
    console.error('Failed to get report details:', error)
    ElMessage.error('Failed to get report details')
  } finally {
    loading.value = false
  }
}

// Download report
const downloadReport = async (format: string = 'markdown') => {
  if (!report.value) {
    ElMessage.warning('The report has not been loaded yet')
    return
  }

  const currentReport = report.value
  try {
    // Show loading prompt
    const loadingMsg = ElMessage({
      message: `Generating${getFormatName(format)}Format report...`,
      type: 'info',
      duration: 0
    })

    const res: any = await ApiClient.get(`/api/reports/${currentReport.id}/download`, { format }, { responseType: 'blob', showLoading: false })

    loadingMsg.close()

    // Compatible: the response interceptor returns Blob directly; compatible returns { data: Blob } old implementation of
    const blob = res instanceof Blob ? res : (res?.data instanceof Blob ? res.data : new Blob([res]))
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    // Set file extension based on format
    const ext = getFileExtension(format)
    // Clean special characters in stock names (used in file names)
    const cleanStockName = (currentReport.stock_name || '')
      .replace(/[/\\:*?"<>|]/g, '') // Remove characters not allowed in file names
      .replace(/\s+/g, '_') // Replace spaces with underscores
      .trim()
    // Build file name: stock code_stock name_analysis report_date
    const fileName = cleanStockName
      ? `${currentReport.stock_symbol}_${cleanStockName}_analysis report_${(currentReport as any).analysis_date}.${ext}`
      : `${currentReport.stock_symbol}_analysis report_${(currentReport as any).analysis_date}.${ext}`
    a.download = fileName

    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    ElMessage.success(`${getFormatName(format)}Report download successful`)
  } catch (error: any) {
    console.error('Download report failed:', error)

    // Show detailed error information
    if (error.message && error.message.includes('pandoc')) {
      ElMessage.error({
        message: 'Word Exporting requires the pandoc tool to be installed (PDF export does not require pandoc)',
        duration: 5000
      })
    } else if (error.message && (error.message.includes('weasyprint') || error.message.includes('pdfkit'))) {
      ElMessage.error({
        message: 'PDF Exporting requires installing the PDF engine: pip install weasyprint (recommended)',
        duration: 5000
      })
    } else {
      ElMessage.error(`Download report failed: ${error.message || 'unknown error'}`)
    }
  }
}

// Helper function: get format name
const getFormatName = (format: string): string => {
  const names: Record<string, string> = {
    'markdown': 'Markdown',
    'docx': 'Word',
    'pdf': 'PDF',
    'json': 'JSON'
  }
  return names[format] || format
}

// Helper function: get file extension
const getFileExtension = (format: string): string => {
  const extensions: Record<string, string> = {
    'markdown': 'md',
    'docx': 'docx',
    'pdf': 'pdf',
    'json': 'json'
  }
  return extensions[format] || 'txt'
}

// Return to list
const goBack = () => {
  router.push('/reports')
}

// Utility function
const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    completed: 'Completed',
    processing: 'Generating',
    failed: 'failed'
  }
  return statusMap[status] || status
}

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const normalizeAnalystName = (analyst: string): string => {
  return analystNameMap[analyst] || analyst
}

// Convert analyst English name to Chinese
const formatAnalysts = (analysts: string[] = []) => {
  return Array.from(new Set(analysts.map(normalizeAnalystName))).join('、')
}

// Get a detailed description of the model (obtained from the backend configuration)
const getModelDescription = (modelInfo: string) => {
  if (!modelInfo || modelInfo === 'Unknown') {
    return 'unknown model'
  }

  // 1. Prioritize finding exact matches from backend configuration
  const config = llmConfigs.value.find(c => c.model_name === modelInfo)
  if (config?.description) {
    return config.description
  }

  // 2. Try fuzzy matching (handling changes in version numbers etc.)
  const fuzzyConfig = llmConfigs.value.find(c =>
    modelInfo.toLowerCase().includes(c.model_name.toLowerCase()) ||
    c.model_name.toLowerCase().includes(modelInfo.toLowerCase())
  )
  if (fuzzyConfig?.description) {
    return fuzzyConfig.description
  }

  // 3. Provide a generic description based on the model name prefix
  const modelLower = modelInfo.toLowerCase()
  if (modelLower.includes('gpt')) {
    return `OpenAI ${modelInfo} - Powerful language model`
  } else if (modelLower.includes('claude')) {
    return `Anthropic ${modelInfo} - High performance inference model`
  } else if (modelLower.includes('qwen')) {
    return `Ali Tongyi Qianwen ${modelInfo} - Chinese optimization model`
  } else if (modelLower.includes('glm')) {
    return `Wisdom spectrum ${modelInfo} - Excellent overall performance`
  } else if (modelLower.includes('deepseek')) {
    return `DeepSeek ${modelInfo} - Cost-effective model`
  } else if (modelLower.includes('ernie')) {
    return `Baidu Wenxin ${modelInfo} - Strong Chinese ability`
  } else if (modelLower.includes('spark')) {
    return `iFlytek Spark ${modelInfo} - Professional model`
  } else if (modelLower.includes('moonshot')) {
    return `Moonshot ${modelInfo} - long context model`
  } else if (modelLower.includes('yi')) {
    return `zero one thing ${modelInfo} - High performance model`
  }

  // 4. Return by default
  return `${modelInfo} - AI large language model`
}

// Define the display order of report modules (according to the analysis process order)
const moduleOrder = [
  // The first stage: macro analysis (2)
  'index_report',
  'sector_report',

  // Phase 2: Analyst Team (4)
  'market_report',
  'fundamentals_report',
  'sentiment_report',
  'news_report',

  // Phase Three: Research Team (Multiple Scenario Research + Preliminary research observations)
  'bull_researcher',
  'bull_report',
  'bear_researcher',
  'bear_report',
  'research_team_decision',
  // 'investment_plan',  // 🔑 Hidden: Same as Research Manager analysis content

  // Phase Four: Deal Team
  'trader_investment_plan',

  // Stage Five: Risk Management Team (Risk Debate)
  'risky_analyst',
  'risky_opinion',
  'safe_analyst',
  'safe_opinion',
  'neutral_analyst',
  'neutral_opinion',
  'risk_management_decision',
  'risk_assessment',

  // Stage Six: Final Research Conclusions
  'final_trade_decision',  // 🔑 Final research conclusion (after risk management)

  // Compatible with old fields
  'investment_debate_state',
  'risk_debate_state',
  'detailed_analysis'
]

// Computed properties: Return existing report modules in order
const orderedModuleNames = computed(() => {
  if (!report.value?.reports) return []

  const availableModules = Object.keys(report.value.reports)

  // Dynamic mode: use report_manifest
  const manifest = report.value?.report_manifest as Array<{
    field: string; display_name: string; order: number
  }> | undefined
  if (manifest && manifest.length > 0) {
    const sorted = [...manifest].sort((a, b) => a.order - b.order)
    const manifestOrdered = sorted.map(m => m.field).filter(f => availableModules.includes(f))
    const remainingOrdered = moduleOrder.filter(name => {
      return availableModules.includes(name) && !manifestOrdered.includes(name)
    })
    const remaining = availableModules.filter(name => {
      return !manifestOrdered.includes(name) && !moduleOrder.includes(name)
    })

    return [...manifestOrdered, ...remainingOrdered, ...remaining]
  }

  // Old logic: sort by moduleOrder
  const ordered = moduleOrder.filter(name => availableModules.includes(name))

  const remaining = availableModules.filter(name => !moduleOrder.includes(name))

  return [...ordered, ...remaining]
})

const isEtfReport = computed(() => {
  const analysts = report.value?.analysts || []
  return report.value?.task_type === 'etf_analysis' || analysts.includes('etf_analyst') || analysts.includes('etf_analyst_v2')
})

const normalizeModuleDisplayName = (displayName?: string, moduleName?: string) => {
  if (moduleName === 'fundamentals_report' && isEtfReport.value) {
    return '📊 ETF analyst'
  }

  const normalized = (displayName || '').replace(/^【|】$/g, '').trim()
  if (normalized) {
    return manifestDisplayNameAliasMap[normalized] || normalized
  }

  if (moduleName) {
    return moduleDisplayNameMap[moduleName] || moduleName.replace(/_/g, ' ')
  }

  return ''
}

const getModuleDisplayName = (moduleName: string) => {
  // Dynamic mode: Get it from report_manifest first display_name
  const manifest = report.value?.report_manifest as Array<{
    field: string; display_name: string
  }> | undefined
  if (manifest) {
    const item = manifest.find(m => m.field === moduleName)
    if (item?.display_name) return normalizeModuleDisplayName(item.display_name, moduleName)
  }

  return normalizeModuleDisplayName(undefined, moduleName)
}

/**
 * Render a risk review JSON object to readable Markdown text.
 * Fields are consistent with the backend risk_assessment / risk_management_decision structures.
 */
const formatRiskAssessment = (value: any): string | null => {
  if (!value || typeof value !== 'object') return null
  const riskLevel = value.risk_level || value.riskLevel
  const riskScore = value.risk_score ?? value.riskScore
  const reasoning = value.reasoning || value.conclusion || value.summary || value.assessment
  const keyRisks = value.key_risks || value.keyRisks || value.risks
  const riskControl = value.risk_control || value.riskControl || value.control || value.suggestions
  const investmentAdjustment = value.investment_adjustment || value.investmentAdjustment || value.adjustment

  if (riskLevel === undefined && riskScore === undefined && !reasoning && !riskControl && !investmentAdjustment) {
    return null
  }

  const parts: string[] = []
  if (riskLevel !== undefined) {
    parts.push(`**risk level**: ${riskLevel}`)
  }
  if (riskScore !== undefined) {
    const score = typeof riskScore === 'number' ? riskScore.toFixed(2) : riskScore
    parts.push(`**risk score**: ${score}`)
  }
  if (reasoning) {
    parts.push(`**Assessment conclusion**: ${reasoning}`)
  }
  if (Array.isArray(keyRisks) && keyRisks.length > 0) {
    parts.push(`**core risk**: `)
    keyRisks.forEach((risk: any) => {
      if (risk) parts.push(`- ${String(risk).trim()}`)
    })
  }
  if (riskControl) {
    parts.push(`**Risk control suggestions**: ${riskControl}`)
  }
  if (investmentAdjustment) {
    parts.push(`**Investment adjustment suggestions**: ${investmentAdjustment}`)
  }

  return parts.join('\n\n')
}

const _stripJsonCodeFence = (text: string): string => {
  // remove ```json ... ``` or ``` ... ``` code block wrapper
  let t = text.trim()
  const fenceMatch = t.match(/^```(?:json|JSON)?\s*\n([\s\S]*?)\n```\s*$/i)
  if (fenceMatch) {
    t = fenceMatch[1].trim()
  }
  return t
}

const _looksLikeRiskJson = (text: string): boolean => {
  const lowered = text.toLowerCase()
  return (
    text.startsWith('{') &&
    (lowered.includes('"risk_level"') ||
      lowered.includes('"risk_score"') ||
      lowered.includes('"reasoning"') ||
      lowered.includes('"key_risks"') ||
      lowered.includes('"risk_control"') ||
      lowered.includes('"investment_adjustment"'))
  )
}

const extractStructuredText = (value: any): string | null => {
  if (!value) return null

  if (typeof value === 'string') {
    // Peel first ```json code block, and then determine whether it is a risk review JSON
    const stripped = _stripJsonCodeFence(value.trim())
    if (!stripped) return null

    if (_looksLikeRiskJson(stripped)) {
      try {
        const parsed = JSON.parse(stripped)
        const riskText = formatRiskAssessment(parsed)
        if (riskText) return riskText
      } catch {
        // Not valid JSON, return as normal text
      }
    }
    // If the original text is ```json Code block but not risky JSON, returns stripped content
    return stripped !== value.trim() ? stripped : value.trim()
  }

  if (typeof value === 'object') {
    // Risk review structured objects are rendered directly as readable text
    const riskText = formatRiskAssessment(value)
    if (riskText) return riskText

    // When content/text fields are nested in objects, recursive attempts are made to parse them.
    // real data structure: { content: "```json\n{...}\n```", success: true }
    for (const key of ['content', 'markdown', 'text', 'message', 'report', 'judge_decision', 'risk_assessment', 'risk_management_decision']) {
      const item = value[key]
      if (item) {
        const nested = extractStructuredText(item)
        if (nested) return nested
      }
    }
  }

  return null
}

const normalizeDisplayedResearchText = (content: string) => {
  if (!content) return ''

  const replacements: Array<[RegExp, string]> = [
    [/Transaction Analysis Plan/g, 'Research and integrate opinions'],
    [/trader plan/g, 'Research and integrate opinions'],
    [/Initial investment plan/g, 'Research team conclusion'],
    [/investment plan/g, 'Research conclusion'],
    [/investment advice/g, 'Research conclusion'],
    [/Operation suggestions/g, 'research perspective'],
    [/Market index analysis/g, 'market environment research'],
    [/Industry sector analysis/g, 'Industry sector research'],
    [/Market Sentiment Analysis/g, 'emotion research'],
    [/News event analysis/g, 'Journalism Research'],
    [/Risk review summary/g, 'Risk review conclusion'],
    [/Comprehensive Research Brief/g, 'Comprehensive research conclusion'],
    [/risk management decisions/g, 'Risk review conclusion'],
    [/Final analysis results/g, 'final research conclusion'],
    [/activist risk analyst/g, 'Highly Resilient Scenario Analyst'],
    [/conservative risk analyst/g, 'Defense Scenario Analyst'],
    [/Neutral Risk Analyst/g, 'Baseline Scenario Analyst']
  ]

  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), content)
}

const prepareMarkdownContent = (content: string) => {
  let preparedText = normalizeDisplayedResearchText(content || '').trim()

  if (!preparedText) {
    return ''
  }

  if (
    ((preparedText.startsWith('"') && preparedText.endsWith('"')) ||
      (preparedText.startsWith("'") && preparedText.endsWith("'"))) &&
    preparedText.length >= 2
  ) {
    preparedText = preparedText.slice(1, -1).trim()
  }

  const fencedMarkdownMatch = preparedText.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i)
  if (fencedMarkdownMatch) {
    preparedText = fencedMarkdownMatch[1].trim()
  }

  return preparedText
}

const renderMarkdown = (content: string) => {
  if (!content) return ''
  try {
    return marked.parse(prepareMarkdownContent(content)) as string
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${prepareMarkdownContent(content)}</pre>`
  }
}

// 🔥 Extract module content (supports the content field in the object)
const getModuleContent = (moduleData: any): string | null => {
  if (!moduleData) return null

  const extractedText = extractStructuredText(moduleData)
  if (extractedText) {
    return normalizeDisplayedResearchText(extractedText)
  }

  return null
}

// Get an in-depth description of the analysis
const getResearchDepthDescription = (depth: number) => {
  const descMap: Record<number, string> = {
    1: 'Quick Analysis - Basic Technical and Fundamental Analysis',
    2: 'Standard analysis - including technical, fundamental and sentiment analysis',
    3: 'In-Depth Analysis - Comprehensive multi-dimensional analysis, including detailed industry and competitive analysis',
    4: 'Expert-Level Analysis - The most comprehensive analysis, including all dimensions and in-depth research',
    5: 'Top level analysis - the highest level of analysis depth, encompassing all possible dimensions of analysis'
  }
  return descMap[depth] || `Analysis depth: ${depth}`
}

const getResearchContentFingerprint = (moduleData: any) => {
  const prepared = prepareMarkdownContent(getModuleContent(moduleData) || '')
  if (!prepared) {
    return ''
  }

  const strippedTitleLines = prepared
    .split('\n')
    .map(line => line.trim())
    .filter(line => {
      const normalizedLine = line
        .replace(/^#{1,6}\s*/, '')
        .replace(/^[>*\-+\d.\s)]+/, '')
        .trim()

      return !['Summary of research conclusions', 'Research Manager Briefing', 'Research team conclusion', 'Research conclusion', 'research brief'].includes(normalizedLine)
    })
    .join('\n')

  return strippedTitleLines
    .replace(/```[\s\S]*?```/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+[.)]\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\[(.*?)\]\([^)]*\)/g, '$1')
    .replace(/[>_*|~]/g, ' ')
    .replace(/[\s\u3000]+/g, '')
}

const userBriefContent = computed(() => {
  if (!report.value?.reports) return null
  return getModuleContent(report.value.reports.trader_investment_plan)
})

const summaryDisplayContent = computed(() => {
  return userBriefContent.value || getModuleContent(report.value?.summary) || ''
})

const detailedModuleNames = computed(() => {
  return orderedModuleNames.value.filter(name => {
    if (name === 'trader_investment_plan') {
      return false
    }

    if (name === 'investment_plan') {
      const reports = report.value?.reports || {}
      const researchDecision = getResearchContentFingerprint(reports.research_team_decision)
      const managerBrief = getResearchContentFingerprint(reports.investment_plan)
      if (researchDecision && researchDecision === managerBrief) {
        return false
      }
    }

    return true
  })
})

// life cycle
onMounted(() => {
  fetchLLMConfigs() // Load model configuration first
  fetchReportDetail() // Reload report details
})
</script>

<style lang="scss" scoped>
.report-detail {
  .loading-container {
    padding: 24px;
  }

  .report-content {
    .report-header {
      margin-bottom: 24px;

      .header-content {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;

        .title-section {
          .report-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 24px;
            font-weight: 600;
            color: var(--el-text-color-primary);
            margin: 0 0 12px 0;
          }

          .report-meta {
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;

            .meta-item {
              display: flex;
              align-items: center;
              gap: 4px;
              color: var(--el-text-color-regular);
              font-size: 14px;
            }
          }
        }

        .action-section {
          display: flex;
          gap: 8px;
        }
      }
    }

    /* Risk warning style */
    .risk-disclaimer {
      margin-bottom: 24px;
      animation: fadeInDown 0.5s ease-out;
    }

    .risk-disclaimer :deep(.el-alert) {
      background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%);
      border: 2px solid #ffc107;
      border-radius: 12px;
      padding: 16px 20px;
      box-shadow: 0 4px 12px rgba(255, 193, 7, 0.2);
    }

    .risk-disclaimer :deep(.el-alert__icon) {
      font-size: 24px;
      color: #ff6b00;
    }

    .disclaimer-content {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 15px;
      line-height: 1.6;
    }

    .disclaimer-icon {
      font-size: 24px;
      color: #ff6b00;
      flex-shrink: 0;
      animation: pulse 2s ease-in-out infinite;
    }

    .disclaimer-text {
      color: #856404;
      flex: 1;
    }

    .disclaimer-text strong {
      color: #d63031;
      font-size: 16px;
      font-weight: 700;
    }

    @keyframes pulse {
      0%, 100% {
        transform: scale(1);
        opacity: 1;
      }
      50% {
        transform: scale(1.1);
        opacity: 0.8;
      }
    }

    @keyframes fadeInDown {
      from {
        opacity: 0;
        transform: translateY(-20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .summary-card,
    .metrics-card,
    .growth-card,
    .modules-card {
      margin-bottom: 24px;

      .card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
      }
    }

    .summary-content {
      line-height: 1.6;
      color: var(--el-text-color-primary);
    }

    .metrics-content {
      .metric-item {
        text-align: center;
        padding: 24px;
        border: 1px solid var(--el-border-color-light);
        border-radius: 12px;
        background: var(--el-fill-color-blank);
        transition: all 0.3s ease;

        &:hover {
          box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
          transform: translateY(-2px);
        }

        .metric-label {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          font-size: 15px;
          font-weight: 500;
          color: var(--el-text-color-regular);
          margin-bottom: 16px;

          .el-icon {
            font-size: 18px;
          }
        }

        .metric-value {
          font-size: 18px;
          font-weight: 600;
          color: var(--el-color-primary);
        }

        .recommendation-value {
          font-size: 16px;
          line-height: 1.6;
          color: var(--el-text-color-primary);
          
          .core-conclusion {
            text-align: left;
            padding: 12px;
            background: var(--el-fill-color-light);
            border-radius: 8px;
            border-left: 3px solid var(--el-color-primary);
            
            strong {
              color: var(--el-color-primary);
              font-weight: 600;
            }
          }
        }
      }

      // Confidence scoring style
      .confidence-item {
        .confidence-display {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;

          .confidence-value {
            display: flex;
            align-items: baseline;
            gap: 4px;
            margin-top: 8px;

            .confidence-number {
              font-size: 32px;
              font-weight: 700;
              color: var(--el-color-primary);
            }

            .confidence-unit {
              font-size: 16px;
              color: var(--el-text-color-regular);
            }
          }

          .confidence-label {
            font-size: 14px;
            font-weight: 500;
            color: var(--el-text-color-secondary);
          }
        }
      }

      // Risk level style
      .risk-item {
        .risk-display {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;

          .risk-stars {
            display: flex;
            gap: 8px;
            font-size: 28px;

            .star-icon {
              color: #DCDFE6;
              transition: all 0.3s ease;

              &.active {
                color: #F7BA2A;
                animation: starPulse 0.6s ease-in-out;
              }
            }
          }

          .risk-label {
            font-size: 18px;
            font-weight: 700;
            margin-top: 4px;
          }

          .risk-description {
            font-size: 13px;
            color: var(--el-text-color-secondary);
            text-align: center;
            line-height: 1.4;
            max-width: 200px;
          }
        }
      }

      .key-points {
        margin-top: 32px;
        padding-top: 24px;
        border-top: 1px solid var(--el-border-color-lighter);

        h4 {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 0 0 16px 0;
          font-size: 16px;
          font-weight: 600;
          color: var(--el-text-color-primary);

          .el-icon {
            font-size: 18px;
            color: var(--el-color-primary);
          }
        }

        ul {
          margin: 0;
          padding: 0;
          list-style: none;

          li {
            display: flex;
            align-items: flex-start;
            gap: 8px;
            margin-bottom: 12px;
            padding: 12px;
            background: var(--el-fill-color-light);
            border-radius: 8px;
            line-height: 1.6;
            transition: all 0.2s ease;

            &:hover {
              background: var(--el-fill-color);
            }

            .point-icon {
              flex-shrink: 0;
              margin-top: 2px;
              font-size: 16px;
              color: var(--el-color-success);
            }
          }
        }
      }
    }

    // Star Pulse Animation
    @keyframes starPulse {
      0%, 100% {
        transform: scale(1);
      }
      50% {
        transform: scale(1.2);
      }
    }

    .module-content {
      .markdown-content {
        line-height: 1.6;
        
        :deep(h1), :deep(h2), :deep(h3) {
          margin: 16px 0 8px 0;
          color: var(--el-text-color-primary);
        }

        :deep(h1) { font-size: 24px; }
        :deep(h2) { font-size: 20px; }
        :deep(h3) { font-size: 16px; }
      }

      .json-content {
        pre {
          background: var(--el-fill-color-light);
          padding: 16px;
          border-radius: 8px;
          overflow-x: auto;
          font-size: 14px;
          line-height: 1.4;
        }
      }
    }
  }

  .error-container {
    padding: 48px 24px;
  }
}
</style>
