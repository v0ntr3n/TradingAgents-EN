<template>
  <div class="favorites">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Star /></el-icon>
        Stock Watchlist
      </h1>
      <p class="page-description">
        Manage the stocks you care about
      </p>
    </div>

    <!-- Action bar -->
    <el-card class="action-card" shadow="never">
      <el-row :gutter="16" align="middle" style="margin-bottom: 16px;">
        <el-col :span="8">
          <el-input
            v-model="searchKeyword"
            placeholder="Search for a stock symbol or name"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>

        <el-col :span="4">
          <el-select v-model="selectedMarket" placeholder="market" clearable>
            <el-option label="A shares" value="A shares" />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-select v-model="selectedBoard" placeholder="plate" clearable>
            <el-option label="motherboard" value="motherboard" />
            <el-option label="GEM" value="GEM" />
            <el-option label="Science and Technology Innovation Board" value="Science and Technology Innovation Board" />
            <el-option label="Beijing Exchange" value="Beijing Exchange" />
            <el-option label="ETF" value="ETF" />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-select v-model="selectedExchange" placeholder="exchange" clearable>
            <el-option label="Shanghai Stock Exchange" value="Shanghai Stock Exchange" />
            <el-option label="Shenzhen Stock Exchange" value="Shenzhen Stock Exchange" />
            <el-option label="Beijing Stock Exchange" value="Beijing Stock Exchange" />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-select v-model="selectedTag" placeholder="label" clearable>
            <el-option
              v-for="tag in userTags"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
        </el-col>
      </el-row>

      <el-row :gutter="16" align="middle">
        <el-col :span="24">
          <div class="action-buttons">
            <el-button @click="refreshData">
              <el-icon><Refresh /></el-icon>
              Refresh
            </el-button>
            <!-- The synchronize real-time quotes button is only displayed when there is an A-share stock watch list. -->
            <el-button
              v-if="hasAStocks"
              type="success"
              @click="syncAllRealtime"
              :loading="syncRealtimeLoading"
            >
              <el-icon><Refresh /></el-icon>
              Synchronize real-time quotes
            </el-button>
            <!-- Batch sync button always shows -->
            <el-button
              type="primary"
              @click="showBatchSyncDialog"
            >
              <el-icon><Download /></el-icon>
              Batch sync data
            </el-button>
            <el-button @click="openTagManager">
              tag management
            </el-button>
            <el-button type="primary" @click="showAddDialog">
              <el-icon><Plus /></el-icon>
              add
            </el-button>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- Stock Watchlist List -->
    <el-card class="favorites-list-card" shadow="never">
      <el-table
        :data="filteredFavorites"
        v-loading="loading"
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="stock_code" label="Stock code" width="120">
          <template #default="{ row }">
            <el-link type="primary" @click="viewStockDetail(row)">
              {{ row.stock_code }}
            </el-link>
          </template>
        </el-table-column>

        <el-table-column prop="stock_name" label="Stock name" width="150" />
        <el-table-column prop="market" label="market" width="80">
          <template #default="{ row }">
            {{ row.market || 'A shares' }}
          </template>
        </el-table-column>
        <el-table-column prop="board" label="plate" width="100">
          <template #default="{ row }">
            {{ row.board || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="exchange" label="exchange" width="140">
          <template #default="{ row }">
            {{ row.exchange || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="current_price" label="current price" width="100">
          <template #default="{ row }">
            <span v-if="row.current_price !== null && row.current_price !== undefined">¥{{ formatPrice(row.current_price) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="change_percent" label="Increase or decrease" width="100">
          <template #default="{ row }">
            <span
              v-if="row.change_percent !== null && row.change_percent !== undefined"
              :class="getChangeClass(row.change_percent)"
            >
              {{ formatPercent(row.change_percent) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="tags" label="label" width="150">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.tags"
              :key="tag"
              size="small"
              :color="getTagColor(tag)"
              effect="dark"
              :style="{ marginRight: '4px' }"
            >
              {{ tag }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="added_at" label="Add time" width="120">
          <template #default="{ row }">
            {{ formatDate(row.added_at) }}
          </template>
        </el-table-column>

        <el-table-column label="Operation" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              type="text"
              size="small"
              @click="editFavorite(row)"
            >
              Edit
            </el-button>
            <!-- Only A shares display the synchronization button -->
            <el-button
              v-if="row.market === 'A shares'"
              type="text"
              size="small"
              @click="showSingleSyncDialog(row)"
              style="color: #409EFF;"
            >
              sync
            </el-button>
            <el-button
              type="text"
              size="small"
              @click="analyzeFavorite(row)"
            >
              analysis
            </el-button>
            <el-button
              type="text"
              size="small"
              @click="removeFavorite(row)"
              style="color: #f56c6c;"
            >
              Remove
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty state -->
      <div v-if="!loading && favorites.length === 0" class="empty-state">
        <el-empty description="There is no stock watch list yet">
          <el-button type="primary" @click="showAddDialog">
            Add first stock to watchlist
          </el-button>
        </el-empty>
      </div>
    </el-card>

    <!-- Add to study list dialog -->
    <el-dialog
      v-model="addDialogVisible"
      title="Add to study list"
      width="500px"
    >
      <el-form :model="addForm" :rules="addRules" ref="addFormRef" label-width="100px">
        <el-form-item label="market type" prop="market">
          <el-select v-model="addForm.market" @change="handleMarketChange">
            <el-option label="A shares" value="A shares" />
          </el-select>
        </el-form-item>

        <el-form-item label="Stock code" prop="stock_code">
          <el-autocomplete
            v-model="addForm.stock_code"
            :fetch-suggestions="searchStocks"
            placeholder="Enter stock code or name to search, such as: 000001 or Ping An Bank"
            clearable
            class="w-full"
            value-key="code"
            :debounce="300"
            @select="handleStockSelect"
            @blur="fetchStockInfo"
          >
            <template #default="{ item }">
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 5px 0;">
                <span style="font-weight: 600; color: #303133;">{{ item.code }}</span>
                <span style="color: #606266; font-size: 13px;">{{ item.name }}</span>
              </div>
            </template>
          </el-autocomplete>
          <div style="font-size: 12px; color: #909399; margin-top: 4px;">
            Supports stock code or name search and automatically fills in after selection
          </div>
        </el-form-item>

        <el-form-item label="Stock name" prop="stock_name">
          <el-input v-model="addForm.stock_name" placeholder="Stock name" />
        </el-form-item>

        <el-form-item label="label">
          <el-select
            v-model="addForm.tags"
            multiple
            filterable
            allow-create
            placeholder="Select or create a label"
          >
            <el-option v-for="tag in userTags" :key="tag" :label="tag" :value="tag">
              <span :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }">
                <span>{{ tag }}</span>
                <span :style="{ display:'inline-block', width:'12px', height:'12px', border:'1px solid #ddd', borderRadius:'2px', marginLeft:'8px', background: getTagColor(tag) }"></span>
              </span>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="Remarks">
          <el-input
            v-model="addForm.notes"
            type="textarea"
            :rows="2"
            placeholder="Optional: add notes"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="addDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleAddFavorite" :loading="addLoading">
          add
        </el-button>
      </template>
    </el-dialog>
    <!-- Edit Stock Watchlist Dialog Box -->
    <el-dialog
      v-model="editDialogVisible"
      title="Edit a stock watchlist"
      width="520px"
    >
      <el-form :model="editForm" ref="editFormRef" label-width="100px">
        <el-form-item label="stocks">
          <div>{{ editForm.stock_code }}｜{{ editForm.stock_name }}（{{ editForm.market }}）</div>
        </el-form-item>

        <el-form-item label="label">
          <el-select v-model="editForm.tags" multiple filterable allow-create placeholder="Select or create a label">
            <el-option v-for="tag in userTags" :key="tag" :label="tag" :value="tag">
              <span :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }">
                <span>{{ tag }}</span>
                <span :style="{ display:'inline-block', width:'12px', height:'12px', border:'1px solid #ddd', borderRadius:'2px', marginLeft:'8px', background: getTagColor(tag) }"></span>
              </span>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="Remarks">
          <el-input v-model="editForm.notes" type="textarea" :rows="2" placeholder="Optional: add notes" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="editDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleUpdateFavorite">save</el-button>
      </template>
    </el-dialog>

    <!-- Tag management dialog -->
    <el-dialog v-model="tagDialogVisible" title="tag management" width="560px">
      <el-table :data="tagList" v-loading="tagLoading" size="small" style="width: 100%; margin-bottom: 12px;">
        <el-table-column label="Name" min-width="220">
          <template #default="{ row }">
            <template v-if="row._editing">
              <el-input v-model="row._name" placeholder="Tag name" size="small" />
            </template>
            <template v-else>
              <el-tag :color="row.color" effect="dark" style="margin-right:6px"></el-tag>
              {{ row.name }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="color" width="140">
          <template #default="{ row }">
            <template v-if="row._editing">
              <el-select v-model="row._color" placeholder="Choose color" size="small" style="width: 200px">
                <el-option v-for="c in COLOR_PALETTE" :key="c" :label="c" :value="c">
                  <span :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }">
                    <span>{{ c }}</span>
                    <span :style="{ display: 'inline-block', width: '12px', height: '12px', border: '1px solid #ddd', borderRadius: '2px', marginLeft: '8px', background: c }"></span>
                  </span>
                </el-option>
              </el-select>
              <span class="color-dot-preview" :style="{ background: row._color }"></span>
            </template>
            <template v-else>
              <span :style="{display:'inline-block',width:'14px',height:'14px',background: row.color,border:'1px solid #ddd',marginRight:'6px'}"></span>
              {{ row.color }}

            </template>
          </template>
        </el-table-column>
        <el-table-column label="sort" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._editing">
              <el-input v-model.number="row._sort" type="number" size="small" />
            </template>
            <template v-else>
              {{ row.sort_order }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="160" fixed="right">
          <template #default="{ row }">
            <template v-if="row._editing">
              <el-button type="text" size="small" @click="saveTag(row)">save</el-button>
              <el-button type="text" size="small" @click="cancelEditTag(row)">Cancel</el-button>
            </template>
            <template v-else>
              <el-button type="text" size="small" @click="editTag(row)">Edit</el-button>
              <el-button type="text" size="small" style="color:#f56c6c" @click="deleteTag(row)">Delete</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div style="display:flex; gap:8px; align-items:center;">
        <el-input v-model="newTag.name" placeholder="New tag name" style="flex:1" />
        <el-select v-model="newTag.color" placeholder="Choose color" style="width:200px">
          <el-option v-for="c in COLOR_PALETTE" :key="c" :label="c" :value="c">
            <span :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }">
              <span>{{ c }}</span>
              <span :style="{ display: 'inline-block', width: '12px', height: '12px', border: '1px solid #ddd', borderRadius: '2px', marginLeft: '8px', background: c }"></span>
            </span>
          </el-option>
        </el-select>
        <span class="color-dot-preview" :style="{ background: newTag.color }"></span>
        <el-input v-model.number="newTag.sort_order" type="number" placeholder="sort" style="width:120px" />
        <el-button type="primary" @click="createTag" :loading="tagLoading">New</el-button>
      </div>

      <template #footer>
        <el-button @click="tagDialogVisible=false">close</el-button>
      </template>
    </el-dialog>

    <!-- Batch sync dialog box -->
    <el-dialog
      v-model="batchSyncDialogVisible"
      title="Batch sync stock data"
      width="500px"
    >
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 16px;"
      >
        <template v-if="syncAllStocks">
          will synchronize all studies in the list <strong>{{ favorites.filter(item => item.market === 'A shares').length }}</strong> Only A-share stocks
        </template>
        <template v-else>
          Selected <strong>{{ selectedStocks.length }}</strong> only stocks
        </template>
      </el-alert>

      <el-form :model="batchSyncForm" label-width="120px">
        <el-form-item label="Sync content">
          <el-checkbox-group v-model="batchSyncForm.syncTypes">
            <el-checkbox label="historical">Historical market data</el-checkbox>
            <el-checkbox label="financial">financial data</el-checkbox>
            <el-checkbox label="basic">Basic data</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="data source">
          <el-radio-group v-model="batchSyncForm.dataSource">
            <el-radio label="tushare" :disabled="!availableSyncSources.tushare">Tushare</el-radio>
            <el-radio label="akshare" :disabled="!availableSyncSources.akshare">AKShare</el-radio>
            <el-radio v-if="!isJdyunMode()" label="qmt" :disabled="!availableSyncSources.qmt">QMT</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Historical data days" v-if="batchSyncForm.syncTypes.includes('historical')">
          <el-input-number v-model="batchSyncForm.days" :min="1" :max="3650" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">
            (Up to 3650 days, about 10 years)
          </span>
        </el-form-item>
      </el-form>

      <el-alert
        type="warning"
        :closable="false"
        style="margin-top: 16px;"
      >
        Batch synchronization may take a long time, please be patient.
      </el-alert>

      <template #footer>
        <el-button @click="batchSyncDialogVisible = false; syncAllStocks = false">Cancel</el-button>
        <el-button type="primary" @click="handleBatchSync" :loading="batchSyncLoading">
          Start syncing
        </el-button>
      </template>
    </el-dialog>

    <!-- Single stock synchronization dialog box -->
    <el-dialog
      v-model="singleSyncDialogVisible"
      title="Sync stock data"
      width="500px"
    >
      <el-form :model="singleSyncForm" label-width="120px">
        <el-form-item label="Stock code">
          <el-input v-model="currentSyncStock.stock_code" disabled />
        </el-form-item>
        <el-form-item label="Stock name">
          <el-input v-model="currentSyncStock.stock_name" disabled />
        </el-form-item>
        <el-form-item label="Sync content">
          <el-checkbox-group v-model="singleSyncForm.syncTypes">
            <el-checkbox label="realtime">Real-time quotes</el-checkbox>
            <el-checkbox label="historical">Historical market data</el-checkbox>
            <el-checkbox label="financial">financial data</el-checkbox>
            <el-checkbox label="basic">Basic data</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="data source">
          <el-radio-group v-model="singleSyncForm.dataSource">
            <el-radio label="tushare" :disabled="!availableSyncSources.tushare">Tushare</el-radio>
            <el-radio label="akshare" :disabled="!availableSyncSources.akshare">AKShare</el-radio>
            <el-radio v-if="!isJdyunMode()" label="qmt" :disabled="!availableSyncSources.qmt">QMT</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Historical data days" v-if="singleSyncForm.syncTypes.includes('historical')">
          <el-input-number v-model="singleSyncForm.days" :min="1" :max="3650" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">
            (Up to 3650 days, about 10 years)
          </span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="singleSyncDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleSingleSync" :loading="singleSyncLoading">
          Start syncing
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { isJdyunMode } from '@/utils/config'
import request from '@/api/request'
import {
  Star,
  Search,
  Refresh,
  Plus,
  Download
} from '@element-plus/icons-vue'
import { favoritesApi } from '@/api/favorites'
import { tagsApi } from '@/api/tags'
import {
  stockSyncApi,
  type BatchStockSyncResponse,
  type SingleStockSyncResponse,
  type StockSyncTaskStatus,
} from '@/api/stockSync'
import { loadManualSyncSourceState, type ManualSyncDataSource } from '@/utils/dataSource'
import { normalizeMarketForAnalysis } from '@/utils/market'
import { ApiClient } from '@/api/request'

import type { FavoriteItem, FavoritesRealtimeSyncTaskStatus } from '@/api/favorites'
import { useAuthStore } from '@/stores/auth'


// Color options (20 preset colors)
const COLOR_PALETTE = [
  '#409EFF', '#1677FF', '#2F88FF', '#52C41A', '#67C23A',
  '#13C2C2', '#FA8C16', '#E6A23C', '#F56C6C', '#EB2F96',
  '#722ED1', '#8E44AD', '#00BFBF', '#1F2D3D', '#606266',
  '#909399', '#C0C4CC', '#FF7F50', '#A0CFFF', '#2C3E50'
]

const router = useRouter()
const STOCK_SYNC_POLL_INTERVAL_MS = 2000
const STOCK_SYNC_POLL_MAX_ATTEMPTS = 300
let favoritesViewDisposed = false

// Responsive data
const loading = ref(false)
const favorites = ref<FavoriteItem[]>([])
const userTags = ref<string[]>([])
const tagColorMap = ref<Record<string, string>>({})
const getTagColor = (name: string) => tagColorMap.value[name] || ''

const searchKeyword = ref('')
const selectedTag = ref('')
const selectedMarket = ref('')
const selectedBoard = ref('')
const selectedExchange = ref('')

// Bulk selection
const selectedStocks = ref<FavoriteItem[]>([])

// Batch sync dialog box
const batchSyncDialogVisible = ref(false)
const batchSyncLoading = ref(false)
const syncAllStocks = ref(false)  // Mark whether to synchronize all A-share stocks
const availableSyncSources = ref<Record<ManualSyncDataSource, boolean>>({
  tushare: true,
  akshare: true,
  qmt: true
})
const batchSyncForm = ref({
  syncTypes: ['historical', 'financial'],
  dataSource: 'tushare' as ManualSyncDataSource,
  days: 365
})

// Single stock synchronization dialog box
const singleSyncDialogVisible = ref(false)
const singleSyncLoading = ref(false)
const currentSyncStock = ref({
  stock_code: '',
  stock_name: ''
})
const singleSyncForm = ref({
  syncTypes: ['realtime'],  // By default, only real-time quotes are selected (most commonly used)
  dataSource: 'tushare' as ManualSyncDataSource,
  days: 365
})

const loadPreferredAvailableSyncSource = async (): Promise<ManualSyncDataSource | null> => {
  try {
    const sourceState = await loadManualSyncSourceState()
    availableSyncSources.value = sourceState.availableSources
    return sourceState.preferredSource
  } catch (error) {
    console.warn('Failed to load available sync data sources, retaining current defaults', error)
    return null
  }
}

// Add dialog
const addDialogVisible = ref(false)
const addLoading = ref(false)
const addFormRef = ref()
const addForm = ref({
  stock_code: '',
  stock_name: '',
  market: 'A shares',
  tags: [],
  notes: ''
})

const addRules = {
  market: [
    { required: true, message: 'Please select market type', trigger: 'change' }
  ],
  stock_code: [
    { required: true, message: 'Please select or enter a stock code', trigger: 'blur' }
  ],
  stock_name: [
    { required: true, message: 'Please enter the stock name', trigger: 'blur' }
  ]
}

// Edit dialog
const editDialogVisible = ref(false)
const editLoading = ref(false)
const editFormRef = ref()
const editForm = ref({
  stock_code: '',
  stock_name: '',
  market: 'A shares',
  tags: [] as string[],
  notes: ''
})


// Computed properties
const filteredFavorites = computed<FavoriteItem[]>(() => {
  let result: FavoriteItem[] = favorites.value

  // keyword search
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter((item: FavoriteItem) =>
      String(item.stock_code || item.symbol || '').toLowerCase().includes(keyword) ||
      item.stock_name.toLowerCase().includes(keyword)
    )
  }

  // Market screening
  if (selectedMarket.value) {
    result = result.filter((item: FavoriteItem) =>
      item.market === selectedMarket.value
    )
  }

  // Section filtering
  if (selectedBoard.value) {
    result = result.filter((item: FavoriteItem) =>
      item.board === selectedBoard.value
    )
  }

  // Exchange filter
  if (selectedExchange.value) {
    result = result.filter((item: FavoriteItem) =>
      item.exchange === selectedExchange.value
    )
  }

  // Tag filter
  if (selectedTag.value) {
    result = result.filter((item: FavoriteItem) =>
      (item.tags || []).includes(selectedTag.value)
    )
  }

  return result
})

// Determine whether there is an A-share stock watch list
const hasAStocks = computed(() => {
  return favorites.value.some(item => item.market === 'A shares')
})

// method
const loadFavorites = async () => {
  loading.value = true
  try {
    const res = await favoritesApi.list()
    favorites.value = ((res as any)?.data || []) as FavoriteItem[]
  } catch (error: any) {
    console.error('Failed to load stock watchlist:', error)
    ElMessage.error(error.message || 'Failed to load stock watchlist')
  } finally {
    loading.value = false
  }
}

// Synchronize real-time quotes
const syncRealtimeLoading = ref(false)
const waitForFavoritesRealtimeTask = async (taskId: string): Promise<FavoritesRealtimeSyncTaskStatus> => {
  for (let attempt = 0; attempt < STOCK_SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
    if (favoritesViewDisposed) {
      throw new Error('The page has been left, stop waiting for synchronization results')
    }

    const res = await favoritesApi.getRealtimeSyncTaskStatus(taskId)
    if (res.success && ['success', 'success_with_errors', 'failed'].includes(res.data.status)) {
      return res.data
    }

    await sleep(STOCK_SYNC_POLL_INTERVAL_MS)
  }

  throw new Error('The real-time market synchronization of the stock watch list has timed out. Please refresh the list later to view the results.')
}

const monitorFavoritesRealtimeTask = async (taskId: string) => {
  try {
    const task = await waitForFavoritesRealtimeTask(taskId)
    if (favoritesViewDisposed) return

    const message = task.result?.message || task.error || task.message || 'Stock watch list real-time quotation synchronization failed'
    if (task.status === 'success') {
      ElMessage.success(message)
    } else if (task.status === 'success_with_errors') {
      ElMessage.warning(message)
    } else {
      ElMessage.error(message)
    }

    await loadFavorites()
  } catch (error: any) {
    if (!favoritesViewDisposed && error?.message !== 'The page has been left, stop waiting for synchronization results') {
      ElMessage.error(error?.message || 'Failed to query the real-time market results of the stock watch list, please refresh the list later to view')
    }
  }
}

const syncAllRealtime = async () => {
  if (favorites.value.length === 0) {
    ElMessage.warning('No stock watchlists to sync')
    return
  }

  syncRealtimeLoading.value = true
  try {
    const preferredSource = await loadPreferredAvailableSyncSource()
    const realtimeSource = preferredSource || (!isJdyunMode() && availableSyncSources.value.qmt ? 'qmt' : availableSyncSources.value.akshare ? 'akshare' : 'tushare')
    const res = await favoritesApi.syncRealtime(realtimeSource)

    if ((res as any)?.success) {
      ElMessage.success('The real-time market synchronization task of the stock watch list has been submitted and is being executed in the background.')
      void monitorFavoritesRealtimeTask(res.data.task_id)
    } else {
      ElMessage.error((res as any)?.message || 'Sync failed')
    }
  } catch (error: any) {
    console.error('Failed to synchronize real-time quotes:', error)
    ElMessage.error(error.message || 'Synchronization failed, please try again later')
  } finally {
    syncRealtimeLoading.value = false
  }
}

const loadUserTags = async () => {
  try {
    const res = await tagsApi.list()
    const list = (res as any)?.data
    if (Array.isArray(list)) {
      userTags.value = list.map((t: any) => t.name)
      tagColorMap.value = list.reduce((acc: Record<string, string>, t: any) => {
        acc[t.name] = t.color
        return acc
      }, {})
    } else {
      userTags.value = []
      tagColorMap.value = {}
    }
  } catch (error) {
    console.error('Failed to load tags:', error)
    userTags.value = []
    tagColorMap.value = {}
  }
}

// Tag Management Dialog - Script
const tagDialogVisible = ref(false)
const tagLoading = ref(false)
const tagList = ref<any[]>([])
const newTag = ref({ name: '', color: '#409EFF', sort_order: 0 })

const loadTagList = async () => {
  tagLoading.value = true
  try {
    const res = await tagsApi.list()
    tagList.value = (res as any)?.data || []
  } catch (e) {
    console.error('Failed to load tag list:', e)
  } finally {
    tagLoading.value = false
  }
}

const openTagManager = async () => {
  tagDialogVisible.value = true
  await loadTagList()
}

const createTag = async () => {
  if (!newTag.value.name || !newTag.value.name.trim()) {
    ElMessage.warning('Please enter a tag name')
    return
  }
  tagLoading.value = true
  try {
    await tagsApi.create({ ...newTag.value })
    ElMessage.success('Created successfully')
    newTag.value = { name: '', color: '#409EFF', sort_order: 0 }
    await loadTagList()
    await loadUserTags()
  } catch (e: any) {
    console.error('Failed to create label:', e)
    ElMessage.error(e?.message || 'Creation failed')
  } finally {
    tagLoading.value = false
  }
}

const editTag = (row: any) => {
  row._editing = true
  row._name = row.name
  row._color = row.color
  row._sort = row.sort_order
}

const cancelEditTag = (row: any) => {
  row._editing = false
}

const saveTag = async (row: any) => {
  tagLoading.value = true
  try {
    await tagsApi.update(row.id, {
      name: row._name ?? row.name,
      color: row._color ?? row.color,
      sort_order: row._sort ?? row.sort_order,
    })
    ElMessage.success('Saved successfully')
    row._editing = false
    await loadTagList()
    await loadUserTags()
  } catch (e: any) {
    console.error('Failed to save label:', e)
    ElMessage.error(e?.message || 'Save failed')
  } finally {
    tagLoading.value = false
  }
}

const deleteTag = async (row: any) => {
  try {
    await ElMessageBox.confirm(`Confirm to delete tag ${row.name} ?`, 'Delete tag', {
      confirmButtonText: 'OK',
      cancelButtonText: 'Cancel',
      type: 'warning'
    })
    tagLoading.value = true
    await tagsApi.remove(row.id)
    ElMessage.success('Deleted')
    await loadTagList()
    await loadUserTags()
  } catch (e) {
    // User canceled or failed
  } finally {
    tagLoading.value = false
  }
}



const refreshData = () => {
  loadFavorites()
  loadUserTags()
}

const showAddDialog = () => {
  addForm.value = {
    stock_code: '',
    stock_name: '',
    market: 'A shares',
    tags: [],
    notes: ''
  }
  addDialogVisible.value = true
}

// Clear stock code and name when switching market types
const handleMarketChange = () => {
  addForm.value.stock_code = ''
  addForm.value.stock_name = ''
  // Clear validation errors
  if (addFormRef.value) {
    addFormRef.value.clearValidate(['stock_code', 'stock_name'])
  }
}

// Search for stocks (symbol and name supported)
// Note: cannot be declared as async——el-autocomplete The fetch-suggestions require synchronous returns
// void The function signature of async function returns Promise<void> Will trigger vue-tsc type error
const searchStocks = (queryString: string, cb: (results: any[]) => void) => {
  const q = queryString?.trim()
  if (!q || q.length < 1) {
    cb([])
    return
  }
  // The correct path is /api/markets/CN/stocks/search
  request
    .get(`/api/markets/CN/stocks/search`, { params: { q, limit: 20 } })
    .then((res: any) => {
      const stocks = res?.data?.stocks || []
      cb(stocks.map((s: any) => ({
        value: s.code || s.symbol || '',
        code: s.code || s.symbol || '',
        name: s.name || '',
      })))
    })
    .catch((err: any) => {
      console.error('Search failed:', err)
      cb([])
    })
}

// Autocomplete after selecting search results
const handleStockSelect = (item: any) => {
  console.log('Selected items:', item)
  // el-autocomplete Item.value will be automatically filled in to v-model, just fill in name
  addForm.value.stock_name = item.name
  addFormRef.value?.clearValidate()
}

const fetchStockInfo = async () => {
  if (!addForm.value.stock_code) return

  try {
    const symbol = addForm.value.stock_code.trim()
    const market = addForm.value.market

    if (market === 'A shares') {
      // Get basic stock information from the backend
      const res = await ApiClient.get(`/api/stock-data/basic-info/${symbol}`)

      if ((res as any)?.success && (res as any)?.data) {
        const stockInfo = (res as any).data
        // Autofill stock names
        if (stockInfo.name) {
          addForm.value.stock_name = stockInfo.name
          ElMessage.success(`Stock name auto-populated: ${stockInfo.name}`)
        }
      } else {
        ElMessage.warning('The stock information was not found, please enter the stock name manually')
      }
    }
  } catch (error: any) {
    console.error('Failed to obtain stock information:', error)
    ElMessage.warning('Failed to obtain stock information, please enter the stock name manually')
  }
}

const handleAddFavorite = async () => {
  try {
    await addFormRef.value.validate()
    addLoading.value = true
    const payload = { ...addForm.value }
    const res = await favoritesApi.add(payload as any)
    if ((res as any)?.success === false) throw new Error((res as any)?.message || 'Add failed')
    ElMessage.success('Added successfully')
    addDialogVisible.value = false
    await loadFavorites()
  } catch (error: any) {
    console.error('Add to study list failed:', error)
    ElMessage.error(error.message || 'Add failed')
  } finally {
    addLoading.value = false
  }
}

const handleUpdateFavorite = async () => {
  try {
    editLoading.value = true
    const payload = {
      tags: editForm.value.tags,
      notes: editForm.value.notes
    }
    const res = await favoritesApi.update(editForm.value.stock_code, payload as any)
    if ((res as any)?.success === false) throw new Error((res as any)?.message || 'Update failed')
    ElMessage.success('Saved successfully')
    editDialogVisible.value = false
    await loadFavorites()
  } catch (error: any) {
    console.error('Failed to update stock watchlist:', error)
    ElMessage.error(error.message || 'Save failed')
  } finally {
    editLoading.value = false
  }
}


const editFavorite = (row: any) => {
  editForm.value = {
    stock_code: row.stock_code || row.symbol || '',
    stock_name: row.stock_name,
    market: row.market || 'A shares',
    tags: Array.isArray(row.tags) ? [...row.tags] : [],
    notes: row.notes || ''
  }
  editDialogVisible.value = true
}

const analyzeFavorite = (row: any) => {
  router.push({
    name: 'SingleAnalysis',
    query: { stock: row.stock_code, market: normalizeMarketForAnalysis(row.market || 'A shares') }
  })
}

const removeFavorite = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to remove from stock watchlist ${row.stock_name} ?`,
      'Confirm removal',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )
    const res = await favoritesApi.remove(row.stock_code)
    if ((res as any)?.success === false) throw new Error((res as any)?.message || 'Removal failed')
    ElMessage.success('Removed successfully')
    await loadFavorites()
  } catch (e) {
    // User canceled or failed
  }
}

const viewStockDetail = (row: any) => {
  router.push({
    name: 'StockDetail',
    params: { code: String(row.stock_code || '').toUpperCase() }
  })
}

// Handle table selection changes
const handleSelectionChange = (selection: FavoriteItem[]) => {
  selectedStocks.value = selection
}

// Show single stock synchronization dialog box
const showSingleSyncDialog = (row: FavoriteItem) => {
  currentSyncStock.value = {
    stock_code: row.stock_code || row.symbol || '',
    stock_name: row.stock_name || ''
  }
  void loadPreferredAvailableSyncSource().then(preferredSource => {
    if (preferredSource) {
      singleSyncForm.value.dataSource = preferredSource
    }
  })
  singleSyncDialogVisible.value = true
}


const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const isTerminalStockSyncStatus = (status?: string): boolean => {
  return status === 'success' || status === 'success_with_errors' || status === 'failed'
}

const buildSingleSyncTaskMessage = (task: StockSyncTaskStatus, symbol: string): string => {
  const result = task.result as SingleStockSyncResponse | null | undefined
  if (!result) {
    return task.error || task.message || `stocks ${symbol} Sync failed`
  }

  const parts = [`stocks ${symbol} Data synchronization completed`]

  if (result.realtime_sync) {
    parts.push(result.realtime_sync.success ? 'Real-time market synchronization successful' : `Real-time market synchronization failed: ${result.realtime_sync.error || 'unknown error'}`)
  }
  if (result.historical_sync) {
    parts.push(result.historical_sync.success ? `historical data ${result.historical_sync.records || 0} Article` : `Historical data synchronization failed: ${result.historical_sync.error || 'unknown error'}`)
  }
  if (result.financial_sync) {
    parts.push(result.financial_sync.success ? 'Financial data synchronization successful' : `Financial data synchronization failed: ${result.financial_sync.error || 'unknown error'}`)
  }
  if (result.basic_sync) {
    parts.push(result.basic_sync.success ? 'Basic data synchronization successful' : `Basic data synchronization failed: ${result.basic_sync.error || 'unknown error'}`)
  }

  return parts.join('；')
}

const buildBatchSyncTaskMessage = (task: StockSyncTaskStatus, symbols: string[]): string => {
  const result = task.result as BatchStockSyncResponse | null | undefined
  if (!result) {
    return task.error || task.message || 'Batch sync failed'
  }

  const parts = [`Batch synchronization completed (total ${symbols.length} only stocks)`]

  if (result.historical_sync) {
    parts.push(`historical data ${result.historical_sync.success_count}/${result.historical_sync.success_count + result.historical_sync.error_count} Success, total ${result.historical_sync.total_records} Article`)
  }
  if (result.financial_sync) {
    parts.push(`financial data ${result.financial_sync.success_count}/${result.financial_sync.total_symbols} success`)
  }
  if (result.basic_sync) {
    parts.push(`Basic data ${result.basic_sync.success_count}/${result.basic_sync.total_symbols} success`)
  }

  return parts.join('；')
}

const waitForStockSyncTask = async (taskId: string): Promise<StockSyncTaskStatus> => {
  for (let attempt = 0; attempt < STOCK_SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
    if (favoritesViewDisposed) {
      throw new Error('The page has been left, stop waiting for synchronization results')
    }

    const res = await stockSyncApi.getTaskStatus(taskId)
    if (res.success && isTerminalStockSyncStatus(res.data.status)) {
      return res.data
    }

    await sleep(STOCK_SYNC_POLL_INTERVAL_MS)
  }

  throw new Error('The synchronization task execution timed out, please refresh the list later to view the results.')
}

const monitorSingleSyncTask = async (taskId: string, symbol: string) => {
  try {
    const task = await waitForStockSyncTask(taskId)
    if (favoritesViewDisposed) return

    const message = buildSingleSyncTaskMessage(task, symbol)
    if (task.status === 'success') {
      ElMessage.success(message)
    } else if (task.status === 'success_with_errors') {
      ElMessage.warning(message)
    } else {
      ElMessage.error(message)
    }

    await loadFavorites()
  } catch (error: any) {
    if (!favoritesViewDisposed && error?.message !== 'The page has been left, stop waiting for synchronization results') {
      ElMessage.error(error?.message || 'Synchronization result query failed, please refresh the list later to view')
    }
  }
}

const monitorBatchSyncTask = async (taskId: string, symbols: string[]) => {
  try {
    const task = await waitForStockSyncTask(taskId)
    if (favoritesViewDisposed) return

    const message = buildBatchSyncTaskMessage(task, symbols)
    if (task.status === 'success') {
      ElMessage.success(message)
    } else if (task.status === 'success_with_errors') {
      ElMessage.warning(message)
    } else {
      ElMessage.error(message)
    }

    await loadFavorites()
  } catch (error: any) {
    if (!favoritesViewDisposed && error?.message !== 'The page has been left, stop waiting for synchronization results') {
      ElMessage.error(error?.message || 'Batch synchronization result query failed, please refresh the list later to view')
    }
  }
}
// Perform a single stock sync
const handleSingleSync = async () => {
  if (singleSyncForm.value.syncTypes.length === 0) {
    ElMessage.warning('Please select at least one sync content')
    return
  }

  singleSyncLoading.value = true
  try {
    const res = await stockSyncApi.syncSingle({
      symbol: currentSyncStock.value.stock_code,
      sync_realtime: singleSyncForm.value.syncTypes.includes('realtime'),
      sync_historical: singleSyncForm.value.syncTypes.includes('historical'),
      sync_financial: singleSyncForm.value.syncTypes.includes('financial'),
      data_source: singleSyncForm.value.dataSource,
      days: singleSyncForm.value.days
    })

    if (res.success) {
      ElMessage.success(`stocks ${currentSyncStock.value.stock_code} The synchronization task has been submitted and is being executed in the background`)
      singleSyncDialogVisible.value = false
      void monitorSingleSyncTask(res.data.task_id, currentSyncStock.value.stock_code)
    } else {
      ElMessage.error(res.message || 'Sync failed')
    }
  } catch (error: any) {
    console.error('Sync failed:', error)
    ElMessage.error(error.message || 'Synchronization failed, please try again later')
  } finally {
    singleSyncLoading.value = false
  }
}

// Show batch sync dialog box
const showBatchSyncDialog = async () => {
  const applyPreferredSource = async () => {
    const preferredSource = await loadPreferredAvailableSyncSource()
    if (preferredSource) {
      batchSyncForm.value.dataSource = preferredSource
    }
  }

  if (selectedStocks.value.length === 0) {
    // Prompt user to select stocks or sync all
    try {
      await ElMessageBox.confirm(
        'Please select the stocks you want to sync first, or select"sync all"To simultaneously research all A-share stocks in the list.',
        'Tips',
        {
          confirmButtonText: 'sync all',
          cancelButtonText: 'Cancel',
          type: 'info',
          distinguishCancelAndClose: true
        }
      )
      // User selection"sync all": Simultaneously research all A-share stocks in the list
      const aStocks = favorites.value.filter(item => item.market === 'A shares')
      if (aStocks.length === 0) {
        ElMessage.warning('There are no A-share stocks in the research list that can be synchronized')
        return
      }
      syncAllStocks.value = true  // Mark as sync all
      await applyPreferredSource()
      batchSyncDialogVisible.value = true
    } catch (action: any) {
      // User selection"Cancel", Do nothing
      if (action === 'cancel') {
        return
      }
    }
  } else {
    syncAllStocks.value = false  // Mark as checked for sync
    await applyPreferredSource()
    batchSyncDialogVisible.value = true
  }
}

// Perform batch synchronization
const handleBatchSync = async () => {
  if (batchSyncForm.value.syncTypes.length === 0) {
    ElMessage.warning('Please select at least one sync content')
    return
  }

  // Determine which stocks to sync based on syncAllStocks flag
  let symbols: string[]
  if (syncAllStocks.value) {
    // Synchronize all: use all A-share stocks
    const aStocks = favorites.value.filter(item => item.market === 'A shares')
    if (aStocks.length === 0) {
      ElMessage.warning('No A-share stocks can be synchronized')
      return
    }
    symbols = aStocks.map(stock => stock.stock_code || stock.symbol || '').filter((symbol): symbol is string => Boolean(symbol))
  } else {
    // Selected Sync: Use selected stocks
    if (selectedStocks.value.length === 0) {
      ElMessage.warning('Please select the stocks to be synchronized first')
      return
    }
    symbols = selectedStocks.value.map(stock => stock.stock_code || stock.symbol || '').filter((symbol): symbol is string => Boolean(symbol))
  }

  batchSyncLoading.value = true
  try {

    const res = await stockSyncApi.syncBatch({
      symbols,
      sync_historical: batchSyncForm.value.syncTypes.includes('historical'),
      sync_financial: batchSyncForm.value.syncTypes.includes('financial'),
      data_source: batchSyncForm.value.dataSource,
      days: batchSyncForm.value.days
    })

    if (res.success) {
      ElMessage.success(`Batch synchronization tasks have been submitted (a total of ${symbols.length} only stocks), executing in the background`)
      batchSyncDialogVisible.value = false
      syncAllStocks.value = false  // Reset all sync flags
      void monitorBatchSyncTask(res.data.task_id, symbols)
    } else {
      ElMessage.error(res.message || 'Batch sync failed')
    }
  } catch (error: any) {
    console.error('Batch sync failed:', error)
    ElMessage.error(error.message || 'Batch synchronization failed, please try again later')
  } finally {
    batchSyncLoading.value = false
  }
}

const getChangeClass = (changePercent: number) => {
  if (changePercent > 0) return 'text-red'
  if (changePercent < 0) return 'text-green'
  return ''
}


const formatPrice = (value: any): string => {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

const formatPercent = (value: any): string => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// life cycle
onMounted(() => {
  const auth = useAuthStore()
  if (auth.isAuthenticated) {
    loadFavorites()
    loadUserTags()
  }
})

onUnmounted(() => {
  favoritesViewDisposed = true
})
</script>

<style lang="scss" scoped>
.favorites {
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

  .action-card {
    margin-bottom: 24px;

    .action-buttons {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }

  /* Color option style */
  .color-dot {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 1px solid #ddd;
    border-radius: 2px;
    margin-left: 8px;
    vertical-align: middle;
  }
  .color-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }
  .color-dot-preview {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 1px solid #ddd;
    border-radius: 2px;
    margin-left: 6px;
    vertical-align: middle;
  }

  .favorites-list-card {
    .empty-state {
      padding: 40px;
      text-align: center;
    }

    .text-red {
      color: #f56c6c;
    }

    .text-green {
      color: #67c23a;
    }
  }
}
</style>
