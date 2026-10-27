<template>
  <el-dialog
    v-model="visible"
    title="📊 Position research history"
    width="1000px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
      View history of all position research reports
    </el-alert>

    <!-- data table -->
    <el-table :data="historyList" v-loading="loading" stripe>
      <el-table-column label="Analysis time" width="160">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="Position quantity" width="100" align="center">
        <template #default="{ row }">
          {{ row.portfolio_snapshot?.total_positions || 0 }} only
        </template>
      </el-table-column>

      <el-table-column label="Total market capitalization" width="120" align="right">
        <template #default="{ row }">
          ¥{{ formatNumber(row.portfolio_snapshot?.total_value || 0) }}
        </template>
      </el-table-column>

      <el-table-column label="floating profit and loss" width="140" align="right">
        <template #default="{ row }">
          <span :class="pnlClass(row.portfolio_snapshot?.unrealized_pnl || 0)">
            {{ formatPnl(row.portfolio_snapshot?.unrealized_pnl || 0) }}
            ({{ formatPct(row.portfolio_snapshot?.unrealized_pnl_pct || 0) }})
          </span>
        </template>
      </el-table-column>

      <el-table-column label="health" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.health_score" :type="getHealthScoreType(row.health_score)">
            {{ row.health_score }}points
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="risk level" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.risk_level" :type="getRiskLevelType(row.risk_level)">
            {{ getRiskLevelText(row.risk_level) }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="Status" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Operation" width="120" align="center" fixed="right">
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
    <AnalysisResultDialog
      v-model:visible="showDetailDialog"
      :report="selectedReport"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { portfolioApi, type PortfolioAnalysisReport } from '@/api/portfolio'
import AnalysisResultDialog from './AnalysisResultDialog.vue'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = ref(false)
const loading = ref(false)
const historyList = ref<PortfolioAnalysisReport[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const showDetailDialog = ref(false)
const selectedReport = ref<PortfolioAnalysisReport | null>(null)

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    loadData()
  }
})

watch(visible, (val) => emit('update:modelValue', val))

const loadData = async () => {
  loading.value = true
  try {
    const res = await portfolioApi.getAnalysisHistory(currentPage.value, pageSize.value)
    historyList.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to load analysis history')
  } finally {
    loading.value = false
  }
}

const handleClose = () => emit('update:modelValue', false)

const viewDetail = (row: PortfolioAnalysisReport) => {
  selectedReport.value = row
  showDetailDialog.value = true
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

// Format numbers
const formatNumber = (num: number) => {
  if (num === undefined || num === null) return '0.00'
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Format profit and loss
const formatPnl = (pnl: number) => {
  if (pnl === undefined || pnl === null) return '¥0.00'
  const prefix = pnl >= 0 ? '+' : ''
  return `${prefix}¥${formatNumber(Math.abs(pnl))}`
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

// Health score type
const getHealthScoreType = (score: number) => {
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}

// Risk level type
const getRiskLevelType = (level: string) => {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  return 'danger'
}

// Risk level text
const getRiskLevelText = (level: string) => {
  const map: Record<string, string> = {
    low: 'low risk',
    medium: 'medium risk',
    high: 'high risk'
  }
  return map[level] || level
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
</style>


