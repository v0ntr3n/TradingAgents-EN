<template>
  <el-dialog
    v-model="visible"
    width="1000px"
    :close-on-click-modal="false"
  >
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
        <span>{{ isEtfPosition ? 'ETF Position analysis' : 'Single stock position analysis' }}</span>
        <el-button
          type="primary"
          size="small"
          link
          @click="showHistoryDialog = true"
          style="margin-right: 40px;"
        >
          <el-icon><Clock /></el-icon>
          History
        </el-button>
      </div>
    </template>

    <!-- Position information display -->
    <div v-if="position" class="position-info">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="securityCodeLabel">{{ position.code }}</el-descriptions-item>
        <el-descriptions-item :label="securityNameLabel">{{ position.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Position quantity">{{ position.quantity }} shares</el-descriptions-item>
        <el-descriptions-item label="cost price">¥{{ position.cost_price.toFixed(2) }}</el-descriptions-item>
        <el-descriptions-item label="current price">¥{{ position.current_price?.toFixed(2) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Position market value">¥{{ position.market_value?.toFixed(2) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="floating profit and loss">
          <span :class="(position.unrealized_pnl || 0) >= 0 ? 'profit' : 'loss'">
            {{ (position.unrealized_pnl || 0) >= 0 ? '+' : '' }}{{ position.unrealized_pnl?.toFixed(2) || '0.00' }}
            ({{ (position.unrealized_pnl_pct || 0) >= 0 ? '+' : '' }}{{ position.unrealized_pnl_pct?.toFixed(2) || '0.00' }}%)
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="industryLabel">{{ industryValue }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- Analysis status prompt -->
    <div v-if="analysisStatus === 'pending' || analysisStatus === 'processing'" class="analysis-status">
      <el-alert type="info" :closable="false">
        <template #title>
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ analysisStatus === 'pending' ? 'Analysis task has been submitted' : 'Under analysis' }}...
        </template>
        <template #default>
          <p>It is expected to take 2-5 minutes to complete. You can:</p>
          <ul>
            <li>Click below"Manually refresh status"button to view the latest progress</li>
            <li>Or close the dialog box and check back later (reopen the dialog box to see the results)</li>
          </ul>
          <el-button
            type="primary"
            size="small"
            :loading="refreshing"
            @click="manualRefreshStatus"
            style="margin-top: 12px;"
          >
            <el-icon v-if="!refreshing"><Refresh /></el-icon>
            {{ refreshing ? 'Refreshing...' : 'Manually refresh status' }}
          </el-button>
        </template>
      </el-alert>
    </div>

    <!-- Analysis parameter settings -->
    <div class="analysis-params" v-if="!analysisResult && analysisStatus !== 'pending' && analysisStatus !== 'processing'">
      <el-divider content-position="left">Analysis settings</el-divider>
      
      <!-- Process selection -->
      <div class="config-section" v-if="workflowsSorted.length > 0">
        <el-form-item label="Analysis process">
          <div style="display: flex; align-items: center; width: 100%;">
            <el-select
              v-model="selectedWorkflowId"
              size="small"
              style="flex: 1;"
              placeholder="Select analysis process"
            >
              <el-option
                v-for="workflow in workflowsSorted"
                :key="workflow.id"
                :label="`${workflow.name} v${workflow.version}`"
                :value="workflow.id"
              />
            </el-select>
            <el-tooltip content="Select different analysis processes, and the system will use the agents and steps corresponding to the process for analysis." placement="top">
              <el-icon style="margin-left: 8px; color: #909399; cursor: help;"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
        </el-form-item>
      </div>
      
      <el-form :model="params" label-width="120px">
        <el-form-item label="target rate of return">
          <el-input-number v-model="params.target_profit_pct" :min="5" :max="100" :step="5" />
          <span class="unit">%</span>
        </el-form-item>
        <el-form-item label="Analyze the view on overweighting">
          <el-switch v-model="params.include_add_position" />
        </el-form-item>

        <el-divider content-position="left">
          <el-checkbox v-model="enableCapitalAnalysis">Enable funding risk analysis</el-checkbox>
        </el-divider>

        <template v-if="enableCapitalAnalysis">
          <el-alert
            v-if="hasAccountCapital"
            type="success"
            :closable="false"
            style="margin-bottom: 12px"
          >
            Data has been automatically obtained from the capital account, total investment funds: ¥{{ (accountSummary?.net_capital?.CNY || 0).toLocaleString() }}
          </el-alert>
          <el-alert
            v-else
            type="info"
            :closable="false"
            style="margin-bottom: 12px"
          >
            No capital account has been set up. Please enter the total amount of funds manually or go to the position page to set up a capital account.
          </el-alert>
          <el-form-item label="Total amount of investment funds">
            <el-input-number
              v-model="params.total_capital"
              :min="10000"
              :max="100000000"
              :step="10000"
              :precision="0"
              :controls="false"
              style="width: 200px"
            />
            <span class="unit">Yuan</span>
            <span class="tip" v-if="!hasAccountCapital">Used to calculate position proportion and risk exposure</span>
          </el-form-item>
          <el-form-item label="Maximum position of a single stock">
            <el-input-number v-model="params.max_position_pct" :min="5" :max="100" :step="5" />
            <span class="unit">%</span>
          </el-form-item>
          <el-form-item label="maximum loss tolerance">
            <el-input-number v-model="params.max_loss_pct" :min="1" :max="50" :step="1" />
            <span class="unit">%</span>
          </el-form-item>
        </template>
      </el-form>
    </div>

    <!-- Analysis failure prompt -->
    <div v-if="analysisResult && analysisResult.status === 'failed'" class="analysis-failed">
      <el-alert type="error" :closable="false">
        <template #title>Analysis failed</template>
        <template #default>
          <p>{{ formatErrorMessage(analysisResult.error_message, 'An error occurred during analysis, please try again later.') }}</p>
          <el-button type="primary" size="small" @click="resetAnalysis" style="margin-top: 10px">
            Reanalyze
          </el-button>
        </template>
      </el-alert>
    </div>

    <!-- AI Connection error message -->
    <div v-else-if="analysisResult && isAIConnectionError" class="analysis-error">
      <el-alert type="warning" :closable="false">
        <template #title>AI Service connection exception</template>
        <template #default>
          <p>{{ analysisResult.action_reason }}</p>
          <p style="margin-top: 8px; color: #909399; font-size: 12px">
            💡 Please check: 1. Whether the network connection is normal; 2. Whether the API Key has been configured; 3. Whether the API service is available
          </p>
          <el-button type="primary" size="small" @click="resetAnalysis" style="margin-top: 10px">
            Reanalyze
          </el-button>
        </template>
      </el-alert>
    </div>

    <!-- Analysis results display -->
    <div v-else-if="analysisResult" class="analysis-result">
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

      <el-divider content-position="left">Analyze results</el-divider>

      <!-- current conclusion -->
      <div class="overview-panel">
        <div class="overview-header">
          <h3>current conclusion</h3>
          <div class="conclusion-content markdown-content" v-html="renderMarkdown(userView.conclusion || 'No conclusion yet')"></div>
        </div>
        <div class="context-chip" v-if="userView.position_context">
          {{ userView.position_context }}
        </div>
      </div>

      <div class="uncertainty-card" v-if="userView.uncertainty_note">
        <h4>uncertainty statement</h4>
        <p>{{ userView.uncertainty_note }}</p>
      </div>

      <!-- Funding risk indicator (if enabled) -->
      <div v-if="analysisResult.risk_metrics" class="risk-metrics-section">
        <h4><el-icon><WalletFilled /></el-icon> Position risk analysis</h4>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="Position proportion">
            <span :class="getRiskLevelClass(analysisResult.risk_metrics.risk_level)">
              {{ analysisResult.risk_metrics.position_pct?.toFixed(2) }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="Position market value">
            ¥{{ analysisResult.risk_metrics.position_value?.toLocaleString() }}
          </el-descriptions-item>
          <el-descriptions-item label="Maximum loss amount">
            <span class="loss">¥{{ analysisResult.risk_metrics.max_loss_amount?.toLocaleString() }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="Impact on total funds">
            <span class="loss">{{ analysisResult.risk_metrics.max_loss_impact_pct?.toFixed(2) }}%</span>
          </el-descriptions-item>
          <el-descriptions-item label="Amount that can be increased">
            <span class="profit">¥{{ analysisResult.risk_metrics.available_add_amount?.toLocaleString() }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="risk level">
            <el-tag :type="getRiskTagType(analysisResult.risk_metrics.risk_level)" size="small">
              {{ getRiskLevelText(analysisResult.risk_metrics.risk_level) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <p class="risk-summary">{{ analysisResult.risk_metrics.risk_summary }}</p>
      </div>

      <!-- Research Addendum -->
      <el-collapse>
        <el-collapse-item title="View study appendix" name="detail">
          <template v-if="appendixSections.length > 0">
            <div
              v-for="section in appendixSections"
              :key="section.key"
              class="appendix-section"
            >
              <h4>{{ section.title }}</h4>
              <div class="detailed-analysis markdown-content" v-html="renderMarkdown(section.content)"></div>
            </div>
          </template>
          <div
            v-else
            class="detailed-analysis markdown-content"
            v-html="renderMarkdown(analysisResult.detailed_analysis || 'No detailed analysis yet')"
          ></div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">close</el-button>
        <el-button
          v-if="!analysisResult"
          type="primary"
          :loading="loading"
          @click="handleAnalyze"
        >
          Start analysis
        </el-button>
        <el-button
          v-else
          type="primary"
          @click="resetAnalysis"
        >
          Reanalyze
        </el-button>
      </span>
    </template>

    <!-- History dialog box -->
    <PositionAnalysisHistoryDialog
      v-model="showHistoryDialog"
      :position="position"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { WarningFilled, WalletFilled, Loading, Refresh, Clock, InfoFilled } from '@element-plus/icons-vue'
import { portfolioApi, type PositionItem, type PositionAnalysisResult, type PositionAnalysisParams, type AccountSummary } from '@/api/portfolio'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'
import { getMarketByStockCode } from '@/utils/market'
import { workflowApi, isSelectableAnalysisWorkflow, type WorkflowSummary } from '@/api/workflow'
import PositionAnalysisHistoryDialog from './PositionAnalysisHistoryDialog.vue'

// Configure marked options
// marked The configuration has been @/utils/markdown Unified management
// Markdown Rendering function (the backend has been converted to Markdown format, and the frontend renders directly)
const renderMarkdown = (content: string) => {
  if (!content) return ''
  
  try {
    return safeMarkdown(content)
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}

/**
 * Convert backend/network error messages into user-friendly Chinese prompts that can be understood.
 * Special processing is done for common current limiting, network, timeout and other situations.
 */
const formatErrorMessage = (err: any, defaultMsg = 'Operation failed, please try again later'): string => {
  if (!err) return defaultMsg
  const msg = String(err?.message || err?.data?.message || err?.error_message || err || '').toLowerCase()

  // Current limiting class
  if (
    msg.includes('429') ||
    msg.includes('rate_limit') ||
    msg.includes('rate limit') ||
    msg.includes('tokens limit') ||
    msg.includes('rate_limited') ||
    msg.includes('Access restrictions') ||
    msg.includes('Current limiting')
  ) {
    return 'There are currently many people using AI analysis and the service is busy. Please try again later. (Tip: Avoid initiating multiple analyzes in a short period of time)'
  }

  // Network/Connectivity
  if (
    msg.includes('network error') ||
    msg.includes('connection error') ||
    msg.includes('failed to fetch') ||
    msg.includes('Connection failed') ||
    msg.includes('network error')
  ) {
    return 'Network connection failed, please check your network status and try again.'
  }

  // timeout class
  if (msg.includes('timeout') || msg.includes('timeout')) {
    return 'The request timed out, please try again later. If it occurs frequently, please contact the administrator.'
  }

  // Insufficient balance/limit
  if (
    msg.includes('insufficient balance') ||
    msg.includes('quota') ||
    msg.includes('Insufficient balance') ||
    msg.includes('Insufficient quota')
  ) {
    return 'AI Analysis: The quota is insufficient. Please contact the administrator to replenish the quota and try again.'
  }

  // Authentication/Permission Class
  if (msg.includes('401') || msg.includes('403') || msg.includes('unauthorized') || msg.includes('No permission')) {
    return 'Login has expired, please refresh the page and log in again and try again.'
  }

  // Server error
  if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('server error')) {
    return 'The server is temporarily unavailable, please try again later.'
  }

  // Return the original message (if it is Chinese and readable, return it directly)
  const original = String(err?.message || err?.data?.message || err?.error_message || defaultMsg)
  if (/[\u4e00-\u9fa5]/.test(original) && original.length < 100) {
    return original
  }

  return defaultMsg
}

const props = defineProps<{
  modelValue: boolean
  position: PositionItem | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const router = useRouter()
const loading = ref(false)
const refreshing = ref(false)
const analysisResult = ref<PositionAnalysisResult | null>(null)
const enableCapitalAnalysis = ref(false)
const accountSummary = ref<AccountSummary | null>(null)
const showHistoryDialog = ref(false)

// Process selection
const workflows = ref<WorkflowSummary[]>([])
const selectedWorkflowId = ref<string>('')

const parseVersion = (v: string): number[] => {
  const parts = String(v || '0.0.0').split('.')
  return parts.map(p => parseInt(p, 10) || 0)
}

const workflowsSorted = computed(() => {
  const arr = workflows.value.filter(
    (w: WorkflowSummary) => isSelectableAnalysisWorkflow(w, 'position_analysis')
  )
  arr.sort((a, b) => {
    const vA = a.version || ''
    const vB = b.version || ''
    const verA = parseVersion(vA)
    const verB = parseVersion(vB)
    for (let i = 0; i < Math.max(verA.length, verB.length); i++) {
      const numA = verA[i] || 0
      const numB = verB[i] || 0
      if (numA !== numB) return numB - numA
    }
    return 0
  })
  return arr
})

// Asynchronous analysis related status
const analysisId = ref<string | null>(null)
const analysisStatus = ref<string>('idle')  // idle, pending, processing, completed, failed

const hasAccountCapital = computed(() => {
  const netCapital = accountSummary.value?.net_capital?.CNY || 0
  return netCapital > 0
})
const isEtfPosition = computed(() => {
  if (!props.position) return false
  return props.position.market === 'CN' && getMarketByStockCode(props.position.code) === 'ETF'
})
const securityCodeLabel = computed(() => isEtfPosition.value ? 'ETF code' : 'Stock code')
const securityNameLabel = computed(() => isEtfPosition.value ? 'ETF Name' : 'Stock name')
const industryLabel = computed(() => isEtfPosition.value ? 'Product classification' : 'Industry')
const industryValue = computed(() => {
  if (!props.position) return '-'
  return isEtfPosition.value ? 'ETF/fund' : (props.position.industry || 'unknown')
})
const params = ref<PositionAnalysisParams>({
  research_depth: 'Standard',
  include_add_position: true,
  target_profit_pct: 20,
  total_capital: 100000,    // Default 100,000
  max_position_pct: 30,     // Default 30%
  max_loss_pct: 10          // Default 10%
})

// Load capital account information
const loadAccountSummary = async () => {
  try {
    const res = await portfolioApi.getAccountSummary()
    if (res.success && res.data) {
      accountSummary.value = res.data
      // If there is a funding account, automatically enable funding analysis and populate the data
      // Use net deposits (total invested funds) instead of total assets
      const netCapital = res.data.net_capital?.CNY || 0
      if (netCapital > 0) {
        enableCapitalAnalysis.value = true
        params.value.total_capital = netCapital
        params.value.max_position_pct = res.data.settings?.max_position_pct || 30
        params.value.max_loss_pct = res.data.settings?.max_loss_pct || 10
      }
    }
  } catch (e) {
    console.error('Failed to load fund account', e)
  }
}

// reset state
// Load available workflows
const loadWorkflows = async () => {
  try {
    const data = await workflowApi.listAll()
    workflows.value = data
    const targetWorkflows = workflowsSorted.value
    if (targetWorkflows.length > 0) {
      const defaultWf = targetWorkflows.find((w: WorkflowSummary) => w.is_default)
      selectedWorkflowId.value = defaultWf ? defaultWf.id : targetWorkflows[0].id
    }
  } catch (e) {
    console.error('Failed to load workflow list:', e)
  }
}

watch(visible, (val) => {
  if (val) {
    // When opening the dialog box, reset the state first and then load the data.
    // Important: Previous analysis results must be cleared first to avoid displaying cached data for other stocks.
    analysisResult.value = null
    analysisId.value = null
    analysisStatus.value = 'idle'

    // Load capital account information and existing analysis reports
    loadAccountSummary()
    loadExistingAnalysis()
    loadWorkflows()
  }
})

// Clear related parameters when fund analysis is not enabled
watch(enableCapitalAnalysis, (val) => {
  if (!val) {
    params.value.total_capital = undefined
  } else {
    // Restore funding account data or default values (use net deposits instead of total assets)
    const netCapital = accountSummary.value?.net_capital?.CNY || 0
    params.value.total_capital = netCapital > 0 ? netCapital : 100000
  }
})

// Check if it is an AI connection error
const isAIConnectionError = computed(() => {
  if (!analysisResult.value) return false
  const reason = analysisResult.value.action_reason || ''
  return reason.includes('AI service') ||
         reason.includes('Connection failed') ||
         reason.includes('Connection error') ||
         reason.includes('AI Analysis is temporarily unavailable') ||
         (analysisResult.value.confidence === 0 && reason.includes('error'))
})

// User version display content (unified display of user_view field after compliance)
const userView = computed(() => analysisResult.value?.user_view || {
  conclusion: analysisResult.value?.action_reason || 'No conclusion yet',
  position_context: '',
  key_points: [] as string[],
  risk_focus: [] as string[],
  watch_items: [] as string[],
  uncertainty_note: ''
})

// Research appendix (only sections with content are displayed)
const appendixSections = computed(() =>
  (analysisResult.value?.appendix_sections || []).filter(section => section?.content)
)

// Perform analysis (asynchronous mode)
const handleAnalyze = async () => {
  if (!props.position) return

  loading.value = true

  try {
    // Step 1: Check whether there is a single stock analysis report cache
    const cacheRes = await portfolioApi.checkStockAnalysisCache(
      props.position.code,
      props.position.market
    )

    if (cacheRes.success && cacheRes.data) {
      const hasCache = cacheRes.data.has_cache

      // If there is no cache, prompt the user to choose
      if (!hasCache) {
        loading.value = false
        try {
          await ElMessageBox.confirm(
            'There is currently no single stock analysis report cache available.\n\n' +
            'It is recommended to conduct single stock analysis first to obtain more accurate position analysis results.\n\n' +
            'You can choose:\n' +
            '• Continue analysis: conduct position analysis directly (without using single stock analysis report)\n' +
            '• Go to single stock analysis first: Jump to the single stock analysis page for analysis first.',
            'Tip: Missing single stock analysis report',
            {
              confirmButtonText: 'Continue analysis',
              cancelButtonText: 'Let s go to single stock analysis first',
              type: 'warning',
              distinguishCancelAndClose: true
            }
          )
          // User selection"Continue analysis", Continue the analysis process
        } catch (action: any) {
          // User selection"Let s go to single stock analysis first"or close the dialog
          if (action === 'cancel') {
            // Jump to the single stock analysis page and bring the stock code parameters
            const marketName = props.position.market === 'CN'
              ? getMarketByStockCode(props.position.code)
              : 'A shares'
            router.push(`/analysis/single?stock_code=${props.position.code}&market=${marketName}`)
            visible.value = false // Close current dialog box
          }
          return // Cancel analysis and do not perform subsequent processes
        }
      } else {
        // There is a cache and cache information can be displayed (optional)
        const ageMinutes = cacheRes.data.cache_age_minutes || 0
        const ageText = ageMinutes < 60 
          ? `${ageMinutes}minutes ago` 
          : `${Math.floor(ageMinutes / 60)}hours ago`
        console.log(`Use cached reports (${ageText}) `)
      }
    }

    // Step 2: Submit the analysis task
    loading.value = true
    analysisStatus.value = 'pending'

    // 🔥 Set position_type according to position source: simulate position -> simulated, User positions -> real
    const positionType = props.position.source === 'paper' ? 'simulated' : 'real'
    const analysisParams = {
      ...params.value,
      position_type: positionType,
      workflow_id: selectedWorkflowId.value || undefined
    }

    const res = await portfolioApi.analyzePositionByCode(
      props.position.code,
      props.position.market,
      analysisParams
    )

    console.log('[Start analysis] response received:', res)
    if (res.success && res.data) {
      // Set analysis ID and status
      analysisId.value = res.data.analysis_id || null
      analysisStatus.value = res.data.status || 'pending'
      
      console.log('[Start analysis] settings analysisId:', analysisId.value, 'status:', analysisStatus.value)

      if (res.data.status === 'completed' && analysisId.value) {
        // Completed reports can be obtained directly
        await fetchAnalysisResult(analysisId.value)
        ElMessage.success('There are recent analysis reports')
      } else {
        // The task has been submitted and will not be polled automatically. The user can refresh it manually.
        ElMessage.success(res.data.message || 'The analysis task has been submitted. It is expected to take 2-5 minutes. Please click later."Manually refresh status"View results')
      }
    } else {
      ElMessage.error(formatErrorMessage(res.message, 'Failed to submit analysis task'))
      analysisStatus.value = 'failed'
    }
  } catch (error: any) {
    // If it is a cancellation operation of MessageBox, no error will be displayed.
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(formatErrorMessage(error, 'Failed to submit analysis task'))
      analysisStatus.value = 'failed'
    }
  } finally {
    loading.value = false
  }
}



// Get analysis results
const fetchAnalysisResult = async (id: string) => {
  try {
    const res = await portfolioApi.getPositionAnalysisStatus(id)
    if (res.success && res.data) {
      analysisResult.value = res.data
      analysisStatus.value = res.data.status || 'completed'
    }
  } catch (error) {
    console.error('Failed to obtain analysis results:', error)
  }
}

// Manually refresh status
const manualRefreshStatus = async () => {
  if (!analysisId.value) {
    console.warn('[Manually refresh status] analysisId Empty and cannot be refreshed')
    ElMessage.warning('The analysis task ID does not exist, please restart the analysis.')
    return
  }

  console.log('[Manually refresh status] Start refreshing,analysisId:', analysisId.value)
  refreshing.value = true
  try {
    const res = await portfolioApi.getPositionAnalysisStatus(analysisId.value)
    console.log('[Manually refresh status] response received:', res)
    if (res.success && res.data) {
      analysisStatus.value = res.data.status || 'unknown'

      if (res.data.status === 'completed') {
        analysisResult.value = res.data
        ElMessage.success('Analysis completed!')
      } else if (res.data.status === 'failed') {
        ElMessage.error(formatErrorMessage(res.data.error_message, 'Analysis failed, please try again later'))
      } else {
        ElMessage.info(`Current status: ${res.data.status}`)
      }
    } else {
      console.error('[Manually refresh status] Response failed:', res)
      ElMessage.error(formatErrorMessage(res.message, 'Failed to get analysis status'))
    }
  } catch (error: any) {
    console.error('[Manually refresh status] Request failed:', error)
    ElMessage.error(formatErrorMessage(error, 'Failed to refresh status, please try again later'))
  } finally {
    refreshing.value = false
  }
}

// Load existing analysis report
// Load existing analysis report
// Note: analysisResult should be cleared before calling this function to avoid displaying cached data of other stocks.
const loadExistingAnalysis = async () => {
  if (!props.position) return

  try {
    // 🔥 Pass the source parameter according to the position source: simulate a position -> paper, User positions -> real
    const source = props.position.source === 'paper' ? 'paper' : 'real'
    const res = await portfolioApi.getLatestPositionAnalysis(
      props.position.code,
      props.position.market,
      source
    )
    // Only update status when the backend returns valid data
    // If res.data is null, it means that there is no analysis report for this stock, and the status is idle
    if (res.success && res.data) {
      analysisId.value = res.data.analysis_id
      analysisStatus.value = res.data.status || 'unknown'

      if (res.data.status === 'completed') {
        analysisResult.value = res.data
      } else if (res.data.status === 'pending' || res.data.status === 'processing') {
        // There is ongoing analysis and no automatic polling. Users can manually refresh to view the status.
        ElMessage.info('An analysis task in progress is detected, please click"Manually refresh status"View the latest progress')
      }
    }
    // If res.data is null, no operation is performed and the idle state reset in the previous watch is maintained.
  } catch (error) {
    console.error('Failed to load existing analysis report:', error)
  }
}

// Reanalyze
const resetAnalysis = () => {
  analysisResult.value = null
  analysisId.value = null
  analysisStatus.value = 'idle'
}

// Auxiliary methods related to risk levels
const getRiskLevelClass = (level?: string) => {
  const map: Record<string, string> = {
    low: 'risk-low',
    medium: 'risk-medium',
    high: 'risk-high',
    critical: 'risk-critical'
  }
  return map[level || ''] || ''
}

const getRiskTagType = (level?: string): 'success' | 'warning' | 'danger' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    low: 'success',
    medium: 'warning',
    high: 'danger',
    critical: 'danger'
  }
  return map[level || ''] || 'info'
}

const getRiskLevelText = (level?: string) => {
  const map: Record<string, string> = {
    low: 'low risk',
    medium: 'medium risk',
    high: 'high risk',
    critical: 'extremely high risk'
  }
  return map[level || ''] || 'unknown'
}
</script>

<style scoped>
.position-info {
  margin-bottom: 16px;
}

.profit { color: #f56c6c; } /* Red indicates profit (Chinese stock market norm) */
.loss { color: #67c23a; } /* Green indicates loss (Chinese stock market norm) */

/* Risk warning style */
.risk-disclaimer {
  margin: 24px 0;
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
  align-items: flex-start;
  gap: 12px;
  font-size: 15px;
  line-height: 1.6;
}

.disclaimer-icon {
  font-size: 24px;
  color: #ff6b00;
  flex-shrink: 0;
  animation: pulse 2s ease-in-out infinite;
  margin-top: 2px;
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

.disclaimer-text ul {
  margin: 8px 0;
  padding-left: 20px;
}

.disclaimer-text li {
  margin-bottom: 6px;
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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

.analysis-status {
  margin: 16px 0;

  ul {
    margin: 8px 0 0 20px;
    padding: 0;
    li {
      margin: 4px 0;
    }
  }

  .is-loading {
    animation: rotating 2s linear infinite;
    margin-right: 8px;
  }
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.analysis-params {
  margin: 16px 0;
}

.unit {
  margin-left: 8px;
  color: #909399;
}

.overview-panel {
  background: linear-gradient(135deg, #f8fafc 0%, #eef4ff 100%);
  border: 1px solid #dbe7ff;
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 20px;
}

.overview-header h3 {
  margin: 0 0 10px 0;
  font-size: 20px;
  color: #1f2937;
}

.overview-header p {
  margin: 0;
  font-size: 15px;
  line-height: 1.9;
  color: #334155;
}

.context-chip {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.85);
  color: #475569;
  line-height: 1.8;
}

.assessment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.assessment-card {
  background: #f8fafc;
  border: 1px solid #e5edf6;
  border-radius: 14px;
  padding: 18px;
}

.assessment-card h4,
.uncertainty-card h4 {
  margin: 0 0 10px 0;
  font-size: 15px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 4px;
}

.bullet-list {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  line-height: 1.8;
}

.bullet-list li + li {
  margin-top: 8px;
}

.uncertainty-card {
  margin-bottom: 20px;
  padding: 16px 18px;
  border-radius: 14px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.uncertainty-card p {
  margin: 0;
  color: #7c2d12;
  line-height: 1.8;
}

.appendix-section {
  padding: 12px 0;
  border-bottom: 1px solid #ebeef5;
}

.appendix-section:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.appendix-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

@media (max-width: 900px) {
  .assessment-grid {
    grid-template-columns: 1fr;
  }
}

.detailed-analysis {
  line-height: 1.6;
  color: #606266;
}

.markdown-content {
  line-height: 1.6;
  color: #606266;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: bold;
  color: #303133;
}

.markdown-content :deep(h1) { font-size: 20px; }
.markdown-content :deep(h2) { font-size: 18px; }
.markdown-content :deep(h3) { font-size: 16px; }
.markdown-content :deep(h4) { font-size: 14px; }

.markdown-content :deep(p) {
  margin: 8px 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
}

.markdown-content :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-content :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-content :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-content :deep(blockquote) {
  border-left: 4px solid #409eff;
  padding-left: 12px;
  margin: 12px 0;
  color: #606266;
}

.markdown-content :deep(strong) {
  font-weight: bold;
  color: #303133;
}

/* Fund risk indicator style */
.risk-metrics-section {
  margin: 16px 0;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.risk-metrics-section h4 {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #303133;
}

.risk-summary {
  margin-top: 8px;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}

.risk-low { color: #67c23a; }
.risk-medium { color: #e6a23c; }
.risk-high { color: #f56c6c; }
.risk-critical { color: #f56c6c; font-weight: bold; }

.tip {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
</style>

