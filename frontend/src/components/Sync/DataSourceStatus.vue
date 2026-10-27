<template>
  <div class="data-source-status">
    <el-card class="status-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon class="header-icon"><Connection /></el-icon>
          <span class="header-title">Data source status</span>
          <el-button 
            type="primary" 
            size="small" 
            :loading="refreshing"
            @click="refreshStatus"
          >
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </div>
      </template>

      <div v-loading="loading" class="status-content">
        <div v-if="error" class="error-message">
          <el-alert
            :title="error"
            type="error"
            :closable="false"
            show-icon
          />
        </div>

        <div v-else-if="displayDataSources.length > 0" class="sources-list">
          <div
            v-for="source in displayDataSources"
            :key="source.name"
            class="source-item"
            :class="{ 'available': source.available, 'unavailable': !source.available }"
          >
            <div class="source-header">
              <div class="source-info">
                <el-tag 
                  :type="source.available ? 'success' : 'danger'"
                  size="small"
                  class="status-tag"
                >
                  {{ source.available ? 'Available' : 'Not available' }}
                </el-tag>
                <span class="source-name">{{ source.name.toUpperCase() }}</span>
                <el-tag size="small" type="info" class="priority-tag">
                  priority: {{ source.priority }}
                </el-tag>
              </div>
              <div class="source-actions">
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="testSingleSource(source.name)"
                  :loading="testingSource === source.name"
                >
                  <el-icon><Operation /></el-icon>
                  test
                </el-button>
              </div>
            </div>
            <div class="source-description">
              {{ source.description }}
            </div>
            
            <!-- Test result display -->
            <div v-if="testResults[source.name]" class="test-results">
              <el-divider content-position="left">
                <span class="divider-text">final test results</span>
              </el-divider>
              <div class="test-result-message">
                <el-alert
                  :title="testResults[source.name].message"
                  :type="testResults[source.name].available ? 'success' : 'error'"
                  :closable="false"
                  show-icon
                />
              </div>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <el-empty description="No data source information yet" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Refresh, Operation } from '@element-plus/icons-vue'
import { getDataSourcesStatus, testDataSources, type DataSourceStatus, type DataSourceTestResult } from '@/api/sync'
import { testApiConnection } from '@/api/request'
import { isJdyunMode } from '@/utils/config'

// Responsive data
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const dataSources = ref<DataSourceStatus[]>([])
const testResults = ref<Record<string, DataSourceTestResult>>({})
const testingSource = ref('')

// JD Cloud version only displays Tushare and AKShare
const JDYUN_ALLOWED_SOURCES = new Set(['tushare', 'akshare'])
const displayDataSources = computed(() => {
  if (!isJdyunMode()) {
    return dataSources.value
  }
  return dataSources.value.filter(source =>
    JDYUN_ALLOWED_SOURCES.has(source.name?.toLowerCase())
  )
})

// Get data source status
const fetchDataSourcesStatus = async () => {
  try {
    console.log('🔍 [DataSourceStatus] Start getting data source status')
    loading.value = true
    error.value = ''

    // Test the API connection first
    console.log('🔍 [DataSourceStatus] Test the API connection first')
    const connectionOk = await testApiConnection()
    console.log('🔍 [DataSourceStatus] API Connection test results:', connectionOk)

    if (!connectionOk) {
      console.error('🔍 [DataSourceStatus] API The connection test failed and subsequent operations are stopped.')
      error.value = 'Unable to connect to the backend service, please make sure the backend service is http://localhost:8000 run'
      return
    }

    console.log('🔍 [DataSourceStatus] API The connection test is successful, continue to obtain the data source status')

    console.log('🔍 [DataSourceStatus] API The connection is normal, call getDataSourcesStatus')
    const response = await getDataSourcesStatus()
    console.log('🔍 [DataSourceStatus] API response:', response)

    if (response.success) {
      console.log('🔍 [DataSourceStatus] API The call is successful, the number of data sources:', response.data?.length || 0)
      console.log('🔍 [DataSourceStatus] Data source details:', response.data)
      dataSources.value = response.data.sort((a, b) => b.priority - a.priority) // Reverse order: highest priority first
      console.log('🔍 [DataSourceStatus] Sorted data source:', dataSources.value)
    } else {
      console.error('🔍 [DataSourceStatus] API call failed')
      console.error('🔍 [DataSourceStatus] full response object:', response)
      console.error('🔍 [DataSourceStatus] Response success field:', response.success)
      console.error('🔍 [DataSourceStatus] Response message field:', response.message)
      console.error('🔍 [DataSourceStatus] response data field:', response.data)
      console.error('🔍 [DataSourceStatus] All properties of the response:', Object.keys(response))
      error.value = response.message || 'Failed to get data source status'
    }
  } catch (err: any) {
    console.error('🔍 [DataSourceStatus] catch exception:', err)
    console.error('🔍 [DataSourceStatus] Exception type:', err.constructor.name)
    console.error('🔍 [DataSourceStatus] Exception message:', err.message)
    console.error('🔍 [DataSourceStatus] exception stack:', err.stack)

    // Check if it is a network error
    if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      console.error('🔍 [DataSourceStatus] This is a network connection error')
      error.value = 'Network connection failed, please check whether the server is running normally'
    } else if (err.message.includes('HTTP')) {
      console.error('🔍 [DataSourceStatus] This is an HTTP status error')
      error.value = `Server error: ${err.message}`
    } else {
      console.error('🔍 [DataSourceStatus] This is a different type of error')
      error.value = err.message || 'Network request failed'
    }
  } finally {
    loading.value = false
    console.log('🔍 [DataSourceStatus] Get data source status completed')
  }
}

// refresh status
const refreshStatus = async () => {
  refreshing.value = true
  await fetchDataSourcesStatus()
  refreshing.value = false
  ElMessage.success('Data source status refreshed')
}

// Test a single data source
const testSingleSource = async (sourceName: string) => {
  try {
    testingSource.value = sourceName
    ElMessage.info(`Testing ${sourceName.toUpperCase()}, please wait...`)

    // Pass a data source name to test only that data source
    const response = await testDataSources(sourceName)
    if (response.success) {
      const results = response.data.test_results
      const sourceResult = results.find(r => r.name === sourceName)
      if (sourceResult) {
        testResults.value[sourceName] = sourceResult
        if (sourceResult.available) {
          ElMessage.success(`✅ ${sourceName.toUpperCase()} Connection successful`)
        } else {
          ElMessage.warning(`⚠️ ${sourceName.toUpperCase()} Connection failed: ${sourceResult.message}`)
        }
      }
    } else {
      ElMessage.error(`test failed: ${response.message}`)
    }
  } catch (err: any) {
    console.error('Test data source failed:', err)
    if (err.code === 'ECONNABORTED') {
      ElMessage.error(`test timeout: ${sourceName.toUpperCase()} The test took too long, please try again later`)
    } else {
      ElMessage.error(`test failed: ${err.message}`)
    }
  } finally {
    testingSource.value = ''
  }
}

// Get data when component is mounted
onMounted(() => {
  fetchDataSourcesStatus()
})
</script>

<style scoped lang="scss">
.data-source-status {
  .status-card {
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

  .status-content {
    min-height: 200px;
  }

  .sources-list {
    .source-item {
      padding: 16px;
      border: 1px solid var(--el-border-color-light);
      border-radius: 8px;
      margin-bottom: 12px;
      transition: all 0.3s ease;

      &.available {
        border-color: var(--el-color-success-light-7);
        background-color: var(--el-color-success-light-9);
      }

      &.unavailable {
        border-color: var(--el-color-danger-light-7);
        background-color: var(--el-color-danger-light-9);
      }

      &:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }

      .source-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;

        .source-info {
          display: flex;
          align-items: center;
          gap: 8px;

          .source-name {
            font-weight: 600;
            font-size: 16px;
          }
        }
      }

      .source-description {
        color: var(--el-text-color-regular);
        font-size: 14px;
        line-height: 1.5;
      }

      .test-results {
        margin-top: 16px;

        .divider-text {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }

        .test-items {
          .test-item {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            font-size: 14px;

            .success-icon {
              color: var(--el-color-success);
            }

            .error-icon {
              color: var(--el-color-danger);
            }

            .test-name {
              font-weight: 500;
              min-width: 80px;
            }

            .test-message {
              color: var(--el-text-color-regular);
              flex: 1;
            }
          }
        }
      }
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
</style>
