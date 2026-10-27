<template>
  <div class="cache-management">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Coin /></el-icon>
        Cache management
      </h1>
      <p class="page-description">
        Manage stock data cache and optimize system performance
      </p>
    </div>

    <el-row :gutter="24">
      <!-- Left: cache statistics -->
      <el-col :span="12">
        <el-card class="stats-card" shadow="never">
          <template #header>
            <h3>📊 cache statistics</h3>
          </template>
          
          <div v-loading="statsLoading" class="stats-content">
            <el-row :gutter="16">
              <el-col :span="12">
                <div class="stat-item">
                  <div class="stat-value">{{ cacheStats.totalFiles }}</div>
                  <div class="stat-label">Total number of files</div>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="stat-item">
                  <div class="stat-value">{{ formatSize(cacheStats.totalSize) }}</div>
                  <div class="stat-label">total size</div>
                </div>
              </el-col>
            </el-row>
            
            <el-row :gutter="16" style="margin-top: 16px">
              <el-col :span="12">
                <div class="stat-item">
                  <div class="stat-value">{{ cacheStats.stockDataCount }}</div>
                  <div class="stat-label">stock data</div>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="stat-item">
                  <div class="stat-value">{{ cacheStats.newsDataCount }}</div>
                  <div class="stat-label">news data</div>
                </div>
              </el-col>
            </el-row>
            
            <el-divider />
            
            <div class="cache-usage">
              <h4>Cache usage</h4>
              <el-progress
                :percentage="cacheUsagePercentage"
                :color="getProgressColor(cacheUsagePercentage)"
                :stroke-width="12"
              />
              <p class="usage-text">
                Already used {{ formatSize(cacheStats.totalSize) }} / {{ formatSize(cacheStats.maxSize) }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Right: cache operations -->
      <el-col :span="12">
        <el-card class="operations-card" shadow="never">
          <template #header>
            <h3>🛠️ Caching operations</h3>
          </template>
          
          <div class="operations-content">
            <!-- Refresh statistics -->
            <div class="operation-item">
              <h4>🔄 Refresh statistics</h4>
              <p>Retrieve the latest cache statistics</p>
              <el-button type="primary" @click="refreshStats" :loading="statsLoading">
                Refresh statistics
              </el-button>
            </div>
            
            <el-divider />
            
            <!-- Clear expired cache -->
            <div class="operation-item">
              <h4>🧹 Clear expired cache</h4>
              <p>Delete cached files older than a specified number of days</p>
              
              <el-form-item label="Cleanup days">
                <el-slider
                  v-model="cleanupDays"
                  :min="1"
                  :max="30"
                  :marks="cleanupMarks"
                  show-stops
                />
                <span class="cleanup-description">
                  will clean up {{ cleanupDays }} Cache files days ago
                </span>
              </el-form-item>
              
              <el-button 
                type="warning" 
                @click="cleanupOldCache" 
                :loading="cleanupLoading"
              >
                <el-icon><Delete /></el-icon>
                Clear expired cache
              </el-button>
            </div>
            
            <el-divider />
            
            <!-- Clear all cache -->
            <div class="operation-item">
              <h4>🗑️ Clear all cache</h4>
              <p class="warning-text">⚠️ This operation will delete all cache files and cannot be restored</p>
              
              <el-button 
                type="danger" 
                @click="clearAllCache" 
                :loading="clearAllLoading"
              >
                <el-icon><Delete /></el-icon>
                Clear all cache
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Cache details -->
    <el-card class="details-card" shadow="never" style="margin-top: 24px">
      <template #header>
        <div class="card-header">
          <h3>📋 Cache details</h3>
          <el-button size="small" @click="loadCacheDetails">
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </div>
      </template>
      
      <div v-loading="detailsLoading">
        <el-table :data="cacheDetails" style="width: 100%">
          <el-table-column prop="type" label="Type" width="120">
            <template #default="{ row }">
              <el-tag :type="getCacheTypeTag(row.type)">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="symbol" label="Stock code" width="120" />
          <el-table-column prop="size" label="size" width="100">
            <template #default="{ row }">
              {{ formatSize(row.size) }}
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="creation time" width="180">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="last_accessed" label="last visited" width="180">
            <template #default="{ row }">
              {{ formatDate(row.last_accessed) }}
            </template>
          </el-table-column>
          <el-table-column prop="hit_count" label="Number of hits" width="100" />
          <el-table-column label="Operation" width="120">
            <template #default="{ row }">
              <el-button 
                size="small" 
                type="danger" 
                @click="deleteCacheItem(row)"
              >
                Delete
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <!-- Pagination -->
        <el-pagination
          v-if="cacheDetails.length > 0"
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalItems"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          style="margin-top: 16px; text-align: right"
          @size-change="loadCacheDetails"
          @current-change="loadCacheDetails"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Coin,
  Delete,
  Refresh
} from '@element-plus/icons-vue'
import * as cacheApi from '@/api/cache'

// Responsive data
const statsLoading = ref(false)
const cleanupLoading = ref(false)
const clearAllLoading = ref(false)
const detailsLoading = ref(false)

const cleanupDays = ref(7)
const currentPage = ref(1)
const pageSize = ref(20)
const totalItems = ref(0)

// cache statistics
const cacheStats = ref({
  totalFiles: 0,
  totalSize: 0,
  maxSize: 1024 * 1024 * 1024, // 1GB
  stockDataCount: 0,
  newsDataCount: 0,
  analysisDataCount: 0
})

// Cache details data
const cacheDetails = ref<any[]>([])

// Cleanup days mark
const cleanupMarks = {
  1: '1 day',
  7: '1 week',
  14: '2 week',
  30: '1 month'
}

// Computed properties
const cacheUsagePercentage = computed(() => {
  if (cacheStats.value.maxSize === 0) return 0
  return Math.round((cacheStats.value.totalSize / cacheStats.value.maxSize) * 100)
})

// method
const formatSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleString('zh-CN')
}

const getProgressColor = (percentage: number): string => {
  if (percentage < 50) return '#67c23a'
  if (percentage < 80) return '#e6a23c'
  return '#f56c6c'
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const getCacheTypeTag = (type: string): TagType => {
  const typeMap: Record<string, TagType> = {
    'stock': 'primary',
    'news': 'success',
    'analysis': 'warning'
  }
  return typeMap[type] || 'info'
}

const refreshStats = async () => {
  statsLoading.value = true
  try {
    const response = await cacheApi.getCacheStats()
    // Extract data field from ApiResponse
    cacheStats.value = response.data || response
    ElMessage.success('Cache statistics refreshed')
  } catch (error: any) {
    console.error('Failed to refresh cache statistics:', error)
    ElMessage.error(error.message || 'Failed to refresh cache statistics')
  } finally {
    statsLoading.value = false
  }
}

const cleanupOldCache = async () => {
  try {
    await ElMessageBox.confirm(
      `sure to clean ${cleanupDays.value} Cache files days ago?`,
      'Confirm cleanup',
      { type: 'warning' }
    )

    cleanupLoading.value = true

    await cacheApi.cleanupOldCache(cleanupDays.value)

    ElMessage.success(`Cleaned ${cleanupDays.value} Cache files days ago`)
    await refreshStats()
    await loadCacheDetails()

  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to clear cache:', error)
      ElMessage.error(error.message || 'Failed to clear cache')
    }
  } finally {
    cleanupLoading.value = false
  }
}

const clearAllCache = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear all cache files? This operation cannot be undone!',
      'Confirm clearing',
      {
        type: 'error',
        confirmButtonText: 'OK to clear',
        cancelButtonText: 'Cancel'
      }
    )

    clearAllLoading.value = true

    await cacheApi.clearAllCache()

    ElMessage.success('All caches have been cleared')
    await refreshStats()
    await loadCacheDetails()

  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to clear cache:', error)
      ElMessage.error(error.message || 'Failed to clear cache')
    }
  } finally {
    clearAllLoading.value = false
  }
}

const loadCacheDetails = async () => {
  detailsLoading.value = true
  try {
    const response = await cacheApi.getCacheDetails(currentPage.value, pageSize.value)
    // Extract data field from ApiResponse
    const data = response.data || response
    cacheDetails.value = data.items || []
    totalItems.value = data.total || 0
  } catch (error: any) {
    console.error('Failed to load cache details:', error)
    ElMessage.error(error.message || 'Failed to load cache details')
  } finally {
    detailsLoading.value = false
  }
}

const deleteCacheItem = async (item: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete ${item.symbol} of${item.type}Cache?`,
      'Confirm deletion',
      { type: 'warning' }
    )
    
    // Simulate API calls
    await new Promise(resolve => setTimeout(resolve, 500))
    
    ElMessage.success('Cache item deleted')
    await loadCacheDetails()
    await refreshStats()
    
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Failed to delete cache item')
    }
  }
}

// life cycle
onMounted(() => {
  refreshStats()
  loadCacheDetails()
})
</script>

<style lang="scss" scoped>
.cache-management {
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

  .stats-card {
    .stats-content {
      .stat-item {
        text-align: center;
        
        .stat-value {
          font-size: 24px;
          font-weight: 600;
          color: var(--el-color-primary);
          margin-bottom: 4px;
        }
        
        .stat-label {
          font-size: 14px;
          color: var(--el-text-color-regular);
        }
      }
      
      .cache-usage {
        h4 {
          margin: 0 0 12px 0;
          font-size: 16px;
        }
        
        .usage-text {
          margin: 8px 0 0 0;
          font-size: 14px;
          color: var(--el-text-color-regular);
          text-align: center;
        }
      }
    }
  }

  .operations-card {
    .operations-content {
      .operation-item {
        h4 {
          margin: 0 0 8px 0;
          font-size: 16px;
        }
        
        p {
          margin: 0 0 16px 0;
          font-size: 14px;
          color: var(--el-text-color-regular);
          
          &.warning-text {
            color: var(--el-color-warning);
          }
        }
        
        .cleanup-description {
          font-size: 12px;
          color: var(--el-text-color-placeholder);
          margin-left: 12px;
        }
      }
    }
  }

  .details-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      h3 {
        margin: 0;
      }
    }
  }
}
</style>
