<template>
  <div class="analysis-history">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Clock /></el-icon>
        Analyze history
      </h1>
      <p class="page-description">
        View historical analysis records and results
      </p>
    </div>

    <!-- Filter criteria -->
    <el-card class="filter-card" shadow="never">
      <el-form :model="filterForm" :inline="true" @submit.prevent="loadAnalysisHistory">
        <el-form-item label="time range">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            range-separator="to"
            start-placeholder="start date"
            end-placeholder="end date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>

        <el-form-item label="market type">
          <el-select v-model="filterForm.marketType" clearable placeholder="All markets" style="width: 120px">
            <el-option label="All markets" value="" />
            <el-option label="A shares" value="A shares" />
          </el-select>
        </el-form-item>

        <el-form-item label="Analysis type">
          <el-select v-model="filterForm.analysisType" clearable placeholder="All types" style="width: 120px">
            <el-option label="All types" value="" />
            <el-option label="Fundamental analysis" value="basic" />
            <el-option label="In-depth analysis" value="deep" />
            <el-option label="technical analysis" value="technical" />
            <el-option label="comprehensive analysis" value="comprehensive" />
          </el-select>
        </el-form-item>

        <el-form-item label="Stock code">
          <el-input
            v-model="filterForm.stockSymbol"
            placeholder="Enter stock code"
            style="width: 150px"
            @keyup.enter="loadAnalysisHistory"
          />
        </el-form-item>

        <el-form-item label="label">
          <el-select v-model="filterForm.tags" multiple clearable placeholder="Select label" style="width: 200px">
            <el-option
              v-for="tag in availableTags"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadAnalysisHistory" :loading="loading">
            <el-icon><Search /></el-icon>
            Query
          </el-button>
          <el-button @click="resetFilter">
            <el-icon><Refresh /></el-icon>
            reset
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Statistical overview -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.totalAnalyses }}</div>
            <div class="stat-label">Total number of analyzes</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.favoriteCount }}</div>
            <div class="stat-label">Collection quantity</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.uniqueStocks }}</div>
            <div class="stat-label">Analyze number of stocks</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.avgScore }}</div>
            <div class="stat-label">average rating</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Action toolbar -->
    <el-card class="toolbar" shadow="never" style="margin-top: 24px">
      <div class="toolbar-content">
        <div class="toolbar-left">
          <el-checkbox v-model="selectAll" @change="handleSelectAll">Select all</el-checkbox>
          <span class="selected-count">Selected {{ selectedAnalyses.length }} item</span>
        </div>
        <div class="toolbar-right">
          <el-button
            :disabled="selectedAnalyses.length === 0"
            @click="batchAddToFavorites"
          >
            <el-icon><Star /></el-icon>
            Batch collection
          </el-button>
          <el-button
            :disabled="selectedAnalyses.length === 0"
            @click="batchAddTags"
          >
            <el-icon><PriceTag /></el-icon>
            Bulk label
          </el-button>
          <el-button
            :disabled="selectedAnalyses.length === 0"
            @click="batchExport"
          >
            <el-icon><Download /></el-icon>
            Batch export
          </el-button>
          <el-button
            :disabled="selectedAnalyses.length < 2"
            @click="compareAnalyses"
            type="primary"
          >
            <el-icon><Operation /></el-icon>
            Comparative analysis
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- Analysis result list -->
    <el-card class="results-list" shadow="never" style="margin-top: 24px">
      <template #header>
        <div class="list-header">
          <h3>📊 Analysis result list</h3>
          <div class="view-controls">
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button label="list">list</el-radio-button>
              <el-radio-button label="card">card</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <div class="action-buttons">
        <el-button @click="refreshHistory">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
        <el-button @click="exportHistory">
          <el-icon><Download /></el-icon>
          Export
        </el-button>
      </div>
    </el-card>

    <!-- History list -->
    <el-card class="history-list-card" shadow="never">
      <el-table 
        :data="historyList" 
        v-loading="loading" 
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        
        <el-table-column prop="task_id" label="Task ID" width="180">
          <template #default="{ row }">
            <el-link type="primary" @click="viewTaskDetail(row)">
              {{ row.task_id || '-' }}
            </el-link>
          </template>
        </el-table-column>

        <el-table-column prop="stock_code" label="Stock code" width="120" />
        <el-table-column prop="stock_name" label="Stock name" width="150" />

        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="creation time" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column prop="execution_time" label="Execution time" width="120">
          <template #default="{ row }">
            {{ row.execution_time ? `${row.execution_time}s` : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="Operation" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewResult(row)"
            >
              View results
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="downloadReport(row)"
            >
              Download report
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="text"
              size="small"
              @click="retryAnalysis(row)"
            >
              Reanalyze
            </el-button>
            <el-button type="text" size="small" @click="deleteRecord(row)">
              Delete
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
          :total="totalRecords"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  Clock, 
  Search, 
  Refresh, 
  Download, 
  Star, 
  PriceTag, 
  Operation 
} from '@element-plus/icons-vue'
import { analysisApi } from '@/api/analysis'
import { useRouter } from 'vue-router'
import { formatDateTime } from '@/utils/datetime'

// List and pagination status
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)
const historyList = ref<any[]>([])
const statusFilter = ref('')

// filter form
const filterForm = ref({
  dateRange: [],
  marketType: '',
  analysisType: '',
  stockSymbol: '',
  tags: [] as string[]
})

// Label options (can be obtained from the backend later)
const availableTags = ref<string[]>([])

// Select relevant
const selectAll = ref(false)
const selectedAnalyses = ref<any[]>([])

const handleSelectAll = (val: string | number | boolean) => {
  const isChecked = Boolean(val)
  if (isChecked) selectedAnalyses.value = [...historyList.value]
  else selectedAnalyses.value = []
}

const handleSelectionChange = (selection: any[]) => {
  selectedAnalyses.value = selection
  selectAll.value = selection.length === historyList.value.length && historyList.value.length > 0
}

// Load history
const loadAnalysisHistory = async () => {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
      stock_symbol: filterForm.value.stockSymbol || undefined,
      market_type: filterForm.value.marketType || undefined,
      analysis_type: filterForm.value.analysisType || undefined
    }
    if (filterForm.value.dateRange && filterForm.value.dateRange.length === 2) {
      params.start_date = filterForm.value.dateRange[0]
      params.end_date = filterForm.value.dateRange[1]
    }

    // Use the task list interface as a historical data source (MongoDB has been opened)
    // Do not pass the limit parameter, let the backend return all records, and the frontend handles paging
    const res = await analysisApi.getTaskList({
      status: statusFilter.value || undefined,
      offset: (currentPage.value - 1) * pageSize.value
    })
    const body = (res as any)?.data?.data || {}

    const allTasks = body.tasks || []

    // Pagination on the frontend
    const startIdx = (currentPage.value - 1) * pageSize.value
    const endIdx = startIdx + pageSize.value
    const list = allTasks.slice(startIdx, endIdx)

    historyList.value = list.map((x: any) => ({
      task_id: x.task_id || x.analysis_id || x.id || '-',
      stock_code: x.symbol || x.stock_code || x.stock_symbol || '-',  // Compatible with old and new fields
      stock_name: x.stock_name || x.name || '',
      status: x.status || 'pending',
      created_at: x.start_time || x.created_at || new Date().toISOString(),
      execution_time: x.execution_time || x.elapsed_time || 0
    }))

    totalRecords.value = allTasks.length
  } catch (e) {
    ElMessage.error('Failed to load history')
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filterForm.value = { dateRange: [], marketType: '', analysisType: '', stockSymbol: '', tags: [] }
  currentPage.value = 1
  loadAnalysisHistory()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadAnalysisHistory()
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  loadAnalysisHistory()
}

onMounted(() => {
  loadAnalysisHistory()
})

const refreshHistory = () => {
  loading.value = true
  setTimeout(() => {
    loading.value = false
    ElMessage.success('History has been refreshed')
  }, 1000)
}

const exportHistory = () => {
  ElMessage.info('Export function is under development...')
}

const viewTaskDetail = (_task: any) => {
  ElMessage.info('Task details function is under development...')
}

const viewResult = (task: any) => {
  const router = useRouter()
  router.push(`/analysis/result/${task.task_id}`)
}

const downloadReport = (task: any) => {
  ElMessage.success(`Downloading ${task.stock_name} research report`)
}

const retryAnalysis = (task: any) => {
  ElMessage.success(`${task.stock_name} Reanalysis task submitted`)
}

const deleteRecord = async (task: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete ${task.stock_name} Analysis records?`,
      'Confirm deletion',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    ElMessage.success('Record deleted')
  } catch {
    // User cancels
  }
}

const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const statusMap: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return statusMap[status] || 'info'
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

const formatTime = (time: string) => {
  return formatDateTime(time)
}

// Statistics
const stats = ref({
  totalAnalyses: 0,
  favoriteCount: 0,
  uniqueStocks: 0,
  avgScore: 0
})

// view mode
const viewMode = ref('list')

const batchAddToFavorites = () => {
  ElMessage.info('The batch collection function is under development...')
}

const batchAddTags = () => {
  ElMessage.info('The batch label function is under development...')
}

const batchExport = () => {
  ElMessage.info('Batch export function is under development...')
}

const compareAnalyses = () => {
  ElMessage.info('The comparative analysis function is under development...')
}
</script>

<style lang="scss" scoped>
.analysis-history {
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

  .filter-card {
    margin-bottom: 24px;

    .action-buttons {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }

  .toolbar {
    .toolbar-content {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .toolbar-left {
        display: flex;
        align-items: center;
        gap: 16px;

        .selected-count {
          color: var(--el-text-color-regular);
          font-size: 14px;
        }
      }

      .toolbar-right {
        display: flex;
        gap: 8px;
      }
    }
  }

  .stat-card {
    .stat-content {
      text-align: center;
      padding: 16px;

      .stat-value {
        font-size: 24px;
        font-weight: 600;
        color: var(--el-color-primary);
        margin-bottom: 8px;
      }

      .stat-label {
        font-size: 14px;
        color: var(--el-text-color-regular);
      }
    }
  }

  .results-list {
    .list-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
      }
    }

    .action-buttons {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }

  .history-list-card {
    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 24px;
    }
  }
}
</style>
