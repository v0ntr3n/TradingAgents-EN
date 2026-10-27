<template>
  <div class="jdyun-config">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>JD Cloud configuration</span>
          <el-tag type="success" size="small">JD Cloud Cooperation Edition</el-tag>
        </div>
      </template>

      <el-alert
        title="JD Cloud Cooperation Edition Instructions"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      >
        <template #default>
          JD Cloud Cooperation Edition injects large models and data source configurations through environment variables, so users do not need to manually configure them.
          If you need to modify the configuration, please contact the administrator to update the environment variables and restart the service.
        </template>
      </el-alert>

      <el-descriptions :column="1" border>
        <el-descriptions-item label="Model service address">
          <span v-if="status.api_base">{{ status.api_base }}</span>
          <el-tag v-else type="danger" size="small">Not configured</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="API Key">
          <el-tag v-if="status.api_key_configured" type="success" size="small">configured</el-tag>
          <el-tag v-else type="danger" size="small">Not configured</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="Current default model">
          <el-tag type="primary">{{ status.current_model || 'not set' }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="Optional model list">
          <div class="model-list">
            <el-tag
              v-for="model in status.available_models"
              :key="model"
              :type="model === status.current_model ? 'primary' : 'info'"
              size="small"
              style="margin-right: 8px; margin-bottom: 4px;"
            >
              {{ model }}
            </el-tag>
          </div>
        </el-descriptions-item>

        <el-descriptions-item label="Embedding model">
          <el-tag type="info">{{ status.embedding_model || 'not set' }}</el-tag>
          <span style="margin-left: 8px; color: #909399; font-size: 12px;">
            (Dimensions: {{ status.embedding_dims || 0 }})
          </span>
        </el-descriptions-item>

        <el-descriptions-item label="Tushare data source">
          <el-tag v-if="status.tushare_token_configured" type="success" size="small">configured</el-tag>
          <el-tag v-else type="danger" size="small">Not configured</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="AKShare data source">
          <el-tag v-if="status.akshare_available" type="success" size="small">Available (free and open source)</el-tag>
          <el-tag v-else type="danger" size="small">Not available</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <div class="config-actions" style="margin-top: 20px;">
        <el-button @click="loadStatus" :loading="loading">refresh status</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { configApi } from '@/api/config'

interface JdyunStatus {
  jdyun_mode: boolean
  api_base: string
  api_key_configured: boolean
  current_model: string
  available_models: string[]
  embedding_model: string
  embedding_dims: number
  tushare_token_configured: boolean
  akshare_available: boolean
}

const status = ref<JdyunStatus>({
  jdyun_mode: true,
  api_base: '',
  api_key_configured: false,
  current_model: '',
  available_models: [],
  embedding_model: '',
  embedding_dims: 0,
  tushare_token_configured: false,
  akshare_available: true,
})

const loading = ref(false)

const loadStatus = async () => {
  loading.value = true
  try {
    const data = await configApi.getJdyunStatus()
    // Compatible with the situation where the old backend does not return akshare_available
    status.value = {
      ...data,
      akshare_available: data.akshare_available ?? true,
    }
  } catch (error: any) {
    ElMessage.error('Failed to obtain JD Cloud configuration status: ' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.jdyun-config {
  max-width: 800px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
