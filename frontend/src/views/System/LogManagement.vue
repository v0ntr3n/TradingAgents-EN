<template>
  <div class="log-management">
    <el-card class="header-card">
      <template #header>
        <div class="card-header">
          <span>📋 Log management</span>
          <div class="header-actions">
            <el-button type="primary" :icon="Refresh" @click="loadLogFiles" :loading="loading">
              Refresh
            </el-button>
            <el-button type="success" :icon="Download" @click="showExportDialog">
              Export log
            </el-button>
          </div>
        </div>
      </template>

      <!-- Statistics -->
      <el-row :gutter="20" class="statistics">
        <el-col :span="6">
          <el-statistic title="Number of log files" :value="statistics.total_files" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="total size (MB)" :value="statistics.total_size_mb" :precision="2" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="error log file" :value="statistics.error_files" />
        </el-col>
        <el-col :span="6">
          <el-button type="primary" @click="loadStatistics">Refresh statistics</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- Log file list -->
    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>Log file list</span>
          <el-input
            v-model="searchKeyword"
            placeholder="Search file name"
            :prefix-icon="Search"
            style="width: 300px"
            clearable
          />
        </div>
      </template>

      <el-table
        :data="filteredLogFiles"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="name" label="file name" min-width="200">
          <template #default="{ row }">
            <el-tag :type="getLogTypeColor(row.type)" size="small">
              {{ row.type }}
            </el-tag>
            {{ row.name }}
          </template>
        </el-table-column>
        <el-table-column prop="size_mb" label="size (MB)" width="120" sortable>
          <template #default="{ row }">
            {{ row.size_mb.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="modified_at" label="modification time" width="180" sortable>
          <template #default="{ row }">
            {{ formatDate(row.modified_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="300" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" :icon="View" @click="viewLog(row)">
              View
            </el-button>
            <el-button type="success" size="small" :icon="Download" @click="downloadLog(row)">
              Download
            </el-button>
            <el-popconfirm
              title="Are you sure you want to delete this log file?"
              @confirm="deleteLog(row)"
            >
              <template #reference>
                <el-button type="danger" size="small" :icon="Delete">
                  Delete
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- View log dialog -->
    <el-dialog
      v-model="viewDialogVisible"
      title="View log"
      width="80%"
      :close-on-click-modal="false"
    >
      <div class="log-viewer">
        <!-- Filter options -->
        <el-form :inline="true" class="filter-form">
          <el-form-item label="Log level">
            <el-select v-model="viewFilter.level" placeholder="All" clearable style="width: 120px">
              <el-option label="ERROR" value="ERROR" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="INFO" value="INFO" />
              <el-option label="DEBUG" value="DEBUG" />
            </el-select>
          </el-form-item>
          <el-form-item label="keywords">
            <el-input v-model="viewFilter.keyword" placeholder="Search keywords" clearable style="width: 200px" />
          </el-form-item>
          <el-form-item label="Number of lines">
            <el-input-number v-model="viewFilter.lines" :min="100" :max="10000" :step="100" style="width: 150px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadLogContent" :loading="viewLoading">
              Apply filtering
            </el-button>
          </el-form-item>
        </el-form>

        <!-- Statistics -->
        <el-descriptions v-if="logContent" :column="4" border size="small" class="log-stats">
          <el-descriptions-item label="Total number of rows">{{ logContent.stats.total_lines }}</el-descriptions-item>
          <el-descriptions-item label="After filtering">{{ logContent.stats.filtered_lines }}</el-descriptions-item>
          <el-descriptions-item label="ERROR">
            <el-tag type="danger" size="small">{{ logContent.stats.error_count }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="WARNING">
            <el-tag type="warning" size="small">{{ logContent.stats.warning_count }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Log content -->
        <div class="log-content" v-loading="viewLoading">
          <pre v-if="logContent">{{ logContent.lines.join('\n') }}</pre>
          <el-empty v-else description="No log content yet" />
        </div>
      </div>
    </el-dialog>

    <!-- Export dialog -->
    <el-dialog
      v-model="exportDialogVisible"
      title="Export log"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="exportForm" label-width="100px">
        <el-form-item label="Select file">
          <el-select
            v-model="exportForm.filenames"
            multiple
            placeholder="Leave blank to export all"
            style="width: 100%"
          >
            <el-option
              v-for="file in logFiles"
              :key="file.name"
              :label="file.name"
              :value="file.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Log level">
          <el-select v-model="exportForm.level" placeholder="All" clearable>
            <el-option label="ERROR" value="ERROR" />
            <el-option label="WARNING" value="WARNING" />
            <el-option label="INFO" value="INFO" />
            <el-option label="DEBUG" value="DEBUG" />
          </el-select>
        </el-form-item>
        <el-form-item label="Export format">
          <el-radio-group v-model="exportForm.format">
            <el-radio label="zip">ZIP Compressed package</el-radio>
            <el-radio label="txt">Merge text files</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exportDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="exportLogs" :loading="exportLoading">
          Export
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Download, Search, View, Delete } from '@element-plus/icons-vue'
import { LogsApi, type LogFileInfo, type LogContentResponse, type LogStatistics } from '@/api/logs'

// data
const loading = ref(false)
const viewLoading = ref(false)
const exportLoading = ref(false)
const logFiles = ref<LogFileInfo[]>([])
const searchKeyword = ref('')
const statistics = ref<LogStatistics>({
  total_files: 0,
  total_size_mb: 0,
  error_files: 0,
  recent_errors: [],
  log_types: {}
})

// View log
const viewDialogVisible = ref(false)
const currentLogFile = ref<LogFileInfo | null>(null)
const logContent = ref<LogContentResponse | null>(null)
const viewFilter = ref({
  level: undefined as string | undefined,
  keyword: '',
  lines: 1000
})

// Export log
const exportDialogVisible = ref(false)
const exportForm = ref({
  filenames: [] as string[],
  level: undefined as string | undefined,
  format: 'zip' as 'zip' | 'txt'
})

// Computed properties
const filteredLogFiles = computed(() => {
  if (!searchKeyword.value) return logFiles.value
  return logFiles.value.filter(file =>
    file.name.toLowerCase().includes(searchKeyword.value.toLowerCase())
  )
})

// method
const loadLogFiles = async () => {
  loading.value = true
  try {
    logFiles.value = await LogsApi.listLogFiles()
    ElMessage.success('Log file list loaded successfully')
  } catch (error: any) {
    ElMessage.error(`Loading failed: ${error.message || error}`)
  } finally {
    loading.value = false
  }
}

const loadStatistics = async () => {
  try {
    statistics.value = await LogsApi.getStatistics(7)
  } catch (error: any) {
    ElMessage.error(`Failed to load statistics: ${error.message || error}`)
  }
}

const viewLog = async (file: LogFileInfo) => {
  currentLogFile.value = file
  viewDialogVisible.value = true
  await loadLogContent()
}

const loadLogContent = async () => {
  if (!currentLogFile.value) return
  
  viewLoading.value = true
  try {
    logContent.value = await LogsApi.readLogFile({
      filename: currentLogFile.value.name,
      lines: viewFilter.value.lines,
      level: viewFilter.value.level as any,
      keyword: viewFilter.value.keyword || undefined
    })
  } catch (error: any) {
    ElMessage.error(`Failed to load log content: ${error.message || error}`)
  } finally {
    viewLoading.value = false
  }
}

const downloadLog = async (file: LogFileInfo) => {
  try {
    const blob = await LogsApi.exportLogs({
      filenames: [file.name],
      format: 'zip'
    })
    
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${file.name}.zip`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    
    ElMessage.success('Log download successful')
  } catch (error: any) {
    ElMessage.error(`Download failed: ${error.message || error}`)
  }
}

const deleteLog = async (file: LogFileInfo) => {
  try {
    await LogsApi.deleteLogFile(file.name)
    ElMessage.success('Log file deleted')
    await loadLogFiles()
  } catch (error: any) {
    ElMessage.error(`Delete failed: ${error.message || error}`)
  }
}

const showExportDialog = () => {
  exportForm.value = {
    filenames: [],
    level: undefined,
    format: 'zip'
  }
  exportDialogVisible.value = true
}

const exportLogs = async () => {
  exportLoading.value = true
  try {
    const blob = await LogsApi.exportLogs({
      filenames: exportForm.value.filenames.length > 0 ? exportForm.value.filenames : undefined,
      level: exportForm.value.level as any,
      format: exportForm.value.format
    })
    
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
    a.download = `logs_export_${timestamp}.${exportForm.value.format}`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    
    ElMessage.success('Log export successful')
    exportDialogVisible.value = false
  } catch (error: any) {
    ElMessage.error(`Export failed: ${error.message || error}`)
  } finally {
    exportLoading.value = false
  }
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const getLogTypeColor = (type: string): TagType => {
  const colors: Record<string, TagType> = {
    error: 'danger',
    webapi: 'primary',
    worker: 'success',
    access: 'info',
    other: 'info'
  }
  return colors[type] || 'info'
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

// life cycle
onMounted(() => {
  loadLogFiles()
  loadStatistics()
})
</script>

<style scoped lang="scss">
.log-management {
  padding: 20px;

  .header-card {
    margin-bottom: 20px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .header-actions {
      display: flex;
      gap: 10px;
    }
  }

  .statistics {
    margin-top: 20px;
  }

  .table-card {
    margin-top: 20px;
  }

  .log-viewer {
    .filter-form {
      margin-bottom: 20px;
      padding: 15px;
      background-color: #f5f7fa;
      border-radius: 4px;
    }

    .log-stats {
      margin-bottom: 15px;
    }

    .log-content {
      max-height: 500px;
      overflow-y: auto;
      background-color: #1e1e1e;
      color: #d4d4d4;
      padding: 15px;
      border-radius: 4px;
      font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
      font-size: 12px;
      line-height: 1.5;

      pre {
        margin: 0;
        white-space: pre-wrap;
        word-wrap: break-word;
      }
    }
  }
}
</style>

