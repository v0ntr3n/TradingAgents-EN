<template>
  <div id="app" class="app-container">
    <!-- Network status indicator -->
    <NetworkStatus />

    <!-- main content area -->
    <router-view v-slot="{ Component, route }">
      <transition
        :name="(route?.meta?.transition as string) || 'fade'"
        mode="out-in"
        appear
      >
        <keep-alive :include="keepAliveComponents">
          <component :is="Component" :key="route?.fullPath || 'default'" />
        </keep-alive>
      </transition>
    </router-view>

    <!-- Configuration Wizard -->
    <ConfigWizard
      v-model="showConfigWizard"
      @complete="handleWizardComplete"
    />

    <!-- Use the Q&A bot pop-up window -->
    <FloatingChat />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import NetworkStatus from '@/components/NetworkStatus.vue'
import FloatingChat from '@/components/UsageHelper/FloatingChat.vue'
import { ApiClient } from '@/api/request'
import { configApi } from '@/api/config'

// Components that need to be cached
const keepAliveComponents = computed(() => [
  'Dashboard',
  'StockScreening',
  'AnalysisHistory'
])

// Configuration Wizard
const showConfigWizard = ref(false)

// Check if you need to show the configuration wizard
const checkFirstTimeSetup = async () => {
  try {
    // Check whether you have completed the configuration wizard
    const wizardCompleted = localStorage.getItem('config_wizard_completed')
    if (wizardCompleted === 'true') {
      return
    }

    // Verify configuration integrity
    const response: any = await ApiClient.get('/api/system/config/validate')
    if (response.success) {
      const result = response.data

      // If any required configuration is missing, display the configuration wizard
      if (!result.success && result.missing_required?.length > 0) {
        // Delay display, waiting for page loading to complete
        setTimeout(() => {
          showConfigWizard.value = true
        }, 1000)
      }
    }
  } catch (error) {
    console.error('Check configuration failed:', error)
  }
}

// Configuration wizard completes processing
const handleWizardComplete = async (data: any) => {
  try {
    console.log('Configuration wizard data:', data)

    // 1. Save large model configuration
    if (data.llm?.provider && data.llm?.apiKey) {
      try {
        // Add the manufacturer first (if it does not exist)
        const providerMap: Record<string, { name: string; base_url?: string }> = {
          deepseek: { name: 'DeepSeek', base_url: 'https://api.deepseek.com' },
          dashscope: { name: 'Tongyi Qianwen', base_url: 'https://dashscope.aliyuncs.com/api/v1' },
          openai: { name: 'OpenAI', base_url: 'https://api.openai.com/v1' },
          google: { name: 'Google Gemini', base_url: 'https://generativelanguage.googleapis.com/v1' }
        }

        const providerInfo = providerMap[data.llm.provider]
        if (providerInfo) {
          // Try to add the manufacturer (it will fail if it already exists, but it will not affect the subsequent process)
          try {
            await configApi.addLLMProvider({
              id: data.llm.provider,
              name: data.llm.provider,
              display_name: providerInfo.name,
              default_base_url: providerInfo.base_url,
              is_active: true,
              supported_features: ['chat', 'completion'] // Add default supported features
            })
          } catch (e) {
            // The manufacturer may already exist, ignore the error
            console.log('The manufacturer may already exist:', e)
          }

          // Add large model configuration
          if (data.llm.modelName) {
            await configApi.updateLLMConfig({
              provider: data.llm.provider,
              model_name: data.llm.modelName,
              enabled: true
            })

            // Set as default large model
            await configApi.setDefaultLLM(data.llm.modelName)
          }
        }
      } catch (error) {
        console.error('Failed to save large model configuration:', error)
        ElMessage.warning('The large model configuration failed to save, please configure it manually in configuration management later.')
      }
    }

    // 2. Save data source configuration
    if (data.datasource?.type) {
      try {
        const dsConfig: any = {
          name: data.datasource.type,
          type: data.datasource.type,
          enabled: true
        }

        // Add authentication information based on data source type
        if (data.datasource.type === 'tushare' && data.datasource.token) {
          dsConfig.api_key = data.datasource.token
        }

        await configApi.addDataSourceConfig(dsConfig)
      } catch (error) {
        console.error('Failed to save data source configuration:', error)
        ElMessage.warning('The data source configuration failed to save, please configure it manually in configuration management later.')
      }
    }

    // 3. Database configuration (MongoDB and Redis)
    // Note: The database configuration is usually in the .env file, here it just records the user s selection
    // The actual database connection needs to be configured in the backend .env file
    if (data.mongodb || data.redis) {
      console.log('Database configuration (needs to be set in .env file):', {
        mongodb: data.mongodb,
        redis: data.redis
      })
    }

    // Tag Configuration Wizard Completed
    localStorage.setItem('config_wizard_completed', 'true')

    ElMessage.success({
      message: 'Configuration completed! Welcome TradingAgents-CN',
      duration: 3000
    })
  } catch (error) {
    console.error('Failed to save configuration:', error)
    ElMessage.error('Failed to save configuration, please try again later')
  }
}

// life cycle
onMounted(() => {
  // Check if you need to show the configuration wizard
  checkFirstTimeSetup()
})
</script>

<style lang="scss">
.app-container {
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
  transition: background-color 0.3s ease;
}

.global-loading {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  background: linear-gradient(90deg, #409EFF 0%, #67C23A 100%);
  height: 2px;
}

// Route transition animation
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease;
}

.slide-left-enter-from {
  transform: translateX(30px);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(-30px);
  opacity: 0;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from {
  transform: translateY(30px);
  opacity: 0;
}

.slide-up-leave-to {
  transform: translateY(-30px);
  opacity: 0;
}

// Responsive design
@media (max-width: 768px) {
  .app-container {
    padding: 0;
  }
}
</style>
