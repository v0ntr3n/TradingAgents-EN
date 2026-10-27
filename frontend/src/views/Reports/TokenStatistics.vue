<template>
  <div class="token-statistics">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Coin /></el-icon>
        Token usage statistics
      </h1>
      <p class="page-description">
        Token Usage, cost analysis and statistical charts
      </p>
    </div>

    <!-- control panel -->
    <el-card class="control-panel" shadow="never">
      <el-row :gutter="24" align="middle">
        <el-col :span="6">
          <el-form-item label="Statistics time range">
            <el-select v-model="timeRange" @change="loadStatistics">
              <el-option label="today" value="today" />
              <el-option label="Last 7 days" value="week" />
              <el-option label="Last 30 days" value="month" />
              <el-option label="Last 90 days" value="quarter" />
              <el-option label="All" value="all" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="Supplier screening">
            <el-select v-model="providerFilter" @change="loadStatistics" clearable>
              <el-option label="All suppliers" value="" />
              <el-option label="Ali Bailian" value="dashscope" />
              <el-option label="OpenAI" value="openai" />
              <el-option label="Google" value="google" />
              <el-option label="DeepSeek" value="deepseek" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <div class="control-buttons">
            <el-button @click="loadStatistics" :loading="loading">
              <el-icon><Refresh /></el-icon>
              Refresh data
            </el-button>
            <el-button @click="exportData">
              <el-icon><Download /></el-icon>
              Export statistics
            </el-button>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- Overview indicators -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="6">
        <el-card class="metric-card" shadow="never">
          <div class="metric-content">
            <div class="metric-value">{{ formatNumber(overview.totalRequests) }}</div>
            <div class="metric-label">Total requests</div>
            <div class="metric-change" :class="getChangeClass(overview.requestsChange)">
              {{ formatChange(overview.requestsChange) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card" shadow="never">
          <div class="metric-content">
            <div class="metric-value">{{ formatNumber(overview.totalTokens) }}</div>
            <div class="metric-label">Total number of tokens</div>
            <div class="metric-change" :class="getChangeClass(overview.tokensChange)">
              {{ formatChange(overview.tokensChange) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card" shadow="never">
          <div class="metric-content">
            <div class="metric-value">¥{{ formatNumber(overview.totalCost) }}</div>
            <div class="metric-label">total cost</div>
            <div class="metric-change" :class="getChangeClass(overview.costChange)">
              {{ formatChange(overview.costChange) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card" shadow="never">
          <div class="metric-content">
            <div class="metric-value">¥{{ formatNumber(overview.avgCostPerRequest) }}</div>
            <div class="metric-label">average cost per trip</div>
            <div class="metric-change" :class="getChangeClass(overview.avgCostChange)">
              {{ formatChange(overview.avgCostChange) }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- chart area -->
    <el-row :gutter="24" style="margin-top: 24px">
      <!-- Token Usage trends -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>📈 Token Usage trends</h3>
          </template>
          <div ref="tokenTrendChart" class="chart-container"></div>
        </el-card>
      </el-col>

      <!-- cost distribution -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>💰 cost distribution</h3>
          </template>
          <div ref="costDistributionChart" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="24" style="margin-top: 24px">
      <!-- Supplier statistics -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>🏢 Supplier statistics</h3>
          </template>
          <div ref="providerChart" class="chart-container"></div>
        </el-card>
      </el-col>

      <!-- Model usage ranking -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <h3>🏆 Model usage ranking</h3>
          </template>
          <div class="model-ranking">
            <div
              v-for="(model, index) in modelRanking"
              :key="model.name"
              class="ranking-item"
            >
              <div class="rank-number">{{ index + 1 }}</div>
              <div class="model-info">
                <div class="model-name">{{ model.name }}</div>
                <div class="model-stats">
                  {{ formatNumber(model.requests) }} requests · 
                  {{ formatNumber(model.tokens) }} Token · 
                  ¥{{ formatNumber(model.cost) }}
                </div>
              </div>
              <div class="usage-bar">
                <el-progress
                  :percentage="(model.requests / modelRanking[0].requests) * 100"
                  :show-text="false"
                  :stroke-width="6"
                />
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- detailed record sheet -->
    <el-card class="records-table" shadow="never" style="margin-top: 24px">
      <template #header>
        <div class="table-header">
          <h3>📋 Detailed records</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="Search for ticker or model name"
            style="width: 200px"
            @input="filterRecords"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
      </template>

      <el-table
        :data="filteredRecords"
        v-loading="loading"
        style="width: 100%"
        :default-sort="{ prop: 'timestamp', order: 'descending' }"
      >
        <el-table-column prop="timestamp" label="time" width="180" sortable>
          <template #default="{ row }">
            {{ formatDateTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="supplier" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ getProviderName(row.provider) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model" label="model" width="150" />
        <el-table-column prop="stock_symbol" label="Stock code" width="100" />
        <el-table-column prop="prompt_tokens" label="input Token" width="100" sortable />
        <el-table-column prop="completion_tokens" label="output Token" width="100" sortable />
        <el-table-column prop="total_tokens" label="total Token" width="100" sortable />
        <el-table-column prop="cost" label="cost(¥)" width="100" sortable>
          <template #default="{ row }">
            ¥{{ formatNumber(row.cost) }}
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="Time consuming(ms)" width="100" sortable />
        <el-table-column label="Operation" width="100">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetails(row)">
              Details
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <el-pagination
        v-if="totalRecords > 0"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="totalRecords"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 16px; text-align: right"
        @size-change="loadRecords"
        @current-change="loadRecords"
      />
    </el-card>

    <!-- Empty state -->
    <el-empty
      v-if="!loading && overview.totalRequests === 0"
      description="No Token usage record yet"
      :image-size="200"
    >
      <template #description>
        <div class="empty-description">
          <p>No Token usage record yet</p>
          <div class="empty-tips">
            <h4>💡 How to start recording Token usage?</h4>
            <ul>
              <li>Perform stock analysis: Use the stock analysis feature</li>
              <li>Ensure API configuration: Check that the API key is configured correctly</li>
              <li>Enable cost tracking: Enable token cost tracking in configuration management</li>
            </ul>
          </div>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Coin,
  Refresh,
  Download,
  Search
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'

interface TokenRecord {
  timestamp: string
  provider: string
  model: string
  stock_symbol: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  duration: number
}

interface ModelRankingItem {
  name: string
  requests: number
  tokens: number
  cost: number
}

const providerNameMap: Record<string, string> = {
  dashscope: 'Ali Bailian',
  openai: 'OpenAI',
  google: 'Google',
  deepseek: 'DeepSeek'
}

// Responsive data
const loading = ref(false)
const timeRange = ref('month')
const providerFilter = ref('')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)

// Chart reference
const tokenTrendChart = ref<HTMLDivElement | null>(null)
const costDistributionChart = ref<HTMLDivElement | null>(null)
const providerChart = ref<HTMLDivElement | null>(null)

// data
const overview = reactive({
  totalRequests: 0,
  totalTokens: 0,
  totalCost: 0,
  avgCostPerRequest: 0,
  requestsChange: 0,
  tokensChange: 0,
  costChange: 0,
  avgCostChange: 0
})

const records = ref<TokenRecord[]>([])
const filteredRecords = ref<TokenRecord[]>([])
const modelRanking = ref<ModelRankingItem[]>([])

// method
const formatNumber = (num: number): string => {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toFixed(2)
}

const formatChange = (change: number): string => {
  if (change > 0) return `+${change.toFixed(1)}%`
  if (change < 0) return `${change.toFixed(1)}%`
  return '0%'
}

const getChangeClass = (change: number): string => {
  if (change > 0) return 'positive'
  if (change < 0) return 'negative'
  return 'neutral'
}

const formatDateTime = (timestamp: string): string => {
  return new Date(timestamp).toLocaleString('zh-CN')
}

const getProviderName = (provider: string): string => {
  return providerNameMap[provider] || provider
}

const loadStatistics = async () => {
  loading.value = true
  try {
    // Simulate API calls
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    // simulated data
    Object.assign(overview, {
      totalRequests: 1234,
      totalTokens: 567890,
      totalCost: 123.45,
      avgCostPerRequest: 0.1,
      requestsChange: 15.2,
      tokensChange: 23.8,
      costChange: 18.5,
      avgCostChange: 2.1
    })
    
    // Load chart data
    await nextTick()
    renderCharts()
    
  } catch (error) {
    ElMessage.error('Failed to load statistics')
  } finally {
    loading.value = false
  }
}

const loadRecords = async () => {
  // Simulate loading of recorded data
  records.value = [
    {
      timestamp: '2024-01-18T14:30:00Z',
      provider: 'dashscope',
      model: 'qwen-turbo',
      stock_symbol: '000001',
      prompt_tokens: 1500,
      completion_tokens: 800,
      total_tokens: 2300,
      cost: 0.023,
      duration: 1200
    }
  ]
  
  totalRecords.value = 50
  filterRecords()
}

const filterRecords = () => {
  if (!searchKeyword.value) {
    filteredRecords.value = records.value
  } else {
    const keyword = searchKeyword.value.toLowerCase()
    filteredRecords.value = records.value.filter(record =>
      record.stock_symbol.toLowerCase().includes(keyword) ||
      record.model.toLowerCase().includes(keyword)
    )
  }
}

const renderCharts = () => {
  // Token Use trend charts
  if (tokenTrendChart.value) {
    const chart1 = echarts.init(tokenTrendChart.value)
    chart1.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: ['1 month', '2 month', '3 month', '4 month', '5 month'] },
      yAxis: { type: 'value' },
      series: [{
        data: [120, 200, 150, 80, 70],
        type: 'line',
        smooth: true
      }]
    })
  }
  
  // cost distribution chart
  if (costDistributionChart.value) {
    const chart2 = echarts.init(costDistributionChart.value)
    chart2.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        data: [
          { value: 1048, name: 'Ali Bailian' },
          { value: 735, name: 'OpenAI' },
          { value: 580, name: 'Google' }
        ]
      }]
    })
  }
  
  // Supplier statistics chart
  if (providerChart.value) {
    const chart3 = echarts.init(providerChart.value)
    chart3.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: ['Ali Bailian', 'OpenAI', 'Google', 'DeepSeek'] },
      yAxis: { type: 'value' },
      series: [{
        data: [120, 200, 150, 80],
        type: 'bar'
      }]
    })
  }
}

const exportData = () => {
  ElMessage.info('Export function is under development...')
}

const viewDetails = (_row?: TokenRecord) => {
  ElMessage.info('Details function is under development...')
}

// life cycle
onMounted(() => {
  loadStatistics()
  loadRecords()
  
  // Simulation model ranking data
  modelRanking.value = [
    { name: 'qwen-turbo', requests: 500, tokens: 150000, cost: 15.0 },
    { name: 'gpt-4', requests: 300, tokens: 120000, cost: 24.0 },
    { name: 'gemini-pro', requests: 200, tokens: 80000, cost: 8.0 }
  ]
})
</script>

<style lang="scss" scoped>
.token-statistics {
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

  .control-panel {
    .control-buttons {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
    }
  }

  .metric-card {
    .metric-content {
      text-align: center;
      
      .metric-value {
        font-size: 28px;
        font-weight: 600;
        color: var(--el-color-primary);
        margin-bottom: 8px;
      }
      
      .metric-label {
        font-size: 14px;
        color: var(--el-text-color-regular);
        margin-bottom: 4px;
      }
      
      .metric-change {
        font-size: 12px;
        
        &.positive {
          color: var(--el-color-success);
        }
        
        &.negative {
          color: var(--el-color-danger);
        }
        
        &.neutral {
          color: var(--el-text-color-placeholder);
        }
      }
    }
  }

  .chart-card {
    .chart-container {
      height: 300px;
    }
    
    .model-ranking {
      .ranking-item {
        display: flex;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid var(--el-border-color-lighter);
        
        &:last-child {
          border-bottom: none;
        }
        
        .rank-number {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--el-color-primary);
          color: white;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          margin-right: 12px;
        }
        
        .model-info {
          flex: 1;
          
          .model-name {
            font-weight: 600;
            margin-bottom: 4px;
          }
          
          .model-stats {
            font-size: 12px;
            color: var(--el-text-color-regular);
          }
        }
        
        .usage-bar {
          width: 100px;
        }
      }
    }
  }

  .records-table {
    .table-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      h3 {
        margin: 0;
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
