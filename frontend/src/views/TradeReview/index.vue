<template>
  <div class="trade-review">
    <!-- Page header -->
    <div class="header">
      <div class="title">
        <el-icon style="margin-right:8px"><TrendCharts /></el-icon>
        <span>Operation review</span>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" text size="small" @click="refreshData">Refresh</el-button>
      </div>
    </div>

    <!-- Compliance Disclaimer -->
    <el-alert
      title="This function is only a learning, research and personal review tool"
      type="info"
      description="The review conclusion is based on your own transaction records and is used for reflection and learning and does not constitute any investment advice. Please make independent judgments based on information from multiple parties for future operations."
      show-icon
      :closable="false"
      style="margin-bottom: 16px;"
    />

    <!-- Switch review type -->
    <el-tabs v-model="reviewSource" type="card" class="source-tabs" @tab-change="handleSourceChange">
      <el-tab-pane label="Review of position operations" name="position">
        <template #label>
          <el-icon><Wallet /></el-icon>
          <span style="margin-left: 4px">Review of position operations</span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="Simulated trading review" name="paper">
        <template #label>
          <el-icon><Goods /></el-icon>
          <span style="margin-left: 4px">Simulated trading review</span>
        </template>
      </el-tab-pane>
    </el-tabs>



    <!-- Filter criteria -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="Stock code">
          <el-input
            v-model="filterForm.code"
            placeholder="Enter stock code"
            clearable
            style="width: 140px"
            @keyup.enter="applyFilter"
          />
        </el-form-item>
        <el-form-item label="time range">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            range-separator="to"
            start-placeholder="start date"
            end-placeholder="end date"
            value-format="YYYY-MM-DD"
            style="width: 260px"
            :shortcuts="dateShortcuts"
          />
        </el-form-item>
        <el-form-item v-if="reviewSource === 'paper'">
          <el-button type="primary" :icon="Search" @click="applyFilter">Filter</el-button>
          <el-button :icon="RefreshRight" @click="resetFilter">reset</el-button>
        </el-form-item>
        <el-form-item v-else>
          <el-button type="primary" :icon="Search" @click="applyPositionFilter">Filter</el-button>
          <el-button :icon="RefreshRight" @click="resetPositionFilter">reset</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Simulated trading statistics card -->
    <el-row v-if="reviewSource === 'paper'" :gutter="16" class="stats-row" v-loading="loading.stats">
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">total number of transactions</div>
          <div class="stat-value">{{ statistics.total_trades }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">winning rate</div>
          <div class="stat-value" :class="(statistics.win_rate || 0) >= 50 ? 'positive' : 'negative'">
            {{ statistics.win_rate?.toFixed(1) || 0 }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">profit-loss ratio</div>
          <div class="stat-value">{{ statistics.profit_loss_ratio?.toFixed(2) || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">Total profit and loss</div>
          <div class="stat-value" :class="(statistics.total_pnl || 0) >= 0 ? 'positive' : 'negative'">
            {{ formatCurrency(statistics.total_pnl) }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">average profit</div>
          <div class="stat-value positive">{{ formatCurrency(statistics.avg_profit) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">average loss</div>
          <div class="stat-value negative">{{ formatCurrency(statistics.avg_loss) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ============== Simulated trading review content ============== -->
    <template v-if="reviewSource === 'paper'">
      <el-tabs v-model="activeTab" class="review-tabs">
        <el-tab-pane label="Positions can be reviewed" name="positions">
          <ReviewableTradesTable
            :stocks="holdingStocks"
            :loading="loading.trades"
            @start-review="startReview"
            @view-report="viewPaperReport"
            @view-history="viewPaperHistory"
          />
        </el-tab-pane>
        <el-tab-pane label="Historical positions" name="historyPositions">
          <ReviewableTradesTable
            :stocks="completedStocks"
            :loading="loading.trades"
            @start-review="startReview"
            @view-report="viewPaperReport"
            @view-history="viewPaperHistory"
          />
        </el-tab-pane>
      <el-tab-pane label="Review history" name="history">
        <ReviewHistoryTable
          :items="reviewHistory"
          :loading="loading.history"
          :total="historyTotal"
          :page="historyPage"
          :page-size="historyPageSize"
          @view="viewReviewDetail"
          @save-case="saveAsCase"
          @delete="deleteReview"
          @page-change="handleHistoryPageChange"
        />
      </el-tab-pane>
      <!-- The periodic review function is temporarily hidden and will be launched in the next version after optimization. -->
      <!-- <el-tab-pane label="Periodic review" name="periodic">
        <div class="periodic-header">
          <el-button type="primary" :icon="Plus" @click="showPeriodicDialog = true">
            Initiate a phased review
          </el-button>
        </div>
        <el-table :data="periodicReviews" v-loading="loading.periodic" stripe>
          <template #empty>
            <el-empty description="There is no staged review record yet" />
          </template>
          <el-table-column label="Review cycle" width="100">
            <template #default="{ row }">
              {{ getPeriodTypeLabel(row.period_type) }}
            </template>
          </el-table-column>
          <el-table-column label="time range" width="200">
            <template #default="{ row }">
              {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
            </template>
          </el-table-column>
          <el-table-column prop="total_trades" label="Number of transactions" width="80" align="center" />
          <el-table-column label="winning rate" width="80" align="center">
            <template #default="{ row }">
              <span :class="row.win_rate >= 50 ? 'positive' : 'negative'">
                {{ row.win_rate?.toFixed(1) || 0 }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Total profit and loss" width="120" align="right">
            <template #default="{ row }">
              <span :class="row.total_pnl >= 0 ? 'positive' : 'negative'">
                {{ formatCurrency(row.total_pnl) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="creation time" width="160">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="Operation" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link @click="viewPeriodicDetail(row.review_id)">
                View details
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="periodicTotal > 0"
          class="pagination"
          :current-page="periodicPage"
          :page-size="periodicPageSize"
          :total="periodicTotal"
          layout="total, prev, pager, next"
          @current-change="handlePeriodicPageChange"
        />
      </el-tab-pane> -->
      <el-tab-pane label="Case library" name="cases">
        <CaseLibraryTable
          :items="cases"
          :loading="loading.cases"
          :total="casesTotal"
          :page="casesPage"
          :page-size="casesPageSize"
          @view="viewReviewDetail"
          @delete="deleteCase"
          @page-change="handleCasesPageChange"
        />
      </el-tab-pane>
      </el-tabs>
    </template>

    <!-- ============== Position operation review content ============== -->
    <template v-else>
      <!-- Position statistics card -->
      <el-row :gutter="16" class="stats-row" v-loading="loading.positionStats">
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">Number of stocks held</div>
            <div class="stat-value">{{ positionStats.total_positions }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">Number of operations</div>
            <div class="stat-value">{{ positionStats.total_operations }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">Cleared</div>
            <div class="stat-value">{{ positionStats.closed_count }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">Realized profit and loss</div>
            <div class="stat-value" :class="(positionStats.realized_pnl || 0) >= 0 ? 'positive' : 'negative'">
              {{ formatCurrency(positionStats.realized_pnl) }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">floating profit and loss</div>
            <div class="stat-value" :class="(positionStats.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative'">
              {{ formatCurrency(positionStats.unrealized_pnl) }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">Total market capitalization</div>
            <div class="stat-value">{{ formatCurrency(positionStats.total_market_value) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-tabs v-model="positionTab" class="review-tabs">
        <el-tab-pane label="Positions can be reviewed" name="positions">
          <PositionChangesTable
            :items="positionChanges"
            :loading="loading.positionChanges"
            @start-review="startPositionReview"
            @view-report="viewLatestReport"
            @view-history="viewStockHistory"
          />
        </el-tab-pane>
        <el-tab-pane label="Historical positions" name="history">
          <HistoryPositionsTable
            :items="historyPositions"
            :loading="loading.historyPositions"
            @start-review="startHistoryPositionReview"
          />
        </el-tab-pane>
        <el-tab-pane label="Position review history" name="positionReviews">
          <!-- Filter tips -->
          <div v-if="positionReviewCodeFilter" class="filter-tip">
            <el-tag closable @close="clearPositionReviewFilter">
              Filter criteria: {{ positionReviewCodeFilter }}
            </el-tag>
          </div>

          <PositionReviewHistoryTable
            :items="positionReviewHistory"
            :loading="loading.positionReviews"
            :total="positionReviewTotal"
            :page="positionReviewPage"
            :page-size="positionReviewPageSize"
            @view="viewPositionReviewDetail"
            @delete="deleteReview"
            @page-change="handlePositionReviewPageChange"
          />
        </el-tab-pane>
        <!-- The periodic review function is temporarily hidden and will be launched in the next version after optimization. -->
        <!-- <el-tab-pane label="Periodic review" name="positionPeriodic">
          <div class="periodic-header">
            <el-button type="primary" :icon="Plus" @click="showPositionPeriodicDialog = true">
              Initiate a phased review
            </el-button>
          </div>
          <el-table :data="positionPeriodicReviews" v-loading="loading.positionPeriodic" stripe>
            <template #empty>
              <el-empty description="There is no staged review record yet" />
            </template>
            <el-table-column label="Review cycle" width="100">
              <template #default="{ row }">
                {{ getPeriodTypeLabel(row.period_type) }}
              </template>
            </el-table-column>
            <el-table-column label="time range" width="200">
              <template #default="{ row }">
                {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_trades" label="Number of transactions" width="80" align="center" />
            <el-table-column label="winning rate" width="80" align="center">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'positive' : 'negative'">
                  {{ row.win_rate?.toFixed(1) || 0 }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="Total profit and loss" width="120" align="right">
              <template #default="{ row }">
                <span :class="row.total_pnl >= 0 ? 'positive' : 'negative'">
                  {{ formatCurrency(row.total_pnl) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="creation time" width="160">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="100" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link @click="viewPeriodicDetail(row.review_id)">
                  View details
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="positionPeriodicTotal > 0"
            class="pagination"
            :current-page="positionPeriodicPage"
            :page-size="positionPeriodicPageSize"
            :total="positionPeriodicTotal"
            layout="total, prev, pager, next"
            @current-change="handlePositionPeriodicPageChange"
          />
        </el-tab-pane> -->
        <el-tab-pane label="Case library" name="positionCases">
          <CaseLibraryTable
            :items="positionCases"
            :loading="loading.positionCases"
            :total="positionCasesTotal"
            :page="positionCasesPage"
            :page-size="positionCasesPageSize"
            @view="viewPositionReviewDetail"
            @delete="deletePositionCase"
            @page-change="handlePositionCasesPageChange"
          />
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- Review details dialog box -->
    <ReviewDetailDialog
      v-model="showDetailDialog"
      :review-id="selectedReviewId"
    />

    <!-- The staged review function is temporarily hidden -->
    <!-- <PeriodicReviewDialog
      v-model="showPeriodicDialog"
      @success="handlePeriodicSuccess"
    /> -->

    <!-- <PeriodicReviewDetailDialog
      v-model="showPeriodicDetailDialog"
      :review-id="selectedPeriodicReviewId"
    /> -->

    <!-- Position review dialog box (common to user positions and simulated trading) -->
    <PositionReviewDialog
      v-model="showPositionReviewDialog"
      :position-data="selectedPositionData"
      :source="reviewSource === 'paper' ? 'paper' : 'real'"
      @success="handleReviewSuccess"
    />

    <!-- The periodic review dialog box for position operations is temporarily hidden. -->
    <!-- <PeriodicReviewDialog
      v-model="showPositionPeriodicDialog"
      source="position"
      @success="handlePositionPeriodicSuccess"
    /> -->

    <!-- Save as case dialog box -->
    <SaveAsCaseDialog
      v-model="showSaveCaseDialog"
      :review-id="saveCaseReviewId"
      :stock-code="saveCaseStockCode"
      @success="handleSaveCaseSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox, type TabPaneName } from 'element-plus'
import { TrendCharts, Refresh, Search, RefreshRight, Goods, Wallet } from '@element-plus/icons-vue'
import { reviewApi, type ReviewListItem, type TradingStatistics, type ReviewableStock, type ReviewType, type PeriodicReviewListItem } from '@/api/review'
import { portfolioApi } from '@/api/portfolio'

import ReviewHistoryTable from './components/ReviewHistoryTable.vue'
import CaseLibraryTable from './components/CaseLibraryTable.vue'
import ReviewableTradesTable from './components/ReviewableTradesTable.vue'
import ReviewDetailDialog from './components/ReviewDetailDialog.vue'
import PositionChangesTable from './components/PositionChangesTable.vue'
import HistoryPositionsTable from './components/HistoryPositionsTable.vue'
import PositionReviewHistoryTable from './components/PositionReviewHistoryTable.vue'
import PositionReviewDialog from './components/PositionReviewDialog.vue'
import SaveAsCaseDialog from './components/SaveAsCaseDialog.vue'

// Review source type
type ReviewSourceType = 'paper' | 'position'
const reviewSource = ref<ReviewSourceType>('position')  // The position operation review is displayed by default.



// filter form
const filterForm = ref<{
  code: string
  dateRange: [string, string] | null
  reviewType: ReviewType | ''
}>({
  code: '',
  dateRange: null,
  reviewType: ''
})

// Date shortcut options
const dateShortcuts = [
  {
    text: 'last week',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 7)
      return [start, end]
    }
  },
  {
    text: 'Last month',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 30)
      return [start, end]
    }
  },
  {
    text: 'Last three months',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 90)
      return [start, end]
    }
  },
  {
    text: 'this year',
    value: () => {
      const end = new Date()
      const start = new Date(end.getFullYear(), 0, 1)
      return [start, end]
    }
  }
]

// data
const statistics = ref<Partial<TradingStatistics>>({})
const reviewHistory = ref<ReviewListItem[]>([])
const cases = ref<ReviewListItem[]>([])
const reviewableStocks = ref<ReviewableStock[]>([])

// Pagination
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = ref(10)
const casesTotal = ref(0)
const casesPage = ref(1)
const casesPageSize = ref(10)

// Loading status
const loading = ref({
  stats: false,
  history: false,
  cases: false,
  trades: false,
  periodic: false,
  positionStats: false,
  positionChanges: false,
  historyPositions: false,
  positionReviews: false,
  positionPeriodic: false,
  positionCases: false
})

// Tab page - positions that can be reviewed are displayed by default
const activeTab = ref('positions')

// Calculated property: Filter stocks in positions (status === 'holding') 
const holdingStocks = computed(() => {
  return reviewableStocks.value.filter(stock => stock.status === 'holding')
})

// Calculated property: Filter stocks with closed positions (status === 'completed') 
const completedStocks = computed(() => {
  return reviewableStocks.value.filter(stock => stock.status === 'completed')
})

// dialog box
const showDetailDialog = ref(false)
const selectedReviewId = ref('')

// Save case dialog box
const showSaveCaseDialog = ref(false)
const saveCaseReviewId = ref('')
const saveCaseStockCode = ref('')

// Periodic review
const periodicReviews = ref<PeriodicReviewListItem[]>([])
const periodicTotal = ref(0)
const periodicPage = ref(1)
const periodicPageSize = ref(10)

// ============== Position review related status ==============
const positionTab = ref('positions')
const positionStats = ref<{
  total_positions: number
  total_operations: number
  closed_count: number
  realized_pnl: number
  unrealized_pnl: number
  total_market_value: number
}>({
  total_positions: 0,
  total_operations: 0,
  closed_count: 0,
  realized_pnl: 0,
  unrealized_pnl: 0,
  total_market_value: 0
})

// Position change record (operation record of current position)
interface PositionChangeItem {
  code: string
  name: string
  market: string
  operations: number
  current_quantity: number
  cost_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  last_operation_time: string
}
const positionChanges = ref<PositionChangeItem[]>([])

// Historical positions (cleared)
interface HistoryPositionItem {
  code: string
  name: string
  market: string
  realized_pnl: number
  realized_pnl_pct: number
  hold_days: number
  cleared_at: string
}
const historyPositions = ref<HistoryPositionItem[]>([])

// Position review history
interface PositionReviewItem {
  id: string
  code: string
  name: string
  review_type: string
  score: number
  created_at: string
  summary: string
  realized_pnl?: number
}
const positionReviewHistory = ref<PositionReviewItem[]>([])
const positionReviewTotal = ref(0)
const positionReviewPage = ref(1)
const positionReviewPageSize = ref(10)
const positionReviewCodeFilter = ref<string>('')  // Stock code filter

// Position review dialog box
const showPositionReviewDialog = ref(false)
const selectedPositionData = ref<any>(null)

// Periodic review of position operations
const positionPeriodicReviews = ref<PeriodicReviewListItem[]>([])
const positionPeriodicTotal = ref(0)
const positionPeriodicPage = ref(1)
const positionPeriodicPageSize = ref(10)

// Position operation case library
const positionCases = ref<ReviewListItem[]>([])
const positionCasesTotal = ref(0)
const positionCasesPage = ref(1)
const positionCasesPageSize = ref(10)

// Format amount
const formatCurrency = (value?: number) => {
  if (value === undefined || value === null) return '-'
  const prefix = value >= 0 ? '+' : ''
  return prefix + value.toFixed(2)
}

// Get filter parameters
const getFilterParams = () => {
  const params: {
    code?: string
    startDate?: string
    endDate?: string
    reviewType?: ReviewType
  } = {}

  if (filterForm.value.code) {
    params.code = filterForm.value.code
  }
  if (filterForm.value.dateRange && filterForm.value.dateRange.length === 2) {
    params.startDate = filterForm.value.dateRange[0]
    params.endDate = filterForm.value.dateRange[1]
  }
  if (filterForm.value.reviewType) {
    params.reviewType = filterForm.value.reviewType
  }

  return params
}

// Load data
const loadStatistics = async () => {
  try {
    loading.value.stats = true
    const params = getFilterParams()
    const res = await reviewApi.getTradingStatistics(params.startDate, params.endDate)
    if (res.success) {
      statistics.value = res.data || {}
    }
  } catch (e: any) {
    console.error('Failed to load statistics:', e)
  } finally {
    loading.value.stats = false
  }
}

const loadReviewHistory = async () => {
  try {
    loading.value.history = true
    const params = getFilterParams()
    const res = await reviewApi.getReviewHistory({
      page: historyPage.value,
      pageSize: historyPageSize.value,
      source: 'paper',  // Simulated trading review only displays the review history of simulated trading
      ...params
    })
    if (res.success) {
      reviewHistory.value = res.data?.items || []
      historyTotal.value = res.data?.total || 0
    }
  } catch (e: any) {
    console.error('Failed to load review history:', e)
  } finally {
    loading.value.history = false
  }
}

const loadCases = async () => {
  try {
    loading.value.cases = true
    const res = await reviewApi.getCases({ page: casesPage.value, pageSize: casesPageSize.value, source: 'paper' })
    if (res.success) {
      cases.value = res.data?.items || []
      casesTotal.value = res.data?.total || 0
    }
  } catch (e: any) {
    console.error('Failed to load case library:', e)
  } finally {
    loading.value.cases = false
  }
}

const loadReviewableTrades = async () => {
  try {
    loading.value.trades = true
    const params = getFilterParams()
    const res = await reviewApi.getReviewableTrades({
      code: params.code,
      startDate: params.startDate,
      endDate: params.endDate
    })
    if (res.success) {
      // Use all_stocks to display all traded stocks (including those that have only been bought but not sold)
      reviewableStocks.value = res.data?.all_stocks || res.data?.completed_stocks || []
    }
  } catch (e: any) {
    console.error('Failed to load resumable transactions:', e)
  } finally {
    loading.value.trades = false
  }
}

const refreshData = () => {
  loadStatistics()
  loadReviewHistory()
  loadCases()
  loadReviewableTrades()
}

// filter operation
const applyFilter = () => {
  historyPage.value = 1
  refreshData()
}

const resetFilter = () => {
  filterForm.value = {
    code: '',
    dateRange: null,
    reviewType: ''
  }
  historyPage.value = 1
  refreshData()
}

// event handling
const viewReviewDetail = (reviewId: string) => {
  selectedReviewId.value = reviewId
  showDetailDialog.value = true
}

const saveAsCase = async (reviewId: string) => {
  // Find the corresponding review record and obtain the stock code
  const review = reviewHistory.value.find(r => r.review_id === reviewId)
  saveCaseReviewId.value = reviewId
  saveCaseStockCode.value = review?.code || ''
  showSaveCaseDialog.value = true
}

const handleSaveCaseSuccess = () => {
  loadReviewHistory()
  loadCases()
}

const deleteCase = async (reviewId: string) => {
  try {
    const res = await reviewApi.deleteCase(reviewId)
    if (res.success) {
      ElMessage.success('Removed from case library')
      loadCases()
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Delete failed')
  }
}

const deleteReview = async (reviewId: string) => {
  try {
    await ElMessageBox.confirm('Are you sure you want to delete this review record? This operation is irreversible.', 'Confirm deletion', {
      type: 'warning'
    })
    const res = await reviewApi.deleteReview(reviewId)
    if (res.success) {
      ElMessage.success('The review record has been deleted')
      loadReviewHistory()
      loadPositionReviewHistory()
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || 'Delete failed')
    }
  }
}

const startReview = async (code: string) => {
  try {
    // Find information about this stock from reviewableStocks
    const stock = reviewableStocks.value.find(s => s.code === code)
    if (!stock) {
      ElMessage.warning('The stock information was not found')
      return
    }

    // Get simulated position data (if the position is open)
    let positionData: any = {
      code: stock.code,
      name: stock.name || stock.code,
      market: stock.market || 'CN',
      type: stock.status === 'completed' ? 'history' : 'current'
    }

    // If the position is open, try to obtain the position details
    if (stock.status === 'holding' || (stock.sell_count || 0) < (stock.buy_count || 0)) {
      try {
        const posRes = await portfolioApi.getPositions('paper')
        const positions = posRes.data?.items || []
        const position = positions.find((p: any) => p.code === code)
        if (position) {
          positionData = {
            code: position.code,
            name: position.name || position.code,
            market: position.market || 'CN',
            type: 'current',
            quantity: position.quantity,
            cost_price: position.cost_price || position.original_avg_cost || 0,
            unrealized_pnl: position.unrealized_pnl || 0
          }
        }
      } catch (e) {
        console.warn('Failed to obtain simulated position details, using default data', e)
      }
    }

    // Use PositionReviewDialog (same interface as user positions)
    selectedPositionData.value = positionData
    showPositionReviewDialog.value = true
  } catch (e: any) {
    console.error('Failed to initiate review:', e)
    ElMessage.error(e.message || 'Failed to initiate review')
  }
}

// View the latest review report of the stock in simulated trading
const viewPaperReport = async (stock: ReviewableStock) => {
  try {
    // Get the latest review report of the stock (only get simulated trading)
    const res = await reviewApi.getReviewHistory({
      page: 1,
      pageSize: 1,
      code: stock.code,
      source: 'paper'  // Get only the review report of simulated trading
    })

    if (res.success && res.data?.items && res.data.items.length > 0) {
      const latestReview = res.data.items[0]
      viewReviewDetail(latestReview.review_id)
    } else {
      ElMessage.warning(`${stock.name || stock.code}(${stock.code}) No review report yet`)
    }
  } catch (e) {
    console.error('Failed to obtain the latest review report:', e)
    ElMessage.error('Failed to obtain review report')
  }
}

// View all the review history of simulated trading of this stock
const viewPaperHistory = (stock: ReviewableStock) => {
  // Set filter criteria
  filterForm.value.code = stock.code
  historyPage.value = 1

  // switch to"Review history"tab page
  activeTab.value = 'history'

  // Reload the data (will automatically use the code and source='paper') 
  loadReviewHistory()

  ElMessage.success(`Viewing ${stock.name || stock.code}(${stock.code}) review history`)
}


const handleHistoryPageChange = (page: number) => {
  historyPage.value = page
  loadReviewHistory()
}

const handleCasesPageChange = (page: number) => {
  casesPage.value = page
  loadCases()
}

// Methods related to staged review
const loadPeriodicReviews = async () => {
  try {
    loading.value.periodic = true
    const res = await reviewApi.getPeriodicReviewHistory(periodicPage.value, periodicPageSize.value)
    if (res.success) {
      periodicReviews.value = res.data?.items || []
      periodicTotal.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to load phased review history:', e)
  } finally {
    loading.value.periodic = false
  }
}

// ============== Methods related to position review ==============
const handleSourceChange = (source: TabPaneName) => {
  if (String(source) === 'paper') {
    refreshData()
    loadPeriodicReviews()
  } else {
    loadPositionData()
  }
}

const loadPositionData = async () => {
  await Promise.all([
    loadPositionStats(),
    loadPositionChanges(),
    loadHistoryPositions(),
    loadPositionReviewHistory(),
    loadPositionPeriodicReviews(),
    loadPositionCases()
  ])
}

const loadPositionStats = async () => {
  try {
    loading.value.positionStats = true
    // Get current position
    const posRes = await portfolioApi.getPositions('real')
    const positions = posRes.data?.items || []

    // Get historical positions
    const histRes = await portfolioApi.getHistoryPositions({ source: 'real', limit: 100 })
    const history = histRes.data?.items || []

    // Calculate statistics
    let totalMarketValue = 0
    let unrealizedPnl = 0
    let realizedPnl = 0

    positions.forEach((p: any) => {
      totalMarketValue += p.market_value || 0
      unrealizedPnl += p.unrealized_pnl || 0
    })

    history.forEach((h: any) => {
      realizedPnl += h.realized_pnl || 0
    })

    positionStats.value = {
      total_positions: positions.length,
      total_operations: 0, // Subsequent statistics from change records
      closed_count: history.length,
      realized_pnl: realizedPnl,
      unrealized_pnl: unrealizedPnl,
      total_market_value: totalMarketValue
    }
  } catch (e) {
    console.error('Failed to load position statistics:', e)
  } finally {
    loading.value.positionStats = false
  }
}

const loadPositionChanges = async () => {
  try {
    loading.value.positionChanges = true
    // Get the current position list
    const res = await portfolioApi.getPositions('real')
    const positions = res.data?.items || []

    // Convert to restoreable format
    positionChanges.value = positions.map((p: any) => ({
      code: p.code,
      name: p.name || p.code,
      market: p.market || 'CN',
      operations: 0,
      current_quantity: p.quantity,
      cost_price: p.cost_price || p.avg_cost,
      unrealized_pnl: p.unrealized_pnl || 0,
      unrealized_pnl_pct: p.unrealized_pnl_pct || 0,
      last_operation_time: p.updated_at || p.created_at
    }))
  } catch (e) {
    console.error('Failed to load position changes:', e)
  } finally {
    loading.value.positionChanges = false
  }
}

const loadHistoryPositions = async () => {
  try {
    loading.value.historyPositions = true
    const res = await portfolioApi.getHistoryPositions({ source: 'real', limit: 50 })
    historyPositions.value = (res.data?.items || []).map((h: any) => ({
      code: h.code,
      name: h.name || h.code,
      market: h.market || 'CN',
      realized_pnl: h.realized_pnl || 0,
      realized_pnl_pct: h.realized_pnl_pct || 0,
      hold_days: h.hold_days || 0,
      cleared_at: h.cleared_at || h.updated_at
    }))
  } catch (e) {
    console.error('Failed to load historical positions:', e)
  } finally {
    loading.value.historyPositions = false
  }
}

const loadPositionReviewHistory = async () => {
  try {
    loading.value.positionReviews = true
    // Call position review history API
    const res = await reviewApi.getReviewHistory({
      page: positionReviewPage.value,
      pageSize: positionReviewPageSize.value,
      code: positionReviewCodeFilter.value || undefined  // If there are filter conditions, pass them in
    })
    if (res.success) {
      // Mapping data fields:review_id -> id, overall_score -> score
      positionReviewHistory.value = (res.data?.items || []).map((item: any) => ({
        id: item.review_id,
        code: item.code,
        name: item.name,
        review_type: item.review_type,
        score: item.overall_score,
        created_at: item.created_at,
        summary: `Profit and loss: ${item.realized_pnl >= 0 ? '+' : ''}${item.realized_pnl.toFixed(2)}Yuan`,
        realized_pnl: item.realized_pnl
      }))
      positionReviewTotal.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to load position review history:', e)
  } finally {
    loading.value.positionReviews = false
  }
}

const startPositionReview = (item: PositionChangeItem) => {
  selectedPositionData.value = {
    code: item.code,
    name: item.name,
    market: item.market,
    type: 'current',
    quantity: item.current_quantity,
    cost_price: item.cost_price,
    unrealized_pnl: item.unrealized_pnl
  }
  showPositionReviewDialog.value = true
}

const startHistoryPositionReview = (item: HistoryPositionItem) => {
  selectedPositionData.value = {
    code: item.code,
    name: item.name,
    market: item.market,
    type: 'history',
    realized_pnl: item.realized_pnl,
    hold_days: item.hold_days,
    cleared_at: item.cleared_at
  }
  showPositionReviewDialog.value = true
}

// View the latest review report for this stock
const viewLatestReport = async (item: PositionChangeItem) => {
  try {
    // Get the latest review report of the stock (only get the user s position)
    const res = await reviewApi.getReviewHistory({
      page: 1,
      pageSize: 1,
      code: item.code,
      source: 'position'  // Only obtain review reports of user positions
    })

    if (res.success && res.data?.items && res.data.items.length > 0) {
      const latestReview = res.data.items[0]
      viewPositionReviewDetail(latestReview.review_id)
    } else {
      ElMessage.warning(`${item.name}(${item.code}) No review report yet`)
    }
  } catch (e) {
    console.error('Failed to obtain the latest review report:', e)
    ElMessage.error('Failed to obtain review report')
  }
}

// View all trading history for this stock
const viewStockHistory = (item: PositionChangeItem) => {
  // Set filter criteria
  positionReviewCodeFilter.value = item.code
  positionReviewPage.value = 1

  // switch to"Position review history"tab page
  positionTab.value = 'positionReviews'

  // Reload data
  loadPositionReviewHistory()

  ElMessage.success(`Viewing ${item.name}(${item.code}) review history`)
}

const viewPositionReviewDetail = (reviewId: string) => {
  selectedReviewId.value = reviewId
  showDetailDialog.value = true
}

const handlePositionReviewPageChange = (page: number) => {
  positionReviewPage.value = page
  loadPositionReviewHistory()
}

const clearPositionReviewFilter = () => {
  positionReviewCodeFilter.value = ''
  positionReviewPage.value = 1
  loadPositionReviewHistory()
}

// Unified review success callback (judged based on reviewSource)
const handleReviewSuccess = (reviewId: string) => {
  console.log('[Review] The resumption of the callback was successful,reviewId:', reviewId, 'reviewSource:', reviewSource.value)
  
  // Open the details page first
  selectedReviewId.value = reviewId
  showDetailDialog.value = true
  console.log('[Review] The details dialog box has been opened.showDetailDialog:', showDetailDialog.value, 'selectedReviewId:', selectedReviewId.value)
  
  // Then close the review dialog box
  showPositionReviewDialog.value = false
  selectedPositionData.value = null
  
  // Refresh the corresponding historical data according to the data source
  if (reviewSource.value === 'paper') {
    // Simulated trading review: Refresh history asynchronously (without blocking the opening of the details page)
    setTimeout(() => {
      loadReviewHistory()
    }, 500)
  } else {
    // User position review: Refresh history asynchronously (without blocking the opening of the details page)
    setTimeout(() => {
      loadPositionReviewHistory()
    }, 500)
  }
}

const applyPositionFilter = () => {
  loadPositionChanges()
  loadHistoryPositions()
}

const resetPositionFilter = () => {
  filterForm.value.code = ''
  filterForm.value.dateRange = null
  loadPositionChanges()
  loadHistoryPositions()
}

// Methods related to phased review of position operations
const loadPositionPeriodicReviews = async () => {
  try {
    loading.value.positionPeriodic = true
    const res = await reviewApi.getPeriodicReviewHistory(positionPeriodicPage.value, positionPeriodicPageSize.value, 'position')
    if (res.success) {
      positionPeriodicReviews.value = res.data?.items || []
      positionPeriodicTotal.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to load position operation periodic review history:', e)
  } finally {
    loading.value.positionPeriodic = false
  }
}

// Related methods of position operation case library
const loadPositionCases = async () => {
  try {
    loading.value.positionCases = true
    const res = await reviewApi.getCases({
      page: positionCasesPage.value,
      pageSize: positionCasesPageSize.value,
      source: 'position'  // Get only the cases of position operations
    })
    if (res.success) {
      positionCases.value = res.data?.items || []
      positionCasesTotal.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to load position operation case library:', e)
  } finally {
    loading.value.positionCases = false
  }
}

const deletePositionCase = async (reviewId: string) => {
  try {
    const res = await reviewApi.deleteCase(reviewId)
    if (res.success) {
      ElMessage.success('Deleted from case library')
      loadPositionCases()
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Delete failed')
  }
}

const handlePositionCasesPageChange = (page: number) => {
  positionCasesPage.value = page
  loadPositionCases()
}



// initialization
onMounted(async () => {
  // Load the corresponding data according to the default reviewSource
  if (reviewSource.value === 'paper') {
    refreshData()
    loadPeriodicReviews()
  } else {
    loadPositionData()
  }
})
</script>

<style scoped lang="scss">
.trade-review {
  padding: 20px;

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    .title {
      display: flex;
      align-items: center;
      font-size: 20px;
      font-weight: 600;
    }
  }

  .source-tabs {
    margin-bottom: 16px;

    :deep(.el-tabs__item) {
      font-size: 14px;
    }
  }



  .filter-card {
    margin-bottom: 20px;

    .filter-form {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;

      :deep(.el-form-item) {
        margin-bottom: 0;
        margin-right: 16px;
      }
    }
  }

  .stats-row {
    margin-bottom: 20px;

    .stat-card {
      text-align: center;

      .stat-label {
        font-size: 12px;
        color: #909399;
        margin-bottom: 8px;
      }

      .stat-value {
        font-size: 20px;
        font-weight: 600;

        &.positive {
          color: #f56c6c;  // Chinese custom: red indicates profit (positive number)
        }

        &.negative {
          color: #67c23a;  // Chinese custom: green indicates loss (negative number)
        }
      }
    }
  }

  .review-tabs {
    background: #fff;
    padding: 16px;
    border-radius: 4px;

    .filter-tip {
      margin-bottom: 16px;
      padding: 8px 12px;
      background: #f5f7fa;
      border-radius: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .periodic-header {
      margin-bottom: 16px;
    }

    .pagination {
      margin-top: 16px;
      justify-content: flex-end;
    }

    .positive {
      color: #f56c6c;  // Chinese custom: red indicates profit (positive number)
    }

    .negative {
      color: #67c23a;  // Chinese custom: green indicates loss (negative number)
    }
  }
}
</style>

