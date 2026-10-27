<template>
  <div class="unified-task-center">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        unified mission center
      </h1>
      <p class="page-description">View and manage all types of analysis tasks (stock analysis, position research, trade reviews, etc.)</p>
    </div>

    <!-- Statistics cards -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.total }}</div>
            <div class="label">general task</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.pending }}</div>
            <div class="label">Waiting</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.processing }}</div>
            <div class="label">In progress</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.completed }}</div>
            <div class="label">Completed</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.failed }}</div>
            <div class="label">failed</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="stat">
            <div class="value">{{ stats.cancelled }}</div>
            <div class="label">Canceled</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- filter form -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="Task type">
          <el-select v-model="filters.taskType" clearable placeholder="All" style="width: 140px">
            <el-option label="All" value="" />
            <el-option v-for="(name, type) in TaskTypeNames" :key="type" :label="name" :value="type" />
          </el-select>
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="filters.status" clearable placeholder="All" style="width: 120px">
            <el-option label="All" value="" />
            <el-option v-for="(name, status) in TaskStatusNames" :key="status" :label="name" :value="status" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="applyFilters" :loading="loading">Query</el-button>
          <el-button @click="resetFilters">reset</el-button>
          <el-button @click="refreshList" :loading="loading">
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- task list -->
    <el-card class="list-card" shadow="never">
      <el-table :data="taskList" v-loading="loading" style="width: 100%">
        <el-table-column prop="task_id" label="Task ID" width="200" show-overflow-tooltip />
        <el-table-column label="Task type" width="120">
          <template #default="{ row }">
            {{ getTaskTypeName(row.task_type) }}
          </template>
        </el-table-column>
        <el-table-column label="Stock/ticker" width="120">
          <template #default="{ row }">
            {{ row.symbol || row.code || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="market" width="80">
          <template #default="{ row }">
            {{ row.market || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="getTaskStatusColor(row.status)">
              {{ getTaskStatusName(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Progress" width="150">
          <template #default="{ row }">
            <el-progress 
              :percentage="row.progress" 
              :status="row.status === 'failed' ? 'exception' : (row.status === 'completed' ? 'success' : undefined)"
            />
          </template>
        </el-table-column>
        <el-table-column label="creation time" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Execution time" width="100">
          <template #default="{ row }">
            {{ row.execution_time > 0 ? row.execution_time.toFixed(2) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="350" fixed="right">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="viewDetail(row)">Details</el-button>
            <el-button type="text" size="small" @click="viewTraces(row)">Execution trace</el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'processing'"
              type="text"
              size="small"
              @click="cancelTask(row)"
            >
              Cancel
            </el-button>
            <el-button
              v-if="row.status === 'suspended'"
              type="text"
              size="small"
              @click="resumeTask(row)"
              style="color: #67c23a;"
            >
              restore
            </el-button>
            <el-button
              v-if="row.status === 'suspended'"
              type="text"
              size="small"
              @click="cancelTask(row)"
              style="color: #f56c6c;"
            >
              Cancel
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="text"
              size="small"
              @click="showError(row)"
            >
              View errors
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="text"
              size="small"
              @click="retryTask(row)"
              style="color: #409EFF;"
            >
              Reanalyze
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadList"
        @current-change="loadList"
        style="margin-top: 16px; justify-content: flex-end"
      />
    </el-card>

    <!-- Task details dialog -->
    <TaskDetailDialog
      v-model="detailDialogVisible"
      :task-id="selectedTaskId"
      :task-detail="selectedTaskDetail"
    />

    <!-- Execution trace dialog box -->
    <ExecutionTraceDialog
      v-model="traceDialogVisible"
      :task-id="traceTaskId"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { List, Refresh } from '@element-plus/icons-vue'
import {
  getTaskList,
  getTaskStatistics,
  cancelTask as cancelTaskApi,
  resumeTask as resumeTaskApi,
  getTaskDetail,
  TaskTypeNames,
  TaskStatusNames,
  TaskStatusColors,
  type TaskListItem,
  type TaskStatistics,
  type TaskDetail
} from '@/api/unifiedTasks'
import { analysisApi } from '@/api/analysis'
import TaskDetailDialog from './components/TaskDetailDialog.vue'
import ExecutionTraceDialog from './components/ExecutionTraceDialog.vue'

// ==================== Status management ====================

const loading = ref(false)
const taskList = ref<TaskListItem[]>([])
const stats = ref<TaskStatistics>({
  total: 0,
  pending: 0,
  processing: 0,
  completed: 0,
  failed: 0,
  cancelled: 0
})

// Pagination
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// Filter
const filters = ref({
  taskType: '',
  status: ''
})

const getTaskTypeName = (taskType: unknown) => {
  if (typeof taskType !== 'string') {
    return '-'
  }
  return TaskTypeNames[taskType as keyof typeof TaskTypeNames] || taskType
}

const getTaskStatusName = (status: unknown) => {
  if (typeof status !== 'string') {
    return '-'
  }
  return TaskStatusNames[status as keyof typeof TaskStatusNames] || status
}

const getTaskStatusColor = (status: unknown) => {
  if (typeof status !== 'string') {
    return 'info'
  }
  return TaskStatusColors[status as keyof typeof TaskStatusColors] || 'info'
}

// Task details dialog
const detailDialogVisible = ref(false)
const selectedTaskId = ref<string>()
const selectedTaskDetail = ref<TaskDetail | null>(null)

// Execution trace dialog box
const traceDialogVisible = ref(false)
const traceTaskId = ref<string>('')

const viewTraces = (row: TaskListItem) => {
  traceTaskId.value = row.task_id
  traceDialogVisible.value = true
}

// Regular refresh
let refreshTimer: any = null

// ==================== method ====================

/**
 * Load task list
 */
const loadList = async () => {
  loading.value = true
  try {
    // Do not pass the limit parameter, let the backend return all records, and the frontend handles paging
    const params: any = {
      skip: (currentPage.value - 1) * pageSize.value
    }

    if (filters.value.taskType) {
      params.task_type = filters.value.taskType
    }
    if (filters.value.status) {
      params.status = filters.value.status
    }

    const res = await getTaskList(params)
    const data = (res as any)?.data?.data || (res as any)?.data || {}

    // Get all tasks and then paginate them on the frontend
    const allTasks = data.tasks || []
    const startIdx = (currentPage.value - 1) * pageSize.value
    const endIdx = startIdx + pageSize.value

    taskList.value = allTasks.slice(startIdx, endIdx)
    total.value = allTasks.length
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to load task list')
  } finally {
    loading.value = false
  }
}

/**
 * Load statistics
 */
const loadStats = async () => {
  try {
    const res = await getTaskStatistics()
    const data = (res as any)?.data?.data || (res as any)?.data || {}
    stats.value = data
  } catch (e: any) {
    console.error('Failed to load statistics:', e)
  }
}

/**
 * Apply filters
 */
const applyFilters = () => {
  currentPage.value = 1
  loadList()
}

/**
 * Reset filter
 */
const resetFilters = () => {
  filters.value = {
    taskType: '',
    status: ''
  }
  currentPage.value = 1
  loadList()
}

/**
 * Refresh list
 */
const refreshList = () => {
  loadList()
  loadStats()
}

/**
 * View task details
 */
const viewDetail = async (row: TaskListItem) => {
  try {
    selectedTaskId.value = row.task_id
    selectedTaskDetail.value = null
    
    // Load task details
    const res = await getTaskDetail(row.task_id)
    const data = (res as any)?.data?.data || (res as any)?.data || {}
    
    selectedTaskDetail.value = data as TaskDetail
    detailDialogVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to get task details')
  }
}

/**
 * Cancel task
 */
const cancelTask = async (row: TaskListItem) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to cancel the task "${row.task_id}" ?`,
      'Confirm action',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    loading.value = true
    await cancelTaskApi(row.task_id)
    ElMessage.success('Task canceled')
    await refreshList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || 'Failed to cancel task')
    }
  } finally {
    loading.value = false
  }
}

/**
 * Resume a suspended task
 */
const resumeTask = async (row: TaskListItem) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to resume task "${row.task_id}" ? The task will be re-queued for execution.`,
      'Confirm action',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'info'
      }
    )

    loading.value = true
    await resumeTaskApi(row.task_id)
    ElMessage.success('Task has been resumed and is being requeued...')
    await refreshList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || 'Recovery task failed')
    }
  } finally {
    loading.value = false
  }
}

/**
 * Show error message
 */
const showError = async (row: TaskListItem) => {
  const errorMessage = row.error_message || 'unknown error'

  await ElMessageBox.alert(
    errorMessage.replace(/\n/g, '<br>'),
    'Error details',
    {
      confirmButtonText: 'OK',
      type: 'error',
      dangerouslyUseHTMLString: true,
      customStyle: {
        width: '600px'
      }
    }
  )
}

/**
 * Recreate failed tasks
 */
const retryTask = async (row: TaskListItem) => {
  try {
    const taskId = row.task_id
    if (!taskId) {
      ElMessage.error('Task ID does not exist')
      return
    }

    loading.value = true
    
    const res = await analysisApi.retryTask(taskId)
    const body = (res as any)?.data || res
    
    if (body.success) {
      ElMessage.success(`Task has been recreated, new task ID: ${body.task_id}`)
      // Refresh list
      await refreshList()
    } else {
      ElMessage.error(body.message || 'Failed to recreate task')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'Failed to recreate task')
  } finally {
    loading.value = false
  }
}

/**
 * Format time
 */
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

/**
 * Set scheduled refresh
 */
const setupAutoRefresh = () => {
  // Refresh every 10 seconds
  refreshTimer = setInterval(() => {
    loadList()
    loadStats()
  }, 10000)
}

// ==================== life cycle ====================

onMounted(() => {
  loadList()
  loadStats()
  setupAutoRefresh()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped lang="scss">
.unified-task-center {
  padding: 20px;

  .page-header {
    margin-bottom: 20px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      color: #303133;
      margin: 0 0 8px 0;
    }

    .page-description {
      color: #909399;
      font-size: 14px;
      margin: 0;
    }
  }

  .stat {
    text-align: center;
    padding: 12px 0;

    .value {
      font-size: 28px;
      font-weight: 600;
      color: #409EFF;
      margin-bottom: 4px;
    }

    .label {
      font-size: 14px;
      color: #909399;
    }
  }

  .filter-card {
    margin-bottom: 16px;
  }

  .list-card {
    :deep(.el-card__body) {
      padding: 20px;
    }
  }
}
</style>


