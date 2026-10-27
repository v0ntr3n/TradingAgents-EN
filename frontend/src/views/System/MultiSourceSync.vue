<template>
  <div class="multi-source-sync">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-info">
          <h1 class="page-title">
            <el-icon class="title-icon"><Connection /></el-icon>
            Synchronization of multiple data sources
          </h1>
          <p class="page-description">
            Manage and monitor the synchronization of basic stock information from multiple data sources, supporting automatic fallback and priority configuration
          </p>
        </div>
        <div class="header-actions">
          <el-button
            type="primary"
            size="large"
            :loading="testing"
            @click="runFullTest"
          >
            <el-icon><Operation /></el-icon>
            Comprehensive testing
          </el-button>
        </div>
      </div>
    </div>

    <!-- Main content -->
    <div class="page-content">
      <el-row :gutter="24">
        <!-- left column -->
        <el-col :lg="12" :md="24" :sm="24">
          <!-- Data source status -->
          <div class="content-section">
            <DataSourceStatus ref="dataSourceStatusRef" />
          </div>
          
          <!-- Usage suggestions -->
          <div class="content-section">
            <SyncRecommendations 
              @task-triggered="handleTaskTriggered"
              @task-resumed="handleTaskResumed"
            />
          </div>
        </el-col>

        <!-- right column -->
        <el-col :lg="12" :md="24" :sm="24">
          <!-- Synchronous control -->
          <div class="content-section">
            <SyncControl @sync-completed="handleSyncCompleted" />
          </div>
          
          <!-- Sync history -->
          <div class="content-section">
            <SyncHistory />
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- Test results dialog box -->
    <el-dialog
      v-model="testDialogVisible"
      title="Comprehensive test results"
      width="80%"
      :close-on-click-modal="false"
    >
      <div v-if="testResults" class="test-results-dialog">
        <div class="test-summary">
          <el-alert
            :title="`Test completed, total tests ${testResults.length} data sources`"
            :type="getOverallTestResult()"
            :closable="false"
            show-icon
          />
        </div>
        
        <div class="test-details">
          <el-row :gutter="16">
            <el-col
              v-for="result in testResults"
              :key="result.name"
              :lg="8"
              :md="12"
              :sm="24"
            >
              <div class="test-result-item">
                <div class="result-header">
                  <el-tag
                    :type="result.available ? 'success' : 'danger'"
                    size="large"
                  >
                    {{ result.name.toUpperCase() }}
                  </el-tag>
                  <span class="priority-info">priority: {{ result.priority }}</span>
                </div>

                <div class="result-message">
                  <el-alert
                    :title="result.message"
                    :type="result.available ? 'success' : 'error'"
                    :closable="false"
                    show-icon
                  />
                </div>
              </div>
            </el-col>
          </el-row>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="testDialogVisible = false">close</el-button>
        <el-button type="primary" @click="exportTestResults">
          <el-icon><Download /></el-icon>
          Export results
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Connection,
  Operation,
  Download
} from '@element-plus/icons-vue'
import { testDataSources, type DataSourceTestResult } from '@/api/sync'
import DataSourceStatus from '@/components/Sync/DataSourceStatus.vue'
import SyncControl from '@/components/Sync/SyncControl.vue'
import SyncRecommendations from '@/components/Sync/SyncRecommendations.vue'
import SyncHistory from '@/components/Sync/SyncHistory.vue'
import { isJdyunMode } from '@/utils/config'

// Responsive data
const testing = ref(false)
const testDialogVisible = ref(false)
const testResults = ref<DataSourceTestResult[] | null>(null)
const dataSourceStatusRef = ref()

// JD Cloud version only displays Tushare and AKShare
const JDYUN_ALLOWED_SOURCES = new Set(['tushare', 'akshare'])
const filterJdyunResults = (results: DataSourceTestResult[]) => {
  if (!isJdyunMode()) return results
  return results.filter(r => JDYUN_ALLOWED_SOURCES.has(r.name?.toLowerCase()))
}

// Run comprehensive tests
const runFullTest = async () => {
  try {
    testing.value = true
    ElMessage.info('Full testing in progress, please wait....')

    // Without passing sourceName, test all data sources
    const response = await testDataSources()
    if (response.success) {
      testResults.value = filterJdyunResults(response.data.test_results || [])
      testDialogVisible.value = true
      const availableCount = testResults.value.filter(r => r.available).length
      ElMessage.success(`Comprehensive testing completed: ${availableCount}/${testResults.value.length} Data source available`)
    } else {
      ElMessage.error(`test failed: ${response.message}`)
    }
  } catch (err: any) {
    console.error('Full test failed:', err)
    if (err.code === 'ECONNABORTED') {
      ElMessage.error('Test timed out, please try again later. Please make sure your network connection is stable.')
    } else {
      ElMessage.error(`test failed: ${err.message}`)
    }
  } finally {
    testing.value = false
  }
}

// Get overall test results
const getOverallTestResult = (): 'success' | 'warning' | 'info' | 'error' => {
  if (!testResults.value) return 'info'

  const hasFailure = testResults.value.some(result => !result.available)

  return hasFailure ? 'warning' : 'success'
}

// Export test results
const exportTestResults = () => {
  if (!testResults.value) return

  const data = {
    timestamp: new Date().toISOString(),
    results: testResults.value
  }
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { 
    type: 'application/json' 
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `data-source-test-results-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  
  ElMessage.success('Test results have been exported')
}

// Handle synchronization completion event
const handleSyncCompleted = (status: string) => {
  console.log('🎉 Received synchronization completion event, status:', status)
  // Here you can trigger history refresh
  // Since we use component references, we can directly call the refresh method of the subcomponent
  // Or emit a global event for the history component to listen to
}

// 🔥 Process task trigger events and refresh data source status
const handleTaskTriggered = async () => {
  console.log('🔄 The task has been triggered, refresh the data source status')
  if (dataSourceStatusRef.value && typeof dataSourceStatusRef.value.refreshStatus === 'function') {
    await dataSourceStatusRef.value.refreshStatus()
  }
}

// 🔥 Handle task recovery events and refresh data source status
const handleTaskResumed = async () => {
  console.log('🔄 Task has been resumed, refresh data source status')
  if (dataSourceStatusRef.value && typeof dataSourceStatusRef.value.refreshStatus === 'function') {
    await dataSourceStatusRef.value.refreshStatus()
  }
}
</script>

<style scoped lang="scss">
.multi-source-sync {
  .page-header {
    margin-bottom: 24px;
    padding: 24px;
    background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-color-primary-light-8) 100%);
    border-radius: 12px;
    
    .header-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .header-info {
        .page-title {
          display: flex;
          align-items: center;
          margin: 0 0 8px 0;
          font-size: 28px;
          font-weight: 600;
          color: var(--el-text-color-primary);
          
          .title-icon {
            margin-right: 12px;
            color: var(--el-color-primary);
          }
        }
        
        .page-description {
          margin: 0;
          font-size: 16px;
          color: var(--el-text-color-regular);
          line-height: 1.5;
        }
      }
      
      .header-actions {
        flex-shrink: 0;
      }
    }
  }

  .page-content {
    .content-section {
      margin-bottom: 24px;
      
      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  .test-results-dialog {
    .test-summary {
      margin-bottom: 24px;
    }
    
    .test-details {
      .test-result-item {
        margin-bottom: 24px;
        padding: 20px;
        border: 1px solid var(--el-border-color-light);
        border-radius: 8px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .result-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;
          
          .priority-info {
            font-size: 14px;
            color: var(--el-text-color-secondary);
          }
        }
        
        .result-tests {
          .test-item {
            padding: 12px;
            border: 1px solid var(--el-border-color-lighter);
            border-radius: 6px;
            height: 100%;
            
            .test-header {
              display: flex;
              align-items: center;
              gap: 6px;
              margin-bottom: 8px;
              
              .success-icon {
                color: var(--el-color-success);
              }
              
              .error-icon {
                color: var(--el-color-danger);
              }
              
              .test-name {
                font-weight: 500;
                font-size: 14px;
              }
            }
            
            .test-message {
              font-size: 12px;
              color: var(--el-text-color-regular);
              margin-bottom: 4px;
              line-height: 1.4;
            }
            
            .test-count,
            .test-date {
              font-size: 12px;
              color: var(--el-text-color-secondary);
            }
          }
        }
      }
    }
  }
}

@media (max-width: 768px) {
  .multi-source-sync {
    .page-header {
      .header-content {
        flex-direction: column;
        align-items: flex-start;
        gap: 16px;
        
        .header-actions {
          width: 100%;
          
          .el-button {
            width: 100%;
          }
        }
      }
    }
    
    .test-results-dialog {
      .test-details {
        .test-result-item {
          .result-tests {
            .el-col {
              margin-bottom: 12px;
            }
          }
        }
      }
    }
  }
}
</style>
