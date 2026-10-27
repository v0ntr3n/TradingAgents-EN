<template>
  <el-dialog
    v-model="visible"
    :title="`${position?.name || position?.code || ''} - Analyze history`"
    width="1000px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
      {{ isEtfPosition ? 'View all analysis report history for this ETF' : 'View all analysis report history for this stock' }}
    </el-alert>

    <!-- data table -->
    <el-table :data="historyList" v-loading="loading" stripe>
      <el-table-column label="Analysis time" width="160">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="Position quantity" width="100" align="right">
        <template #default="{ row }">
          {{ row.position_snapshot?.quantity || 0 }} shares
        </template>
      </el-table-column>

      <el-table-column label="cost price" width="100" align="right">
        <template #default="{ row }">
          ¥{{ (row.position_snapshot?.cost_price || 0).toFixed(2) }}
        </template>
      </el-table-column>

      <el-table-column label="current price" width="100" align="right">
        <template #default="{ row }">
          ¥{{ (row.position_snapshot?.current_price || 0).toFixed(2) }}
        </template>
      </el-table-column>

      <el-table-column label="floating profit and loss" width="140" align="right">
        <template #default="{ row }">
          <span :class="pnlClass(row.position_snapshot?.unrealized_pnl || 0)">
            {{ formatPnl(row.position_snapshot?.unrealized_pnl || 0) }}
            ({{ formatPct(row.position_snapshot?.unrealized_pnl_pct || 0) }})
          </span>
        </template>
      </el-table-column>

      <el-table-column label="analysis point of view" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.action" :type="getActionType(row.action)" size="small">
            {{ getActionText(row.action) }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="One sentence conclusion" min-width="260">
        <template #default="{ row }">
          <span class="conclusion-preview">{{ row.user_view?.conclusion || row.action_reason || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="Position type" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.position_type === 'simulated' || (position?.source === 'paper')" type="warning" size="small">
            Simulated position
          </el-tag>
          <el-tag v-else type="success" size="small">
            User positions
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Status" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Operation" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            link
            @click="viewDetail(row)"
            :disabled="row.status !== 'completed'"
          >
            View details
          </el-button>
          <el-button
            type="danger"
            size="small"
            link
            @click="handleDelete(row)"
          >
            Delete
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div style="margin-top: 16px; text-align: right">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadData"
        @size-change="loadData"
      />
    </div>

    <!-- Details dialog -->
    <PositionAnalysisDetailDialog
      v-model="showDetailDialog"
      :report="selectedReport"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { portfolioApi, type PositionItem, type PositionAnalysisResult } from '@/api/portfolio'
import PositionAnalysisDetailDialog from './PositionAnalysisDetailDialog.vue'
import { getMarketByStockCode } from '@/utils/market'

const props = defineProps<{
  modelValue: boolean
  position: PositionItem | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = ref(false)
const loading = ref(false)
const historyList = ref<PositionAnalysisResult[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const showDetailDialog = ref(false)
const selectedReport = ref<PositionAnalysisResult | null>(null)

const positionId = computed(() => {
  if (!props.position) return null
  return `${props.position.code}_${props.position.market}`
})
const isEtfPosition = computed(() => {
  if (!props.position) return false
  return props.position.market === 'CN' && getMarketByStockCode(props.position.code) === 'ETF'
})

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && positionId.value) {
    loadData()
  }
})

watch(visible, (val) => emit('update:modelValue', val))

const loadData = async () => {
  if (!positionId.value) return

  loading.value = true
  try {
    // 🔥 Pass the source parameter according to the position source: simulate a position -> paper, User positions -> real
    const source = props.position?.source === 'paper' ? 'paper' : 'real'
    const res = await portfolioApi.getPositionAnalysisHistory(positionId.value, currentPage.value, pageSize.value, source)
    historyList.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to load analysis history')
  } finally {
    loading.value = false
  }
}

const handleClose = () => emit('update:modelValue', false)

const viewDetail = (row: PositionAnalysisResult) => {
  selectedReport.value = row
  showDetailDialog.value = true
}

// Delete analysis records
const handleDelete = async (row: PositionAnalysisResult) => {
  if (!row.analysis_id) {
    ElMessage.warning('Unable to get analysis ID and cannot delete')
    return
  }

  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete this analysis record?\n Analysis time: ${formatTime(row.created_at)}`,
      'Confirm deletion',
      {
        confirmButtonText: 'Delete',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    // Call the delete interface
    const res = await portfolioApi.deletePositionAnalysis(row.analysis_id)
    if (res.success) {
      ElMessage.success('Delete successfully')
      // Reload data
      await loadData()
    } else {
      ElMessage.error(res.message || 'Delete failed')
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || 'Delete failed')
    }
  }
}

// Format time
const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Format profit and loss
const formatPnl = (pnl: number) => {
  if (pnl === undefined || pnl === null) return '¥0.00'
  const prefix = pnl >= 0 ? '+' : ''
  return `${prefix}¥${Math.abs(pnl).toFixed(2)}`
}

// Format percentage
const formatPct = (pct: number) => {
  if (pct === undefined || pct === null) return '0.00%'
  const prefix = pct >= 0 ? '+' : ''
  return `${prefix}${pct.toFixed(2)}%`
}

// profit and loss pattern
const pnlClass = (pnl: number) => {
  if (pnl > 0) return 'text-success'
  if (pnl < 0) return 'text-danger'
  return ''
}

// Analyze view types (converged into three compliance labels: optimistic/cautious/neutral)
const getActionType = (action: string) => {
  if (action === 'buy' || action === 'add' || action === 'optimistic') return 'success'
  if (action === 'sell' || action === 'reduce' || action === 'clear' || action === 'Prudence') return 'danger'
  return 'info'
}

// Analyze opinion text (unified into three compliance labels: optimistic/cautious/neutral)
const getActionText = (action: string) => {
  const map: Record<string, string> = {
    // Old Trading Order/Market View Terms → Three compliance labels
    buy: 'optimistic',
    add: 'optimistic',
    hold: 'Neutral',
    reduce: 'Prudence',
    sell: 'Prudence',
    clear: 'Prudence',
    // old market view terminology
    'bullish': 'optimistic',
    'Bearish': 'Prudence',
    'Overweight view': 'optimistic',
    'Underweight view': 'Prudence',
    'wait and see view': 'Neutral',
    // New Compliance Terminology
    'optimistic': 'optimistic',
    'Prudence': 'Prudence',
    'Neutral': 'Neutral'
  }
  return map[action] || action
}

// status type
const getStatusType = (status: string) => {
  if (status === 'completed') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

// status text
const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: 'Waiting',
    processing: 'Analyzing',
    completed: 'Completed',
    failed: 'failed'
  }
  return map[status] || status
}
</script>

<style scoped>
.text-success {
  color: #67c23a;
}

.text-danger {
  color: #f56c6c;
}

.conclusion-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.6;
}
</style>


