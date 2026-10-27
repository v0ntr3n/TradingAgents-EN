<template>
  <div class="sync-control">
    <el-card class="control-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon class="header-icon"><Refresh /></el-icon>
          <span class="header-title">Basic information synchronization</span>
        </div>
      </template>

      <div class="control-content">
        <!-- Current sync status -->
        <div class="sync-status-section">
          <h4 class="section-title">Current status</h4>
          <div class="status-display">
            <el-tag 
              :type="getStatusType(syncStatus?.status)"
              size="large"
              class="status-tag"
            >
              {{ getStatusText(syncStatus?.status) }}
            </el-tag>
            <div v-if="syncStatus?.status === 'running'" class="progress-info">
              <el-progress 
                :percentage="getProgress()"
                :status="syncStatus.errors > 0 ? 'warning' : 'success'"
                :stroke-width="8"
              />
              <div class="progress-text">
                Synchronizing... {{ syncStatus.total > 0 ? `${syncStatus.updated + syncStatus.inserted}/${syncStatus.total}` : '' }}
              </div>
            </div>
            <div v-else-if="syncStatus?.status === 'queued'" class="progress-text">
              The synchronization task has been submitted and the background is starting. Please wait and start automatically.
            </div>
          </div>
        </div>

        <!-- Synchronization statistics -->
        <div v-if="syncStatus && syncStatus.status !== 'never_run'" class="sync-stats-section">
          <h4 class="section-title">Synchronization statistics</h4>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-value">{{ syncStatus.total }}</div>
              <div class="stat-label">total</div>
            </div>
            <div class="stat-item">
              <div class="stat-value success">{{ syncStatus.inserted }}</div>
              <div class="stat-label">New</div>
            </div>
            <div class="stat-item">
              <div class="stat-value primary">{{ syncStatus.updated }}</div>
              <div class="stat-label">update</div>
            </div>
            <div class="stat-item">
              <div class="stat-value danger">{{ syncStatus.errors }}</div>
              <div class="stat-label">Error</div>
            </div>
          </div>
          
          <!-- Data source used -->
          <div v-if="syncStatus.data_sources_used?.length" class="sources-used">
            <div class="sources-label">Data source used:</div>
            <div class="sources-tags">
              <el-tag
                v-for="source in syncStatus.data_sources_used"
                :key="source"
                size="small"
                type="info"
              >
                {{ source }}
              </el-tag>
            </div>
          </div>

          <!-- Last sync time -->
          <div v-if="syncStatus.finished_at" class="sync-time">
            <div class="time-label">completion time:</div>
            <div class="time-value">{{ formatTime(syncStatus.finished_at) }}</div>
          </div>
        </div>

        <!-- Synchronous control -->
        <div class="sync-controls-section">
          <h4 class="section-title">Synchronous operation</h4>
          
          <!-- Data source selection -->
          <div class="source-selection">
            <el-form :model="syncForm" label-width="120px" size="default">
              <el-form-item label="Prioritize data sources:">
                <el-select
                  v-model="syncForm.preferred_sources"
                  multiple
                  placeholder="Choose a preferred data source (optional)"
                  style="width: 100%"
                  clearable
                >
                  <el-option
                    v-for="source in availableSources"
                    :key="source.name"
                    :label="source.name.toUpperCase()"
                    :value="source.name"
                    :disabled="!source.available"
                  >
                    <span>{{ source.name.toUpperCase() }}</span>
                    <span style="float: right; color: var(--el-text-color-secondary);">
                      priority: {{ source.priority }}
                    </span>
                  </el-option>
                </el-select>
              </el-form-item>
              
              <el-form-item label="Force synchronization:">
                <el-switch
                  v-model="syncForm.force"
                  active-text="Yes"
                  inactive-text="No"
                />
                <div class="form-help">
                  Force sync will ignore running sync tasks
                </div>
              </el-form-item>
            </el-form>
          </div>

          <!-- Action button -->
          <div class="action-buttons">
            <el-button
              type="primary"
              size="large"
              :loading="syncing || isSyncInProgress(syncStatus?.status)"
              :disabled="isSyncInProgress(syncStatus?.status) && !syncForm.force"
              @click="startSync"
            >
              <el-icon><Refresh /></el-icon>
              {{ getSyncButtonText() }}
            </el-button>
            
            <el-button
              size="large"
              :loading="refreshing"
              @click="refreshStatus"
            >
              <el-icon><RefreshRight /></el-icon>
              refresh status
            </el-button>
            
            <el-button
              size="large"
              type="warning"
              :loading="clearingCache"
              @click="clearCache"
            >
              <el-icon><Delete /></el-icon>
              Clear cache
            </el-button>

            <!-- Temporary test button -->


            <el-button
              size="large"
              type="success"
              :loading="syncing"
              @click="forceSync"
            >
              🔄 force resync
            </el-button>
          </div>
        </div>

        <!-- error message -->
        <div v-if="syncStatus?.message && syncStatus.status === 'failed'" class="error-section">
          <el-alert
            :title="syncStatus.message"
            type="error"
            :closable="false"
            show-icon
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, RefreshRight, Delete } from '@element-plus/icons-vue'
import {
  getSyncStatus,
  runStockBasicsSync,
  clearSyncCache,
  getDataSourcesStatus,
  type SyncStatus,
  type DataSourceStatus
} from '@/api/sync'
import { isJdyunMode } from '@/utils/config'

// Props
interface Props {
  autoRefresh?: boolean
  refreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoRefresh: true,
  refreshInterval: 5000
})

// Emits
const emit = defineEmits<{
  syncCompleted: [status: string]
}>()

// Responsive data
const syncing = ref(false)
const refreshing = ref(false)
const clearingCache = ref(false)
const syncStatus = ref<SyncStatus | null>(null)
const availableSources = ref<DataSourceStatus[]>([])
const refreshTimer = ref<NodeJS.Timeout | null>(null)

// form data
const syncForm = reactive({
  preferred_sources: [] as string[],
  force: false
})

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

// JD Cloud version only displays Tushare and AKShare
const JDYUN_ALLOWED_SOURCES = new Set(['tushare', 'akshare'])
const isJdyunAllowedSource = (name: string) => JDYUN_ALLOWED_SOURCES.has(name?.toLowerCase())

// Get data source status
const fetchDataSources = async () => {
  try {
    const response = await getDataSourcesStatus()
    if (response.success) {
      // Filter out local data sources (local data sources do not participate in synchronization operations)
      // JD Cloud version only displays Tushare and AKShare
      availableSources.value = response.data
        .filter(source => source.name !== 'local')
        .filter(source => !isJdyunMode() || isJdyunAllowedSource(source.name))
        .sort((a, b) => b.priority - a.priority) // Reverse order: highest priority first
    }
  } catch (err: any) {
    console.error('Failed to get data source status:', err)
  }
}

// Start syncing
const startSync = async () => {
  try {
    syncing.value = true
    
    const params = {
      force: syncForm.force,
      preferred_sources: syncForm.preferred_sources.length > 0 
        ? syncForm.preferred_sources.join(',') 
        : undefined
    }
    
    const response = await runStockBasicsSync(params)
    if (response.success) {
      const responseStatus = response.data.status
      console.log('🚀 The synchronization task started successfully, current status:', responseStatus)

      syncStatus.value = response.data

      if (responseStatus === 'queued') {
        ElMessage.success(response.data.message || 'The synchronization task has been submitted and the background is starting, please wait.')
        startStatusPolling()
        console.log('⏳ The synchronization task has been submitted to the background and polling status has started.')
      } else if (responseStatus === 'running') {
        ElMessage.success('Synchronization task started')
        // Start polling status
        startStatusPolling()
        console.log('🔄 Status polling started, interval:', props.refreshInterval, 'ms')
      } else if (responseStatus === 'success' || responseStatus === 'success_with_errors' || responseStatus === 'failed') {
        // Synchronization has been completed and the results are displayed directly.
        ElMessage.success('Synchronization task completed')
        console.log('✅ Synchronization is completed, notification will be displayed directly')
        showSyncCompletionNotification(responseStatus)
      } else {
        ElMessage.info(response.data.message || `Sync status:${getStatusText(responseStatus)}`)
      }
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

// refresh status
const refreshStatus = async () => {
  refreshing.value = true
  await fetchSyncStatus()
  refreshing.value = false
  ElMessage.success('Status has been refreshed')
}

// Clear cache
const clearCache = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear the sync cache? This will delete all cached data.',
      'Confirm to clear cache',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )
    
    clearingCache.value = true
    const response = await clearSyncCache()
    if (response.success) {
      ElMessage.success('cache cleared')
    } else {
      ElMessage.error(`Failed to clear cache: ${response.message}`)
    }
  } catch (err: any) {
    if (err !== 'cancel') {
      console.error('Failed to clear cache:', err)
      ElMessage.error(`Failed to clear cache: ${err.message}`)
    }
  } finally {
    clearingCache.value = false
  }
}

// Start status polling
const startStatusPolling = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
  }

  if (props.autoRefresh) {
    let previousStatus = syncStatus.value?.status
    let pollCount = 0
    const maxPolls = 60 // Poll up to 60 times (5 minutes)

    console.log('🔄 Start status polling, initial status:', previousStatus)

    refreshTimer.value = setInterval(async () => {
      pollCount++
      await fetchSyncStatus()

      const currentStatus = syncStatus.value?.status
      console.log(`🔍 polling #${pollCount}: ${previousStatus} -> ${currentStatus}`)

      // Check status changes and provide user feedback
      if (['queued', 'running'].includes(previousStatus || '') && currentStatus && !['queued', 'running'].includes(currentStatus)) {
        // Synchronization is completed and result notification is displayed.
        console.log('🎉 Synchronization completion detected, status changed from', previousStatus, 'become', currentStatus)
        showSyncCompletionNotification(currentStatus)
        stopStatusPolling()
        return
      }

      // Update previous status
      previousStatus = currentStatus

      // Also stops polling if sync completes but no status change detected
      if (currentStatus && !['queued', 'running'].includes(currentStatus)) {
        console.log('🛑 Non-running status detected, stop polling:', currentStatus)
        stopStatusPolling()
        return
      }

      // Prevent infinite polling
      if (pollCount >= maxPolls) {
        console.log('⏰ The number of polling reaches the upper limit, stop polling')
        stopStatusPolling()
      }
    }, props.refreshInterval)
  }
}

// Stop status polling
const stopStatusPolling = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

// Show sync completion notification
const showSyncCompletionNotification = (status: string) => {
  console.log('📢 Display synchronization completion notification, status:', status)

  const stats = syncStatus.value
  if (!stats) {
    console.warn('⚠️ Unable to get sync statistics')
    return
  }

  const total = stats.total || 0
  const inserted = stats.inserted || 0
  const updated = stats.updated || 0
  const errors = stats.errors || 0

  console.log('📊 Synchronization statistics:', { total, inserted, updated, errors })

  let title = ''
  let message = ''
  let type: 'success' | 'warning' | 'error' = 'success'

  if (status === 'success') {
    title = '🎉 Synchronization completed!'
    message = `Processed ${total} records, new ${inserted} article, update ${updated} Article`
    type = 'success'
  } else if (status === 'success_with_errors') {
    title = '⚠️ Sync completed with errors!'
    message = `Processed ${total} records, new ${inserted} article, update ${updated} bar, error ${errors} Article`
    type = 'warning'
  } else if (status === 'failed') {
    title = '❌ Synchronization failed!'
    message = stats.message || 'unknown error'
    type = 'error'
  }

  // Show page notifications
  ElMessage({
    message: `${title} ${message}`,
    type,
    duration: 8000,
    showClose: true
  })

  // Emit a synchronization completion event to notify the parent component
  emit('syncCompleted', status)

  // If there is data source information used, it will also be displayed.
  if (stats.data_sources_used && stats.data_sources_used.length > 0) {
    setTimeout(() => {
      ElMessage({
        message: `📡 Data source used: ${stats.data_sources_used.join(', ')}`,
        type: 'info',
        duration: 6000,
        showClose: true
      })
    }, 1000)
  }
}

// Get status type
const getStatusType = (status?: string): 'success' | 'warning' | 'info' | 'danger' => {
  const typeMap: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    idle: 'info',
    queued: 'warning',
    running: 'warning',
    success: 'success',
    success_with_errors: 'warning',
    failed: 'danger',
    never_run: 'info'
  }
  return typeMap[status || 'never_run'] || 'info'
}

// Get status text
const getStatusText = (status?: string) => {
  const textMap: Record<string, string> = {
    idle: 'free',
    queued: 'Starting in the background',
    running: 'Running',
    success: 'success',
    success_with_errors: 'Partially successful',
    failed: 'failed',
    never_run: 'Not running'
  }
  return textMap[status || 'never_run'] || 'unknown'
}

// Get progress percentage
const getProgress = () => {
  if (!syncStatus.value || syncStatus.value.total === 0) return 0
  return Math.round(((syncStatus.value.inserted + syncStatus.value.updated) / syncStatus.value.total) * 100)
}

// Get sync button text
const getSyncButtonText = () => {
  if (syncing.value) return 'Starting...'

  const status = syncStatus.value?.status
  if (status === 'queued') {
    return 'Starting in the background...'
  }
  if (status === 'running') {
    const progress = getProgress()
    if (progress > 0) {
      return `Synchronizing ${progress}%`
    }
    return 'Synchronizing...'
  }

  return 'Start syncing'
}

// Format time
const formatTime = (isoString: string) => {
  try {
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return isoString
  }
}



// force resync
const forceSync = async () => {
  console.log('🔄 force resync')

  // Clear the current status first
  syncStatus.value = null

  // Set forced synchronization flag
  const originalForce = syncForm.force
  syncForm.force = true

  try {
    await startSync()
  } finally {
    // Restore original settings
    syncForm.force = originalForce
  }
}

// Component mounting
onMounted(async () => {
  await Promise.all([
    fetchSyncStatus(),
    fetchDataSources()
  ])
  
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
.sync-control {
  .control-card {
    .card-header {
      display: flex;
      align-items: center;
      
      .header-icon {
        margin-right: 8px;
        color: var(--el-color-primary);
      }
      
      .header-title {
        font-weight: 600;
      }
    }
  }

  .control-content {
    .section-title {
      margin: 0 0 16px 0;
      font-size: 16px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    .sync-status-section {
      margin-bottom: 24px;
      
      .status-display {
        .status-tag {
          margin-bottom: 12px;
        }
        
        .progress-info {
          .progress-text {
            margin-top: 8px;
            font-size: 14px;
            color: var(--el-text-color-regular);
          }
        }
      }
    }

    .sync-stats-section {
      margin-bottom: 24px;
      
      .stats-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 16px;
        
        .stat-item {
          text-align: center;
          padding: 16px;
          border: 1px solid var(--el-border-color-light);
          border-radius: 8px;
          
          .stat-value {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 4px;
            
            &.success { color: var(--el-color-success); }
            &.primary { color: var(--el-color-primary); }
            &.danger { color: var(--el-color-danger); }
          }
          
          .stat-label {
            font-size: 14px;
            color: var(--el-text-color-secondary);
          }
        }
      }
      
      .sources-used {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 12px;

        .sources-label {
          font-size: 14px;
          color: var(--el-text-color-regular);
        }
      }

      .sync-time {
        display: flex;
        align-items: center;
        gap: 8px;

        .time-label {
          font-size: 14px;
          color: var(--el-text-color-regular);
        }

        .time-value {
          font-size: 14px;
          color: var(--el-text-color-primary);
          font-weight: 500;
        }
      }
    }

    .sync-controls-section {
      margin-bottom: 24px;
      
      .source-selection {
        margin-bottom: 20px;
        
        .form-help {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          margin-top: 4px;
        }
      }
      
      .action-buttons {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
      }
    }

    .error-section {
      margin-top: 16px;
    }
  }
}

@media (max-width: 768px) {
  .sync-control {
    .control-content {
      .sync-stats-section {
        .stats-grid {
          grid-template-columns: repeat(2, 1fr);
        }
      }
      
      .sync-controls-section {
        .action-buttons {
          flex-direction: column;
          
          .el-button {
            width: 100%;
          }
        }
      }
    }
  }
}
</style>
