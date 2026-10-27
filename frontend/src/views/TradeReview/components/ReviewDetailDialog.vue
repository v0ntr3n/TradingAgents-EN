<template>
  <el-dialog
    v-model="visible"
    :title="`Review details - ${report?.trade_info?.code || ''}`"
    width="900px"
    :close-on-click-modal="false"
  >
    <div v-loading="loading" class="review-detail">
      <!-- 🔄 Progress display interface (task in progress) -->
      <template v-if="report && (report.status === 'pending' || report.status === 'processing')">
        <div class="progress-container">
          <!-- top status card -->
          <div class="status-card">
            <div class="status-icon">
              <el-icon class="rotating" :size="48" color="#409EFF"><Loading /></el-icon>
            </div>
            <div class="status-content">
              <h2 class="status-title">Analyzing transaction review</h2>
              <div class="stock-info">
                <span class="stock-code">{{ report.trade_info?.code || '000000' }}</span>
                <span class="stock-name">{{ report.trade_info?.name || 'Loading...' }}</span>
              </div>
              <el-tag
                :type="report.status === 'processing' ? 'primary' : 'info'"
                size="large"
                effect="light"
              >
                {{ report.status === 'processing' ? '🔄 Analyzing' : '⏳ Waiting' }}
              </el-tag>
            </div>
          </div>

          <!-- Analysis step description -->
          <div class="analysis-steps">
            <div class="steps-title">
              <el-icon><InfoFilled /></el-icon>
              <span>AI Your transaction is being analyzed from multiple dimensions</span>
            </div>
            <div class="steps-grid">
              <div class="step-item">
                <div class="step-icon">📊</div>
                <div class="step-text">Market environment analysis</div>
              </div>
              <div class="step-item">
                <div class="step-icon">⏰</div>
                <div class="step-text">Evaluation of buying and selling opportunities</div>
              </div>
              <div class="step-item">
                <div class="step-icon">💰</div>
                <div class="step-text">Position and risk review</div>
              </div>
              <div class="step-item">
                <div class="step-icon">🧠</div>
                <div class="step-text">Trading psychology analysis</div>
              </div>
              <div class="step-item">
                <div class="step-icon">📈</div>
                <div class="step-text">Revenue attribution analysis</div>
              </div>
            </div>
          </div>

          <!-- Estimated time reminder -->
          <div class="time-estimate">
            <el-icon><Clock /></el-icon>
            <span>Estimated to take 2-5 minutes, please be patient...</span>
          </div>

          <!-- Bottom operation button -->
          <div class="progress-actions">
            <el-button size="large" @click="visible = false">close</el-button>
            <el-button size="large" type="primary" @click="loadReport" :loading="loading">
              refresh status
            </el-button>
          </div>
        </div>
      </template>

      <!-- ✅ Complete results display interface (task completed) -->
      <template v-else-if="report && report.status === 'completed'">
        <!-- Transaction Summary -->
        <el-descriptions title="Transaction Summary" :column="3" border size="small" class="section">
          <el-descriptions-item label="Stock code">{{ report.trade_info?.code }}</el-descriptions-item>
          <el-descriptions-item label="Position holding days">{{ report.trade_info?.holding_days }}day</el-descriptions-item>
          <el-descriptions-item label="Profit and loss amount">
            <span :class="getTotalPnl() >= 0 ? 'positive' : 'negative'">
              {{ formatPnl(getTotalPnl()) }}Yuan
            </span>
            <span v-if="report.trade_info?.is_holding && report.trade_info?.unrealized_pnl" class="unrealized-hint">
              (Realized: {{ formatPnl(report.trade_info.realized_pnl) }}, float: {{ formatPnl(report.trade_info.unrealized_pnl) }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="average buying price">{{ report.trade_info?.avg_buy_price?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="average selling price">{{ report.trade_info?.avg_sell_price?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="Yield">
            <span :class="getTotalPnlPct() >= 0 ? 'positive' : 'negative'">
              {{ formatPct(getTotalPnlPct()) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="handling fee" :span="3">{{ report.trade_info?.total_commission?.toFixed(2) }}Yuan</el-descriptions-item>
        </el-descriptions>

        <!-- Related party transaction plan (if there is) -->
        <div v-if="report.trading_system_name" class="section trading-plan-section">
          <h4><el-icon><Document /></el-icon> Related party transaction plan</h4>
          <div class="trading-plan-info">
            <el-tag type="primary" size="large">{{ report.trading_system_name }}</el-tag>
            <p class="plan-note">
              This transaction has been linked to the trading plan, and AI analysis has been evaluated in conjunction with the plan rules.
              For a detailed analysis of plan execution, please see below"AI Analysis and summary"and"Detailed analysis"part.
            </p>
          </div>

          <!-- Trading plan execution status -->
          <el-row :gutter="16" class="plan-execution-row" v-if="report.ai_review?.plan_adherence || report.ai_review?.plan_deviation">
            <el-col :span="12" v-if="report.ai_review?.plan_adherence">
              <div class="analysis-card plan-adherence">
                <h4><el-icon><CircleCheck /></el-icon> Plan executed well</h4>
                <div class="markdown-content" v-html="renderMarkdown(report.ai_review.plan_adherence)"></div>
              </div>
            </el-col>
            <el-col :span="12" v-if="report.ai_review?.plan_deviation">
              <div class="analysis-card plan-deviation">
                <h4><el-icon><Warning /></el-icon> deviation from plan</h4>
                <div class="markdown-content" v-html="renderMarkdown(report.ai_review.plan_deviation)"></div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- AI analysis -->
        <div class="section">
          <h4>Review conclusion</h4>
          <div class="summary markdown-content" v-html="renderMarkdown(report.ai_review?.summary)"></div>
        </div>

        <!-- Advantages and Disadvantages -->
        <el-row :gutter="16" class="section">
          <el-col :span="12">
            <div class="analysis-card strengths">
              <h4><el-icon><CircleCheck /></el-icon> Things done well</h4>
              <div class="markdown-content" v-html="renderMarkdown((report.ai_review?.strengths || []).join('\n\n'))"></div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="analysis-card weaknesses">
              <h4><el-icon><Warning /></el-icon> exposed issues</h4>
              <div class="markdown-content" v-html="renderMarkdown((report.ai_review?.weaknesses || []).join('\n\n'))"></div>
            </div>
          </el-col>
        </el-row>

        <!-- Review improvements -->
        <div class="section" v-if="report.ai_review?.suggestions?.length">
          <h4><el-icon><Pointer /></el-icon> Key points for subsequent improvements</h4>
          <div class="suggestions markdown-content" v-html="renderMarkdown((report.ai_review?.suggestions || []).join('\n\n'))"></div>
        </div>

        <div class="section">
          <TaskGrowthPanel :task-id="growthTaskId" />
        </div>

        <!-- Detailed analysis -->
        <el-collapse class="section">
          <el-collapse-item title="Time to review" name="timing" v-if="report.ai_review?.timing_analysis">
            <div class="markdown-content" v-html="renderMarkdown(report.ai_review?.timing_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Position review" name="position" v-if="report.ai_review?.position_analysis">
            <div class="markdown-content" v-html="renderMarkdown(report.ai_review?.position_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Emotional review" name="emotion" v-if="report.ai_review?.emotion_analysis">
            <div class="markdown-content" v-html="renderMarkdown(report.ai_review?.emotion_analysis)"></div>
          </el-collapse-item>
          <el-collapse-item title="Attribution review" name="attribution" v-if="report.ai_review?.attribution_analysis">
            <div class="markdown-content" v-html="renderMarkdown(report.ai_review?.attribution_analysis)"></div>
          </el-collapse-item>
        </el-collapse>
      </template>

      <!-- ❌ Failure status display interface -->
      <template v-else-if="report && report.status === 'failed'">
        <div class="error-container">
          <el-result
            icon="error"
            title="Review failed"
            :sub-title="report.error_message || 'unknown error'"
          >
            <template #extra>
              <el-button type="primary" @click="visible = false">close</el-button>
            </template>
          </el-result>
        </div>
      </template>

      <!-- ⚠️ No data status -->
      <template v-else-if="!report && !loading">
        <el-empty description="No data yet" />
      </template>
    </div>

    <template #footer>
      <span v-if="report && report.status === 'completed'">
        <el-button @click="visible = false">close</el-button>
        <el-button v-if="!report.is_case_study" type="primary" @click="showSaveCaseDialog">
          Save to case library
        </el-button>
      </span>
    </template>
  </el-dialog>

  <!-- Save as case dialog box -->
  <SaveAsCaseDialog
    v-model="saveCaseDialogVisible"
    :review-id="props.reviewId"
    :stock-code="report?.trade_info?.code"
    :source="report?.source"
    @success="handleSaveCaseSuccess"
  />
</template>

<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Warning, Pointer, Document, Loading, InfoFilled, Clock } from '@element-plus/icons-vue'
import { reviewApi, type TradeReviewReport } from '@/api/review'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'
import TaskGrowthPanel from '@/components/growth/TaskGrowthPanel.vue'
import SaveAsCaseDialog from './SaveAsCaseDialog.vue'

// Configure marked options
// marked The configuration has been @/utils/markdown Unified management
const props = defineProps<{
  modelValue: boolean
  reviewId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const loading = ref(false)
const report = ref<TradeReviewReport | null>(null)
const saveCaseDialogVisible = ref(false)
const growthTaskId = computed(() => props.reviewId || report.value?.task_id || null)

const loadReport = async () => {
  if (!props.reviewId) return

  try {
    loading.value = true
    const res = await reviewApi.getReviewDetail(props.reviewId)
    if (res.success) {
      report.value = res.data || null
      // 🔍 debug log
      console.log('📊 [Review details] API Return data:', res.data)
      console.log('📊 [Review details] trading_system_id:', res.data?.trading_system_id)
      console.log('📊 [Review details] trading_system_name:', res.data?.trading_system_name)

      // 🔄 If status is pending or processing, start polling
      if (report.value && (report.value.status === 'pending' || report.value.status === 'processing')) {
        console.log('🔄 [Review details] The task is in progress, start polling...')
        startPolling()
      }
    }
  } catch (e: any) {
    // If it is a 404 error, it may be that the task is still being created, try polling
    if (e.message?.includes('404') || e.message?.includes('does not exist')) {
      console.log('🔄 [Review details] Data not found, maybe the task is still being created, start polling...')
      ElMessage.info('The review task is being executed, please wait....')
      startPolling()
    } else {
      ElMessage.error(e.message || 'Failed to load review details')
    }
  } finally {
    loading.value = false
  }
}

// Polling related
let pollingTimer: number | null = null
const POLLING_INTERVAL = 10000 // Polling interval: 10 seconds
const maxPollingAttempts = 60 // Poll up to 60 times (10 minutes)
let pollingAttempts = 0

const startPolling = () => {
  // Clear previous timer
  if (pollingTimer) {
    clearInterval(pollingTimer)
  }

  pollingAttempts = 0

  pollingTimer = window.setInterval(async () => {
    pollingAttempts++

    console.log(`🔄 [Review details] Polling ${pollingAttempts} times...`)

    try {
      const res = await reviewApi.getReviewDetail(props.reviewId)
      if (res.success && res.data) {
        report.value = res.data

        // Stop polling if task completes or fails
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          console.log(`✅ [Review details] Task${res.data.status === 'completed' ? 'Complete' : 'failed'}, Stop polling`)
          stopPolling()

          if (res.data.status === 'completed') {
            ElMessage.success('Review completed')
          } else {
            ElMessage.error(res.data.error_message || 'Review failed')
          }
        }
      }
    } catch (e) {
      console.log('🔄 [Review details] Polling failed, continue to wait...')
    }

    // If the maximum number of polling times is exceeded, polling will be stopped.
    if (pollingAttempts >= maxPollingAttempts) {
      console.log('⏱️ [Review details] Polling timeout, stop polling')
      stopPolling()
      ElMessage.warning('The review task takes a long time to execute, please refresh and view later.')
    }
  }, POLLING_INTERVAL) // Poll every 10 seconds
}

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
  pollingAttempts = 0
}

const formatPnl = (value?: number) => {
  if (value === undefined || value === null) return '-'
  const prefix = value >= 0 ? '+' : ''
  return prefix + value.toFixed(2)
}

const formatPct = (value?: number) => {
  if (value === undefined || value === null) return '-'
  const prefix = value >= 0 ? '+' : ''
  return prefix + value.toFixed(2) + '%'
}

// 🆕 Calculate total profit and loss (realized + floating profit and loss)
const getTotalPnl = () => {
  if (!report.value?.trade_info) return 0
  const tradeInfo = report.value.trade_info
  const realized = tradeInfo.realized_pnl || 0
  // If the position is still open, add floating profit and loss
  if (tradeInfo.is_holding && tradeInfo.unrealized_pnl !== undefined) {
    return realized + tradeInfo.unrealized_pnl
  }
  return realized
}

// 🆕 Calculate total return
const getTotalPnlPct = () => {
  if (!report.value?.trade_info) return 0
  const tradeInfo = report.value.trade_info
  const realizedPct = tradeInfo.realized_pnl_pct || 0
  if (tradeInfo.is_holding && tradeInfo.unrealized_pnl_pct !== undefined) {
    const totalBuyAmount = tradeInfo.total_buy_amount || 0
    if (totalBuyAmount > 0) {
      const totalPnl = getTotalPnl()
      return (totalPnl / totalBuyAmount) * 100
    }
    return realizedPct + tradeInfo.unrealized_pnl_pct
  }
  return realizedPct
}

const renderMarkdown = (content?: string) => {
  if (!content) return ''
  try {
    return safeMarkdown(content)
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}

const showSaveCaseDialog = () => {
  saveCaseDialogVisible.value = true
}

const handleSaveCaseSuccess = () => {
  if (report.value) {
    report.value.is_case_study = true
  }
}

watch(() => [props.modelValue, props.reviewId], ([show, id]) => {
  if (show && id) {
    loadReport()
  } else if (!show) {
    stopPolling()
  }
}, { immediate: true })

onBeforeUnmount(() => {
  console.log('🧹 [Review details] Uninstall components and clean up polling resources...')
  stopPolling()
})
</script>

<style scoped lang="scss">
.review-detail {
  .progress-container {
    padding: 32px 24px;

    .status-card {
      display: flex;
      align-items: center;
      gap: 24px;
      padding: 32px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      border-radius: 12px;
      margin-bottom: 32px;
      color: white;

      .status-icon {
        .rotating {
          animation: rotate 2s linear infinite;
          filter: drop-shadow(0 2px 8px rgba(255, 255, 255, 0.3));
        }
      }

      .status-content {
        flex: 1;
        text-align: left;

        .status-title {
          margin: 0 0 12px 0;
          font-size: 24px;
          font-weight: 600;
          color: white;
        }

        .stock-info {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;

          .stock-code {
            font-size: 18px;
            font-weight: 600;
            color: white;
            background: rgba(255, 255, 255, 0.2);
            padding: 4px 12px;
            border-radius: 6px;
          }

          .stock-name {
            font-size: 16px;
            color: rgba(255, 255, 255, 0.9);
          }
        }

        :deep(.el-tag) {
          background: rgba(255, 255, 255, 0.2);
          border-color: rgba(255, 255, 255, 0.3);
          color: white;
          font-size: 14px;
          padding: 8px 16px;
          height: auto;
        }
      }
    }

    .analysis-steps {
      margin-bottom: 32px;

      .steps-title {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 20px;
        font-size: 15px;
        color: #606266;
        justify-content: center;

        .el-icon {
          color: #409EFF;
        }
      }

      .steps-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 16px;

        .step-item {
          padding: 20px 16px;
          background: #f5f7fa;
          border-radius: 8px;
          text-align: center;
          transition: all 0.3s ease;

          &:hover {
            background: #ecf5ff;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(64, 158, 255, 0.1);
          }

          .step-icon {
            font-size: 32px;
            margin-bottom: 8px;
          }

          .step-text {
            font-size: 13px;
            color: #606266;
            line-height: 1.4;
          }
        }
      }
    }

    .time-estimate {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 16px;
      background: #fff7e6;
      border: 1px solid #ffe7ba;
      border-radius: 8px;
      margin-bottom: 32px;
      color: #e6a23c;
      font-size: 14px;

      .el-icon {
        font-size: 18px;
      }
    }

    .progress-actions {
      display: flex;
      justify-content: center;
      gap: 12px;
    }
  }

  .error-container {
    padding: 20px;
  }

  @keyframes rotate {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  .section {
    margin-bottom: 20px;

    h4 {
      margin: 0 0 12px 0;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }

  .summary {
    padding: 12px 16px;
    background: #f5f7fa;
    border-radius: 4px;
    line-height: 1.6;
  }

  .markdown-content {
    line-height: 1.6;

    :deep(h1), :deep(h2), :deep(h3), :deep(h4), :deep(h5), :deep(h6) {
      margin: 16px 0 8px 0;
      color: var(--el-text-color-primary);
    }

    :deep(h1) { font-size: 24px; }
    :deep(h2) { font-size: 20px; }
    :deep(h3) { font-size: 16px; }
    :deep(h4) { font-size: 14px; }

    :deep(p) {
      margin: 8px 0;
      line-height: 1.6;
    }

    :deep(ul), :deep(ol) {
      margin: 8px 0;
      padding-left: 20px;

      li {
        margin: 4px 0;
        line-height: 1.5;
      }
    }

    :deep(code) {
      background: var(--el-fill-color-light);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 13px;
      color: var(--el-text-color-primary);
    }

    :deep(pre) {
      background: var(--el-fill-color-light);
      color: var(--el-text-color-primary);
      padding: 12px;
      border-radius: 6px;
      overflow-x: auto;
      margin: 12px 0;
      font-size: 13px;

      code {
        background: none;
        padding: 0;
        color: inherit;
      }
    }

    :deep(blockquote) {
      border-left: 4px solid var(--el-color-primary);
      margin: 12px 0;
      padding: 8px 12px;
      color: var(--el-text-color-secondary);
      background: var(--el-fill-color-light);
      border-radius: 4px;
    }

    :deep(strong) {
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    :deep(em) {
      font-style: italic;
      color: var(--el-text-color-regular);
    }
  }

  .analysis-card {
    padding: 16px;
    border-radius: 8px;
    height: 100%;

    &.strengths { background: #f0f9eb; }
    &.weaknesses { background: #fef0f0; }
    &.plan-adherence { background: #e8f4fd; border: 1px solid #b3d8f2; }
    &.plan-deviation { background: #fff7e6; border: 1px solid #ffd591; }

    h4 { margin: 0 0 12px 0; font-size: 14px; }
    ul { margin: 0; padding-left: 20px; li { margin-bottom: 6px; } }
  }

  .unrealized-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-left: 8px;
    font-weight: normal;
  }

  .suggestions {
    padding-left: 20px;

    li { margin-bottom: 8px; line-height: 1.5; }
  }

  .trading-plan-section {
    .trading-plan-info {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px;
      background: #f0f9ff;
      border-radius: 8px;
      border: 1px solid #d1e7ff;
      margin-bottom: 16px;

      .el-tag {
        flex-shrink: 0;
      }

      .plan-note {
        margin: 0;
        font-size: 13px;
        color: #606266;
        line-height: 1.6;
      }
    }

    .plan-execution-row {
      margin-top: 0;
    }

    h4 {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      font-size: 14px;
      color: #303133;

      .el-icon {
        color: #409eff;
      }
    }
  }

  .positive { color: #f56c6c; }
  .negative { color: #67c23a; }
  .warning { color: #e6a23c; }
}
</style>

