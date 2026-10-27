<template>
  <el-dialog
    v-model="visible"
    title="Mission details"
    width="1200px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="task-detail">
      <template v-if="taskDetail">
        <!-- Basic information -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <el-icon><InfoFilled /></el-icon>
              <span>Basic information</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Task ID" :span="2">
              <el-text copyable>{{ taskDetail.task_id }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="Task type">
              <el-tag>{{ TaskTypeNames[taskDetail.task_type] || taskDetail.task_type }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Status">
              <el-tag :type="TaskStatusColors[taskDetail.status]">
                {{ TaskStatusNames[taskDetail.status] || taskDetail.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Progress">
              <el-progress 
                :percentage="taskDetail.progress" 
                :status="taskDetail.status === 'failed' ? 'exception' : (taskDetail.status === 'completed' ? 'success' : undefined)"
              />
            </el-descriptions-item>
            <el-descriptions-item label="current step">
              {{ taskDetail.current_step || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="Engine type">
              {{ taskDetail.engine_type }}
            </el-descriptions-item>
            <el-descriptions-item label="Preference type">
              {{ taskDetail.preference_type }}
            </el-descriptions-item>
            <el-descriptions-item label="Workflow ID">
              {{ taskDetail.workflow_id || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- time information -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <el-icon><Clock /></el-icon>
              <span>time information</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="creation time">
              {{ formatTime(taskDetail.created_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="start time">
              {{ taskDetail.started_at ? formatTime(taskDetail.started_at) : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="completion time">
              {{ taskDetail.completed_at ? formatTime(taskDetail.completed_at) : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="Execution time">
              {{ taskDetail.execution_time > 0 ? taskDetail.execution_time.toFixed(2) + 's' : '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- Task parameters -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <el-icon><Setting /></el-icon>
              <span>Task parameters</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <template v-for="(value, key) in taskDetail.task_params" :key="key">
              <el-descriptions-item :label="formatLabel(key)">
                <template v-if="isArray(value)">
                  <el-tag 
                    v-for="(item, idx) in value" 
                    :key="idx" 
                    style="margin-right: 4px; margin-bottom: 4px"
                  >
                    {{ formatArrayItem(key, item) }}
                  </el-tag>
                </template>
                <template v-else-if="isObject(value)">
                  <el-collapse>
                    <el-collapse-item :title="`View ${formatLabel(key)} Details`" :name="key">
                      <pre class="json-content">{{ JSON.stringify(value, null, 2) }}</pre>
                    </el-collapse-item>
                  </el-collapse>
                </template>
                <template v-else>
                  {{ formatValue(value) }}
                </template>
              </el-descriptions-item>
            </template>
          </el-descriptions>
        </el-card>

        <!-- Execution statistics -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <el-icon><DataAnalysis /></el-icon>
              <span>Execution statistics</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Number of retries">
              {{ taskDetail.retry_count }} / {{ taskDetail.max_retries }}
            </el-descriptions-item>
            <el-descriptions-item label="Token Usage">
              {{ taskDetail.tokens_used || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="cost">
              {{ taskDetail.cost ? '¥' + taskDetail.cost.toFixed(4) : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="User ID">
              <el-text copyable>{{ taskDetail.user_id }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="Number of candidate memories">
              {{ growthSummary.memory_items_count }}
            </el-descriptions-item>
            <el-descriptions-item label="Number of growth suggestions">
              {{ growthSummary.suggestions_count }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <TaskGrowthPanel
          class="section-card"
          :task-id="taskDetail.task_id"
          :initial-context="growthContext"
          close-on-navigate
          @navigated="visible = false"
          @updated="handleGrowthUpdated"
        />

        <!-- error message -->
        <el-card v-if="taskDetail.error_message" shadow="never" class="section-card error-card">
          <template #header>
            <div class="card-header">
              <el-icon><Warning /></el-icon>
              <span>error message</span>
            </div>
          </template>
          <el-alert
            :title="taskDetail.error_message"
            type="error"
            :closable="false"
            show-icon
          />
        </el-card>

        <!-- Single Stock Research Task - View Report Button (shown even if no results data is available) -->
        <el-card v-if="isStockAnalysisTask && !hasResult" shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <el-icon><Document /></el-icon>
              <span>research report</span>
            </div>
          </template>
          <div style="padding: 16px;">
            <el-button
              type="primary"
              @click="goToReport"
            >
              <el-icon><Document /></el-icon>
              View research report
            </el-button>
          </div>
        </el-card>

        <!-- Result data (if any) -->
        <el-card v-if="hasResult" shadow="never" class="section-card">
          <template #header>
            <div class="card-header" style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-icon><Document /></el-icon>
                <span>Result data</span>
              </div>
              <el-button
                v-if="isStockAnalysisTask"
                type="primary"
                size="small"
                @click="goToReport"
              >
                <el-icon><Document /></el-icon>
                View report
              </el-button>
            </div>
          </template>
          <el-collapse>
            <el-collapse-item title="View result details" name="result">
              <pre class="json-content">{{ JSON.stringify(taskDetail.result, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>

      <el-empty v-else-if="!loading" description="No data yet" />
    </div>

    <template #footer>
      <el-button @click="visible = false">close</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { InfoFilled, Clock, Setting, DataAnalysis, Warning, Document } from '@element-plus/icons-vue'
import { TaskType, TaskTypeNames, TaskStatusNames, TaskStatusColors, type TaskDetail } from '@/api/unifiedTasks'
import type { TaskGrowthContextPayload } from '@/api/workflowGrowth'
import TaskGrowthPanel from '@/components/growth/TaskGrowthPanel.vue'
import { convertAnalystIdsToNames } from '@/constants/analysts'

const props = defineProps<{
  modelValue: boolean
  taskId?: string
  taskDetail?: TaskDetail | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const loading = ref(false)
const router = useRouter()
const growthContext = ref<TaskGrowthContextPayload | null>(null)
const growthSummary = computed(() => {
  const direct = growthContext.value?.summary
  const fromTask = props.taskDetail?.growth_context
  const fromResult = props.taskDetail?.result?.growth_context

  return {
    memory_items_count: direct?.memory_items_count ?? fromTask?.memory_items_count ?? fromResult?.memory_items_count ?? 0,
    suggestions_count: direct?.suggestions_count ?? fromTask?.suggestions_count ?? fromResult?.suggestions_count ?? 0
  }
})

// Determine whether there is result data
const hasResult = computed(() => {
  return props.taskDetail?.result && Object.keys(props.taskDetail.result).length > 0
})

// Determine whether it is a single stock research task
const isStockAnalysisTask = computed(() => {
  const taskType = props.taskDetail?.task_type
  const isStockAnalysis = taskType === TaskType.STOCK_ANALYSIS || taskType === TaskType.ETF_ANALYSIS
  
  // debug log
  if (process.env.NODE_ENV === 'development') {
    console.log('[TaskDetailDialog] Task type judgment:', {
      taskType,
      TaskType_STOCK_ANALYSIS: TaskType.STOCK_ANALYSIS,
      isStockAnalysis
    })
  }
  
  return isStockAnalysis
})

const handleGrowthUpdated = (context: TaskGrowthContextPayload | null) => {
  growthContext.value = context
}

// Get report ID (extracted from task results)
const reportId = computed(() => {
  // For single-stock research tasks, task_id is preferred (because the reporting API supports querying by task_id)
  if (isStockAnalysisTask.value && props.taskDetail?.task_id) {
    // If there is a result, use the one in the result first.analysis_id
    if (props.taskDetail?.result) {
      const result = props.taskDetail.result
      // Use analysis_id first, then use task_id
      const id = result.analysis_id || props.taskDetail.task_id
      
      // Debug log (development environment)
      if (process.env.NODE_ENV === 'development') {
        console.log('[TaskDetailDialog] Report ID extraction:', {
          taskType: props.taskDetail?.task_type,
          task_id: props.taskDetail.task_id,
          result_analysis_id: result.analysis_id,
          result_report_id: result.report_id,
          final_reportId: id
        })
      }
      
      return id
    }
    
    // If there is no result, use it directly task_id
    return props.taskDetail.task_id
  }
  
  return null
})

// Jump to report details page
const goToReport = () => {
  // Use reportId first, if not, use task_id
  const id = reportId.value || props.taskDetail?.task_id
  
  if (!id) {
    console.error('[TaskDetailDialog] Unable to jump: Missing report ID', {
      reportId: reportId.value,
      task_id: props.taskDetail?.task_id,
      taskDetail: props.taskDetail
    })
    ElMessage.error('Unable to get report ID, please try again later')
    return
  }
  
  // debug log
  if (process.env.NODE_ENV === 'development') {
    console.log('[TaskDetailDialog] Jump to report details page:', {
      reportId: id,
      task_id: props.taskDetail?.task_id,
      task_type: props.taskDetail?.task_type
    })
  }
  
  try {
    router.push(`/reports/view/${id}`)
    visible.value = false // Close dialog
  } catch (error) {
    console.error('[TaskDetailDialog] Jump failed:', error)
    ElMessage.error('Jump failed, please try again later')
  }
}

// formatting tags
const formatLabel = (key: string): string => {
  const labelMap: Record<string, string> = {
    symbol: 'Stock code',
    stock_code: 'Stock code',
    code: 'code',
    market_type: 'market type',
    market: 'market',
    analysis_date: 'Analysis date',
    research_depth: 'Research depth',
    selected_analysts: 'Selected Analyst',
    custom_prompt: 'Custom prompt words',
    include_sentiment: 'Contains sentiment analysis',
    include_risk: 'Include risk assessment',
    language: 'language',
    quick_analysis_model: 'Quickly analyze models',
    deep_analysis_model: 'Deep analysis model',
    workflow_id: 'Workflow ID',
    preference_type: 'Preference type',
    position_type: 'Position type',
    risk_tolerance: 'risk tolerance',
    ticker: 'Stock code',
    company_name: 'Company name',
    market_name: 'Market name',
    currency_name: 'currency name',
    currency_symbol: 'currency symbol',
    lookback_days: 'Number of days to look back',
    max_debate_rounds: 'Maximum number of debate rounds'
  }
  return labelMap[key] || key
}

// Format value
const formatValue = (value: any): string => {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' && value.length > 100) {
    return value.substring(0, 100) + '...'
  }
  return String(value)
}

// Format array items (special handling of analyst names)
const formatArrayItem = (key: string, item: any): string => {
  // If it is the selected analyst field, convert the English ID to a Chinese name
  if (key === 'selected_analysts' && typeof item === 'string') {
    const chineseNames = convertAnalystIdsToNames([item])
    return chineseNames[0] || item
  }
  return String(item)
}

// Determine whether it is an array
const isArray = (value: any): boolean => {
  return Array.isArray(value)
}

// Determine whether it is an object
const isObject = (value: any): boolean => {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
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
    minute: '2-digit',
    second: '2-digit'
  })
}

watch(
  () => [props.modelValue, props.taskDetail?.growth_context, props.taskDetail?.result?.growth_context],
  ([visible]) => {
    if (visible) {
      growthContext.value = (props.taskDetail?.growth_context as TaskGrowthContextPayload | null)
        || (props.taskDetail?.result?.growth_context as TaskGrowthContextPayload | null)
        || null
    }
  },
  { immediate: true }
)

</script>

<style scoped lang="scss">
  .growth-item {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 16px;
    background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  }

  .growth-item-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }

  .growth-item-title-row {
    display: flex;
    flex-direction: column;
    gap: 8px;

    h4 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: #1f2937;
    }
  }

  .growth-item-tags,
  .growth-actions,
  .growth-evidence {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .growth-summary-text {
    margin: 0 0 10px;
    color: #4b5563;
    line-height: 1.7;
  }

  .growth-content {
    white-space: pre-wrap;
    line-height: 1.7;
    color: #1f2937;
  }

  .growth-evidence {
    margin-top: 10px;
    align-items: center;
  }

  .growth-meta-label {
    color: #6b7280;
    font-size: 13px;
  }
</style>

