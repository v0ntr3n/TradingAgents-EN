<template>
  <div class="operation-logs">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        Operation log
      </h1>
      <p class="page-description">
        View, filter and analyze system operation logs
      </p>
    </div>

    <!-- Filter control panel -->
    <el-card class="filter-panel" shadow="never">
      <el-form :model="filterForm" :inline="true" @submit.prevent="loadLogs">
        <el-form-item label="time range">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="datetimerange"
            range-separator="to"
            start-placeholder="start time"
            end-placeholder="end time"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 350px"
          />
        </el-form-item>

        <el-form-item label="Operation type">
          <el-select v-model="filterForm.actionType" clearable placeholder="All types" style="width: 150px">
            <el-option label="All types" value="" />
            <el-option label="stock analysis" value="stock_analysis" />
            <el-option label="Configuration management" value="config_management" />
            <el-option label="Caching operations" value="cache_operation" />
            <el-option label="Data import" value="data_import" />
            <el-option label="Data export" value="data_export" />
            <el-option label="System settings" value="system_settings" />
          </el-select>
        </el-form-item>

        <el-form-item label="operating status">
          <el-select v-model="filterForm.success" clearable placeholder="All status" style="width: 120px">
            <el-option label="All status" value="" />
            <el-option label="success" :value="true" />
            <el-option label="failed" :value="false" />
          </el-select>
        </el-form-item>

        <el-form-item label="keywords">
          <el-input
            v-model="filterForm.keyword"
            placeholder="Search operation content"
            style="width: 200px"
            @keyup.enter="loadLogs"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadLogs" :loading="loading">
            <el-icon><Search /></el-icon>
            Query
          </el-button>
          <el-button @click="resetFilter">
            <el-icon><Refresh /></el-icon>
            reset
          </el-button>
          <el-button @click="exportLogs">
            <el-icon><Download /></el-icon>
            Export
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Statistical overview -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.totalLogs }}</div>
            <div class="stat-label">Total number of logs</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.successLogs }}</div>
            <div class="stat-label">successful operation</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.failedLogs }}</div>
            <div class="stat-label">failed operation</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.successRate }}%</div>
            <div class="stat-label">success rate</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Operation type distribution chart -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>📊 Operation type distribution</h3>
          </template>
          <div ref="actionTypeChart" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>📈 Operational trends</h3>
          </template>
          <div ref="operationTrendChart" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Log list -->
    <el-card class="logs-table" shadow="never" style="margin-top: 24px">
      <template #header>
        <div class="table-header">
          <h3>📋 Operation log list</h3>
          <div class="table-actions">
            <el-button size="small" @click="loadLogs">
              <el-icon><Refresh /></el-icon>
              Refresh
            </el-button>
            <el-button size="small" @click="clearLogs" type="danger">
              <el-icon><Delete /></el-icon>
              Clear log
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="logs"
        v-loading="loading"
        style="width: 100%"
        :default-sort="{ prop: 'timestamp', order: 'descending' }"
        @row-click="viewLogDetails"
      >
        <el-table-column prop="timestamp" label="time" width="180" sortable>
          <template #default="{ row }">
            {{ formatDateTime(row.timestamp) }}
          </template>
        </el-table-column>

        <el-table-column prop="action_type" label="Operation type" width="120">
          <template #default="{ row }">
            <el-tag :type="getActionTypeTag(row.action_type)" size="small">
              {{ getActionTypeName(row.action_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="action" label="Operation content" min-width="200">
          <template #default="{ row }">
            <div class="action-content">
              <div class="action-title">{{ row.action }}</div>
              <div v-if="row.details && row.details.stock_symbol" class="action-detail">
                stocks: {{ row.details.stock_symbol }}
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="success" label="Status" width="80">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? 'success' : 'failed' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="duration_ms" label="Time consuming" width="100">
          <template #default="{ row }">
            <span v-if="row.duration_ms">{{ row.duration_ms }}ms</span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="ip_address" label="IP address" width="120" />

        <el-table-column label="Operation" width="100">
          <template #default="{ row }">
            <el-button size="small" @click.stop="viewLogDetails(row)">
              Details
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <el-pagination
        v-if="totalLogs > 0"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="totalLogs"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 16px; text-align: right"
        @size-change="loadLogs"
        @current-change="loadLogs"
      />
    </el-card>

    <!-- Log details dialog box -->
    <el-dialog
      v-model="detailDialogVisible"
      title="Operation log details"
      width="600px"
    >
      <div v-if="selectedLog" class="log-details">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Operating time">
            {{ formatDateTime(selectedLog.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="Operation type">
            <el-tag :type="getActionTypeTag(selectedLog.action_type)">
              {{ getActionTypeName(selectedLog.action_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Operation content" :span="2">
            {{ selectedLog.action }}
          </el-descriptions-item>
          <el-descriptions-item label="operating status">
            <el-tag :type="selectedLog.success ? 'success' : 'danger'">
              {{ selectedLog.success ? 'success' : 'failed' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Time consuming">
            {{ selectedLog.duration_ms ? selectedLog.duration_ms + 'ms' : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP address">
            {{ selectedLog.ip_address || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="session ID">
            {{ selectedLog.session_id || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- error message -->
        <div v-if="!selectedLog.success && selectedLog.error_message" class="error-section">
          <h4>error message</h4>
          <el-alert
            :title="selectedLog.error_message"
            type="error"
            :closable="false"
            show-icon
          />
        </div>

        <!-- Details -->
        <div v-if="selectedLog.details" class="details-section">
          <h4>Details</h4>
          <el-input
            :model-value="JSON.stringify(selectedLog.details, null, 2)"
            type="textarea"
            :rows="8"
            readonly
          />
        </div>
      </div>
    </el-dialog>

    <!-- Empty state -->
    <el-empty
      v-if="!loading && logs.length === 0"
      description="No operation log yet"
      :image-size="200"
    >
      <template #description>
        <div class="empty-description">
          <p>There are currently no operation logs that meet the criteria.</p>
          <div class="empty-tips">
            <h4>💡 How to generate operation log?</h4>
            <ul>
              <li>Perform stock analysis operations</li>
              <li>Modify system configuration</li>
              <li>Perform cache management operations</li>
              <li>Import and export data</li>
            </ul>
          </div>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  Search,
  Refresh,
  Download,
  Delete
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  OperationLogsApi,
  type OperationLog,
  type OperationLogQuery,
  type OperationLogStats,
  getActionTypeName,
  getActionTypeTagColor,
  formatDateTime
} from '@/api/operationLogs'

// Responsive data
const loading = ref(false)
const detailDialogVisible = ref(false)
const selectedLog = ref<OperationLog | null>(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalLogs = ref(0)

// Chart reference
const actionTypeChart = ref()
const operationTrendChart = ref()

// filter form
const filterForm = reactive<{
  dateRange: string[]
  actionType: string
  success: boolean | ''
  keyword: string
}>({
  dateRange: [],
  actionType: '',
  success: '',
  keyword: ''
})

// Statistics
const stats = reactive({
  totalLogs: 0,
  successLogs: 0,
  failedLogs: 0,
  successRate: 0
})

// Log data
const logs = ref<OperationLog[]>([])

// Statistics details
const statsData = ref<OperationLogStats | null>(null)

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

// method
const getActionTypeTag = (actionType: string): TagType => {
  return getActionTypeTagColor(actionType) as TagType
}

const loadLogs = async () => {
  loading.value = true
  try {
    // Build query parameters
    const queryParams: OperationLogQuery = {
      page: currentPage.value,
      page_size: pageSize.value,
      start_date: filterForm.dateRange[0] || undefined,
      end_date: filterForm.dateRange[1] || undefined,
      action_type: filterForm.actionType || undefined,
      success: typeof filterForm.success === 'boolean' ? filterForm.success : undefined,
      keyword: filterForm.keyword || undefined
    }

    // Call the API to get the log list
    const response = await OperationLogsApi.getOperationLogs(queryParams)

    if (response.success) {
      logs.value = response.data.logs
      totalLogs.value = response.data.total

      // Get statistics
      await loadStats()

      // Render chart
      await nextTick()
      renderCharts()
    } else {
      ElMessage.error(response.message || 'Failed to obtain operation log')
    }

  } catch (error) {
    console.error('Failed to load operation log:', error)
    ElMessage.error('Failed to load operation log')
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const response = await OperationLogsApi.getOperationLogStats(30)

    if (response.success) {
      statsData.value = response.data

      // Update statistics
      stats.totalLogs = response.data.total_logs
      stats.successLogs = response.data.success_logs
      stats.failedLogs = response.data.failed_logs
      stats.successRate = response.data.success_rate
    }
  } catch (error) {
    console.error('Failed to get statistics:', error)
  }
}

const resetFilter = () => {
  Object.assign(filterForm, {
    dateRange: [],
    actionType: '',
    success: '',
    keyword: ''
  })
  loadLogs()
}

const exportLogs = async () => {
  try {
    loading.value = true

    const params = {
      start_date: filterForm.dateRange[0] || undefined,
      end_date: filterForm.dateRange[1] || undefined,
      action_type: filterForm.actionType || undefined
    }

    const blob = await OperationLogsApi.exportOperationLogsCSV(params)

    // Create download link
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `operation_logs_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    ElMessage.success('Operation log exported successfully')
  } catch (error) {
    console.error('Failed to export operation log:', error)
    ElMessage.error('Failed to export operation log')
  } finally {
    loading.value = false
  }
}

const clearLogs = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear all operation logs? This operation cannot be undone!',
      'Confirm clearing',
      {
        type: 'error',
        confirmButtonText: 'OK to clear',
        cancelButtonText: 'Cancel'
      }
    )

    loading.value = true

    const response = await OperationLogsApi.clearOperationLogs()

    if (response.success) {
      ElMessage.success(response.message)
      loadLogs()
    } else {
      ElMessage.error(response.message || 'Failed to clear operation log')
    }

  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to clear operation log:', error)
      ElMessage.error('Failed to clear operation log')
    }
  } finally {
    loading.value = false
  }
}

const viewLogDetails = (row: any) => {
  selectedLog.value = row
  detailDialogVisible.value = true
}

const renderCharts = () => {
  if (!statsData.value) return

  // Operation type distribution chart
  if (actionTypeChart.value) {
    const chart1 = echarts.init(actionTypeChart.value)

    const pieData = Object.entries(statsData.value.action_type_distribution).map(([type, count]) => ({
      value: count,
      name: getActionTypeName(type)
    }))

    chart1.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: '60%',
        data: pieData
      }]
    })
  }

  // Operation trend chart
  if (operationTrendChart.value) {
    const chart2 = echarts.init(operationTrendChart.value)

    const hourlyData = statsData.value.hourly_distribution
    const hours = hourlyData.map(item => item.hour)
    const counts = hourlyData.map(item => item.count)

    chart2.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: hours
      },
      yAxis: { type: 'value' },
      series: [{
        data: counts,
        type: 'line',
        smooth: true,
        areaStyle: {}
      }]
    })
  }
}

// life cycle
onMounted(() => {
  loadLogs()
})
</script>

<style lang="scss" scoped>
.operation-logs {
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

  .stat-card {
    .stat-content {
      text-align: center;
      
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

  .chart-card {
    .chart-container {
      height: 250px;
    }
  }

  .logs-table {
    .table-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      h3 {
        margin: 0;
      }
      
      .table-actions {
        display: flex;
        gap: 8px;
      }
    }
    
    .action-content {
      .action-title {
        font-weight: 500;
        margin-bottom: 2px;
      }
      
      .action-detail {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
      }
    }
  }

  .log-details {
    .error-section,
    .details-section {
      margin-top: 16px;
      
      h4 {
        margin: 0 0 8px 0;
        font-size: 14px;
        color: var(--el-text-color-primary);
      }
    }
  }

  .empty-description {
    .empty-tips {
      margin-top: 16px;
      text-align: left;
      
      h4 {
        margin: 0 0 8px 0;
        color: var(--el-text-color-primary);
      }
      
      ul {
        margin: 0;
        padding-left: 20px;
        
        li {
          margin-bottom: 4px;
          color: var(--el-text-color-regular);
        }
      }
    }
  }
}
</style>
