<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="Position research report"
    width="800px"
    destroy-on-close
  >
    <div v-if="report" class="analysis-report">
      <!-- Risk warning -->
      <div class="risk-disclaimer">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <span style="font-size: 14px;">
              <strong>⚠️ IMPORTANT NOTE:</strong>This report is only used for learning, research and position risk identification, and does not provide trading guidance.
            </span>
          </template>
        </el-alert>
      </div>

      <!-- health score -->
      <div class="score-section">
        <div class="score-circle" :class="scoreClass">
          <div class="score-value">{{ report.health_score?.toFixed(0) || '-' }}</div>
          <div class="score-label">health</div>
        </div>
        <div class="risk-badge">
          <el-tag :type="riskTagType" size="large">risk level: {{ report.risk_level || '-' }}</el-tag>
        </div>
      </div>

      <!-- Portfolio overview -->
      <el-card shadow="never" class="section-card">
        <template #header><span>📊 Portfolio overview</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="Position quantity">{{ report.portfolio_snapshot?.total_positions }} only</el-descriptions-item>
          <el-descriptions-item label="Total market capitalization">¥{{ formatNumber(report.portfolio_snapshot?.total_value) }}</el-descriptions-item>
          <el-descriptions-item label="total cost">¥{{ formatNumber(report.portfolio_snapshot?.total_cost) }}</el-descriptions-item>
          <el-descriptions-item label="floating profit and loss">
            <span :class="pnlClass(report.portfolio_snapshot?.unrealized_pnl)">
              {{ formatPnl(report.portfolio_snapshot?.unrealized_pnl) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="Profit and loss ratio">
            <span :class="pnlClass(report.portfolio_snapshot?.unrealized_pnl_pct)">
              {{ formatPct(report.portfolio_snapshot?.unrealized_pnl_pct) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="Analysis takes time">{{ report.execution_time?.toFixed(1) }}s</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- concentration analysis -->
      <el-card shadow="never" class="section-card">
        <template #header><span>📈 concentration analysis</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="The largest share of positions">{{ report.concentration_analysis?.top1_pct?.toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="The proportion of the top three holdings">{{ report.concentration_analysis?.top3_pct?.toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="The proportion of the top five holdings">{{ report.concentration_analysis?.top5_pct?.toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="HHI Index">{{ report.concentration_analysis?.hhi_index?.toFixed(0) }}</el-descriptions-item>
          <el-descriptions-item label="Number of industries">{{ report.concentration_analysis?.industry_count }} a</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- AI Research results -->
      <el-card shadow="never" class="section-card">
        <template #header><span>🤖 AI Research conclusion</span></template>

        <div class="ai-section">
          <div class="ai-title">📝 Comprehensive Research Summary</div>
          <div class="ai-content">{{ report.ai_analysis?.summary || 'None yet' }}</div>
        </div>

        <el-row :gutter="16">
          <el-col :span="12">
            <div class="ai-section">
              <div class="ai-title success">✅ Combination advantages</div>
              <ul class="ai-list">
                <li v-for="(item, idx) in report.ai_analysis?.strengths" :key="idx">{{ item }}</li>
              </ul>
              <div v-if="!report.ai_analysis?.strengths?.length" class="ai-empty">None yet</div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="ai-section">
              <div class="ai-title warning">⚠️ Combination disadvantages</div>
              <ul class="ai-list">
                <li v-for="(item, idx) in report.ai_analysis?.weaknesses" :key="idx">{{ item }}</li>
              </ul>
              <div v-if="!report.ai_analysis?.weaknesses?.length" class="ai-empty">None yet</div>
            </div>
          </el-col>
        </el-row>

        <div class="ai-section">
          <div class="ai-title primary">💡 Suggestions for follow-up observations</div>
          <ul class="ai-list">
            <li v-for="(item, idx) in report.ai_analysis?.suggestions" :key="idx">{{ item }}</li>
          </ul>
          <div v-if="!report.ai_analysis?.suggestions?.length" class="ai-empty">None yet</div>
        </div>
      </el-card>
    </div>
    
    <el-empty v-else description="No analysis data yet" />
    
    <template #footer>
      <el-button @click="$emit('update:visible', false)">close</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PortfolioAnalysisReport } from '@/api/portfolio'

const props = defineProps<{
  visible: boolean
  report?: PortfolioAnalysisReport | null
}>()

defineEmits<{
  'update:visible': [value: boolean]
}>()

const scoreClass = computed(() => {
  const score = props.report?.health_score || 0
  if (score >= 80) return 'excellent'
  if (score >= 60) return 'good'
  if (score >= 40) return 'fair'
  return 'poor'
})

const riskTagType = computed(() => {
  const level = props.report?.risk_level
  if (level === 'low') return 'success'
  if (level === 'in') return 'warning'
  return 'danger'
})

const formatNumber = (val?: number) => {
  if (val === undefined || val === null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatPnl = (val?: number) => {
  if (val === undefined || val === null) return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + formatNumber(val)
}

const formatPct = (val?: number) => {
  if (val === undefined || val === null) return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + val.toFixed(2) + '%'
}

const pnlClass = (val?: number) => {
  if (val === undefined || val === null) return ''
  return val >= 0 ? 'profit' : 'loss'
}
</script>

<style scoped>
.analysis-report {
  max-height: 70vh;
  overflow-y: auto;
}

.score-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40px;
  margin-bottom: 24px;
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  border-radius: 8px;
}

.score-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: white;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.score-circle.excellent { border: 4px solid #67C23A; }
.score-circle.good { border: 4px solid #409EFF; }
.score-circle.fair { border: 4px solid #E6A23C; }
.score-circle.poor { border: 4px solid #F56C6C; }

.score-value {
  font-size: 36px;
  font-weight: 700;
}

.score-circle.excellent .score-value { color: #67C23A; }
.score-circle.good .score-value { color: #409EFF; }
.score-circle.fair .score-value { color: #E6A23C; }
.score-circle.poor .score-value { color: #F56C6C; }

.score-label {
  font-size: 14px;
  color: #909399;
}

.section-card {
  margin-bottom: 16px;
}

.profit { color: #F56C6C; } /* Red indicates profit (Chinese stock market norm) */
.loss { color: #67C23A; } /* Green indicates loss (Chinese stock market norm) */

.ai-section {
  margin-bottom: 16px;
}

.ai-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 14px;
}

.ai-title.success { color: #67C23A; }
.ai-title.warning { color: #E6A23C; }
.ai-title.primary { color: #409EFF; }

.ai-content {
  color: #606266;
  line-height: 1.6;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.ai-list {
  margin: 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.8;
}

.ai-empty {
  color: #909399;
  font-size: 13px;
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

