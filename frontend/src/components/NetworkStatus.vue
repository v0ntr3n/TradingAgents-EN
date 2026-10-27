<template>
  <div class="network-status" v-if="showStatus">
    <el-alert
      v-if="!appStore.isOnline"
      title="Network connection has been lost"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>Please check your network connection</span>
      </template>
    </el-alert>
    
    <el-alert
      v-else-if="!appStore.apiConnected"
      title="Backend service connection failed"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>Unable to connect to backend service, please check if the service is running properly</span>
        <el-button 
          type="primary" 
          size="small" 
          @click="retryConnection"
          :loading="retrying"
          style="margin-left: 10px;"
        >
          Retry connection
        </el-button>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const retrying = ref(false)

// Only show status if there is a network problem
const showStatus = computed(() => {
  return !appStore.isOnline || !appStore.apiConnected
})

// Retry connection
const retryConnection = async () => {
  retrying.value = true
  try {
    await appStore.checkApiConnection()
    if (appStore.apiConnected) {
      console.log('✅ API Connection restored')
    }
  } catch (error) {
    console.error('❌ Retry connection failed:', error)
  } finally {
    retrying.value = false
  }
}

// Regularly check API connection status
let checkInterval: number | null = null

onMounted(() => {
  // Check API connection status every 30 seconds
  checkInterval = window.setInterval(() => {
    if (appStore.isOnline && !appStore.apiConnected) {
      appStore.checkApiConnection()
    }
  }, 30000)
})

onUnmounted(() => {
  if (checkInterval) {
    clearInterval(checkInterval)
  }
})
</script>

<style scoped>
.network-status {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  max-width: 400px;
}

.network-status :deep(.el-alert) {
  margin-bottom: 10px;
}

.network-status :deep(.el-alert__content) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
