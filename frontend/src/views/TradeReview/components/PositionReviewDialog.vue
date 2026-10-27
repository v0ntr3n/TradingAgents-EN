<template>
    <el-dialog
    v-model="visible"
    :title="props.source === 'paper' ? 'Simulated trading review' : 'Review of position operations'"
    width="600px"
    :close-on-click-modal="false"
  >
    <div v-if="positionData" class="position-info">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="Stock code">{{ positionData.code }}</el-descriptions-item>
        <el-descriptions-item label="Stock name">{{ positionData.name }}</el-descriptions-item>
        <el-descriptions-item label="market">
          <el-tag size="small">{{ positionData.market }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Review type">
          <el-tag size="small" :type="positionData.type === 'current' ? 'primary' : 'success'">
            {{ positionData.type === 'current' ? 'Current position' : 'Historical positions' }}
          </el-tag>
        </el-descriptions-item>
        <template v-if="positionData.type === 'current'">
          <el-descriptions-item label="Position quantity">{{ positionData.quantity }}</el-descriptions-item>
          <el-descriptions-item label="cost price">{{ positionData.cost_price?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="floating profit and loss" :span="2">
            <span :class="(positionData.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative'">
              {{ formatPnl(positionData.unrealized_pnl) }}
            </span>
          </el-descriptions-item>
        </template>
        <template v-else>
          <el-descriptions-item label="Realized profit and loss">
            <span :class="(positionData.realized_pnl || 0) >= 0 ? 'positive' : 'negative'">
              {{ formatPnl(positionData.realized_pnl) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="Holding days">{{ positionData.hold_days }} day</el-descriptions-item>
        </template>
      </el-descriptions>
    </div>

    <el-divider content-position="left">Review analysis content</el-divider>

    <el-form :model="form" label-width="100px">
      <!-- Process selection -->
      <el-form-item v-if="workflowsSorted.length > 0" label="Analysis process">
        <div style="display: flex; align-items: center; width: 100%">
          <el-select
            v-model="selectedWorkflowId"
            size="small"
            style="flex: 1"
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
            <el-icon style="margin-left: 8px; color: #909399; cursor: help"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
      </el-form-item>
      <!-- 🆕 Remove analysis version selection and use workflow analysis uniformly -->
      <el-form-item label="Review analysis content">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            Use the multi-dimensional workflow engine to conduct in-depth analysis, which is expected to take 1-3 minutes to complete.
          </template>
        </el-alert>
      </el-form-item>
      <el-form-item v-if="canUseTradingPlanCheck" label="Related party transaction plan">
        <el-select
          v-model="form.trading_system_id"
          placeholder="Choose a trading plan (optional)"
          clearable
          :loading="loadingTradingSystems"
          style="width: 100%"
        >
          <el-option
            v-for="system in tradingSystems"
            :key="system.id"
            :label="system.name"
            :value="system.id || system.name"
          >
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>{{ system.name }}</span>
              <div style="display: flex; gap: 4px; align-items: center">
                <el-tag v-if="system.is_active" size="small" type="success">Default</el-tag>
                <el-tag size="small" type="info">{{ getStyleLabel(system.style) }}</el-tag>
              </div>
            </div>
          </el-option>
        </el-select>
        <div class="form-tip">After selection, execution consistency check will be carried out according to the trading plan rules.</div>
      </el-form-item>
      <el-form-item v-else label="Perform consistency check">
        <div class="form-tip">Advanced students can associate trading plans and conduct consistency checks on review results.</div>
      </el-form-item>
      <el-form-item label="Analysis Dimensions">
        <div class="dimensions-list">
          <div class="dimension-item">
            <el-tag type="info" size="large">timing</el-tag>
            <span class="dimension-desc">Analyze whether the timing of buying and selling is reasonable</span>
          </div>
          <div class="dimension-item">
            <el-tag type="info" size="large">position</el-tag>
            <span class="dimension-desc">Evaluate the rationality and risk control of position management</span>
          </div>
          <div class="dimension-item">
            <el-tag type="info" size="large">emotions</el-tag>
            <span class="dimension-desc">Analyze emotional factors and discipline execution in operational decisions</span>
          </div>
          <div class="dimension-item">
            <el-tag type="info" size="large">attribution</el-tag>
            <span class="dimension-desc">Analyze the source of income and distinguish whether it is ability or luck</span>
          </div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        Start review
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { reviewApi, type TradeRecord } from '@/api/review'
import * as tradingSystemApi from '@/api/tradingSystem'
import type { TradingSystem } from '@/api/tradingSystem'
import { useLicenseStore } from '@/stores/license'
import { workflowApi, isSelectableAnalysisWorkflow, type WorkflowSummary } from '@/api/workflow'

interface PositionData {
  code: string
  name: string
  market: string
  type: 'current' | 'history'
  quantity?: number
  cost_price?: number
  unrealized_pnl?: number
  realized_pnl?: number
  hold_days?: number
  cleared_at?: string
}

const props = defineProps<{
  modelValue: boolean
  positionData: PositionData | null
  source?: 'paper' | 'real'  // data source: paper(simulated trading) or real(User positions)
  workflowId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success', reviewId: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})
const licenseStore = useLicenseStore()
const canUseTradingPlanCheck = computed(() => licenseStore.hasFeature('trading_plan_check'))

const form = ref({
  // 🆕 Remove analysis_version and use workflow analysis uniformly
  // 🆕 Remove dimensions and replace them with fixed dimensions: timing, position, sentiment, attribution
  // 🆕 Remove notes, this field is not used by the backend
  trading_system_id: ''
})

const submitting = ref(false)

// Process selection
const workflows = ref<WorkflowSummary[]>([])
const selectedWorkflowId = ref<string>('')

const parseVersion = (v: string): number[] => {
  const parts = String(v || '0.0.0').split('.')
  return parts.map(p => parseInt(p, 10) || 0)
}

const workflowsSorted = computed(() => {
  const arr = workflows.value.filter(
    (w: WorkflowSummary) => isSelectableAnalysisWorkflow(w, 'trade_review')
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

// Trading plan related
const tradingSystems = ref<TradingSystem[]>([])
const loadingTradingSystems = ref(false)

// Load trading plan list
const loadTradingSystems = async () => {
  if (!canUseTradingPlanCheck.value) {
    tradingSystems.value = []
    form.value.trading_system_id = ''
    return
  }

  loadingTradingSystems.value = true
  try {
    const res = await tradingSystemApi.getTradingSystems()
    tradingSystems.value = res.data?.systems || []
    
    // 🔥 The default trading plan is automatically selected (is_active: true) 
    const activeSystem = tradingSystems.value.find(system => system.is_active)
    if (activeSystem && activeSystem.id) {
      form.value.trading_system_id = activeSystem.id
    }
  } catch (e: any) {
    console.error('Failed to load trading plan list:', e)
  } finally {
    loadingTradingSystems.value = false
  }
}

watch(visible, async (val) => {
  if (!val) {
    // Reset form when closing dialog box
    form.value = {
      // 🆕 Remove analysis_version, dimensions, and notes
      trading_system_id: ''
    }
  } else {
    if (!licenseStore.licenseInfo) {
      await licenseStore.verifyLicense()
    }
    // When opening the dialog box, the list of trading plans is reloaded and the default plan is automatically selected
    await loadTradingSystems()
    // Load workflow list
    await loadWorkflows()
  }
})

const formatPnl = (val?: number) => {
  if (val === undefined || val === null) return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + val.toFixed(2)
}

const getStyleLabel = (style: string) => {
  const labels: Record<string, string> = {
    short_term: 'short term',
    medium_term: 'center line',
    long_term: 'long term'
  }
  return labels[style] || style
}

const parseTime = (value?: string) => {
  if (!value) return null
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? null : timestamp
}

const getTradeSortTime = (trade: TradeRecord) => {
  return parseTime(trade.timestamp) ?? parseTime(trade.created_at) ?? 0
}

const segmentPositionTrades = (trades: TradeRecord[]) => {
  const sortedTrades = [...trades].sort((left, right) => getTradeSortTime(left) - getTradeSortTime(right))
  const segments: TradeRecord[][] = []
  let startIndex = 0

  sortedTrades.forEach((trade, index) => {
    if (trade.quantity_after === 0) {
      const segment = sortedTrades.slice(startIndex, index + 1)
      if (segment.length) {
        segments.push(segment)
      }
      startIndex = index + 1
    }
  })

  if (startIndex < sortedTrades.length) {
    segments.push(sortedTrades.slice(startIndex))
  }

  return segments.filter(segment => segment.length > 0)
}

const selectTradesForPositionCycle = (trades: TradeRecord[], positionData: PositionData, source: 'paper' | 'real') => {
  if (source !== 'real' || trades.length === 0) {
    return trades
  }

  const segments = segmentPositionTrades(trades)
  if (segments.length === 0) {
    return trades
  }

  if (positionData.type === 'current') {
    const activeSegment = [...segments].reverse().find(segment => {
      const lastTrade = segment[segment.length - 1]
      return (lastTrade.quantity_after ?? 0) > 0
    })
    return activeSegment || segments[segments.length - 1]
  }

  const closedSegments = segments.filter(segment => {
    const lastTrade = segment[segment.length - 1]
    return lastTrade.quantity_after === 0
  })

  if (closedSegments.length === 0) {
    return segments[segments.length - 1]
  }

  const clearedAt = parseTime(positionData.cleared_at)
  if (clearedAt === null) {
    return closedSegments[closedSegments.length - 1]
  }

  let bestSegment = closedSegments[0]
  let bestDiff = Math.abs(getTradeSortTime(closedSegments[0][closedSegments[0].length - 1]) - clearedAt)

  closedSegments.slice(1).forEach(segment => {
    const endTime = getTradeSortTime(segment[segment.length - 1])
    const diff = Math.abs(endTime - clearedAt)
    if (diff < bestDiff) {
      bestSegment = segment
      bestDiff = diff
    }
  })

  return bestSegment
}

const handleSubmit = async () => {
  if (!props.positionData) {
    ElMessage.error('Position data does not exist')
    return
  }

  try {
    submitting.value = true

    const source = props.source || 'real'  // Default user position
    
    // 1. Get all transaction records for this stock
    const tradesRes = await reviewApi.getTradesByCode(props.positionData.code, source)
    const trades = tradesRes.data?.trades || []

    if (trades.length === 0) {
      ElMessage.warning('There is currently no analyzable transaction record for this stock.')
      return
    }

    const reviewTrades = selectTradesForPositionCycle(trades, props.positionData, source)

    if (reviewTrades.length === 0) {
      ElMessage.warning('No transaction record corresponding to the current position period was found.')
      return
    }

    // 2. Get the transaction ID list of the current position period
    const tradeIds = reviewTrades.map(t => t.trade_id)

    // 3. Create review analysis (unified use of workflow analysis)
    const reviewRes = await reviewApi.createTradeReview({
      trade_ids: tradeIds,
      review_type: 'complete_trade',
      code: props.positionData.code,
      source: source,  // Use the passed in data source
      trading_system_id: canUseTradingPlanCheck.value ? (form.value.trading_system_id || undefined) : undefined,
      workflow_id: selectedWorkflowId.value || undefined,
      use_workflow: true  // 🆕 Unified use of workflow analytics
    })

    if (reviewRes.data) {
      console.log('[PositionReviewDialog] The review was created successfully.reviewId:', reviewRes.data.review_id)
      // First trigger the success event and let the parent component open the details page
      emit('success', reviewRes.data.review_id)
      console.log('[PositionReviewDialog] success event triggered')
      // Delay the closing of the dialog box to ensure that the details page is opened first
      setTimeout(() => {
        visible.value = false
        console.log('[PositionReviewDialog] Dialog closed')
      }, 200)
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Review failed')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped lang="scss">
.position-info {
  margin-bottom: 16px;
}
.positive { color: #f56c6c; }  // Chinese custom: red indicates profit (positive number)
.negative { color: #67c23a; }  // Chinese custom: green indicates loss (negative number)
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.dimensions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dimension-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dimension-desc {
  font-size: 14px;
  color: #606266;
  flex: 1;
}
.version-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;

  .version-desc {
    font-size: 13px;
    color: #606266;
  }
}
</style>

