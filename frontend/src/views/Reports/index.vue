<template>
  <div class="reports">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        analysis report
      </h1>
      <p class="page-description">
        View and manage stock analysis reports, support export in multiple formats (batch export up to 10)
      </p>
    </div>

    <!-- Filter and action bar -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-input
            v-model="searchKeyword"
            placeholder="Search for a stock symbol or name"
            clearable
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
        
        <el-col :span="4">
          <el-select v-model="marketFilter" placeholder="Market screening" clearable @change="handleMarketChange">
            <el-option label="A shares" value="A shares" />
          </el-select>
        </el-col>
        
        <el-col :span="6">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="to"
            start-placeholder="start date"
            end-placeholder="end date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateChange"
          />
        </el-col>
        
        <el-col :span="8">
          <div class="action-buttons">
            <el-dropdown @command="(format: string) => exportSelected(format)">
              <el-button :disabled="selectedReports.length === 0" :loading="batchExporting">
                <el-icon><Download /></el-icon>
                Batch export
                <span v-if="selectedReports.length > 0">({{ selectedReports.length }}/10)</span>
                <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="markdown">Markdown</el-dropdown-item>
                  <el-dropdown-item command="docx">Word Documentation</el-dropdown-item>
                  <el-dropdown-item command="pdf">PDF</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button @click="refreshReports">
              <el-icon><Refresh /></el-icon>
              Refresh
            </el-button>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- Report list -->
    <el-card class="reports-list-card" shadow="never">
      <el-table
        ref="tableRef"
        :data="filteredReports"
        @selection-change="handleSelectionChange"
        v-loading="loading"
        style="width: 100%"
      >
        <el-table-column type="selection" width="55" :selectable="isRowSelectable" />
        
        <el-table-column prop="title" label="Report title" min-width="200">
          <template #default="{ row }">
            <div class="report-title">
              <el-link type="primary" @click="viewReport(row)">
                {{ row.stock_code }} - {{ row.stock_name }}
              </el-link>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="type" label="report type" width="120">
          <template #default="{ row }">
            <el-tag :type="getTypeColor(row.type)">
              {{ getTypeText(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="format" label="Format" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.format.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="model_info" label="Analytical model" width="180">
          <template #default="{ row }">
            <el-tag v-if="row.model_info && row.model_info !== 'Unknown'" type="info" size="small">
              {{ row.model_info }}
            </el-tag>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="research_depth" label="Analysis depth" width="100" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.research_depth" :content="getResearchDepthDescription(row.research_depth)" placement="top">
              <el-tag type="warning" size="small" style="cursor: help;">
                Depth {{ row.research_depth }}
              </el-tag>
            </el-tooltip>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="creation time" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="Operation" width="250" fixed="right">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="viewReport(row)">
              View
            </el-button>
            <el-dropdown
              v-if="row.status === 'completed'"
              trigger="click"
              @command="(format) => downloadReport(row, format)"
            >
              <el-button type="text" size="small">
                Download <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="markdown">
                    <el-icon><document /></el-icon> Markdown
                  </el-dropdown-item>
                  <el-dropdown-item command="docx">
                    <el-icon><document /></el-icon> Word Documentation
                  </el-dropdown-item>
                  <el-dropdown-item command="pdf">
                    <el-icon><document /></el-icon> PDF
                  </el-dropdown-item>
                  <el-dropdown-item command="json" divided>
                    <el-icon><document /></el-icon> JSON (raw data)
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              type="text"
              size="small"
              @click="deleteReport(row)"
              style="color: var(--el-color-danger)"
            >
              Delete
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty v-if="!loading" description="No analysis report yet" :image-size="120">
            <template #description>
              <p>There is no analysis report yet. Perform a stock analysis to generate a report.</p>
            </template>
          </el-empty>
        </template>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="totalReports"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  Search,
  Download,
  Refresh,
  ArrowDown
} from '@element-plus/icons-vue'
import { ApiClient } from '@/api/request'

type ElTagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

interface ReportListItem {
  id: string | number
  title?: string
  stock_code: string
  stock_name?: string
  analysis_date?: string
  type: string
  format: string
  status: string
  model_info?: string
  research_depth?: number
  created_at: string
}

// Use routing
const router = useRouter()

// Responsive data
const loading = ref(false)
const searchKeyword = ref('')
const marketFilter = ref('')
const dateRange = ref<[string, string] | null>(null)
const selectedReports = ref<ReportListItem[]>([])
const currentPage = ref(1)
const pageSize = ref(20)
const totalReports = ref(0)

const reports = ref<ReportListItem[]>([])

// Computed properties
const filteredReports = computed<ReportListItem[]>(() => {
  // Data is now fetched directly from the API, no front-end filtering required
  return reports.value
})

// API call function
const fetchReports = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: currentPage.value.toString(),
      page_size: pageSize.value.toString()
    })

    if (searchKeyword.value) {
      params.append('search_keyword', searchKeyword.value)
    }
    if (marketFilter.value) {
      params.append('market_filter', marketFilter.value)
    }
    if (dateRange.value) {
      params.append('start_date', dateRange.value[0])
      params.append('end_date', dateRange.value[1])
    }

    const result = await ApiClient.get<any>(`/api/reports/list?${params}`)

    if (result.success) {
      reports.value = Array.isArray(result.data?.reports) ? result.data.reports as ReportListItem[] : []
      totalReports.value = result.data.total
    } else {
      throw new Error(result.message || 'Failed to get report list')
    }
  } catch (error) {
    console.error('Failed to get report list:', error)
    ElMessage.error('Failed to get report list')
  } finally {
    loading.value = false
  }
}

// method
const handleSearch = () => {
  currentPage.value = 1
  fetchReports()
}

const handleDateChange = () => {
  currentPage.value = 1
  fetchReports()
}

const handleMarketChange = () => {
  currentPage.value = 1
  fetchReports()
}

const MAX_BATCH_EXPORT = 10
let isCorrectingSelection = false

const handleSelectionChange = (selection: ReportListItem[]) => {
  if (isCorrectingSelection) return
  if (selection.length > MAX_BATCH_EXPORT) {
    isCorrectingSelection = true
    const toKeep = selection.slice(0, MAX_BATCH_EXPORT)
    selectedReports.value = toKeep
    ElMessage.warning(`Most choices ${MAX_BATCH_EXPORT} reports`)
    nextTick(() => {
      tableRef.value?.clearSelection()
      toKeep.forEach((row) => tableRef.value?.toggleRowSelection(row, true))
      isCorrectingSelection = false
    })
  } else {
    selectedReports.value = selection
  }
}

const isRowSelectable = (row: ReportListItem) => {
  if (selectedReports.value.length < MAX_BATCH_EXPORT) return true
  return selectedReports.value.some((r) => r.id === row.id)
}

const tableRef = ref<{
  clearSelection: () => void
  toggleRowSelection: (row: ReportListItem, selected?: boolean) => void
} | null>(null)

const viewReport = (report: ReportListItem) => {
  // Jump to report details page
  router.push(`/reports/view/${report.id}`)
}

const downloadReport = async (report: ReportListItem, format: string = 'markdown') => {
  try {
    // Show loading prompt
    const loadingMsg = ElMessage({
      message: `Generating${getFormatName(format)}Format report...`,
      type: 'info',
      duration: 0
    })

    const res: any = await ApiClient.get(`/api/reports/${report.id}/download`, { format }, { responseType: 'blob', showLoading: false })

    loadingMsg.close()

    // Compatible: the response interceptor returns Blob directly; compatible returns { data: Blob } old implementation of
    const blob = res instanceof Blob ? res : (res?.data instanceof Blob ? res.data : new Blob([res]))
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    // Set file extension based on format
    const ext = getFileExtension(format)
    // Clean special characters in stock names (used in file names)
    const cleanStockName = (report.stock_name || '')
      .replace(/[/\\:*?"<>|]/g, '') // Remove characters not allowed in file names
      .replace(/\s+/g, '_') // Replace spaces with underscores
      .trim()
    // Build file name: stock code_stock name_analysis report_date
    const fileName = cleanStockName
      ? `${report.stock_code}_${cleanStockName}_analysis report_${report.analysis_date}.${ext}`
      : `${report.stock_code}_analysis report_${report.analysis_date}.${ext}`
    a.download = fileName

    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    ElMessage.success(`${getFormatName(format)}Report download successful`)
  } catch (error: any) {
    console.error('Download report failed:', error)

    // Show detailed error information
    if (error.message && error.message.includes('pandoc')) {
      ElMessage.error({
        message: 'Word Exporting requires the pandoc tool to be installed (PDF export does not require pandoc)',
        duration: 5000
      })
    } else if (error.message && (error.message.includes('weasyprint') || error.message.includes('pdfkit'))) {
      ElMessage.error({
        message: 'PDF Exporting requires installing the PDF engine: pip install weasyprint (recommended)',
        duration: 5000
      })
    } else {
      ElMessage.error(`Download report failed: ${error.message || 'unknown error'}`)
    }
  }
}

// Helper function: get format name
const getFormatName = (format: string): string => {
  const names: Record<string, string> = {
    'markdown': 'Markdown',
    'docx': 'Word',
    'pdf': 'PDF',
    'json': 'JSON'
  }
  return names[format] || format
}

// Helper function: get file extension
const getFileExtension = (format: string): string => {
  const extensions: Record<string, string> = {
    'markdown': 'md',
    'docx': 'docx',
    'pdf': 'pdf',
    'json': 'json'
  }
  return extensions[format] || 'txt'
}

const deleteReport = async (report: ReportListItem) => {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete the report "${report.title}" ?`,
      'Confirm deletion',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    // call delete API
    const result = await ApiClient.delete(`/api/reports/${report.id}`)

    if (result.success) {
      ElMessage.success('Report deleted')
      refreshReports()
    } else {
      throw new Error(result.message || 'Delete failed')
    }
  } catch (error: unknown) {
    if (!(error instanceof Error && error.message === 'cancel')) {
      console.error('Delete report failed:', error)
      ElMessage.error('Delete report failed')
    }
  }
}

const batchExporting = ref(false)

const exportSelected = async (format: string = 'markdown') => {
  const toExport = selectedReports.value
    .filter((r) => r.status === 'completed')
    .slice(0, MAX_BATCH_EXPORT)
  if (toExport.length === 0) {
    ElMessage.warning('Please select a completed report to export')
    return
  }
  batchExporting.value = true
  let successCount = 0
  try {
    for (let i = 0; i < toExport.length; i++) {
      const report = toExport[i]
      try {
        const res: any = await ApiClient.get(`/api/reports/${report.id}/download`, { format }, { responseType: 'blob', showLoading: false })
        // Compatible: the response interceptor returns Blob directly; compatible returns { data: Blob } old implementation of
        const blob = res instanceof Blob ? res : (res?.data instanceof Blob ? res.data : new Blob([res]))
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const ext = getFileExtension(format)
        const cleanStockName = (report.stock_name || '').replace(/[/\\:*?"<>|]/g, '').replace(/\s+/g, '_').trim()
        const fileName = cleanStockName
          ? `${report.stock_code}_${cleanStockName}_analysis report_${report.analysis_date}.${ext}`
          : `${report.stock_code}_analysis report_${report.analysis_date}.${ext}`
        a.download = fileName
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        successCount++
        if (i < toExport.length - 1) { await new Promise(r => setTimeout(r, 300)) }
      } catch (e) {
        console.error(`Export ${report.stock_code} failed:`, e)
        ElMessage.error(`Export ${report.stock_code} failed`)
      }
    }
    ElMessage.success(`Batch export completed, successful ${successCount}/${toExport.length} a`)
  } finally {
    batchExporting.value = false
  }
}

const refreshReports = () => {
  fetchReports()
}

const getTypeColor = (type: string): ElTagType => {
  const colorMap: Record<string, ElTagType> = {
    single: 'primary',
    batch: 'success',
    portfolio: 'warning'
  }
  return colorMap[type] || 'info'
}

const getTypeText = (type: string) => {
  const textMap: Record<string, string> = {
    single: 'single stock analysis',
    batch: 'Batch analysis',
    portfolio: 'Portfolio'
  }
  return textMap[type] || type
}

const getStatusType = (status: string): ElTagType => {
  const statusMap: Record<string, ElTagType> = {
    completed: 'success',
    processing: 'warning',
    failed: 'danger'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    completed: 'Completed',
    processing: 'Generating',
    failed: 'failed'
  }
  return statusMap[status] || status
}

import { formatDateTime } from '@/utils/datetime'

const formatTime = (time: string) => {
  return formatDateTime(time)
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  fetchReports()
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  fetchReports()
}

// Get an in-depth description of the analysis
const getResearchDepthDescription = (depth: number) => {
  const descMap: Record<number, string> = {
    1: 'Quick Analysis - Basic Technical and Fundamental Analysis',
    2: 'Standard analysis - including technical, fundamental and sentiment analysis',
    3: 'In-Depth Analysis - Comprehensive multi-dimensional analysis, including detailed industry and competitive analysis',
    4: 'Expert-Level Analysis - The most comprehensive analysis, including all dimensions and in-depth research',
    5: 'Top level analysis - the highest level of analysis depth, encompassing all possible dimensions of analysis'
  }
  return descMap[depth] || `Analysis depth: ${depth}`
}

// life cycle
onMounted(() => {
  fetchReports()
})
</script>

<style lang="scss" scoped>
.reports {
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

  .reports-list-card {
    .report-title {
      .report-subtitle {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
        margin-top: 2px;
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
