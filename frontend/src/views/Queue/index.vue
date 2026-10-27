<template>
  <div class="queue-management">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        mission center
      </h1>
      <p class="page-description">
        Real-time monitoring and management of analysis task status
      </p>
    </div>

    <!-- Queue task list -->
    <el-card class="queue-list-card" header="task queue">
      <template #header>
        <div class="card-header">
          <span>task queue</span>
          <div class="header-actions">
            <el-button type="text" @click="refreshQueue">
              <el-icon><Refresh /></el-icon>
              Refresh
            </el-button>
            <el-button type="text" @click="clearCompleted">
              <el-icon><Delete /></el-icon>
              Cleanup completed
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="queueTasks" v-loading="loading" style="width: 100%" @mouseenter="isInteracting = true" @mouseleave="isInteracting = false">
        <el-table-column prop="task_id" label="Task ID" width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="viewTaskDetail(row)">
              {{ row.task_id.substring(0, 8) }}...
            </el-link>
          </template>
        </el-table-column>

        <el-table-column prop="stock_code" label="Stock code" width="120" />
        <el-table-column prop="stock_name" label="Stock name" width="150" />

        <el-table-column prop="status" label="Status" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="progress" label="Progress" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :status="getProgressStatus(row.status)"
              :stroke-width="8"
            />
          </template>
        </el-table-column>

        <el-table-column prop="priority" label="priority" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.priority > 0" type="warning" size="small">
              high ({{ row.priority }})
            </el-tag>
            <span v-else>Ordinary</span>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="creation time" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="Operation" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              type="text"
              size="small"
              @click="cancelTask(row)"
            >
              Cancel
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="text"
              size="small"
              @click="retryTask(row)"
            >
              Try again
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewResult(row)"
            >
              View results
            </el-button>
            <el-button type="text" size="small" @click="viewTaskDetail(row)">
              Details
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="totalTasks"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- View results popup -->
    <el-dialog v-model="resultDialogVisible" title="Task results" width="60%">
      <div v-if="resultData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Stock code">{{ resultData.stock_symbol || resultData.stock_code || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Status">{{ getStatusText(deriveStatusForDialog(resultData, currentTaskRow)) }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top: 16px;">
          <h4>Suggestions</h4>
          <div class="markdown-content" v-html="renderMarkdown(resultData.recommendation || 'None')"></div>
        </div>
        <div style="margin-top: 16px;">
          <h4>Summary</h4>
          <div class="markdown-content" v-html="renderMarkdown(resultData.summary || 'None')"></div>
        </div>
      </div>
      <template #footer>
        <el-button @click="resultDialogVisible = false">close</el-button>
        <el-button type="primary" @click="openReportDialog">View report details</el-button>
      </template>
    </el-dialog>

    <!-- Task details pop-up window -->
    <el-dialog v-model="detailDialogVisible" title="Mission details" width="50%">
      <div v-if="detailData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Task ID">{{ detailData.task_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Status">{{ getStatusText(deriveStatusForDialog(detailData, currentTaskRow)) }}</el-descriptions-item>
          <el-descriptions-item label="Progress">{{ (detailData.progress ?? 0) + '%' }}</el-descriptions-item>
          <el-descriptions-item label="start time">{{ formatTime(detailData.start_time || detailData.created_at || new Date().toISOString()) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>

    <!-- Report details pop-up window -->
    <el-dialog v-model="reportDialogVisible" title="Report details" width="70%">
      <template v-if="reportSections.length > 0">
        <el-tabs v-model="activeReportTab">
          <el-tab-pane
            v-for="(sec, idx) in reportSections"
            :key="sec.key || idx"
            :label="sec.title"
            :name="String(idx)"
          >
            <div
              v-if="typeof sec.content === 'string'"
              class="markdown-content"
              v-html="renderMarkdown(sec.content)"
            ></div>
            <div v-else class="json-content">
              <pre>{{ JSON.stringify(sec.content, null, 2) }}</pre>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
      <template v-else>
        <el-empty description="There is currently no report content to display." />
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

import { analysisApi } from '@/api/analysis'
import { fetchTaskResultWithRetry } from '@/utils/taskResult'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'

// Simple Markdown rendering, consistent with single stock research
// marked The configuration has been @/utils/markdown Unified management
const renderMarkdown = (content: string) => {
  if (!content) return ''
  try {
    return safeMarkdown(content)
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}

import {
  List,
  Refresh,
  Delete
} from '@element-plus/icons-vue'

// routing
const router = useRouter()

// Responsive data
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const totalTasks = ref(0)



const queueTasks = ref<any[]>([])

// Current line reference (used for pop-up window status)
const currentTaskRow = ref<any | null>(null)

// Results/Details/Report Pop-up status
const resultDialogVisible = ref(false)
const resultData = ref<any | null>(null)
const detailDialogVisible = ref(false)
const detailData = ref<any | null>(null)
const reportDialogVisible = ref(false)
const reportSections = ref<Array<{ key: string; title: string; content: any }>>([])
const activeReportTab = ref('0')

// Whether in user interaction (mouseover, selection, etc.), used to suppress automatic refresh
const isInteracting = ref(false)

// timer
let refreshTimer: NodeJS.Timeout | null = null
// const AUTO_REFRESH_MS = 30000 // 30 seconds (auto refresh turned off)


// method

// unified state normalization
const normalizeStatusValue = (s?: string): string => {
  if (!s) return 'pending'
  if (s === 'running') return 'processing'
  if (s === 'cancelled') return 'cancelled'
  return s
}

const deriveStatusForDialog = (data: any, row: any): string => {
  const s = data?.status ?? row?.status
  if (s) return normalizeStatusValue(s)
  if (typeof data?.success === 'boolean') return data.success ? 'completed' : 'failed'
  if (typeof data?.progress === 'number') return data.progress >= 100 ? 'completed' : (data.progress > 0 ? 'processing' : 'pending')
  if (data?.summary || data?.recommendation) return 'completed'

  return 'pending'
}

const refreshQueue = async () => {
  loading.value = true
  try {
    // Do not pass the limit parameter and let the backend return all records
    const res = await analysisApi.getTaskList({
      offset: (currentPage.value - 1) * pageSize.value,
    })

    // The backend returns ApiResponse uniformly, and the data is in res.data.data
    const body = res?.data?.data || {}
    const allTasksRaw = body?.tasks || []

    // Pagination on the frontend
    const startIdx = (currentPage.value - 1) * pageSize.value
    const endIdx = startIdx + pageSize.value
    const tasksRaw = allTasksRaw.slice(startIdx, endIdx)

    const tasks = tasksRaw.map((t: any) => ({
      task_id: t.task_id,
      stock_code: t.stock_code,
      stock_name: t.stock_name || '',
      status: normalizeStatusValue(t.status),
      progress: typeof t.progress === 'number' ? t.progress : 0,
      priority: 0,
      created_at: t.start_time || new Date().toISOString(),
    }))

    queueTasks.value = tasks
    totalTasks.value = allTasksRaw.length
    ElMessage.success('Queue data has been refreshed')
  } catch (error) {
    ElMessage.error('Refresh failed')
  } finally {
    loading.value = false
  }
}

const clearCompleted = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear all completed tasks?',
      'Confirm cleanup',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    ElMessage.success('Completed tasks cleared')
  } catch {
    // User cancels
  }
}

const cancelTask = async (task: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to cancel the task ${task.task_id} ?`,
      'Confirm cancellation',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    ElMessage.success('Task canceled')
  } catch {
    // User cancels
  }
}

const retryTask = (task: any) => {
  ElMessage.success(`Task ${task.task_id} Requeued`)
}

const viewResult = async (task: any) => {
  try {
    currentTaskRow.value = task
    const data = await fetchTaskResultWithRetry(task.task_id, {
      seedData: task.result_data
    })
    if (!data) {
      ElMessage.warning('Task results are temporarily unavailable')
      return
    }
    resultData.value = data
    resultDialogVisible.value = true
  } catch (e) {
    ElMessage.error('Failed to get results')
  }
}

const viewTaskDetail = async (task: any) => {
  try {
    currentTaskRow.value = task
    // Only call /status to avoid invalid /details 404 noise
    const res = await analysisApi.getTaskStatus(task.task_id)
    // The response interceptor has returned response.data, so res is ApiResponse<T>
    const data = res?.data
    if (!data) {
      ElMessage.warning('No detailed data yet')
      return
    }
    detailData.value = data
    detailDialogVisible.value = true
  } catch (e) {
    ElMessage.error('Failed to get task details')
  }
}

const openReportDialog = () => {
  // Use task_id first, then analysis_id (the backend is compatible with task_id/analysis_id/_id)
  const id = currentTaskRow.value?.task_id
    || resultData.value?.task_id
    || detailData.value?.task_id
    || resultData.value?.analysis_id
    || detailData.value?.result_data?.analysis_id
    || currentTaskRow.value?.analysis_id
  if (!id) {
    ElMessage.warning('Report ID not found, unable to jump')
    return
  }
  resultDialogVisible.value = false
  router.push({ name: 'ReportDetail', params: { id } })
}


const getStatusType = (status: string): 'success' | 'info' | 'warning' | 'danger' => {
  const statusMap: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return statusMap[status] ?? 'info'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    pending: 'Waiting',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'failed',
    cancelled: 'Canceled'
  }
  return statusMap[status] || status
}

const getProgressStatus = (status: string) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
}

// Monitor paging changes and automatically refresh
watch([currentPage, pageSize], () => {
  refreshQueue()
})

// life cycle
onMounted(async () => {
  // Pull it immediately when entering for the first time
  await refreshQueue()
  // Auto-refresh is turned off. If you need to re-enable it, it can be restored to setInterval
  // refreshTimer = setInterval(() => { refreshQueue() }, AUTO_REFRESH_MS)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style lang="scss" scoped>
.queue-management {
  .page-header {
    margin-bottom: 24px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
    }

    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .stats-row {
    margin-bottom: 24px;

    .stat-card {
      .stat-content {
        display: flex;
        align-items: center;
        gap: 16px;

        .stat-icon {
          width: 48px;
          height: 48px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          color: white;

          &.pending {
            background: linear-gradient(135deg, #909399, #c0c4cc);
          }

          &.processing {
            background: linear-gradient(135deg, #e6a23c, #f7ba2a);
          }

          &.completed {
            background: linear-gradient(135deg, #67c23a, #85ce61);
          }

          &.failed {
            background: linear-gradient(135deg, #f56c6c, #f78989);
          }
        }

        .stat-info {
          .stat-value {
            font-size: 24px;
            font-weight: 600;
            color: var(--el-text-color-primary);
            line-height: 1;
          }

          .stat-label {
            font-size: 14px;
            color: var(--el-text-color-regular);
            margin-top: 4px;
          }
        }
      }
    }
  }

  .queue-list-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .header-actions {
        display: flex;
        gap: 8px;
      }
    }

    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 24px;
    }
  }
}
</style>
