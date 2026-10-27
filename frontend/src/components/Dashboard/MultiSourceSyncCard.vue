<template>
  <div class="multi-source-sync-card">
    <el-card class="sync-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Connection /></el-icon>
            <span class="header-title">Synchronization of multiple data sources</span>
          </div>
          <div class="header-right">
            <el-button 
              type="primary" 
              size="small" 
              link
              @click="goToSyncPage"
            >
              management
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading" class="card-content">
        <!-- Sync status -->
        <div class="sync-status-section">
          <div class="status-display">
            <el-tag 
              :type="getStatusType(syncStatus?.status)"
              size="large"
              class="status-tag"
            >
              {{ getStatusText(syncStatus?.status) }}
            </el-tag>
            
            <div v-if="syncStatus?.status === 'running'" class="progress-display">
              <el-progress 
                :percentage="getProgress()"
                :status="syncStatus.errors > 0 ? 'warning' : 'success'"
                :stroke-width="6"
                :show-text="false"
              />
              <div class="progress-text">
                {{ syncStatus.total > 0 ? `${syncStatus.updated + syncStatus.inserted}/${syncStatus.total}` : 'Synchronizing...' }}
              </div>
            </div>
          </div>
        </div>

        <!-- Data source status -->
        <div class="sources-status-section">
          <div class="sources-header">
            <span class="sources-title">Data source status</span>
            <el-button 
              size="small" 
              type="primary" 
              link
              :loading="refreshing"
              @click="refreshStatus"
            >
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          
          <div class="sources-list">
            <div 
              v-for="source in dataSources" 
              :key="source.name"
              class="source-item"
              :class="{ 'available': source.available }"
            >
              <div class="source-info">
                <span class="source-name">{{ source.name.toUpperCase() }}</span>
                <el-icon 
                  :class="source.available ? 'status-success' : 'status-error'"
                >
                  <component :is="source.available ? 'SuccessFilled' : 'CircleCloseFilled'" />
                </el-icon>
              </div>
              <div class="source-priority">priority: {{ source.priority }}</div>
            </div>
          </div>
        </div>

        <!-- Quick operation -->
        <div class="quick-actions-section">
          <el-button
            type="primary"
            size="small"
            :loading="syncing"
            :disabled="isSyncInProgress(syncStatus?.status)"
            @click="quickSync"
            style="width: 100%"
          >
            <el-icon><Refresh /></el-icon>
            {{ isSyncInProgress(syncStatus?.status) ? 'Synchronizing...' : 'Quick sync' }}
          </el-button>
        </div>

        <!-- Recently synced information -->
        <div v-if="syncStatus && syncStatus.status !== 'never_run'" class="last-sync-section">
          <div class="last-sync-info">
            <div class="sync-stats">
              <span class="stat-item">total: {{ syncStatus.total }}</span>
              <span class="stat-item success">update: {{ syncStatus.updated }}</span>
              <span class="stat-item danger">Error: {{ syncStatus.errors }}</span>
            </div>
            <div v-if="syncStatus.finished_at" class="sync-time">
              {{ formatLastSyncTime(syncStatus.finished_at) }}
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  Connection, 
  ArrowRight, 
  Refresh
} from '@element-plus/icons-vue'
import { 
  getSyncStatus, 
  getDataSourcesStatus, 
  runStockBasicsSync,
  type SyncStatus, 
  type DataSourceStatus 
} from '@/api/sync'

// routing
const router = useRouter()

// Responsive data
const loading = ref(false)
const refreshing = ref(false)
const syncing = ref(false)
const syncStatus = ref<SyncStatus | null>(null)
const dataSources = ref<DataSourceStatus[]>([])
const refreshTimer = ref<NodeJS.Timeout | null>(null)

const isSyncInProgress = (status?: string) => ['queued', 'running'].includes(status || '')

// Get sync status
const fetchSyncStatus = async () => {
  try {
    const response = await getSyncStatus()
    if (response.success) {
      syncStatus.value = response.data
    }
  } catch (err: any) {
    console.error('Failed to get sync status:', err)
  }
}

// Get data source status
const fetchDataSources = async () => {
  try {
    const response = await getDataSourcesStatus()
    if (response.success) {
      dataSources.value = response.data
        .sort((a, b) => b.priority - a.priority) // Reverse order: highest priority first
        .slice(0, 3) // Only show the first 3 data sources
    }
  } catch (err: any) {
    console.error('Failed to get data source status:', err)
  }
}

// refresh status
const refreshStatus = async () => {
  refreshing.value = true
  await Promise.all([
    fetchSyncStatus(),
    fetchDataSources()
  ])
  refreshing.value = false
}

// Quick sync
const quickSync = async () => {
  try {
    syncing.value = true
    
    const response = await runStockBasicsSync()
    if (response.success) {
      syncStatus.value = response.data
      if (response.data.status === 'queued') {
        ElMessage.success(response.data.message || 'The synchronization task has been submitted and the background is starting, please wait.')
      } else {
        ElMessage.success('Synchronization task started')
      }
      startStatusPolling()
    } else {
      ElMessage.error(`Sync start failed: ${response.message}`)
    }
  } catch (err: any) {
    console.error('Failed to start sync:', err)
    ElMessage.error(`Sync start failed: ${err.message}`)
  } finally {
    syncing.value = false
  }
}

// Jump to the synchronization management page
const goToSyncPage = () => {
  router.push('/settings/sync')
}

// Start status polling
const startStatusPolling = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
  }
  
  refreshTimer.value = setInterval(async () => {
    await fetchSyncStatus()
    
    // If synchronization is complete, stop polling
    if (syncStatus.value?.status && !isSyncInProgress(syncStatus.value.status)) {
      stopStatusPolling()
    }
  }, 3000)
}

// Stop status polling
const stopStatusPolling = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

// Get status type
const getStatusType = (status?: SyncStatus['status'] | string): 'success' | 'info' | 'warning' | 'danger' => {
  const typeMap: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    idle: 'info',
    queued: 'warning',
    running: 'warning',
    success: 'success',
    success_with_errors: 'warning',
    failed: 'danger',
    never_run: 'info'
  }
  return typeMap[status ?? 'never_run'] ?? 'info'
}

// Get status text
const getStatusText = (status?: SyncStatus['status'] | string) => {
  const textMap: Record<string, string> = {
    idle: 'free',
    queued: 'Starting in the background',
    running: 'Running',
    success: 'success',
    success_with_errors: 'Partially successful',
    failed: 'failed',
    never_run: 'Not running'
  }
  return textMap[status ?? 'never_run'] ?? 'unknown'
}

// Get progress percentage
const getProgress = () => {
  if (!syncStatus.value || syncStatus.value.total === 0) return 0
  return Math.round(((syncStatus.value.inserted + syncStatus.value.updated) / syncStatus.value.total) * 100)
}

// Format last sync time
const formatLastSyncTime = (timeStr: string) => {
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  if (diff < 60000) {
    return 'just finished'
  } else if (diff < 3600000) {
    return `${Math.floor(diff / 60000)}minutes ago`
  } else if (diff < 86400000) {
    return `${Math.floor(diff / 3600000)}hours ago`
  } else {
    return date.toLocaleDateString('zh-CN')
  }
}

// Component mounting
onMounted(async () => {
  loading.value = true
  await Promise.all([
    fetchSyncStatus(),
    fetchDataSources()
  ])
  loading.value = false
  
  // If synchronizing, start polling
  if (isSyncInProgress(syncStatus.value?.status)) {
    startStatusPolling()
  }
})

// Component uninstallation
onUnmounted(() => {
  stopStatusPolling()
})
</script>

<style scoped lang="scss">
.multi-source-sync-card {
  .sync-card {
    height: 100%;
    
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .header-left {
        display: flex;
        align-items: center;
        
        .header-icon {
          margin-right: 8px;
          color: var(--el-color-primary);
        }
        
        .header-title {
          font-weight: 600;
          font-size: 16px;
        }
      }
    }
  }

  .card-content {
    .sync-status-section {
      margin-bottom: 16px;
      
      .status-display {
        .status-tag {
          margin-bottom: 8px;
        }
        
        .progress-display {
          .progress-text {
            margin-top: 4px;
            font-size: 12px;
            color: var(--el-text-color-secondary);
            text-align: center;
          }
        }
      }
    }

    .sources-status-section {
      margin-bottom: 16px;
      
      .sources-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
        
        .sources-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--el-text-color-primary);
        }
      }
      
      .sources-list {
        .source-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 8px;
          margin-bottom: 4px;
          border-radius: 4px;
          background-color: var(--el-fill-color-lighter);
          
          &.available {
            background-color: var(--el-color-success-light-9);
          }
          
          .source-info {
            display: flex;
            align-items: center;
            gap: 6px;
            
            .source-name {
              font-size: 12px;
              font-weight: 500;
            }
            
            .status-success {
              color: var(--el-color-success);
              font-size: 12px;
            }
            
            .status-error {
              color: var(--el-color-danger);
              font-size: 12px;
            }
          }
          
          .source-priority {
            font-size: 11px;
            color: var(--el-text-color-secondary);
          }
        }
      }
    }

    .quick-actions-section {
      margin-bottom: 16px;
    }

    .last-sync-section {
      .last-sync-info {
        .sync-stats {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
          
          .stat-item {
            font-size: 12px;
            
            &.success { color: var(--el-color-success); }
            &.danger { color: var(--el-color-danger); }
          }
        }
        
        .sync-time {
          font-size: 11px;
          color: var(--el-text-color-secondary);
          text-align: center;
        }
      }
    }
  }
}
</style>
