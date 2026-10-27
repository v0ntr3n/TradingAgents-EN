<template>
  <div class="task-center">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        mission center
      </h1>
      <p class="page-description">Unified view and management of analysis tasks: in progress/completed/failed</p>
    </div>

    <el-card class="tabs-card" shadow="never">
      <el-tabs v-model="activeTab" @tab-click="onTabChange">
        <el-tab-pane label="In progress" name="running" />
        <el-tab-pane label="Completed" name="completed" />
        <el-tab-pane label="failed" name="failed" />
        <el-tab-pane label="All" name="all" />
      </el-tabs>
    </el-card>

    <!-- filter form -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="time range">
          <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="to" start-placeholder="start date" end-placeholder="end date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 260px" />
        </el-form-item>
        <el-form-item label="market">
          <el-select v-model="filters.market" clearable placeholder="All" style="width: 120px">
            <el-option label="All" value="" />
            <el-option label="A shares" value="A shares" />
          </el-select>
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="filters.status" clearable placeholder="All" style="width: 120px">
            <el-option label="All" value="" />
            <el-option label="In progress" value="processing" />
            <el-option label="Completed" value="completed" />
            <el-option label="failed" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="stocks">
          <el-input v-model="filters.stock" placeholder="code or name" style="width: 160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="applyFilters" :loading="loading">Query</el-button>
          <el-button @click="resetFilters">reset</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Statistics cards -->
    <el-row :gutter="16" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.total }}</div><div class="label">general task</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.completed }}</div><div class="label">Completed</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.failed }}</div><div class="label">failed</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.uniqueStocks }}</div><div class="label">Number of shares</div></div></el-card>
      </el-col>
    </el-row>


    <el-card class="list-card" shadow="never">
      <div class="list-header">
        <div class="left">
          <el-input v-model="keyword" placeholder="Search ticker/name" clearable style="width: 220px" />
          <el-button @click="refreshList" :loading="loading">
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </div>
        <div class="right">
          <el-button @click="exportSelected" :disabled="selectedRows.length===0">
            <el-icon><Download /></el-icon>
            Export selected
          </el-button>
        </div>
      </div>

      <el-table :data="filteredList" v-loading="loading" style="width: 100%" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="task_id" label="Task ID" width="220" />
        <el-table-column prop="stock_code" label="Stock code" width="120" />
        <el-table-column prop="stock_name" label="Stock name" width="150" />
        <el-table-column label="Status" width="110">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="Progress" width="120">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :status="row.status==='failed'?'exception':(row.status==='completed'?'success':undefined)"/>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="start time" width="180">
          <template #default="{ row }">
            {{ formatTime(row.start_time || row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="350" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status==='completed'" type="text" size="small" @click="openResult(row)">View results</el-button>
            <el-button v-if="row.status==='completed'" type="text" size="small" @click="openReport(row)">Report details</el-button>
            <el-button v-if="row.status==='failed'" type="text" size="small" @click="showErrorDetail(row)">View errors</el-button>
            <el-button v-if="row.status==='failed'" type="text" size="small" @click="retryTask(row)">Try again</el-button>
            <el-button v-if="row.status==='processing' || row.status==='running' || row.status==='pending'" type="text" size="small" @click="markAsFailed(row)">Marking failed</el-button>
            <el-button type="text" size="small" @click="deleteTask(row)" style="color: #f56c6c;">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- Result pop-up window componentization -->
    <TaskResultDialog
      v-model="resultVisible"
      :result="currentResult"
      @close="resultVisible=false"
      @view-report="openReport(currentRow)"
    />


    <!-- Report details pop-up window componentized (reserved) -->
    <TaskReportDialog v-model="reportVisible" :sections="reportSections" @close="reportVisible=false" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { List, Refresh, Download } from '@element-plus/icons-vue'
import { analysisApi } from '@/api/analysis'
import { fetchTaskResultWithRetry } from '@/utils/taskResult'
import { createWebSocket, type ManagedWebSocket } from '@/utils/createWebSocket'
import TaskResultDialog from '@/components/Global/TaskResultDialog.vue'
import TaskReportDialog from '@/components/Global/TaskReportDialog.vue'

const router = useRouter()
const route = useRoute()

const activeTab = ref<'running'|'completed'|'failed'|'all'>('running')
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const list = ref<any[]>([])
const selectedRows = ref<any[]>([])
// Screening and Statistics
const filters = ref<{ dateRange: string[]; market: string; status: string; stock: string }>({
  dateRange: [], market: '', status: '', stock: ''
})
const stats = ref({ total: 0, completed: 0, failed: 0, uniqueStocks: 0 })


// WebSocket Connection management
let wsConnections: Map<string, ManagedWebSocket> = new Map()
let timer: any = null

const setupPolling = () => {
  clearInterval(timer)
  // Refresh the list periodically (every 5 seconds)
  if (activeTab.value === 'running') {
    timer = setInterval(() => loadList(), 5000)
  }
}

// Connect to WebSocket to get task progress
const connectTaskWebSocket = (taskId: string) => {
  if (wsConnections.has(taskId)) {
    return // Connected
  }

  try {
    const ws = createWebSocket(`/api/ws/task/${taskId}`, {
      autoReconnect: true,
      maxReconnectAttempts: 5,
      heartbeatInterval: 0,
      onOpen: () => {
        console.log(`✅ WebSocket Connection successful: ${taskId}`)
      },
      onMessage: (message) => {
        if (message.type === 'progress_update') {
          // Update task progress in list
          const taskIndex = list.value.findIndex(t => t.task_id === taskId)
          if (taskIndex >= 0) {
            list.value[taskIndex].progress = message.progress
            list.value[taskIndex].status = message.status
            list.value[taskIndex].message = message.message
            console.log(`📊 Update task progress: ${taskId} -> ${message.progress}%`)
          }
        }
      },
      onError: (error) => {
        console.error(`❌ WebSocket Error: ${taskId}`, error)
      },
      onClose: () => {
        console.log(`🔌 WebSocket Disconnect: ${taskId}`)
        wsConnections.delete(taskId)
      },
    })

    wsConnections.set(taskId, ws)
  } catch (e) {
    console.error('WebSocket Connection failed:', e)
  }
}

// Disconnect all WebSocket connections
const disconnectAllWebSockets = () => {
  wsConnections.forEach((ws) => {
    try {
      ws.close()
    } catch (e) {
      console.error('Failed to close WebSocket:', e)
    }
  })
  wsConnections.clear()
}

const statusParam = computed(() => {
  if (activeTab.value === 'all') return undefined
  if (activeTab.value === 'running') return 'processing'
  return activeTab.value
})

const loadList = async () => {
  loading.value = true
  try {
    // Construct parameters based on filters and tabs
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
      status: filters.value.status || statusParam.value,
      stock_code: filters.value.stock || undefined
    }
    if (filters.value.market) params.market_type = filters.value.market
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0]
      params.end_date = filters.value.dateRange[1]
    }

    const res = await analysisApi.getHistory(params)
    const body = (res as any)?.data?.data || (res as any)?.data || {}
    let tasks = body.tasks || body.analyses || []

    // When there are no filtering conditions and the history interface is empty, the task list interface is used (to ensure that the data can be seen)
    const noExtraFilters = !filters.value.market && !filters.value.stock && (!filters.value.dateRange || filters.value.dateRange.length === 0)
    if (tasks.length === 0 && noExtraFilters) {
      try {
        // Do not pass the limit parameter and let the backend return all records
        const res2 = await analysisApi.getTaskList({
          status: statusParam.value,
          offset: (currentPage.value - 1) * pageSize.value
        })
        const body2 = (res2 as any)?.data?.data || {}
        const allTasks = body2.tasks || []

        // Pagination on the frontend
        const startIdx = (currentPage.value - 1) * pageSize.value
        const endIdx = startIdx + pageSize.value
        tasks = allTasks.slice(startIdx, endIdx)
        total.value = allTasks.length
      } catch (error) {
        console.debug('[TaskCenter] Failed to load rollback task list:', error)
      }
    } else {
      total.value = body.total ?? tasks.length
    }

    list.value = tasks

    // Connect to running tasks WebSocket
    tasks.forEach((task: any) => {
      if (task.status === 'processing' || task.status === 'running' || task.status === 'pending') {
        connectTaskWebSocket(task.task_id)
      }
    })

    // statistics
    const completed = tasks.filter((x:any) => x.status === 'completed').length
    const failed = tasks.filter((x:any) => x.status === 'failed').length
    const uniqueStocks = new Set(tasks.map((x:any) => x.stock_code || x.stock_symbol)).size
    stats.value = { total: tasks.length, completed, failed, uniqueStocks }
  } catch (e:any) {
    ElMessage.error(e?.message || 'Loading failed')
  } finally {
    loading.value = false
  }
}

// Query/Reset
const applyFilters = () => { currentPage.value = 1; loadList() }
const resetFilters = () => { filters.value = { dateRange: [], market: '', status: '', stock: '' }; currentPage.value = 1; loadList() }

// Report popup status
const reportVisible = ref(false)
const reportSections = ref<Array<{ key?: string; title: string; content: any }>>([])

const filteredList = computed(() => {
  let arr = list.value
  if (keyword.value) {
    const k = keyword.value.toLowerCase()
    arr = arr.filter((x:any) => (x.stock_code||'').toLowerCase().includes(k) || (x.stock_name||'').toLowerCase().includes(k) || (x.task_id||'').toLowerCase().includes(k))
  }
  return arr
})

const handleSizeChange = (size:number) => { pageSize.value = size; currentPage.value = 1; loadList() }
const handleCurrentChange = (page:number) => { currentPage.value = page; loadList() }
const onTabChange = () => {
  // Use nextTick to ensure that the value of activeTab has been updated
  nextTick(() => {
    currentPage.value = 1
    loadList()
    setupPolling()
  })
}
const refreshList = () => loadList()
const onSelectionChange = (rows:any[]) => { selectedRows.value = rows }

// Results and reports
const resultVisible = ref(false)
const currentResult = ref<any>(null)
const currentRow = ref<any>(null)

const openResult = async (row:any) => {
  currentRow.value = row
  try {
    const body = await fetchTaskResultWithRetry(row.task_id, {
      seedData: row.result_data
    })
    currentResult.value = body
    resultVisible.value = true
  } catch (e:any) {
    ElMessage.error('Failed to get results')
  }
}

const openReport = (row:any) => {
  const id = row?.task_id || row?.analysis_id || row?.id
  if (!id) {
    ElMessage.warning('Report not found ID')
    return
  }
  router.push({ name: 'ReportDetail', params: { id } })
}

// Recreate failed tasks
const retryTask = async (row: any) => {
  try {
    const taskId = row.task_id || row.analysis_id || row.id
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
      await loadList()
      
      // Optional: Automatically switch to"In progress"tab page
      if (activeTab.value === 'failed') {
        activeTab.value = 'running'
        await loadList()
      }
    } else {
      ElMessage.error(body.message || 'Failed to recreate task')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'Failed to recreate task')
  } finally {
    loading.value = false
  }
}

// Show error details
const showErrorDetail = async (row: any) => {
  try {
    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('Task ID does not exist')
      return
    }

    // Get task details
    const res = await analysisApi.getTaskStatus(taskId)
    const task = (res as any)?.data?.data || row

    const errorMessage = task.error_message || task.message || 'unknown error'

    // Use ElMessageBox to display error details
    await ElMessageBox.alert(
      errorMessage,
      'Error details',
      {
        confirmButtonText: 'OK',
        type: 'error',
        dangerouslyUseHTMLString: true,
        customStyle: {
          width: '600px'
        },
        // Format display using HTML, preserving line breaks
        message: errorMessage.replace(/\n/g, '<br>')
      }
    )
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e?.message || 'Failed to get error details')
    }
  }
}

// Mark task as failed
const markAsFailed = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm the task "${row.stock_name || row.stock_code}" Mark as failed?`,
      'Confirm action',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('Task ID does not exist')
      return
    }

    loading.value = true
    await analysisApi.markTaskAsFailed(taskId)
    ElMessage.success('Task marked as failed')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || 'Marking failed')
    }
  } finally {
    loading.value = false
  }
}

// Delete task
const deleteTask = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm you want to delete the task "${row.stock_name || row.stock_code}" ? This operation is irreversible!`,
      'Confirm deletion',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'error'
      }
    )

    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('Task ID does not exist')
      return
    }

    loading.value = true
    await analysisApi.deleteTask(taskId)
    ElMessage.success('Task deleted')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || 'Delete failed')
    }
  } finally {
    loading.value = false
  }
}

// Export selected tasks
const exportSelected = () => {
  try {
    const data = JSON.stringify(selectedRows.value, null, 2)
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tasks_selected_${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('Export successful')
  } catch {
    ElMessage.error('Export failed')
  }
}

onMounted(() => {
  // Initialize tab page based on route query
  const tab = String((route.query as any)?.tab || '').toLowerCase()
  const validTabs = ['running', 'completed', 'failed', 'all']
  if (validTabs.includes(tab)) {
    activeTab.value = tab as any
  }
  loadList(); setupPolling()
})

// Monitor the tab changes of routing query and dynamically switch tabs
watch(() => (route.query as any)?.tab, (newVal) => {
  const tab = String(newVal || '').toLowerCase()
  const validTabs = ['running', 'completed', 'failed', 'all']
  if (validTabs.includes(tab)) {
    activeTab.value = tab as any
    currentPage.value = 1
    loadList()
    setupPolling()
  }
})
onUnmounted(() => {
  clearInterval(timer)
  disconnectAllWebSockets()
})

const getStatusType = (status:string): 'success' | 'info' | 'warning' | 'danger' => {
  const map: Record<string,'success'|'info'|'warning'|'danger'> = {
    pending: 'info', processing: 'warning', completed: 'success', failed: 'danger', cancelled: 'info'
  }
  return map[status] || 'info'
}
import { formatDateTime } from '@/utils/datetime'

const getStatusText = (status:string) => ({ pending:'Waiting', processing:'Processing', completed:'Completed', failed:'failed', cancelled:'Canceled' } as any)[status] || status
const formatTime = (t:string) => t ? formatDateTime(t) : '-'
</script>

<style scoped lang="scss">
.task-center {
  .page-header { margin-bottom: 24px; }
  .page-title { display:flex; align-items:center; gap:8px; font-size:24px; font-weight:600; margin:0 0 8px 0; }
  .page-description { color: var(--el-text-color-regular); margin:0; }
  .tabs-card { margin-bottom: 16px; }
  .list-header { display:flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap:8px; }
  .pagination-wrapper { display:flex; justify-content:center; margin-top: 16px; }
}
</style>

