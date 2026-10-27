<template>
  <div class="usage-statistics-container">
    <el-card class="header-card">
      <template #header>
        <div class="card-header">
          <span class="title">
            <el-icon><DataAnalysis /></el-icon>
            Usage statistics and billing
          </span>
          <div class="header-actions">
            <el-select v-model="selectedDays" @change="loadData" style="width: 120px; margin-right: 10px;">
              <el-option label="Last 7 days" :value="7" />
              <el-option label="Last 30 days" :value="30" />
              <el-option label="Last 90 days" :value="90" />
            </el-select>
            <el-button type="primary" :icon="Refresh" @click="loadData">Refresh</el-button>
          </div>
        </div>
      </template>

      <!-- Statistical overview -->
      <el-row :gutter="20" class="stats-overview">
        <el-col :span="6">
          <el-statistic title="Total requests" :value="statistics.total_requests">
            <template #prefix>
              <el-icon><Document /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="total input Token" :value="statistics.total_input_tokens">
            <template #prefix>
              <el-icon><Upload /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="total output Token" :value="statistics.total_output_tokens">
            <template #prefix>
              <el-icon><Download /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <div class="cost-statistic">
            <div class="cost-label">
              <el-icon><Money /></el-icon>
              <span>total cost</span>
            </div>
            <div class="cost-values">
              <div v-for="(cost, currency) in statistics.cost_by_currency" :key="currency" class="cost-item">
                <span class="cost-amount">{{ cost.toFixed(4) }}</span>
                <span class="cost-currency">{{ getCurrencySymbol(currency) }}</span>
              </div>
              <div v-if="Object.keys(statistics.cost_by_currency || {}).length === 0" class="cost-item">
                <span class="cost-amount">0.0000</span>
                <span class="cost-currency">Yuan</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- chart area -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>Statistics by supplier</span>
          </template>
          <div ref="providerChartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>Statistics by model</span>
          </template>
          <div ref="modelChartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>daily cost trend</span>
          </template>
          <div ref="dailyChartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Use record form -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span>Usage records</span>
          <el-button type="danger" size="small" @click="handleDeleteOldRecords">
            Clean up old records
          </el-button>
        </div>
      </template>

      <el-table :data="records" style="width: 100%" v-loading="loading">
        <el-table-column prop="timestamp" label="time" width="180">
          <template #default="{ row }">
            {{ formatTimestamp(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="supplier" width="120" />
        <el-table-column prop="model_name" label="model" width="180" />
        <el-table-column prop="input_tokens" label="input Token" width="120" align="right" />
        <el-table-column prop="output_tokens" label="output Token" width="120" align="right" />
        <el-table-column prop="cost" label="cost" width="140" align="right">
          <template #default="{ row }">
            {{ row.cost.toFixed(4) }} {{ getCurrencySymbol(row.currency || 'CNY') }}
          </template>
        </el-table-column>
        <el-table-column prop="analysis_type" label="Analysis type" width="150" />
        <el-table-column prop="session_id" label="session ID" show-overflow-tooltip />
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="totalRecords"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadRecords"
        @current-change="loadRecords"
        style="margin-top: 20px; justify-content: center;"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataAnalysis, Refresh, Document, Upload, Download, Money } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  getUsageRecords,
  getUsageStatistics,
  deleteOldRecords,
  type UsageRecord,
  type UsageStatistics
} from '@/api/usage'

// data
const selectedDays = ref(7)
const loading = ref(false)
const statistics = ref<UsageStatistics>({
  total_requests: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  total_cost: 0,
  cost_by_currency: {},
  by_provider: {},
  by_model: {},
  by_date: {}
})
const records = ref<UsageRecord[]>([])
const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)

// Chart reference
const providerChartRef = ref<HTMLElement>()
const modelChartRef = ref<HTMLElement>()
const dailyChartRef = ref<HTMLElement>()

// Chart example
let providerChart: echarts.ECharts | null = null
let modelChart: echarts.ECharts | null = null
let dailyChart: echarts.ECharts | null = null

// Format timestamp
const formatTimestamp = (timestamp: string) => {
  return new Date(timestamp).toLocaleString('zh-CN')
}

// Get currency symbol
const getCurrencySymbol = (currency: string) => {
  const symbols: Record<string, string> = {
    'CNY': 'Yuan',
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥'
  }
  return symbols[currency] || currency
}

// Load statistics
const loadStatistics = async () => {
  try {
    const res = await getUsageStatistics({ days: selectedDays.value })
    if (res.success) {
      statistics.value = res.data
      await nextTick()
      renderCharts()
    }
  } catch (error) {
    console.error('Failed to load statistics:', error)
    ElMessage.error('Failed to load statistics')
  }
}

// Load usage records
const loadRecords = async () => {
  try {
    loading.value = true
    const res = await getUsageRecords({
      limit: pageSize.value
    })
    if (res.success) {
      records.value = res.data.records
      totalRecords.value = res.data.total
    }
  } catch (error) {
    console.error('Failed to load usage records:', error)
    ElMessage.error('Failed to load usage records')
  } finally {
    loading.value = false
  }
}

// Load all data
const loadData = async () => {
  await Promise.all([loadStatistics(), loadRecords()])
}

// Render chart
const renderCharts = () => {
  renderProviderChart()
  renderModelChart()
  renderDailyChart()
}

// Render supplier chart
const renderProviderChart = () => {
  if (!providerChartRef.value) return

  if (!providerChart) {
    providerChart = echarts.init(providerChartRef.value)
  }

  const data = Object.entries(statistics.value.by_provider).map(([name, value]: [string, any]) => ({
    name,
    value: value.cost
  }))

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: ¥{c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: 'cost',
        type: 'pie',
        radius: '50%',
        data,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }

  providerChart.setOption(option)
}

// Render model diagram
const renderModelChart = () => {
  if (!modelChartRef.value) return

  if (!modelChart) {
    modelChart = echarts.init(modelChartRef.value)
  }

  const data = Object.entries(statistics.value.by_model)
    .map(([name, value]: [string, any]) => ({
      name,
      value: value.cost
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10) // Only show the first 10

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.name),
      axisLabel: {
        rotate: 45,
        interval: 0
      }
    },
    yAxis: {
      type: 'value',
      name: 'cost(Yuan)'
    },
    series: [
      {
        data: data.map(item => item.value),
        type: 'bar',
        itemStyle: {
          color: '#409EFF'
        }
      }
    ]
  }

  modelChart.setOption(option)
}

// Render daily cost chart
const renderDailyChart = () => {
  if (!dailyChartRef.value) return

  if (!dailyChart) {
    dailyChart = echarts.init(dailyChartRef.value)
  }

  const sortedData = Object.entries(statistics.value.by_date)
    .sort(([a], [b]) => a.localeCompare(b))

  const option = {
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: sortedData.map(([date]) => date)
    },
    yAxis: {
      type: 'value',
      name: 'cost(Yuan)'
    },
    series: [
      {
        data: sortedData.map(([, value]: [string, any]) => value.cost),
        type: 'line',
        smooth: true,
        itemStyle: {
          color: '#67C23A'
        },
        areaStyle: {
          color: 'rgba(103, 194, 58, 0.2)'
        }
      }
    ]
  }

  dailyChart.setOption(option)
}

// Delete old records
const handleDeleteOldRecords = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to delete old records from 90 days ago? This operation is irreversible.',
      'warning',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    const res = await deleteOldRecords(90)
    if (res.data?.success) {
      ElMessage.success(`Deleted ${res.data.deleted_count} old records`)
      loadData()
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete old records:', error)
      ElMessage.error('Failed to delete old records')
    }
  }
}

// Component mounting
onMounted(() => {
  loadData()
})
</script>

<style scoped lang="scss">
.usage-statistics-container {
  padding: 20px;
}

.header-card {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
    }

    .header-actions {
      display: flex;
      align-items: center;
    }
  }
}

.cost-statistic {
  padding: 20px;

  .cost-label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #909399;
    font-size: 14px;
    margin-bottom: 12px;
  }

  .cost-values {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .cost-item {
      display: flex;
      align-items: baseline;
      gap: 4px;

      .cost-amount {
        font-size: 24px;
        font-weight: 600;
        color: #303133;
      }

      .cost-currency {
        font-size: 14px;
        color: #909399;
      }
    }
  }
}

.stats-overview {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>

