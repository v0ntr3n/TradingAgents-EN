<template>
  <div class="sync-history">
    <el-card class="history-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon class="header-icon"><Clock /></el-icon>
          <span class="header-title">Sync history</span>
          <el-button
            type="primary"
            size="small"
            :loading="loading"
            @click="refreshHistory"
          >
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </div>
      </template>

      <div v-loading="loading" class="history-content">
        <div v-if="error" class="error-message">
          <el-alert
            :title="error"
            type="error"
            :closable="false"
            show-icon
          />
        </div>

        <div v-else-if="historyList.length > 0" class="history-list">
          <el-timeline>
            <el-timeline-item
              v-for="(item, index) in historyList"
              :key="index"
              :timestamp="formatTime(item.finished_at || item.started_at)"
              :type="getTimelineType(item.status)"
              :icon="getTimelineIcon(item.status)"
              placement="top"
            >
              <div class="history-item">
                <div class="item-header">
                  <el-tag 
                    :type="getStatusType(item.status)"
                    size="small"
                    class="status-tag"
                  >
                    {{ getStatusText(item.status) }}
                  </el-tag>
                  <span class="job-name">{{ item.job }}</span>
                </div>
                
                <div class="item-stats">
                  <div class="stats-row">
                    <span class="stat-item">total: {{ item.total }}</span>
                    <span class="stat-item success">New: {{ item.inserted }}</span>
                    <span class="stat-item primary">update: {{ item.updated }}</span>
                    <span class="stat-item danger">Error: {{ item.errors }}</span>
                  </div>
                  
                  <div v-if="item.data_sources_used?.length" class="sources-row">
                    <span class="sources-label">data source:</span>
                    <el-tag 
                      v-for="source in item.data_sources_used" 
                      :key="source"
                      size="small"
                      type="info"
                      class="source-tag"
                    >
                      {{ source }}
                    </el-tag>
                  </div>
                  
                  <div v-if="item.last_trade_date" class="trade-date-row">
                    <span class="trade-date-label">transaction date:</span>
                    <span class="trade-date-value">{{ item.last_trade_date }}</span>
                  </div>
                </div>
                
                <div v-if="item.message" class="item-message">
                  <el-alert
                    :title="item.message"
                    :type="item.status === 'failed' ? 'error' : 'warning'"
                    :closable="false"
                    size="small"
                  />
                </div>
                
                <div class="item-duration">
                  <span class="duration-text">
                    {{ getDuration(item.started_at, item.finished_at) }}
                  </span>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
          
          <!-- load more -->
          <div v-if="hasMore" class="load-more">
            <el-button 
              type="primary" 
              link 
              :loading="loadingMore"
              @click="loadMore"
            >
              load more
            </el-button>
          </div>
        </div>

        <div v-else class="empty-state">
          <el-empty description="No sync history yet" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Clock, Refresh, SuccessFilled, CircleCloseFilled, Warning } from '@element-plus/icons-vue'
import { getSyncHistory, type SyncStatus } from '@/api/sync'

// Responsive data
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const historyList = ref<SyncStatus[]>([])
const hasMore = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)

// Get sync history
const fetchHistory = async (page = 1) => {
  try {
    if (page === 1) {
      loading.value = true
      historyList.value = []
      currentPage.value = 1
    } else {
      loadingMore.value = true
    }

    error.value = ''

    console.log(`📚 Get synchronization history, page number: ${page}`)

    // Call the real history API
    const response = await getSyncHistory({
      page,
      page_size: pageSize.value
    })

    if (response.success) {
      const { records, total, has_more } = response.data

      console.log(`📊 Get ${records.length} historical records, total: ${total}`)

      if (page === 1) {
        historyList.value = records
      } else {
        historyList.value.push(...records)
      }

      hasMore.value = has_more

      // If there is no history, display empty status
      if (records.length === 0 && page === 1) {
        console.log('📝 No sync history yet')
      }
    } else {
      throw new Error(response.message || 'Failed to get history')
    }
  } catch (err: any) {
    console.error('Failed to obtain synchronization history:', err)
    error.value = err.message || 'Network request failed'

    // If the first page fails to load, an error message is displayed.
    if (page === 1) {
      ElMessage.error(`Failed to obtain synchronization history: ${err.message}`)
    }
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

// load more
const loadMore = async () => {
  currentPage.value++
  await fetchHistory(currentPage.value)
}

// Refresh history
const refreshHistory = async () => {
  console.log('🔄 Manually refresh sync history')
  await fetchHistory(1)
  ElMessage.success('Sync history has been refreshed')
}

// Get status type
const getStatusType = (status: string): 'success' | 'warning' | 'info' | 'danger' => {
  const typeMap: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    idle: 'info',
    running: 'warning',
    success: 'success',
    success_with_errors: 'warning',
    failed: 'danger',
    never_run: 'info'
  }
  return typeMap[status] || 'info'
}

// Get status text
const getStatusText = (status: string) => {
  const textMap: Record<string, string> = {
    idle: 'free',
    running: 'Running',
    success: 'success',
    success_with_errors: 'Partially successful',
    failed: 'failed',
    never_run: 'Not running'
  }
  return textMap[status] || 'unknown'
}

// Get timeline type
const getTimelineType = (status: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' => {
  const typeMap: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    success: 'success',
    success_with_errors: 'warning',
    failed: 'danger',
    running: 'primary'
  }
  return typeMap[status] || 'info'
}

// Get timeline icon
const getTimelineIcon = (status: string) => {
  const iconMap: Record<string, any> = {
    success: SuccessFilled,
    success_with_errors: Warning,
    failed: CircleCloseFilled,
    running: Clock
  }
  return iconMap[status] || Clock
}

// Format time
const formatTime = (timeStr?: string) => {
  if (!timeStr) return ''
  
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  // if it were today
  if (diff < 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString('zh-CN', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    })
  }
  
  // if it was yesterday or earlier
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Calculate duration
const getDuration = (startTime?: string, endTime?: string) => {
  if (!startTime || !endTime) return ''
  
  const start = new Date(startTime)
  const end = new Date(endTime)
  const duration = end.getTime() - start.getTime()
  
  if (duration < 1000) {
    return `${duration}ms`
  } else if (duration < 60000) {
    return `${Math.round(duration / 1000)}s`
  } else {
    const minutes = Math.floor(duration / 60000)
    const seconds = Math.round((duration % 60000) / 1000)
    return `${minutes}m ${seconds}s`
  }
}

// Get data when component is mounted
onMounted(() => {
  fetchHistory()
})
</script>

<style scoped lang="scss">
.sync-history {
  .history-card {
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .header-icon {
        margin-right: 8px;
        color: var(--el-color-primary);
      }
      
      .header-title {
        font-weight: 600;
        flex: 1;
      }
    }
  }

  .history-content {
    min-height: 300px;
    max-height: 600px;
    overflow-y: auto;
  }

  .history-list {
    .history-item {
      .item-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        
        .job-name {
          font-weight: 500;
          color: var(--el-text-color-regular);
        }
      }
      
      .item-stats {
        margin-bottom: 8px;
        
        .stats-row {
          display: flex;
          gap: 16px;
          margin-bottom: 4px;
          
          .stat-item {
            font-size: 12px;
            
            &.success { color: var(--el-color-success); }
            &.primary { color: var(--el-color-primary); }
            &.danger { color: var(--el-color-danger); }
          }
        }
        
        .sources-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
          
          .sources-label {
            font-size: 12px;
            color: var(--el-text-color-secondary);
          }
          
          .source-tag {
            font-size: 10px;
          }
        }
        
        .trade-date-row {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          
          .trade-date-label {
            margin-right: 4px;
          }
        }
      }
      
      .item-message {
        margin-bottom: 8px;
      }
      
      .item-duration {
        .duration-text {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }
    }
    
    .load-more {
      text-align: center;
      padding: 16px 0;
    }
  }

  .error-message {
    margin-bottom: 16px;
  }

  .empty-state {
    text-align: center;
    padding: 40px 0;
  }
}

// Customize timeline style
:deep(.el-timeline-item__timestamp) {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

:deep(.el-timeline-item__wrapper) {
  padding-left: 28px;
}

:deep(.el-timeline-item__tail) {
  border-left: 2px solid var(--el-border-color-lighter);
}
</style>
