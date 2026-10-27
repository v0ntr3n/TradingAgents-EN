<template>
  <el-dialog
    v-model="visible"
    title="Analysis report details"
    width="900px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div v-if="report" class="analysis-detail">
      <!-- Risk warning -->
      <div class="risk-disclaimer">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <span style="font-size: 14px;">
              <strong>⚠️ IMPORTANT NOTE:</strong>All analysis conclusions in this analysis are used to learn and verify AI securities analysis technology and are not used as real trading guidance.
            </span>
          </template>
        </el-alert>
      </div>

      <!-- Position snapshot -->
      <div class="section">
        <h3>📊 Position snapshot</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="securityCodeLabel">{{ report.position_snapshot?.code || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="securityNameLabel">{{ report.position_snapshot?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Position quantity">{{ report.position_snapshot?.quantity || 0 }} shares</el-descriptions-item>
          <el-descriptions-item label="cost price">¥{{ (report.position_snapshot?.cost_price || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="current price">¥{{ (report.position_snapshot?.current_price || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="Position market value">¥{{ (report.position_snapshot?.market_value || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="floating profit and loss">
            <span :class="pnlClass(report.position_snapshot?.unrealized_pnl || 0)">
              {{ formatPnl(report.position_snapshot?.unrealized_pnl || 0) }}
              ({{ formatPct(report.position_snapshot?.unrealized_pnl_pct || 0) }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item :label="industryLabel">{{ industryValue }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- current conclusion -->
      <div class="section">
        <h3>💡 current conclusion</h3>
        <div class="summary-panel markdown-content" v-html="renderMarkdown(view.conclusion || report.action_reason || 'None yet')"></div>

        <div class="uncertainty-box" v-if="view.uncertainty_note">
          <h4>uncertainty statement</h4>
          <p>{{ view.uncertainty_note }}</p>
        </div>
      </div>

      <!-- Research Addendum -->
      <div class="section" v-if="appendixSections.length > 0 || report.detailed_analysis">
        <h3>📝 Research Addendum</h3>
        <template v-if="appendixSections.length > 0">
          <div
            v-for="section in appendixSections"
            :key="`detail-appendix-${section.key}`"
            class="appendix-section"
          >
            <h4>{{ section.title }}</h4>
            <div class="markdown-content" v-html="renderMarkdown(section.content)"></div>
          </div>
        </template>
        <div v-else class="markdown-content" v-html="renderMarkdown(report.detailed_analysis)"></div>
      </div>

      <div class="section">
        <TaskGrowthPanel :task-id="growthTaskId" />
      </div>

      <!-- Analysis time -->
      <div class="section">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="Analysis time">{{ formatTime(report.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="Execution time">{{ report.execution_time || 0 }} seconds</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">close</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { type PositionAnalysisResult } from '@/api/portfolio'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'
import TaskGrowthPanel from '@/components/growth/TaskGrowthPanel.vue'
import { getMarketByStockCode } from '@/utils/market'

type PositionSnapshot = {
  code?: string
  name?: string
  quantity?: number
  cost_price?: number
  current_price?: number
  market_value?: number
  unrealized_pnl?: number
  unrealized_pnl_pct?: number
  industry?: string
}

// Configure marked options
// marked The configuration has been @/utils/markdown Unified management
const props = defineProps<{
  modelValue: boolean
  report: (PositionAnalysisResult & { position_snapshot?: PositionSnapshot }) | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = ref(false)
const growthTaskId = computed(() => props.report?.task_id || props.report?.analysis_id || null)

// User version display content (unified display of user_view field after compliance)
const view = computed(() => props.report?.user_view || {
  conclusion: props.report?.action_reason || '',
  position_context: '',
  key_points: [] as string[],
  risk_focus: [] as string[],
  watch_items: [] as string[],
  uncertainty_note: ''
})

// Research appendix (only sections with content are displayed)
const appendixSections = computed(() =>
  (props.report?.appendix_sections || []).filter(section => section?.content)
)

const isEtfReport = computed(() => {
  const code = props.report?.position_snapshot?.code
  return !!code && getMarketByStockCode(code) === 'ETF'
})
const securityCodeLabel = computed(() => isEtfReport.value ? 'ETF code' : 'Stock code')
const securityNameLabel = computed(() => isEtfReport.value ? 'ETF Name' : 'Stock name')
const industryLabel = computed(() => isEtfReport.value ? 'Product classification' : 'Industry')
const industryValue = computed(() => {
  if (isEtfReport.value) return 'ETF/fund'
  return props.report?.position_snapshot?.industry || 'unknown'
})

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => emit('update:modelValue', val))

const handleClose = () => emit('update:modelValue', false)

// Markdown rendering
const renderMarkdown = (content: string) => {
  if (!content) return ''
  try {
    return safeMarkdown(content)
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}

// Format time
const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  return date.toLocaleString('zh-CN')
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
</script>

<style scoped>
.analysis-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.section {
  margin-bottom: 24px;
}

.section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.section h4 {
  font-size: 14px;
  font-weight: 500;
  margin: 12px 0 8px 0;
  color: #606266;
}

.text-success {
  color: #67c23a;
}

.text-danger {
  color: #f56c6c;
}

.summary-panel {
  padding: 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef4ff 100%);
  border: 1px solid #dbe7ff;
}

.summary-conclusion,
.summary-context {
  margin: 0;
  line-height: 1.8;
  color: #334155;
}

.summary-conclusion {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.summary-context {
  margin-top: 10px;
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.info-card {
  padding: 16px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e5edf6;
}

.info-card h4,
.uncertainty-box h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #1f2937;
}

.info-card ul {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  line-height: 1.8;
}

.uncertainty-box {
  margin-top: 16px;
  padding: 16px;
  border-radius: 14px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.uncertainty-box p {
  margin: 0;
  line-height: 1.8;
  color: #7c2d12;
}

.appendix-section {
  padding: 10px 0;
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
  .section-grid {
    grid-template-columns: 1fr;
  }
}

.markdown-content {
  line-height: 1.8;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin-top: 16px;
  margin-bottom: 8px;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
}

.markdown-content :deep(p) {
  margin: 8px 0;
}

.markdown-content :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
}

.markdown-content :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
}

.risk-disclaimer {
  margin-bottom: 24px;
}

.risk-disclaimer :deep(.el-alert) {
  background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%);
  border: 2px solid #ffc107;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 4px 12px rgba(255, 193, 7, 0.2);
}
</style>

