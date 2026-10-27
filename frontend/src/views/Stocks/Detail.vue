<template>
  <div class="stock-detail-redesign">

    <!-- ════════ 1. Top: Stock Overview + Operation entrance ════════ -->
    <StockOverview
      :code="code"
      :stock-name="stockName"
      :market-label="marketLabel"
      :is-etf="isEtf"
      :quote="quote"
      :etf-basics="etfBasics"
      :is-fav="isFav"
      :refresh-text="refreshText"
      :sync-status="syncStatus"
      :sync-loading="syncLoading"
      :clear-cache-loading="clearCacheLoading"
      @refresh="refreshMockQuote"
      @analyze="onAnalyze"
      @sync="showSyncDialog"
      @paper-trading="goPaperTrading"
      @toggle-favorite="onToggleFavorite"
      @clear-cache="clearCache"
      @go-position-analysis="goToPositionAnalysis"
      @add-position="showAddPositionDialog"
      @go-trade-review="goToTradeReview"
      @go-trade-review-history="goToReviewHistory"
      @go-api-guide="goToApiGuide"
    />

    <!-- ════════ 2. Smart Assistant main entrance (immediately at the top, highlighted) ════════ -->
    <AssistantHero
      :code="code"
      :stock-name="stockName"
      :has-analysis="assistantHasAnalysis"
      :has-position="assistantHasPosition"
      :has-review="assistantHasReview"
      :has-fundamentals="assistantHasFundamentals"
      :has-kline="assistantHasKline"
      @ask="handleAssistantHeroAsk"
    />

    <!-- ════════ 3. Research path (sticky navigation) ════════ -->
    <ResearchFlow
      :steps="researchFlowSteps"
      :active-key="activeFlowKey"
      @step-click="handleFlowStepClick"
    />

    <!-- ════════ 4. K line + core indicators ════════ -->
    <div class="main-grid" id="kline-section">
      <KlineChart
        :title="klineCardTitle"
        :category="klineCategory"
        :values="klineValues"
        :volumes="klineVolumes"
        :period="period"
        :period-options="periodOptions"
        :kline-source="klineSource"
        :last-k-time="lastKTime"
        :last-k-close="lastKClose"
        @update-period="handlePeriodChange"
      />
      <CoreMetrics
        :basics="basics"
        :financial-snapshot="financialSnapshot"
        :factor-warning-entries="detailFactorWarningEntries"
        :factor-diagnostic-entries="detailFactorDiagnosticEntries"
      />
    </div>

    <!-- ════════ 5. Single stock analysis results ════════ -->
    <AnalysisResultCard
      :analysis-status="analysisStatus"
      :analysis-progress="analysisProgress"
      :analysis-message="analysisMessage"
      :last-analysis="lastAnalysis"
      :last-task-info="lastTaskInfo"
      :one-sentence-conclusion="oneSentenceConclusion"
      :report-keys="reportKeys"
      :history-count="analysisHistoryCount"
      @analyze="onAnalyze"
      @view-reports="showReportsDialog = true"
      @open-report="openReport"
      @view-history="goToAnalysisHistory"
    />

    <!-- ════════ 6. Position analysis + Transaction review (tab switching) ════════ -->
    <PositionReviewTabs
      :position-summary="positionSummary"
      :review-summary="reviewSummary"
      :position-data="positionData"
      :review-history="reviewHistory"
      :position-history-count="positionHistoryCount"
      @go-position-analysis="goToPositionAnalysis"
      @go-trade-review="goToTradeReview"
      @view-position-task-detail="viewPositionTaskDetail"
      @view-review-task-detail="viewReviewTaskDetail"
      @view-position-history="goToPositionHistory"
      @view-review-history="goToReviewHistory"
      @select-review-item="selectReviewItem"
    />

    <!-- ════════ 7. Intelligent assistant dialogue area ════════ -->
    <AssistantChat
      ref="assistantChatRef"
      v-model:messages="assistantMessages"
      :code="code"
      :stock-name="stockName"
      :loaded-modules="assistantLoadedModules"
      :initial-prompt="assistantInitialPrompt"
      :loading="assistantLoading"
      input-placeholder="Enter a question, such as: Combining analysis and holdings, what should I focus on tracking next?"
      @ask="handleAssistantAsk"
    />

    <!-- ════════ 8. Fundamentals + News ════════ -->
    <BottomSection
      :is-etf="isEtf"
      :basics="basics"
      :financial-snapshot="financialSnapshot"
      :etf-basics="etfBasics"
      :financial-raw-sections="financialRawSections"
      :news-items="newsItems"
      :news-filter="newsFilter"
      :news-loading="newsLoading"
      :news-source="newsSource"
      @news-filter-change="(v: string) => newsFilter = v"
    />

    <!-- back to top -->
    <BackToTop :show-after="600" />

    <!-- Add position dialog -->
    <AddPositionDialog
      v-model:visible="addPositionDialogVisible"
      :initial-data="addPositionInitialData"
      @success="onAddPositionSuccess"
    />

    <!-- ════════ Dialog box (retain original logic) ════════ -->

    <!-- Detailed Report Dialog -->
    <el-dialog
      v-model="showReportsDialog"
      title="📊 Detailed analysis report"
      width="80%"
      :close-on-click-modal="false"
      class="reports-dialog"
    >
      <el-tabs v-model="activeReportTab" type="border-card">
        <el-tab-pane
          v-for="key in reportKeys"
          :key="key"
          :label="formatReportName(key)"
          :name="key"
        >
          <div class="report-content">
            <el-scrollbar height="500px">
              <div class="markdown-body" v-html="renderMarkdown(getReportContent(lastAnalysis?.reports?.[key]))"></div>
            </el-scrollbar>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="showReportsDialog = false">close</el-button>
        <el-button type="primary" @click="exportReport">Export report</el-button>
      </template>
    </el-dialog>

    <!-- Data synchronization dialog box -->
    <el-dialog
      v-model="syncDialogVisible"
      :title="syncDialogTitle"
      width="500px"
    >
      <el-form :model="syncForm" label-width="120px">
        <el-form-item :label="securityCodeLabel">
          <el-input v-model="code" disabled />
        </el-form-item>
        <el-form-item :label="isEtf ? 'ETF Name' : 'Stock name'">
          <el-input v-model="stockName" disabled />
        </el-form-item>
        <el-form-item label="Sync content">
          <el-checkbox-group v-model="syncForm.syncTypes">
            <el-checkbox label="realtime">Real-time quotes</el-checkbox>
            <el-checkbox label="historical">Historical market data</el-checkbox>
            <el-checkbox v-if="!isEtf" label="financial">financial data</el-checkbox>
            <el-checkbox label="basic">Basic data</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="data source">
          <el-radio-group v-model="syncForm.dataSource">
            <el-radio label="tushare" :disabled="!availableSyncSources.tushare">Tushare</el-radio>
            <el-radio label="akshare" :disabled="!availableSyncSources.akshare">AKShare</el-radio>
            <el-radio v-if="!isJdyunMode()" label="qmt" :disabled="!availableSyncSources.qmt">QMT</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Historical data days" v-if="syncForm.syncTypes.includes('historical')">
          <el-input-number v-model="syncForm.days" :min="1" :max="3650" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">
            (Up to 3650 days, about 10 years)
          </span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="syncDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleSync" :loading="syncLoading">
          Start syncing
        </el-button>
      </template>
    </el-dialog>

    <!-- Review details dialog box -->
    <el-dialog
      v-model="reviewDetailVisible"
      title="Review details"
      width="800px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="reviewDetailLoading" class="detail-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>Loading...</span>
      </div>
      <div v-else-if="currentReviewDetail" class="review-detail-content">
        <!-- Transaction Summary -->
        <el-descriptions title="Transaction Summary" :column="3" border size="small" class="section">
          <el-descriptions-item label="Stock code">{{ currentReviewDetail.trade_info?.code }}</el-descriptions-item>
          <el-descriptions-item label="Position holding days">{{ currentReviewDetail.trade_info?.holding_days }}day</el-descriptions-item>
          <el-descriptions-item label="Profit and loss amount">
            <span :class="getTotalPnl() >= 0 ? 'positive' : 'negative'">
              {{ formatPnlValue(getTotalPnl()) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="average buying price">{{ currentReviewDetail.trade_info?.avg_buy_price?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="average selling price">{{ currentReviewDetail.trade_info?.avg_sell_price?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="Yield">
            <span :class="getTotalPnlPct() >= 0 ? 'positive' : 'negative'">
              {{ formatPct(getTotalPnlPct()) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="handling fee" :span="3">{{ currentReviewDetail.trade_info?.total_commission?.toFixed(2) }}Yuan</el-descriptions-item>
        </el-descriptions>

        <!-- Review conclusion -->
        <div class="section">
          <h4 class="section-title">Review conclusion</h4>
          <div class="summary markdown-content" v-html="renderMarkdown(currentReviewDetail.ai_review?.summary)"></div>
        </div>

        <!-- Advantages and Disadvantages -->
        <el-row :gutter="16" class="section">
          <el-col :span="12">
            <div class="analysis-card strengths">
              <h4><el-icon><CircleCheck /></el-icon> Things done well</h4>
              <div class="markdown-content" v-html="renderMarkdown((currentReviewDetail.ai_review?.strengths || []).join('\n\n'))"></div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="analysis-card weaknesses">
              <h4><el-icon><Warning /></el-icon> exposed issues</h4>
              <div class="markdown-content" v-html="renderMarkdown((currentReviewDetail.ai_review?.weaknesses || []).join('\n\n'))"></div>
            </div>
          </el-col>
        </el-row>

        <!-- Review improvements -->
        <div class="section" v-if="currentReviewDetail.ai_review?.suggestions?.length">
          <h4 class="section-title"><el-icon><Pointer /></el-icon> Key points for subsequent improvements</h4>
          <div class="suggestions markdown-content" v-html="renderMarkdown((currentReviewDetail.ai_review?.suggestions || []).join('\n\n'))"></div>
        </div>

        <!-- Detailed analysis -->
        <el-collapse class="section">
          <el-collapse-item title="Time to review" name="timing" v-if="currentReviewDetail.ai_review?.timing_analysis">
            <div class="markdown-content" v-html="renderMarkdown(currentReviewDetail.ai_review?.timing_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Position review" name="position" v-if="currentReviewDetail.ai_review?.position_analysis">
            <div class="markdown-content" v-html="renderMarkdown(currentReviewDetail.ai_review?.position_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Emotional review" name="emotion" v-if="currentReviewDetail.ai_review?.emotion_analysis">
            <div class="markdown-content" v-html="renderMarkdown(currentReviewDetail.ai_review?.emotion_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Attribution review" name="attribution" v-if="currentReviewDetail.ai_review?.attribution_analysis">
            <div class="markdown-content" v-html="renderMarkdown(currentReviewDetail.ai_review?.attribution_analysis)"></div>
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button @click="reviewDetailVisible = false">close</el-button>
      </template>
    </el-dialog>

  </div>
</template>


<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, CircleCheck, Warning, Pointer } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'
import { stocksApi } from '@/api/stocks'
import { assistantApi, type AssistantThreadItem } from '@/api/assistant'
import { ApiClient } from '@/api/request'
import {
  stockSyncApi,
  type SingleStockSyncResponse,
  type StockSyncTaskStatus,
} from '@/api/stockSync'
import { clearAllCache } from '@/api/cache'
import { use as echartsUse } from 'echarts/core'
import { CandlestickChart } from 'echarts/charts'

import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { favoritesApi } from '@/api/favorites'
import { useAuthStore } from '@/stores/auth'
import type { StockInfo } from '@/types/analysis'
import { getFactorDiagnosticEntries, getFactorWarningEntries } from '@/utils/factorPresentation'
import { loadManualSyncSourceState, type ManualSyncDataSource } from '@/utils/dataSource'
import { isJdyunMode } from '@/utils/config'
import { getReportName } from '@/utils/reportPresentation'
import { getTaskList, getTaskDetail, TaskType, TaskStatus } from '@/api/unifiedTasks'
import { reviewApi } from '@/api/review'
import { portfolioApi } from '@/api/portfolio'

// New version of stock details page sub-component
import StockOverview from './components/StockOverview.vue'
import AssistantHero from './components/AssistantHero.vue'
import ResearchFlow from './components/ResearchFlow.vue'
import KlineChart from './components/KlineChart.vue'
import CoreMetrics from './components/CoreMetrics.vue'
import AnalysisResultCard from './components/AnalysisResultCard.vue'
import PositionReviewTabs from './components/PositionReviewTabs.vue'
import AssistantChat from './components/AssistantChat.vue'
import BottomSection from './components/BottomSection.vue'
import BackToTop from './components/BackToTop.vue'
import AddPositionDialog from '@/views/Portfolio/components/AddPositionDialog.vue'


echartsUse([CandlestickChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, TitleComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const STOCK_SYNC_POLL_INTERVAL_MS = 2000
const STOCK_SYNC_POLL_MAX_ATTEMPTS = 300
let stockDetailDisposed = false


// analysis status
const analysisStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
const analysisProgress = ref(0)
const analysisMessage = ref('')
const lastAnalysis = ref<any | null>(null)
const lastTaskInfo = ref<any | null>(null) // Save task information (including end_time, etc.)

// Report dialog box
const showReportsDialog = ref(false)
const activeReportTab = ref('')

const reportKeys = computed(() => Object.keys(lastAnalysis.value?.reports || {}))
const oneSentenceConclusion = computed(() => {
  const traderPlan = getReportContent(lastAnalysis.value?.reports?.trader_investment_plan)
  const conclusion = extractMarkdownSection(traderPlan, 'One sentence conclusion')
  return conclusion || lastAnalysis.value?.summary || '-'
})

// Stock code (obtained from route parameters)
watch(
  () => route.params.code,
  (value) => {
    if (String(value || '').trim()) {
      return
    }
    ElMessage.error('Stock code cannot be empty')
    router.push({ name: 'Dashboard' })
  },
  { immediate: true }
)

const code = computed(() => String(route.params.code || '').toUpperCase())
const symbol = computed(() => code.value.split('.')[0])  // Extract 6-digit code
const stockName = ref('')
const market = ref('')
const isFav = ref(false)

const ETF_CODE_PREFIXES = ['50', '51', '52', '56', '58', '15', '16', '18']

function isLikelyEtfCode(value: string): boolean {
  const text = String(value || '').trim()
  return /^\d{6}$/.test(text) && ETF_CODE_PREFIXES.some(prefix => text.startsWith(prefix))
}

const isEtf = computed(() => market.value === 'ETF' || isLikelyEtfCode(symbol.value))
const marketLabel = computed(() => isEtf.value ? 'ETF' : (market.value || '-'))
const securityName = computed(() => isEtf.value ? 'ETF' : 'stocks')
const securityCodeLabel = computed(() => `${securityName.value}code`)
const syncDialogTitle = computed(() => `sync${securityName.value}data`)
const klineCardTitle = computed(() => isEtf.value ? 'ETF price trend' : 'Price K line')

// ECharts K line configuration
const kOption = ref<EChartsOption>({
  grid: { left: 40, right: 20, top: 20, bottom: 40 },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'cross' }
  },
  xAxis: {
    type: 'category',
    data: [],
    boundaryGap: true,
    axisLine: { onZero: false }
  },
  yAxis: {
    scale: true,
    type: 'value'
  },
  dataZoom: [
    { type: 'inside', start: 70, end: 100 },
    { start: 70, end: 100 }
  ],
  series: [
    {
      type: 'candlestick',
      name: 'K line',
      data: [],
      itemStyle: {
        color: '#ef4444',
        color0: '#16a34a',
        borderColor: '#ef4444',
        borderColor0: '#16a34a'
      }
    }
  ]
})

const lastKTime = ref<string | null>(null)
const lastKClose = ref<number | null>(null)

// Quotation (initialization)
const quote = reactive({
  price: NaN,
  changePercent: NaN,
  open: NaN,
  high: NaN,
  low: NaN,
  prevClose: NaN,
  volume: NaN,
  amount: NaN,
  turnover: NaN,
  amplitude: NaN,
  tradeDate: null as string | null,
  turnoverDate: null as string | null,
  amplitudeDate: null as string | null,
  updatedAt: null as string | null
})

const lastRefreshAt = ref<Date | null>(null)
const refreshText = computed(() => lastRefreshAt.value ? `Refreshed ${lastRefreshAt.value.toLocaleTimeString()}` : 'Not refreshed')

// Sync status
const syncStatus = ref<any>(null)

// Data synchronization dialog box
const syncDialogVisible = ref(false)
const syncLoading = ref(false)

// Add position dialog
const addPositionDialogVisible = ref(false)
const addPositionInitialData = computed(() => ({
  code: code.value,
  name: stockName.value,
  market: isEtf.value ? 'ETF' : 'CN',
  cost_price: Number(quote.price) || undefined
}))
const availableSyncSources = reactive<Record<ManualSyncDataSource, boolean>>({
  tushare: true,
  akshare: true,
  qmt: true
})
const syncForm = reactive({
  syncTypes: ['realtime'],  // Real-time quotes are selected by default
  dataSource: 'tushare' as ManualSyncDataSource,
  days: 365
})

watch(isEtf, (value) => {
  if (value) {
    syncForm.syncTypes = syncForm.syncTypes.filter(type => type !== 'financial')
  }
}, { immediate: true })

// clear cache
const clearCacheLoading = ref(false)

// Show sync dialog
function showSyncDialog() {
  syncDialogVisible.value = true
}

// Display the Add Position dialog box
function showAddPositionDialog() {
  addPositionDialogVisible.value = true
}

function onAddPositionSuccess() {
  addPositionDialogVisible.value = false
  // Refresh position related data
  fetchPositionAnalysisSummary()
  fetchPositionData()
}

async function loadPreferredSyncDataSource() {
  try {
    const sourceState = await loadManualSyncSourceState()
    availableSyncSources.tushare = sourceState.availableSources.tushare
    availableSyncSources.akshare = sourceState.availableSources.akshare
    availableSyncSources.qmt = isJdyunMode() ? false : sourceState.availableSources.qmt

    if (sourceState.preferredSource) {
      // In JD Cloud mode, if the first choice is qmt, it will fall back
      if (isJdyunMode() && sourceState.preferredSource === 'qmt') {
        // fall through to default selection
      } else {
        syncForm.dataSource = sourceState.preferredSource
        return
      }
    }

    if (availableSyncSources.qmt) {
      syncForm.dataSource = 'qmt'
    } else if (availableSyncSources.akshare) {
      syncForm.dataSource = 'akshare'
    } else if (availableSyncSources.tushare) {
      syncForm.dataSource = 'tushare'
    }
  } catch (error) {
    console.warn('Failed to load synchronization data source priority, retain the current default value', error)
  }
}

const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const isTerminalStockSyncStatus = (status?: string): boolean => {
  return status === 'success' || status === 'success_with_errors' || status === 'failed'
}

const buildSingleSyncTaskMessage = (task: StockSyncTaskStatus, symbol: string): string => {
  const result = task.result as SingleStockSyncResponse | null | undefined
  if (!result) {
    return task.error || task.message || `stocks ${symbol} Sync failed`
  }

  const parts = [`stocks ${symbol} Data synchronization completed`]

  if (result.realtime_sync) {
    if (result.realtime_sync.success) {
      const dataSourceUsed = (result.realtime_sync as any).data_source_used
      if (dataSourceUsed && dataSourceUsed !== syncForm.dataSource) {
        parts.push(`Real-time market synchronization was successful (automatically switched to ${String(dataSourceUsed).toUpperCase()} data source)`)
      } else {
        parts.push('Real-time market synchronization successful')
      }
    } else {
      parts.push(`Real-time market synchronization failed: ${result.realtime_sync.error || 'unknown error'}`)
    }
  }

  if (result.historical_sync) {
    parts.push(result.historical_sync.success ? `historical data ${result.historical_sync.records || 0} Article` : `Historical data synchronization failed: ${result.historical_sync.error || 'unknown error'}`)
  }
  if (result.financial_sync) {
    parts.push(result.financial_sync.success ? 'Financial data synchronization successful' : `Financial data synchronization failed: ${result.financial_sync.error || 'unknown error'}`)
  }
  if (result.basic_sync) {
    parts.push(result.basic_sync.success ? 'Basic data synchronization successful' : `Basic data synchronization failed: ${result.basic_sync.error || 'unknown error'}`)
  }

  return parts.join('；')
}

const waitForStockSyncTask = async (taskId: string): Promise<StockSyncTaskStatus> => {
  for (let attempt = 0; attempt < STOCK_SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
    if (stockDetailDisposed) {
      throw new Error('The page has been left, stop waiting for synchronization results')
    }

    const res = await stockSyncApi.getTaskStatus(taskId)
    if (res.success && isTerminalStockSyncStatus(res.data.status)) {
      return res.data
    }

    await sleep(STOCK_SYNC_POLL_INTERVAL_MS)
  }

  throw new Error('The synchronization task execution timed out, please refresh the page later to view the results.')
}

const monitorSingleSyncTask = async (taskId: string, symbol: string) => {
  try {
    const task = await waitForStockSyncTask(taskId)
    if (stockDetailDisposed) return

    const message = buildSingleSyncTaskMessage(task, symbol)
    if (task.status === 'success') {
      ElMessage.success(message)
    } else if (task.status === 'success_with_errors') {
      ElMessage.warning(message)
    } else {
      ElMessage.error(message)
    }

    await Promise.all([
      fetchQuote(),
      fetchFundamentals(),
      fetchFinancials(),
      fetchKline(),
      fetchSyncStatus(),
    ])
  } catch (error: any) {
    if (!stockDetailDisposed && error?.message !== 'The page has been left, stop waiting for synchronization results') {
      ElMessage.error(error?.message || 'Synchronization result query failed, please refresh the page later to view')
    }
  }
}
// Perform synchronization
async function handleSync() {
  if (syncForm.syncTypes.length === 0) {
    ElMessage.warning('Please select at least one sync content')
    return
  }

  syncLoading.value = true
  try {
    const res = await stockSyncApi.syncSingle({
      symbol: code.value,
      sync_realtime: syncForm.syncTypes.includes('realtime'),
      sync_historical: syncForm.syncTypes.includes('historical'),
      sync_financial: syncForm.syncTypes.includes('financial'),
      sync_basic: syncForm.syncTypes.includes('basic'),
      data_source: syncForm.dataSource,
      days: syncForm.days
    })

    if (res.success) {
      ElMessage.success(`stocks ${code.value} The synchronization task has been submitted and is being executed in the background`)
      syncDialogVisible.value = false
      void monitorSingleSyncTask(res.data.task_id, code.value)
    } else {
      ElMessage.error(res.message || 'Sync failed')
    }
  } catch (error: any) {
    console.error('Sync failed:', error)
    ElMessage.error(error.message || 'Synchronization failed, please try again later')
  } finally {
    syncLoading.value = false
  }
}

async function refreshMockQuote() {
  // Instead, call the backend interface to obtain real data.
  await fetchQuote()
}

// clear cache
async function clearCache() {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear all caches? After clearing, you need to re-obtain the data from the data source.',
      'clear cache',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    clearCacheLoading.value = true
    await clearAllCache()
    ElMessage.success('Cache cleared, data is being refreshed...')

    // Refresh current page data
    await Promise.all([
      fetchQuote(),
      fetchFundamentals(),
      fetchFinancials(),
      fetchKline(),
      fetchNews()
    ])

    ElMessage.success('Data has been refreshed')
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Clear cache failed:', error)
      ElMessage.error(error.message || 'Clear cache failed')
    }
  } finally {
    clearCacheLoading.value = false
  }
}

async function fetchQuote() {
  // 🔥 Parameter validation: Make sure the ticker is not empty
  if (!code.value) {
    console.warn('The stock code is empty, skip getting quotes')
    return
  }

  try {
    const res = await stocksApi.getQuote(code.value)
    const d: any = (res as any)?.data || {}
    // The backend is snake_case, the frontend status is camelCase, and the mapping is done here
    quote.price = Number(d.price ?? d.close ?? quote.price)
    quote.changePercent = Number(d.change_percent ?? quote.changePercent)
    quote.open = Number(d.open ?? quote.open)
    quote.high = Number(d.high ?? quote.high)
    quote.low = Number(d.low ?? quote.low)
    quote.prevClose = Number(d.prev_close ?? quote.prevClose)
    quote.volume = Number.isFinite(d.volume) ? Number(d.volume) : quote.volume
    quote.amount = Number.isFinite(d.amount) ? Number(d.amount) : quote.amount
    quote.turnover = Number.isFinite(d.turnover_rate) ? Number(d.turnover_rate) : quote.turnover
    quote.amplitude = Number.isFinite(d.amplitude) ? Number(d.amplitude) : quote.amplitude

    // 🔥 Get data date (used to mark non-today data)
    quote.tradeDate = d.trade_date || null  // Transaction date (for volume and value)
    quote.turnoverDate = d.turnover_rate_date || d.trade_date || null
    quote.amplitudeDate = d.amplitude_date || d.trade_date || null
    quote.updatedAt = d.updated_at || null  // 🔥 Data update time

    if (d.name) stockName.value = d.name
    market.value = d.market || (isLikelyEtfCode(symbol.value) ? 'ETF' : market.value)
    lastRefreshAt.value = new Date()
  } catch (e) {
    console.error('Failed to get quote', e)
  }
}

const etfBasics = reactive({
  fundType: '',
  trackIndex: '',
  fundScale: '' as string | number,
  fundShare: '' as string | number,
  fundShareDate: '',
  management: '',
  custodian: '',
  managementFee: null as string | number | null,
  custodianFee: null as string | number | null,
  unitNav: NaN,
  accumNav: NaN,
  navGrowthRate: null as string | number | null,
  premiumDiscountRate: null as string | number | null,
  latestNavDate: '',
  purchaseStatus: '',
  redemptionStatus: '',
  marketPrice: NaN,
  updatedAt: ''
})

async function fetchFundamentals() {
  try {
    const res = await stocksApi.getFundamentals(code.value)
    const f: any = (res as any)?.data || {}
    // Fundamental snapshot mapping (subject to the background)
    if (f.name) stockName.value = f.name
    market.value = f.market || (isLikelyEtfCode(symbol.value) ? 'ETF' : market.value)

    if (f.security_type === 'ETF' || market.value === 'ETF' || isLikelyEtfCode(symbol.value)) {
      detailFactorDiagnostics.value = {}
      detailFactorWarnings.value = {}
      etfBasics.fundType = f.fund_type || f.industry || ''
      etfBasics.trackIndex = f.track_index || f.sector || ''
      etfBasics.fundScale = f.fund_scale || ''
      etfBasics.fundShare = f.fund_share || ''
      etfBasics.fundShareDate = f.fund_share_date || ''
      etfBasics.management = f.management || ''
      etfBasics.custodian = f.custodian || ''
      etfBasics.managementFee = f.management_fee ?? null
      etfBasics.custodianFee = f.custodian_fee ?? null
      etfBasics.unitNav = Number.isFinite(f.unit_nav) ? Number(f.unit_nav) : NaN
      etfBasics.accumNav = Number.isFinite(f.accum_nav) ? Number(f.accum_nav) : NaN
      etfBasics.navGrowthRate = f.nav_growth_rate ?? null
      etfBasics.premiumDiscountRate = f.premium_discount_rate ?? null
      etfBasics.latestNavDate = f.latest_nav_date || ''
      etfBasics.purchaseStatus = f.purchase_status || ''
      etfBasics.redemptionStatus = f.redemption_status || ''
      etfBasics.marketPrice = Number.isFinite(f.market_price) ? Number(f.market_price) : NaN
      etfBasics.updatedAt = f.updated_at || ''
      return
    }

    basics.industry = f.industry || basics.industry
    basics.sector = f.sector || basics.sector || '—'
    // Backend total_mv unit: 100 million yuan, converted here to yuan to coordinate with the amount formatting function
    basics.marketCap = Number.isFinite(f.total_mv) ? Number(f.total_mv) * 1e8 : basics.marketCap
    // Use pe_ttm first, then pe
    basics.pe = Number.isFinite(f.pe_ttm) ? Number(f.pe_ttm) : (Number.isFinite(f.pe) ? Number(f.pe) : basics.pe)
    // 🔥 Newly added: PB (price to book ratio)
    basics.pb = Number.isFinite(f.pb) ? Number(f.pb) : basics.pb
    // 🔥 New: PS (price-to-sales ratio) - use ps_ttm first, then ps
    basics.ps = Number.isFinite(f.ps_ttm) ? Number(f.ps_ttm) : (Number.isFinite(f.ps) ? Number(f.ps) : basics.ps)
    // ROE and debt ratio
    basics.roe = Number.isFinite(f.roe) ? Number(f.roe) : basics.roe
    const ff: any = f
    basics.debtRatio = Number.isFinite(ff.debt_ratio) ? Number(ff.debt_ratio) : basics.debtRatio
    basics.dividendYield = Number.isFinite(ff.dividend_yield) ? Number(ff.dividend_yield) : basics.dividendYield
    basics.currentRatio = Number.isFinite(ff.current_ratio) ? Number(ff.current_ratio) : basics.currentRatio
    basics.reportPeriod = ff.report_period || basics.reportPeriod
    detailFactorDiagnostics.value = f.factor_diagnostics || {}
    detailFactorWarnings.value = f.factor_warnings || {}

    // Get the real-time identification of PE/PB
    basics.peIsRealtime = ff.pe_is_realtime || false
    basics.peSource = ff.pe_source || ''
    basics.peUpdatedAt = ff.pe_updated_at || null
  } catch (e) {
    console.error('Failed to get fundamentals', e)
  }
}

async function fetchFinancials() {
  if (isLikelyEtfCode(symbol.value) || market.value === 'ETF') {
    financialRawSections.value = []
    return
  }

  try {
    const res = await stocksApi.getFinancials(code.value, { includeRaw: true })
    const d: any = (res as any)?.data || {}
    const summary: any = d.summary || {}
    const rawData: Record<string, any[]> = d.raw_data || {}

    basics.dividendYield = Number.isFinite(summary.dividend_yield) ? Number(summary.dividend_yield) : basics.dividendYield
    basics.currentRatio = Number.isFinite(summary.current_ratio) ? Number(summary.current_ratio) : basics.currentRatio
    basics.reportPeriod = summary.report_period || d.report_period || basics.reportPeriod
    basics.roe = Number.isFinite(summary.roe) ? Number(summary.roe) : basics.roe
    basics.debtRatio = Number.isFinite(summary.debt_to_assets) ? Number(summary.debt_to_assets) : basics.debtRatio
    if (Object.keys(detailFactorDiagnostics.value || {}).length === 0 && d.factor_diagnostics) {
      detailFactorDiagnostics.value = d.factor_diagnostics
    }
    if (Object.keys(detailFactorWarnings.value || {}).length === 0 && d.factor_warnings) {
      detailFactorWarnings.value = d.factor_warnings
    }

    financialSnapshot.annDate = summary.ann_date || d.ann_date || ''
    financialSnapshot.dataSource = summary.data_source || d.data_source || ''
    financialSnapshot.grossMargin = Number.isFinite(summary.gross_margin) ? Number(summary.gross_margin) : NaN
    financialSnapshot.netprofitMargin = Number.isFinite(summary.netprofit_margin) ? Number(summary.netprofit_margin) : NaN
    financialSnapshot.revenue = Number.isFinite(summary.revenue) ? Number(summary.revenue) : NaN
    financialSnapshot.netProfit = Number.isFinite(summary.net_profit) ? Number(summary.net_profit) : NaN
    financialSnapshot.nCashflowAct = Number.isFinite(summary.n_cashflow_act) ? Number(summary.n_cashflow_act) : NaN
    financialSnapshot.totalAssets = Number.isFinite(summary.total_assets) ? Number(summary.total_assets) : NaN
    financialSnapshot.totalLiab = Number.isFinite(summary.total_liab) ? Number(summary.total_liab) : NaN

    financialRawSections.value = Object.entries(rawData)
      .filter(([, items]) => Array.isArray(items) && items.length > 0)
      .map(([key, items]) => ({
        key,
        label: financialRawLabels[key] || key,
        count: items.length,
      }))
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'object' ? detail?.message : detail
    if (msg) {
      ElMessage.warning(`${msg}, Please click Sync Data to obtain`)
    } else {
      console.error('Failed to get financial details', e)
    }
  }
}

async function fetchSyncStatus() {
  try {
    const res = await ApiClient.get('/api/stock-data/sync-status/quotes')
    const d: any = (res as any)?.data || {}
    syncStatus.value = d
  } catch (e) {
    console.warn('Failed to get sync status', e)
  }
}

let timer: any = null

let authReadyPromise: Promise<void> | null = null

async function ensureAuthReady() {
  if (authReadyPromise) {
    await authReadyPromise
    return
  }

  authReadyPromise = (async () => {
    const storedToken = localStorage.getItem('auth-token')
    const storedRefreshToken = localStorage.getItem('refresh-token')

    if (!authStore.token && storedToken) {
      authStore.token = storedToken
      authStore.isAuthenticated = true
    }

    if (!authStore.refreshToken && storedRefreshToken) {
      authStore.refreshToken = storedRefreshToken
    }

    if (authStore.token) {
      try {
        await authStore.checkAuthStatus()
      } catch (error) {
        console.warn('Detail page authentication status recovery failed:', error)
      }
    }
  })()

  try {
    await authReadyPromise
  } finally {
    authReadyPromise = null
  }
}

async function checkFavorite() {
  try {
    const res: any = await favoritesApi.check(code.value)
    const d: any = (res as any)?.data || {}
    isFav.value = !!d.is_favorite
  } catch (e) {
    console.warn('Check following failed', e)
  }
}
onMounted(async () => {
  stockDetailDisposed = false
  await ensureAuthReady()
  await loadPreferredSyncDataSource()

  // First load: open the backend (parallel)
  await Promise.all([
    fetchQuote(),
    fetchFundamentals(),
    fetchFinancials(),
    fetchKline(),
    fetchNews(),
    checkFavorite(),
    fetchLatestAnalysis(),  // Get the latest historical analysis report
    fetchSyncStatus(),  // Get sync status
    fetchPositionAnalysisSummary(),  // Get a summary of position analysis
    fetchTradeReviewSummary(),  // Get transaction review summary
    fetchReviewHistory(),  // Get review history list
    fetchPositionData()  // Get position data
  ])
  // Refresh quotes every 30 seconds
  timer = setInterval(fetchQuote, 30000)

  // Initialize the stock topic (depending on the report data above, placed after Promise.all)
  // Asynchronous execution does not block page rendering; downgrades to default theme on failure
  void initStockAssistantThread()
})
onUnmounted(() => {
  stockDetailDisposed = true
  if (timer) clearInterval(timer)
})



// K Line occupancy related
const periodOptions = ['day K','week K','month K']
const period = ref('day K')

const klineSource = ref<string | undefined>(undefined)
// 🔥 K Line raw data (for use by the new version of KlineChart component, including MA5/MA20 + trading volume)
const klineCategory = ref<string[]>([])
const klineValues = ref<number[][]>([])   // [open, close, low, high]
const klineVolumes = ref<number[]>([])

function periodLabelToParam(p: string): string {
  if (p.includes('5')) return '5m'
  if (p.includes('15')) return '15m'
  if (p.includes('60')) return '60m'
  if (p.includes('day')) return 'day'
  if (p.includes('week')) return 'week'
  if (p.includes('month')) return 'month'
  return '5m'
}

// Refresh the K line when the cycle switches
watch(period, () => { fetchKline() })

async function fetchKline() {
  await ensureAuthReady()

  try {
    const param = periodLabelToParam(period.value)
    const res = await stocksApi.getKline(code.value, param as any, 200, 'none')
    const d: any = (res as any)?.data || {}
    klineSource.value = d.source
    const items: any[] = Array.isArray(d.items) ? d.items : []

    const category: string[] = []
    const values: number[][] = [] // [open, close, low, high]

    for (const it of items) {
      const t = String(it.time || it.trade_time || it.trade_date || '')
      const o = Number(it.open ?? NaN)
      const h = Number(it.high ?? NaN)
      const l = Number(it.low ?? NaN)
      const c = Number(it.close ?? NaN)
      if (!Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c) || !t) continue
      category.push(t)
      values.push([o, c, l, h])
    }

    if (category.length) {
      lastKTime.value = category[category.length - 1]
      lastKClose.value = values[values.length - 1][1]
    }

    // 🔥 Raw data required to populate the new KlineChart component (including trading volume)
    klineCategory.value = category
    klineValues.value = values
    klineVolumes.value = items
      .map((it: any) => Number(it.volume ?? it.vol ?? 0))
      .filter((_v: number, idx: number) => idx < values.length)

    kOption.value = {
      ...kOption.value,
      xAxis: { type: 'category', data: category, boundaryGap: true, axisLine: { onZero: false } },
      series: [
        {
          type: 'candlestick',
          name: 'K line',
          data: values,
          itemStyle: {
            color: '#ef4444',
            color0: '#16a34a',
            borderColor: '#ef4444',
            borderColor0: '#16a34a'
          }
        }
      ]
    }
  } catch (e) {
    console.error('Failed to obtain K line', e)
  }
}


// News
const newsFilter = ref('all')
const newsItems = ref<any[]>([])
const newsLoading = ref(true)
const newsSource = ref<string | undefined>(undefined)

function cleanTitle(s: any): string {
  const t = String(s || '')
  return t.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim()
}

async function fetchNews() {
  newsLoading.value = true
  try {
    const res = await stocksApi.getNews(code.value, 30, 50, true)
    const d: any = (res as any)?.data || {}
    const itemsRaw: any[] = Array.isArray(d.items) ? d.items : []
    newsItems.value = itemsRaw.map((it: any) => {
      const title = cleanTitle(it.title || it.summary || it.name || '')
      const url = it.url || it.link || '#'
      const source = it.source || d.source || ''
      const time = it.time || it.pub_time || it.publish_time || it.pub_date || ''
      const type = it.type || 'news'
      return { title, url, source, time, type }
    })
    newsSource.value = d.source
  } catch (e) {
    console.error('Failed to get news', e)
  } finally {
    newsLoading.value = false
  }
}

// Fundamentals (mock)
const basics = reactive({
  industry: '-',
  sector: '-',
  marketCap: NaN,
  pe: NaN,
  pb: NaN,              // 🔥 New: Price to Book Ratio
  ps: NaN,              // 🔥 New: price-to-sales ratio
  roe: NaN,
  debtRatio: NaN,
  dividendYield: NaN,
  currentRatio: NaN,
  reportPeriod: '',
  peIsRealtime: false,  // PE Is it real-time data?
  peSource: '',         // PE Data source
  peUpdatedAt: null     // PE Update time
})

const financialSnapshot = reactive({
  annDate: '',
  dataSource: '',
  grossMargin: NaN,
  netprofitMargin: NaN,
  revenue: NaN,
  netProfit: NaN,
  nCashflowAct: NaN,
  totalAssets: NaN,
  totalLiab: NaN,
})

const financialRawSections = ref<Array<{ key: string; label: string; count: number }>>([])
const detailFactorDiagnostics = ref<StockInfo['factor_diagnostics']>({})
const detailFactorWarnings = ref<StockInfo['factor_warnings']>({})

const financialRawLabels: Record<string, string> = {
  income_statement: 'income statement',
  balance_sheet: 'balance sheet',
  cashflow_statement: 'cash flow statement',
  financial_indicators: 'financial indicators',
  main_business: 'Main business',
}

const detailFactorRow = computed<StockInfo>(() => ({
  symbol: symbol.value,
  name: stockName.value || code.value,
  market: market.value || 'CN',
  factor_diagnostics: detailFactorDiagnostics.value,
  factor_warnings: detailFactorWarnings.value,
}))

const detailFactorWarningEntries = computed(() => getFactorWarningEntries(detailFactorRow.value))
const detailFactorDiagnosticEntries = computed(() => getFactorDiagnosticEntries(detailFactorRow.value))

// Operation
function onAnalyze() {
  router.push({ name: 'SingleAnalysis', query: { stock: code.value } })
}
async function onToggleFavorite() {
  try {
    if (!isFav.value) {
      const payload = {
        symbol: symbol.value,
        stock_code: symbol.value,  // Compatible fields
        stock_name: stockName.value,
        market: market.value
      }
      await favoritesApi.add(payload)
      isFav.value = true
      ElMessage.success('Already added to watchlist')
    } else {
      await favoritesApi.remove(code.value)
      isFav.value = false
      ElMessage.success('Removed from following')
    }
  } catch (e: any) {
    console.error('Follow operation failed', e)
    ElMessage.error(e?.message || 'Follow operation failed')
  }
}

function goPaperTrading() {
  router.push({ name: 'PaperTradingHome', query: { code: code.value, market: market.value } })
}

// Get the latest historical analysis report
async function fetchLatestAnalysis() {
  try {
    const resp = await getTaskList({
      task_type: TaskType.STOCK_ANALYSIS,
      status: TaskStatus.COMPLETED,
      symbol: symbol.value,
      limit: 1
    })

    const tasks = resp?.data?.tasks || []

    if (tasks && tasks.length > 0) {
      const latestTask = tasks[0]

      // Save task information
      lastTaskInfo.value = latestTask

      // Get full results by task_id
      if (latestTask.task_id) {
        try {
          const detailResp = await getTaskDetail(latestTask.task_id)
          const result = detailResp?.data?.result
          if (result) {
            lastAnalysis.value = result
            analysisStatus.value = 'completed'
          }
        } catch (e) {
          console.warn('⚠️ Failed to obtain task results:', e)
        }
      }
    }
  } catch (e) {
    console.warn('⚠️ Failed to obtain historical analysis report:', e)
  }
}

// ============================================================================
// Position analysis summary & Transaction review summary
// Display the latest position analysis and transaction review conclusions related to the current stock on the details page
// Data source: /api/v2/tasks/list (filtered by task_type)+ /api/v2/tasks/{task_id} (get result)
// ============================================================================

interface PositionSnapshot {
  cost_price?: number
  current_price?: number
  quantity?: number
  unrealized_pnl?: number
  unrealized_pnl_pct?: number
  holding_days?: number
  position_pct?: number
}

interface PositionSummaryState {
  has: boolean
  taskId: string
  completedAt: string
  snapshot: PositionSnapshot | null
  action: string  // hold/buy/sell/reduce
  confidence: number | null
  conclusion: string
  keyPoints: string[]
}

interface ReviewSummaryState {
  has: boolean
  taskId: string
  completedAt: string
  riskLevel: string
  confidenceScore: number | null
  summary: string
  recommendation: string
  tradeCount: number | null
}

const positionSummary = reactive<PositionSummaryState>({
  has: false,
  taskId: '',
  completedAt: '',
  snapshot: null,
  action: '',
  confidence: null,
  conclusion: '',
  keyPoints: []
})

const reviewSummary = reactive<ReviewSummaryState>({
  has: false,
  taskId: '',
  completedAt: '',
  riskLevel: '',
  confidenceScore: null,
  summary: '',
  recommendation: '',
  tradeCount: null
})

// Review history list status
const reviewHistory = reactive<{
  loading: boolean
  items: any[]
  total: number
  selectedIndex: number
}>({
  loading: false,
  items: [],
  total: 0,
  selectedIndex: 0
})

// Review details pop-up window status
const reviewDetailVisible = ref(false)
const reviewDetailLoading = ref(false)
const currentReviewDetail = ref<any>(null)

// Determine whether the task belongs to the current stock (first match from the top-level symbol/code of the task, and then match from task_params)
function taskMatchesCurrentStock(task: any): boolean {
  const targetCode = symbol.value  // 6 Bit code (suffix removed)
  const targetCodeUpper = code.value  // Complete code (may include suffix such as SH)
  const params = task?.task_params || task?.params || {}
  const candidates = [
    task.symbol,        // Top-level field matching from list API
    task.code,
    params.symbol,      // Match from task_params
    params.code,
    params.stock_code,
    params.symbol_code
  ].filter(Boolean).map((v: any) => String(v).toUpperCase())
  return candidates.some(c => c === targetCode.toUpperCase() || c === targetCodeUpper.toUpperCase() || c.startsWith(targetCode.toUpperCase()))
}

async function fetchPositionAnalysisSummary() {
  try {
    const resp: any = await getTaskList({
      task_type: TaskType.POSITION_ANALYSIS,
      status: TaskStatus.COMPLETED,
      limit: 50
    })
    const tasks = resp?.data?.tasks || resp?.tasks || []
    // Filter out tasks related to the current stock and sort them in descending order of completion time
    const matched = tasks
      .filter((t: any) => taskMatchesCurrentStock(t))
      .sort((a: any, b: any) => {
        const ta = new Date(a.completed_at || a.created_at).getTime()
        const tb = new Date(b.completed_at || b.created_at).getTime()
        return tb - ta
      })

    if (matched.length === 0) {
      positionSummary.has = false
      return
    }

    const latest = matched[0]
    positionSummary.taskId = latest.task_id
    positionSummary.completedAt = latest.completed_at || latest.created_at

    // Get task details result
    try {
      const detail: any = await getTaskDetail(latest.task_id)
      const result = detail?.data?.result || detail?.result || {}
      const snapshot = result?.position_snapshot || null
      const ai = result?.ai_analysis || {}
      const userView = ai?.user_view || {}

      positionSummary.snapshot = snapshot ? {
        cost_price: snapshot.cost_price,
        current_price: snapshot.current_price,
        quantity: snapshot.quantity,
        unrealized_pnl: snapshot.unrealized_pnl,
        unrealized_pnl_pct: snapshot.unrealized_pnl_pct,
        holding_days: snapshot.holding_days,
        position_pct: snapshot.position_pct
      } : null
      positionSummary.action = ai.action || ''
      positionSummary.confidence = typeof ai.confidence === 'number' ? ai.confidence : null
      positionSummary.conclusion = userView.conclusion || ai.action_reason || ''
      positionSummary.keyPoints = Array.isArray(userView.key_points) ? userView.key_points : []
    } catch (e) {
      console.warn('⚠️ Failed to obtain position analysis details:', e)
    }

    positionSummary.has = true
  } catch (e) {
    console.warn('⚠️ Failed to obtain position analysis summary:', e)
    positionSummary.has = false
  }
}

async function fetchTradeReviewSummary() {
  try {
    const resp: any = await reviewApi.getTradeReviewSummary(code.value)
    const data = resp?.data || {}
    if (!data.has) {
      reviewSummary.has = false
      return
    }
    reviewSummary.taskId = data.task_id || ''
    reviewSummary.completedAt = data.completed_at || ''
    reviewSummary.summary = data.summary || ''
    reviewSummary.recommendation = data.recommendation || ''
    reviewSummary.riskLevel = data.risk_level || ''
    reviewSummary.confidenceScore = data.confidence_score ?? null
    reviewSummary.tradeCount = data.trade_count ?? null
    reviewSummary.has = true
  } catch (e) {
    console.warn('⚠️ Failed to obtain transaction review summary:', e)
    reviewSummary.has = false
  }
}

// Get the review history list of the current stock
async function fetchReviewHistory() {
  reviewHistory.loading = true
  try {
    const resp: any = await reviewApi.getReviewHistory({
      code: code.value,
      page: 1,
      pageSize: 20
    })
    reviewHistory.items = resp?.data?.items || []
    reviewHistory.total = resp?.data?.total || 0
    reviewHistory.selectedIndex = 0
  } catch (e) {
    console.warn('⚠️ Failed to obtain review history:', e)
    reviewHistory.items = []
    reviewHistory.total = 0
  } finally {
    reviewHistory.loading = false
  }
}

// Position data status
const positionData = reactive<{
  loading: boolean
  real: {
    has: boolean
    quantity: number
    cost_price: number
    current_price: number
    market_value: number
    unrealized_pnl: number
    unrealized_pnl_pct: number
  }
  paper: {
    has: boolean
    quantity: number
    cost_price: number
    current_price: number
    market_value: number
    unrealized_pnl: number
    unrealized_pnl_pct: number
  }
}>({
  loading: false,
  real: { has: false, quantity: 0, cost_price: 0, current_price: 0, market_value: 0, unrealized_pnl: 0, unrealized_pnl_pct: 0 },
  paper: { has: false, quantity: 0, cost_price: 0, current_price: 0, market_value: 0, unrealized_pnl: 0, unrealized_pnl_pct: 0 }
})

// Get current stock position information
async function fetchPositionData() {
  positionData.loading = true
  try {
    // Obtain real and simulated positions in parallel
    const [realRes, paperRes] = await Promise.all([
      portfolioApi.getPositions('real').catch(() => ({ success: false, data: { items: [] } })),
      portfolioApi.getPositions('paper').catch(() => ({ success: false, data: { items: [] } }))
    ])

    // Find the current firm position of a stock
    const realPositions = realRes?.data?.items || []
    const realMatch = realPositions.find((p: any) => p.code === symbol.value || p.code === code.value)
    if (realMatch) {
      positionData.real = {
        has: true,
        quantity: realMatch.quantity || 0,
        cost_price: realMatch.cost_price || 0,
        current_price: realMatch.current_price || 0,
        market_value: realMatch.market_value || 0,
        unrealized_pnl: realMatch.unrealized_pnl || 0,
        unrealized_pnl_pct: realMatch.unrealized_pnl_pct || 0
      }
    }

    // Find simulated positions for the current stock
    const paperPositions = paperRes?.data?.items || []
    const paperMatch = paperPositions.find((p: any) => p.code === symbol.value || p.code === code.value)
    if (paperMatch) {
      positionData.paper = {
        has: true,
        quantity: paperMatch.quantity || 0,
        cost_price: paperMatch.cost_price || 0,
        current_price: paperMatch.current_price || 0,
        market_value: paperMatch.market_value || 0,
        unrealized_pnl: paperMatch.unrealized_pnl || 0,
        unrealized_pnl_pct: paperMatch.unrealized_pnl_pct || 0
      }
    }
  } catch (e) {
    console.warn('⚠️ Failed to obtain position data:', e)
  } finally {
    positionData.loading = false
  }
}

// Select review history items
function selectReviewItem(index: number) {
  reviewHistory.selectedIndex = index
  const item = reviewHistory.items[index]
  if (item) {
    reviewSummary.taskId = item.review_id || item.task_id || ''
    reviewSummary.completedAt = item.completed_at || item.created_at || ''
    reviewSummary.summary = item.summary || ''
    reviewSummary.recommendation = item.recommendation || ''
    reviewSummary.riskLevel = item.risk_level || item.riskLevel || ''
    reviewSummary.confidenceScore = item.confidence_score ?? item.confidenceScore ?? null
    reviewSummary.tradeCount = item.trade_count ?? item.tradeCount ?? null
    reviewSummary.has = true
  }
}

// View review details (pop-up window display)
async function viewReviewDetail(reviewId?: string) {
  const targetId = reviewId || reviewSummary.taskId
  if (!targetId) {
    ElMessage.warning('No review details yet')
    return
  }
  
  reviewDetailVisible.value = true
  reviewDetailLoading.value = true
  currentReviewDetail.value = null
  
  try {
    const resp: any = await reviewApi.getReviewDetail(targetId)
    currentReviewDetail.value = resp?.data || resp
  } catch (e) {
    console.warn('⚠️ Failed to obtain review details:', e)
    ElMessage.error('Failed to obtain review details')
  } finally {
    reviewDetailLoading.value = false
  }
}

// Jump to the position analysis page (prefill the stock code through query)
function goToPositionAnalysis() {
  router.push({
    path: '/portfolio',
    query: {
      symbol: symbol.value,
      code: code.value
    }
  })
}

// Jump to the transaction review page
function goToTradeReview() {
  router.push({
    path: '/review',
    query: {
      symbol: symbol.value,
      code: code.value
    }
  })
}

// View position analysis task details (jump to task center)
function viewPositionTaskDetail() {
  if (positionSummary.taskId) {
    router.push({ path: '/tasks/unified', query: { task_id: positionSummary.taskId } })
  }
}

function viewReviewTaskDetail() {
  // Change to a pop-up window display on this page instead of jumping to the task center
  viewReviewDetail()
}

// Formatting functions related to position analysis (only required for the dialog box)

// Format profit and loss values
function formatPnlValue(pnl: any): string {
  const n = Number(pnl)
  if (!Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return `${sign}¥${n.toFixed(2)}`
}

// Get total profit and loss
function getTotalPnl(): number {
  if (!currentReviewDetail.value?.trade_info) return 0
  const info = currentReviewDetail.value.trade_info
  return (info.realized_pnl || 0) + (info.unrealized_pnl || 0)
}

// Get the total return
function getTotalPnlPct(): number {
  if (!currentReviewDetail.value?.trade_info) return 0
  const info = currentReviewDetail.value.trade_info
  return info.total_pnl_pct || 0
}

// Format percentage
function formatPct(pct: any): string {
  const n = Number(pct)
  if (!Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(2)}%`
}

// fmtConf Removed: Compliance requirements do not demonstrate confidence

// Format report name
function formatReportName(key: string): string {
  const isEtfAnalysis = Array.isArray(lastAnalysis.value?.analysts) && lastAnalysis.value.analysts.includes('etf_analyst')
  return getReportName(key, isEtfAnalysis)
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function extractMarkdownSection(content: string, heading: string): string {
  if (!content) return ''
  const headingPattern = escapeRegExp(heading)
  const match = content.match(new RegExp(`(?:^|\\n)#{1,6}\\s*${headingPattern}\\s*\\n([\\s\\S]*?)(?=\\n#{1,6}\\s+|$)`, 'i'))
  return match?.[1]?.trim() || ''
}

// 🔥 Extract report content (supports the content field in the object)
function getReportContent(reportData: any): string {
  if (!reportData) return ''
  
  // If it is a string, return it directly
  if (typeof reportData === 'string') {
    return reportData
  }
  
  // If it is an object, the content field is extracted first.
  if (typeof reportData === 'object') {
    if (reportData.content && typeof reportData.content === 'string') {
      return reportData.content
    }
    if (reportData.markdown && typeof reportData.markdown === 'string') {
      return reportData.markdown
    }
    if (reportData.judge_decision && typeof reportData.judge_decision === 'string') {
      return reportData.judge_decision
    }
  }

  return String(reportData)
}

// Open the specified report
function openReport(reportKey: string) {
  showReportsDialog.value = true
  activeReportTab.value = reportKey
}

// Export report
function exportReport() {
  if (!lastAnalysis.value?.reports) {
    ElMessage.warning('No reports can be exported yet')
    return
  }

  // Generate complete report in Markdown format
  let fullReport = `# ${code.value} Stock analysis report\n\n`

  // Format analysis time for reporting (compatible with completed_at / created_at / end_time)
  const reportTimeSrc = lastTaskInfo.value?.completed_at || lastTaskInfo.value?.created_at || lastTaskInfo.value?.end_time
  const reportTime = reportTimeSrc
    ? new Date(reportTimeSrc).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })
    : lastAnalysis.value?.analysis_date

  fullReport += `**Analysis time**: ${reportTime}\n`
  fullReport += `**research observation**: ${lastAnalysis.value.recommendation}\n\n`
  fullReport += `---\n\n`

  for (const [key, content] of Object.entries(lastAnalysis.value.reports)) {
    fullReport += `## ${formatReportName(key)}\n\n`
    fullReport += `${content}\n\n`
    fullReport += `---\n\n`
  }

  // Create download link
  const blob = new Blob([fullReport], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url

  // Use analysis date as file name (simplified format)
  const fileDate = lastAnalysis.value.analysis_date || new Date().toISOString().slice(0, 10)
  link.download = `${code.value}_analysis report_${fileDate}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)

  ElMessage.success('Report exported')
}

// ============================================================================
// New version details page: Research Path/Intelligent Assistant/Historical Navigation
// ============================================================================

// Study path steps (dynamically calculate status based on loaded data)
const researchFlowSteps = computed<{ key: string; title: string; desc: string; status: 'done' | 'active' | 'pending' }[]>(() => {
  return [
    {
      key: 'kline',
      title: 'Market trend',
      desc: 'K line + core indicators',
      status: klineValues.value.length > 0 ? 'done' : 'pending',
    },
    {
      key: 'analysis',
      title: 'single stock analysis',
      desc: 'AI research report',
      status: lastAnalysis.value ? 'done' : (analysisStatus.value === 'running' ? 'active' : 'pending'),
    },
    {
      key: 'position-review',
      title: 'Position holding and review',
      desc: 'Position status + Transaction Review',
      status: (positionSummary.has || reviewSummary.has) ? 'done' : 'pending',
    },
    {
      key: 'fundamentals',
      title: 'Fundamentals',
      desc: 'financial data + News',
      status: Number.isFinite(basics.pe) || Number.isFinite(financialSnapshot.revenue) ? 'done' : 'pending',
    },
    {
      key: 'assistant',
      title: 'Intelligent Assistant Interpretation',
      desc: 'Panorama covers all the above modules',
      status: 'active',
    },
  ]
})

// Research path currently active step (for ResearchFlow highlighting)
const activeFlowKey = ref<string>('')

function handleFlowStepClick(key: string) {
  activeFlowKey.value = key
  const idMap: Record<string, string> = {
    kline: 'kline-section',
    analysis: 'analysis-result-section',
    'position-review': 'position-review-section',
    fundamentals: 'bottom-section',
    assistant: 'assistant-chat',
  }
  const targetId = idMap[key]
  if (targetId) {
    const el = document.getElementById(targetId)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }
}

// Smart assistant chat status
const assistantMessages = ref<Array<{ role: 'user' | 'bot'; content: string }>>([])
const assistantLoading = ref(false)
const assistantInitialPrompt = ref('')
const assistantChatRef = ref<any>(null)

// Stock thread status
const stockAssistantThreadId = ref<string>('')
const stockAssistantThreadReady = ref(false)
const stockAssistantStreamController = ref<AbortController | null>(null)

// Loaded module (for assistant header display)
const assistantLoadedModules = computed(() => {
  const mods: string[] = []
  if (klineValues.value.length) mods.push('K line')
  if (lastAnalysis.value) mods.push('single stock analysis')
  if (positionSummary.has) mods.push('Position')
  if (reviewSummary.has) mods.push('Review')
  if (Number.isFinite(basics.pe) || Number.isFinite(financialSnapshot.revenue)) mods.push('Fundamentals')
  return mods
})

// Whether the assistant has loaded each module (for AssistantHero display)
const assistantHasAnalysis = computed(() => !!lastAnalysis.value)
const assistantHasPosition = computed(() => positionSummary.has)
const assistantHasReview = computed(() => reviewSummary.has)
const assistantHasFundamentals = computed(() => Number.isFinite(basics.pe) || Number.isFinite(financialSnapshot.revenue))
const assistantHasKline = computed(() => klineValues.value.length > 0)

// Handling Assistant Shortcut Issues (from AssistantHero)
function handleAssistantHeroAsk(prompt: string) {
  assistantInitialPrompt.value = prompt
}

// ════════ Stock theme initialization (docking with existing smart assistant module) ════════

const STALE_THRESHOLD_HOURS = 24

// Directory of available modules for single stock analysis reports (used to inject stock_scope for LLM on-demand adjustment tool to obtain complete content)
// Consistent with _ANALYST_LABELS in backend core/tools/implementations/assistant_ops/report_query.py
const STOCK_REPORT_MODULES = [
  { key: 'market_report', title: 'Market technical analysis', desc: 'K Line shape, technical indicators, support and pressure levels' },
  { key: 'fundamentals_report', title: 'fundamental research', desc: 'Financial data, valuation, industry position' },
  { key: 'news_report', title: 'Journalism Research', desc: 'Recent announcements, industry news, event driven' },
  { key: 'sentiment_report', title: 'sentiment analysis', desc: 'Social media public opinion, institutional views' },
  { key: 'trader_investment_plan', title: 'Research and integrate opinions', desc: 'Conclusions of multi-scenario research + research observation' },
  { key: 'research_team_decision', title: 'Research team conclusion', desc: 'Summary of team research observations after multi-scenario research' },
  { key: 'risk_management_decision', title: 'Risk review conclusion', desc: 'risk boundary + Follow-up observations' },
  { key: 'final_trade_decision', title: 'Comprehensive research conclusion', desc: 'Summary of final research observations' },
]

/** Initialize stock theme: create/get theme + Load historical messages + Automatically correlate reports */
async function initStockAssistantThread() {
  if (!code.value) return
  try {
    const title = `Equity research · ${code.value} ${stockName.value || ''}`.trim()
    const thread = await assistantApi.createThread(title)
    stockAssistantThreadId.value = thread.thread_id

    // Load historical messages (if there has been a previous conversation)
    const historyRes = await assistantApi.getThreadMessages(thread.thread_id)
    const hasHistory = !!(historyRes.messages && historyRes.messages.length > 0)
    if (hasHistory) {
      assistantMessages.value = historyRes.messages.map(m => ({
        role: m.role === 'user' ? 'user' as const : 'bot' as const,
        content: m.content,
      }))
    }

    // Automatically correlate reports (without blocking the main process)
    void autoLinkReports(thread)
    stockAssistantThreadReady.value = true

    // Only when entering for the first time (no historical messages), check the report timeliness and proactively remind the user
    if (!hasHistory) {
      checkStaleReportsAndRemind()
    }
  } catch (e) {
    console.warn('Failed to initialize stock assistant theme', e)
    // Downgrade on failure: users are still allowed to send messages, conversation_id is empty and the default topic is used
  }
}

/** Check the timeliness of the report. If there is an expired report, proactively push a bot message to remind the user to re-analyze it. */
function checkStaleReportsAndRemind() {
  const scope = buildStockScopeContext()
  const staleItems: string[] = []

  const stockReport = scope.reports?.stock_report
  if (stockReport?.is_stale) {
    staleItems.push(`Single stock analysis report (${stockReport.completed_at || 'unknown time'} Generated, expired approx. ${stockReport.stale_hours} hours)`)
  }

  const positionReport = scope.reports?.position_report
  if (positionReport?.is_stale) {
    staleItems.push(`Position analysis report (${positionReport.completed_at || 'unknown time'} Generated, expired approx. ${positionReport.stale_hours} hours)`)
  }

  const reviewData = scope.review_summary
  if (reviewData?.is_stale) {
    staleItems.push(`Transaction review report (${reviewData.completed_at || 'unknown time'} Generated, expired approx. ${reviewData.stale_hours} hours)`)
  }

  if (staleItems.length === 0) return

  const reminder = [
    `⚠️ The following reports have been detected as expired (more than ${STALE_THRESHOLD_HOURS} hours), I won t draw conclusions based on old reports:`,
    '',
    ...staleItems.map(s => `• ${s}`),
    '',
    'If you want me to interpret based on the latest data, please click the Reanalyze button of the corresponding module; or reply Reanalyze below, and I will guide you to initiate it.'
  ].join('\n')

  assistantMessages.value.push({ role: 'bot', content: reminder })
}

/** Automatically associate single stock analysis reports, position analysis reports, and transaction review reports to topics */
async function autoLinkReports(thread: AssistantThreadItem) {
  const threadId = thread.thread_id
  const existingKeys = new Set(
    (thread.report_refs || []).map(r => `${r.ref_type}:${r.report_key}`),
  )

  // Related single stock analysis report
  if (lastTaskInfo.value?.task_id) {
    const key = `stock_report:${lastTaskInfo.value.task_id}`
    if (!existingKeys.has(key)) {
      try {
        await assistantApi.attachThreadReport(threadId, 'stock_report', lastTaskInfo.value.task_id)
      } catch (e) {
        console.warn('Related single stock analysis report failed', e)
      }
    }
  }

  // Related position analysis report (you need to search candidates first to get analysis_id)
  if (positionSummary.has) {
    try {
      const candidates = await assistantApi.getThreadReportCandidates(
        threadId,
        'position_report',
        code.value,
        5,
      )
      const matched = candidates.items.find(
        item => (item.symbol || '').toUpperCase() === code.value.toUpperCase(),
      )
      if (matched) {
        const key = `position_report:${matched.report_key}`
        if (!existingKeys.has(key)) {
          await assistantApi.attachThreadReport(threadId, 'position_report', matched.report_key)
        }
      }
    } catch (e) {
      console.warn('Related position analysis report failed', e)
    }
  }

  // Related transaction review report (task_id is review_id, use task_id directly as report_key)
  if (reviewSummary.has && reviewSummary.taskId) {
    const key = `review_report:${reviewSummary.taskId}`
    if (!existingKeys.has(key)) {
      try {
        await assistantApi.attachThreadReport(threadId, 'review_report', reviewSummary.taskId)
      } catch (e) {
        console.warn('Related transaction review report failed', e)
      }
    }
  }
}

/** Build the stock context (injected into the backend system prompt via user_context.stock_scope) */
function buildStockScopeContext() {
  const now = Date.now()
  const parseTime = (s: string) => (s ? new Date(s).getTime() : 0)
  const calcStale = (ts: number) => {
    if (!ts) return { is_stale: false }
    const hours = Math.round((now - ts) / 3_600_000)
    return { is_stale: hours > STALE_THRESHOLD_HOURS, stale_hours: hours }
  }

  const scope: Record<string, any> = {
    code: code.value,
    stock_name: stockName.value,
    thread_id: stockAssistantThreadId.value,
    reports: {},
  }

  if (lastTaskInfo.value?.task_id) {
    const ts = parseTime(lastTaskInfo.value.completed_at || lastTaskInfo.value.created_at || '')
    // Inject report table of contents instead of truncating summary body, LLM passes get_report_detail(task_id, module_key) Get full content on demand
    const existingKeys = Object.keys(lastAnalysis.value?.reports || {})
    scope.reports.stock_report = {
      task_id: lastTaskInfo.value.task_id,
      completed_at: lastTaskInfo.value.completed_at || lastTaskInfo.value.created_at || '',
      ...calcStale(ts),
      available_modules: STOCK_REPORT_MODULES,
      existing_modules: existingKeys,
    }
  }

  if (positionSummary.has && positionSummary.taskId) {
    const ts = parseTime(positionSummary.completedAt)
    // No text is injected into the position report, LLM passes get_position_analysis(code, market) Get full content
    scope.reports.position_report = {
      analysis_id: positionSummary.taskId,
      completed_at: positionSummary.completedAt,
      ...calcStale(ts),
    }
  }

  if (reviewSummary.has) {
    const ts = parseTime(reviewSummary.completedAt)
    // No text is injected into the review report, LLM passes get_trade_review_detail(review_id) Get full content
    // Note: backend task_id is review_id (see trade_review_service.py:1908 Note)
    scope.review_summary = {
      task_id: reviewSummary.taskId,
      review_id: reviewSummary.taskId,  // task_id That is review_id
      completed_at: reviewSummary.completedAt,
      ...calcStale(ts),
      trade_count: reviewSummary.tradeCount ?? undefined,
    }
  }

  if (Number.isFinite(quote.price)) {
    scope.current_quote = {
      price: quote.price,
      change_percent: quote.changePercent,
    }
  }

  return scope
}

// Handle assistant sending issues (streaming LLM conversations, docking with existing smart assistant modules)
async function handleAssistantAsk(prompt: string) {
  if (!prompt.trim() || assistantLoading.value) return

  const conversationId = stockAssistantThreadId.value || undefined
  const stockScope = buildStockScopeContext()

  assistantLoading.value = true

  // Place an empty bot message for streaming append
  const botMsgIdx = assistantMessages.value.push({ role: 'bot', content: '' }) - 1
  let firstTokenReceived = false

  stockAssistantStreamController.value = assistantApi.chatStream(
    prompt,
    conversationId,
    undefined, // model, Use system default
    undefined, // model_config_id
    {
      onToken(content: string) {
        if (!firstTokenReceived) firstTokenReceived = true
        assistantMessages.value[botMsgIdx].content += content
      },
      onDone(data) {
        assistantLoading.value = false
        stockAssistantStreamController.value = null
        // If the server returns conversation_id (the topic is created for the first time), update the local
        if (data.conversation_id && !stockAssistantThreadId.value) {
          stockAssistantThreadId.value = data.conversation_id
        }
        // If the reply is empty (rare), give a friendly reminder
        if (!assistantMessages.value[botMsgIdx].content.trim()) {
          assistantMessages.value[botMsgIdx].content =
            'Sorry, I can t answer this question right now. Please try again later.'
        }
      },
      onError(msg: string) {
        assistantLoading.value = false
        stockAssistantStreamController.value = null
        if (!firstTokenReceived) {
          assistantMessages.value[botMsgIdx].content =
            `Sorry, an error occurred while processing your request:${msg}\n\n You can try again later, or go to the Smart Assistant home page to continue the conversation.`
        } else {
          assistantMessages.value[botMsgIdx].content +=
            `\n\n---\n⚠️ Response to interruption:${msg}`
        }
      },
    },
    {
      // extraPayload: Inject stock context via user_context
      assistant_role: 'general',
      user_context: {
        stock_scope: stockScope,
      },
    },
  )
}

// History navigation
function goToAnalysisHistory() {
  router.push({ path: '/tasks/unified', query: { type: 'stock_analysis', symbol: code.value } })
}

function goToPositionHistory() {
  router.push({ path: '/tasks/unified', query: { type: 'position_analysis', symbol: code.value } })
}

function goToReviewHistory() {
  router.push({ path: '/tasks/unified', query: { type: 'trade_review', symbol: code.value } })
}

function goToApiGuide() {
  router.push({ name: 'StockDataApiGuide', query: { code: code.value } })
}

// Analyze the number of historical records (simplified: inferred based on existing reports)
const analysisHistoryCount = computed(() => {
  // It can actually be obtained from the backend. Here we first use whether lastAnalysis exists as a prompt.
  return lastAnalysis.value ? 1 : 0
})

// Position analysis historical quantity
const positionHistoryCount = computed(() => {
  return positionSummary.has ? 1 : 0
})

// K Line cycle switching
function handlePeriodChange(p: string) {
  // Only update period, by watch(period) Automatically trigger fetchKline to avoid repeated requests
  period.value = p
}

</script>

<style scoped lang="scss">
.stock-detail {
  display: flex; flex-direction: column; gap: 16px;
}

/* ════════ New version of details page layout ════════ */
.stock-detail-redesign {
  display: flex;
  flex-direction: column;
  gap: 0; /* Subcomponent comes with margin-bottom */
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.main-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
  align-items: start;
}

@media (max-width: 1024px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

/* Review details dialog box style (reserved) */
.review-detail-content {
  .section {
    margin-bottom: 16px;
  }
  .section-title {
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 8px;
    color: var(--el-text-color-primary);
  }
  .summary {
    font-size: 14px;
    line-height: 1.7;
    color: var(--el-text-color-regular);
  }
  .analysis-card {
    padding: 12px;
    border-radius: 8px;
    background: var(--el-fill-color-light);
    h4 {
      font-size: 14px;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    &.strengths h4 { color: #16a34a; }
    &.weaknesses h4 { color: #ef4444; }
  }
  .suggestions {
    font-size: 13px;
    line-height: 1.7;
    color: var(--el-text-color-regular);
  }
  .positive { color: #ef4444; font-weight: 600; }
  .negative { color: #16a34a; font-weight: 600; }
}

.detail-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.reports-dialog {
  .report-content {
    min-height: 500px;
  }
}

.header { display: flex; justify-content: space-between; align-items: center; }
.title { display: flex; flex-direction: column; gap: 8px; }
.title-main { display: flex; align-items: center; gap: 12px; }
.title-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta-text { font-size: 12px; color: var(--el-text-color-secondary); }
.code { font-size: 22px; font-weight: 700; }
.name { font-size: 18px; color: var(--el-text-color-regular); }
.actions { display: flex; gap: 8px; }

.quote-card { border-radius: 12px; }
.quote { display: flex; flex-direction: column; gap: 8px; }
.price-row { display: flex; align-items: center; gap: 12px; }
.price { font-size: 32px; font-weight: 800; }
.change { font-size: 16px; font-weight: 700; }
.up { color: #e53935; }
.down { color: #16a34a; }
.stats { display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; margin-top: 6px; }
.stats .item { display: flex; flex-direction: column; font-size: 12px; color: var(--el-text-color-secondary); }
.stats .item b { color: var(--el-text-color-primary); font-size: 14px; }

.factor-hints {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.factor-hints-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.factor-hints-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.factor-hint-tag {
  cursor: help;
}

.factor-hint-popover {
  display: flex;
  flex-direction: column;
  gap: 6px;
  line-height: 1.6;
}

.factor-hint-popover-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.factor-hint-line {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.body { margin-top: 4px; }
.card-hd { display: flex; align-items: center; justify-content: space-between; }
.k-chart { height: 320px; }
.legend { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }

.news-card .news-list { display: flex; flex-direction: column; }
.news-item { padding: 10px 12px; border-bottom: 1px solid var(--el-border-color-lighter); transition: background-color .2s ease; }
.news-item:last-child { border-bottom: none; }
.news-item:hover { background: var(--el-fill-color-light); border-radius: 8px; }
.news-item .row { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.news-item .left { display: flex; align-items: flex-start; gap: 8px; flex: 1 1 auto; min-width: 0; }
.news-item .tag { flex: 0 0 auto; }
.news-item .title { font-weight: 600; display: flex; align-items: center; gap: 6px; flex: 1 1 auto; min-width: 0; }
.news-item .title a, .news-item .title span { color: var(--el-text-color-primary); text-decoration: none; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.news-item .title a:hover { text-decoration: underline; }
.news-item .ext { color: var(--el-text-color-placeholder); font-size: 14px; }
.news-item .title:hover .ext { color: var(--el-color-primary); }
.news-item .right { color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; margin-left: 8px; }
.news-item .meta { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }

.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.fact { display: flex; flex-direction: column; font-size: 12px; }
.fact b { font-size: 14px; color: var(--el-text-color-primary); }
.financial-card { margin-top: 12px; }
.raw-section-summary { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.raw-title { font-size: 12px; color: var(--el-text-color-secondary); }
.raw-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.raw-hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5; }

.quick-actions { display: flex; flex-direction: column; gap: 8px; }

@media (max-width: 1024px) {
  .stats { grid-template-columns: repeat(4, 1fr); }
  .header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .actions { flex-wrap: wrap; }
}

/* Report related styles */
.reports-section {
  margin-top: 8px;
}

.reports-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  margin-top: 8px;
}

.reports-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.reports-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.report-tag {
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  padding: 6px 12px;
}

.report-tag:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Report dialog style */
.reports-dialog :deep(.el-dialog__body) {
  padding: 0;
}

.report-content {
  padding: 20px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-primary);
}

.markdown-body h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 20px 0 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--el-border-color);
}

.markdown-body h2 {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 12px;
}

.markdown-body h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px;
}

.markdown-body p {
  margin: 8px 0;
}

.markdown-body ul, .markdown-body ol {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-body li {
  margin: 4px 0;
}

.markdown-body code {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
}

.markdown-body pre {
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-body blockquote {
  border-left: 4px solid var(--el-color-primary);
  padding-left: 12px;
  margin: 12px 0;
  color: var(--el-text-color-secondary);
}

.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

.markdown-body th, .markdown-body td {
  border: 1px solid var(--el-border-color);
  padding: 8px 12px;
  text-align: left;
}

.markdown-body th {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.analysis-detail-card .detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Analyze time metainformation */
.analysis-meta {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.analysis-meta .analysis-time {
  display: flex;
  align-items: center;
  gap: 6px;
}

.analysis-meta .el-icon {
  font-size: 14px;
}

/* Sync status prompt */
.sync-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 6px;
  border: 1px solid #bae6fd;
  font-size: 13px;
  color: #0369a1;
}

.sync-status .el-icon {
  font-size: 14px;
  color: #0284c7;
}

.sync-info {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

// ============================================================================
// Position Analysis Summary Card
// ============================================================================
.position-analysis-card {
  margin-top: 16px;
  border-left: 3px solid var(--el-color-primary);

  .card-hd {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .card-hd-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .card-hd-tag {
    margin-left: 4px;
    font-weight: normal;
  }

  .card-hd-actions {
    display: flex;
    gap: 4px;
  }

  .position-summary {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .snapshot-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    padding: 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  .snap-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .snap-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .snap-value {
    font-size: 15px;
    color: var(--el-text-color-primary);
  }

  .pnl-positive {
    color: var(--el-color-success);
  }

  .pnl-negative {
    color: var(--el-color-danger);
  }

  .ai-advice {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .advice-row {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
  }

  .advice-label {
    color: var(--el-text-color-secondary);
  }

  .advice-conclusion {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    padding: 10px 12px;
    background: var(--el-color-primary-light-9);
    border-left: 3px solid var(--el-color-primary);
    border-radius: 4px;
    font-size: 14px;
    line-height: 1.5;
    color: var(--el-text-color-primary);
  }

  .advice-icon {
    color: var(--el-color-primary);
    flex-shrink: 0;
    margin-top: 2px;
  }

  .advice-keypoints {
    padding: 10px 12px;
    background: var(--el-color-warning-light-9);
    border-left: 3px solid var(--el-color-warning);
    border-radius: 4px;
  }

  .keypoints-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-color-warning-dark);
    margin-bottom: 6px;
  }

  .keypoints-list {
    margin: 0;
    padding-left: 20px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-text-color-regular);
  }
}

// ============================================================================
// Transaction review summary card
// ============================================================================
.trade-review-card {
  margin-top: 16px;
  border-left: 3px solid var(--el-color-success);

  .card-hd {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .card-hd-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .card-hd-tag {
    margin-left: 4px;
    font-weight: normal;
  }

  .card-hd-actions {
    display: flex;
    gap: 4px;
  }

  .review-summary {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .review-meta {
    display: flex;
    gap: 24px;
    padding: 10px 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
  }

  .meta-label {
    color: var(--el-text-color-secondary);
  }

  .meta-value {
    color: var(--el-text-color-primary);
  }

  .review-conclusion,
  .review-recommendation {
    padding: 10px 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  .review-recommendation {
    background: var(--el-color-success-light-9);
  }

  .conclusion-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
  }

  .conclusion-text {
    font-size: 14px;
    line-height: 1.6;
    color: var(--el-text-color-primary);
  }
}

// ============================================================================
// Review details pop-up window
// ============================================================================
.detail-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 8px;
  color: var(--el-text-color-secondary);
}

.review-detail-content {
  .detail-section {
    margin-bottom: 24px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .content-box {
    padding: 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  .review-list {
    padding-left: 20px;
    margin: 0;

    li {
      margin-bottom: 8px;
      font-size: 14px;
      line-height: 1.6;
      color: var(--el-text-color-primary);

      &:last-child {
        margin-bottom: 0;
      }
    }
  }
}

.pnl-positive {
  color: var(--el-color-success) !important;
}

.pnl-negative {
  color: var(--el-color-danger) !important;
}

.positive {
  color: var(--el-color-success) !important;
}

.negative {
  color: var(--el-color-danger) !important;
}

// Complete review details
.review-detail-content {
  .section {
    margin-bottom: 20px;

    .section-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }

  .summary {
    padding: 12px;
    background: var(--el-fill-color-light);
    border-radius: 8px;
  }

  .analysis-card {
    padding: 16px;
    border-radius: 8px;
    background: var(--el-bg-color-page);

    h4 {
      margin: 0 0 12px;
      font-size: 14px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    &.strengths {
      background: var(--el-color-success-light-9);
      border: 1px solid var(--el-color-success-light-8);
    }

    &.weaknesses {
      background: var(--el-color-danger-light-9);
      border: 1px solid var(--el-color-danger-light-8);
    }
  }

  .suggestions {
    padding: 12px;
    background: var(--el-color-primary-light-9);
    border-radius: 8px;
  }

  .markdown-content {
    :deep(p) {
      margin: 0 0 8px;
      line-height: 1.6;
      color: var(--el-text-color-primary);

      &:last-child {
        margin-bottom: 0;
      }
    }

    :deep(ul), :deep(ol) {
      padding-left: 20px;
      margin: 0 0 8px;
    }

    :deep(li) {
      margin-bottom: 4px;
      line-height: 1.6;
    }
  }
}

// ============================================================================
// Position information card
// ============================================================================
.position-card {
  margin-bottom: 16px;

  .position-info {
    .position-section {
      margin-bottom: 16px;

      &:last-child {
        margin-bottom: 0;
      }
    }

    .position-section-title {
      margin-bottom: 10px;
    }

    .position-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 12px;

      .pos-item {
        text-align: center;

        .pos-label {
          display: block;
          font-size: 12px;
          color: var(--el-text-color-secondary);
          margin-bottom: 4px;
        }

        .pos-value {
          font-size: 14px;
          font-weight: 600;
          color: var(--el-text-color-primary);

          &.positive {
            color: #f56c6c;
          }

          &.negative {
            color: #67c23a;
          }
        }
      }
    }
  }
}
</style>
