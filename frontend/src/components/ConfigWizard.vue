<template>
  <el-dialog
    v-model="visible"
    title="Configuration Wizard"
    width="800px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="currentStep > 0"
  >
    <div class="config-wizard">
      <!-- step indicator -->
      <el-steps :active="currentStep" align-center finish-status="success">
        <el-step title="welcome" icon="el-icon-star-on" />
        <el-step title="Database configuration" icon="el-icon-coin" />
        <el-step title="Large model configuration" icon="el-icon-cpu" />
        <el-step title="Data source configuration" icon="el-icon-data-board" />
        <el-step title="Complete" icon="el-icon-circle-check" />
      </el-steps>

      <!-- Step content -->
      <div class="wizard-content">
        <!-- steps 0: welcome -->
        <div v-if="currentStep === 0" class="step-content welcome-step">
          <div class="welcome-icon">
            <el-icon :size="80" color="#409EFF"><Setting /></el-icon>
          </div>
          <h2>Welcome TradingAgents-CN</h2>
          <p class="welcome-text">
            Let s configure your system in a few simple steps.
            This will help you quickly start using the stock analysis features.
          </p>
          <el-alert
            title="Tips"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              <div>You can always"Configuration management"page to modify these settings.</div>
              <div>If you have already configured your system, you can skip this wizard.</div>
            </template>
          </el-alert>
        </div>

        <!-- steps 1: Database configuration -->
        <div v-if="currentStep === 1" class="step-content">
          <h3>Database configuration</h3>
          <p class="step-description">
            The system needs to connect to MongoDB and Redis databases.
          </p>

          <el-form :model="wizardData" label-width="120px">
            <el-divider content-position="left">MongoDB Configuration</el-divider>
            <el-form-item label="host address">
              <el-input
                v-model="wizardData.mongodb.host"
                placeholder="localhost"
              />
            </el-form-item>
            <el-form-item label="port">
              <el-input
                v-model="wizardData.mongodb.port"
                placeholder="27017"
                type="number"
              />
            </el-form-item>
            <el-form-item label="Database name">
              <el-input
                v-model="wizardData.mongodb.database"
                placeholder="tradingagents"
              />
            </el-form-item>

            <el-divider content-position="left">Redis Configuration</el-divider>
            <el-form-item label="host address">
              <el-input
                v-model="wizardData.redis.host"
                placeholder="localhost"
              />
            </el-form-item>
            <el-form-item label="port">
              <el-input
                v-model="wizardData.redis.port"
                placeholder="6379"
                type="number"
              />
            </el-form-item>
          </el-form>

          <el-alert
            title="Note"
            type="warning"
            :closable="false"
            show-icon
            description="The database configuration needs to be set in the .env file, which is only used to verify the connection."
          />
        </div>

        <!-- steps 2: Large model configuration -->
        <div v-if="currentStep === 2" class="step-content">
          <h3>Large model configuration</h3>
          <p class="step-description">
            Configure at least one large model API key for AI analysis functionality.
          </p>

          <el-form :model="wizardData" label-width="120px">
            <el-form-item label="Choose a large model">
              <el-select
                v-model="wizardData.llm.provider"
                placeholder="Please select a large model provider"
                @change="handleProviderChange"
              >
                <el-option label="Volcano Ark (recommended, domestically produced and stable)" value="volcengine" />
                <el-option label="DeepSeek (Recommended, cost-effective)" value="deepseek" />
                <el-option label="Tongyi Qianwen" value="dashscope" />
                <el-option label="OpenAI" value="openai" />
                <el-option label="Google Gemini" value="google" />
              </el-select>
            </el-form-item>

            <el-form-item v-if="wizardData.llm.provider" label="API key">
              <el-input
                v-model="wizardData.llm.apiKey"
                type="password"
                placeholder="Please enter API key"
                show-password
              />
            </el-form-item>

            <el-form-item v-if="wizardData.llm.provider" label="Model name">
              <el-select
                v-model="wizardData.llm.modelName"
                placeholder="Please select a model"
              >
                <template v-for="model in availableModels" :key="model.value">
                  <el-option
                    :label="model.label"
                    :value="model.value"
                  />
                </template>
              </el-select>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="wizardData.llm.provider"
            :title="`How to get ${getProviderName(wizardData.llm.provider)} API Key?`"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              <div>
                <div style="margin-bottom: 8px;">{{ getProviderHelp(wizardData.llm.provider) }}</div>
                <div>
                  <el-link
                    :href="getProviderUrl(wizardData.llm.provider)"
                    type="primary"
                    target="_blank"
                  >
                    Go to get →
                  </el-link>
                </div>
              </div>
            </template>
          </el-alert>
        </div>

        <!-- steps 3: Data source configuration -->
        <div v-if="currentStep === 3" class="step-content">
          <h3>Data source configuration</h3>
          <p class="step-description">
            Select a stock data source to obtain market data and basic information.
          </p>

          <el-form :model="wizardData" label-width="120px">
            <el-form-item label="Default data source">
              <el-select
                v-model="datasourceType"
                placeholder="Please select a data source"
              >
                <el-option label="AKShare (Recommended, free (no key required)" value="akshare" />
                <el-option label="Tushare (Professional A-share data)" value="tushare" />
              </el-select>
            </el-form-item>

            <el-form-item
              v-if="datasourceType === 'tushare'"
              label="Tushare Token"
            >
              <el-input
                v-model="datasourceToken"
                placeholder="Please enter Tushare Token"
              />
            </el-form-item>
          </el-form>

          <el-alert
            v-if="datasourceType === 'akshare'"
            title="AKShare No configuration required"
            type="success"
            :closable="false"
            show-icon
            description="AKShare is a free data source that requires no API key to use."
          />

          <el-alert
            v-if="datasourceType === 'tushare'"
            title="How to get Tushare Token?"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              <div>
                <div>1. Visit Tushare official website to register an account</div>
                <div>2. Log in after email verification</div>
                <div>3. Get it in personal center Token</div>
                <div style="margin-top: 8px;">
                  <el-link
                    href="https://tushare.pro/weborder/#/login?reg=tacn"
                    type="primary"
                    target="_blank"
                  >
                    Go to register →
                  </el-link>
                </div>
              </div>
            </template>
          </el-alert>
        </div>

        <!-- steps 4: Complete -->
        <div v-if="currentStep === 4" class="step-content complete-step">
          <div class="complete-icon">
            <el-icon :size="80" color="#67C23A"><CircleCheck /></el-icon>
          </div>
          <h2>Configuration completed!</h2>
          <p class="complete-text">
            Congratulations! You have completed the basic configuration. Now you can start using the system.
          </p>

          <div class="config-summary">
            <h4>Configuration summary</h4>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="database">
                MongoDB: {{ wizardData.mongodb.host }}:{{ wizardData.mongodb.port }}
              </el-descriptions-item>
              <el-descriptions-item label="large model">
                {{ getProviderName(wizardData.llm.provider) }} - {{ wizardData.llm.modelName }}
              </el-descriptions-item>
              <el-descriptions-item label="data source">
                {{ getDataSourceName(datasourceType) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <el-alert
            title="Next step"
            type="success"
            :closable="false"
            show-icon
          >
            <template #default>
              <div>
                <div>• visit"Dashboard"View system overview</div>
                <div>• visit"single stock research"Start researching stocks</div>
                <div>• visit"Configuration management"Adjust detailed settings</div>
              </div>
            </template>
          </el-alert>
        </div>
      </div>
    </div>

    <!-- Bottom button (must be a direct child of el-dialog) -->
    <template #footer>
      <div class="wizard-footer">
        <el-button
          v-if="currentStep > 0 && currentStep < 4"
          @click="handlePrevious"
        >
          Previous step
        </el-button>
        <el-button
          v-if="currentStep === 0"
          @click="handleSkip"
        >
          Skip wizard
        </el-button>
        <el-button
          v-if="currentStep < 4"
          type="primary"
          @click="handleNext"
          :loading="saving"
        >
          {{ currentStep === 0 ? 'Start configuration' : 'Next step' }}
        </el-button>
        <el-button
          v-if="currentStep === 4"
          type="primary"
          @click="handleComplete"
        >
          Complete
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, CircleCheck } from '@element-plus/icons-vue'

// type definition
interface DataSourceConfig {
  type: string
  token: string
  apiKey: string
}

interface WizardData {
  mongodb: {
    host: string
    port: number
    database: string
  }
  redis: {
    host: string
    port: number
  }
  llm: {
    provider: string
    apiKey: string
    modelName: string
  }
  datasource: DataSourceConfig
}

// Props
interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'complete', data: WizardData): void
}>()

// Responsive data
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const currentStep = ref(0)
const saving = ref(false)

const wizardData = ref<WizardData>({
  mongodb: {
    host: 'localhost',
    port: 27017,
    database: 'tradingagents'
  },
  redis: {
    host: 'localhost',
    port: 6379
  },
  llm: {
    provider: '',
    apiKey: '',
    modelName: ''
  },
  datasource: {
    type: 'akshare',
    token: '',
    apiKey: ''
  }
})

// List of available models
const availableModels = computed(() => {
  const provider = wizardData.value.llm.provider
  const models: Record<string, Array<{ label: string; value: string }>> = {
    volcengine: [
      { label: 'doubao-seed-2.0-pro', value: 'doubao-seed-2.0-pro' },
      { label: 'doubao-seed-2.0-lite', value: 'doubao-seed-2.0-lite' },
      { label: 'doubao-seed-code', value: 'doubao-seed-code' },
      { label: 'glm-5.2', value: 'glm-5.2' },
      { label: 'deepseek-v4-pro', value: 'deepseek-v4-pro' },
      { label: 'kimi-k2.6', value: 'kimi-k2.6' }
    ],
    volcengine_coding: [
      { label: 'doubao-seed-2.0-code', value: 'doubao-seed-2.0-code' },
      { label: 'doubao-seed-2.0-pro', value: 'doubao-seed-2.0-pro' },
      { label: 'doubao-seed-2.0-lite', value: 'doubao-seed-2.0-lite' },
      { label: 'doubao-seed-code', value: 'doubao-seed-code' },
      { label: 'glm-5.2', value: 'glm-5.2' },
      { label: 'kimi-k2.7-code', value: 'kimi-k2.7-code' },
      { label: 'deepseek-v4-flash', value: 'deepseek-v4-flash' },
      { label: 'deepseek-v4-pro', value: 'deepseek-v4-pro' },
      { label: 'minimax-m3', value: 'minimax-m3' },
      { label: 'minimax-m2.7', value: 'minimax-m2.7' },
      { label: 'kimi-k2.6', value: 'kimi-k2.6' }
    ],
    deepseek: [
      { label: 'deepseek-chat', value: 'deepseek-chat' },
      { label: 'deepseek-coder', value: 'deepseek-coder' }
    ],
    dashscope: [
      { label: 'qwen-turbo', value: 'qwen-turbo' },
      { label: 'qwen-plus', value: 'qwen-plus' },
      { label: 'qwen-max', value: 'qwen-max' }
    ],
    openai: [
      { label: 'gpt-3.5-turbo', value: 'gpt-3.5-turbo' },
      { label: 'gpt-4', value: 'gpt-4' },
      { label: 'gpt-4-turbo', value: 'gpt-4-turbo' }
    ],
    google: [
      { label: 'gemini-pro', value: 'gemini-pro' },
      { label: 'gemini-2.5-pro', value: 'gemini-2.5-pro' }
    ]
  }
  return models[provider] || []
})

// Computed properties related to data sources, used for two-way binding
const datasourceType = computed({
  get: () => wizardData.value.datasource.type,
  set: (value: string) => {
    wizardData.value.datasource.type = value
  }
})

const datasourceToken = computed({
  get: () => wizardData.value.datasource.token,
  set: (value: string) => {
    wizardData.value.datasource.token = value
  }
})


// method
const handleProviderChange = () => {
  wizardData.value.llm.modelName = ''
  if (availableModels.value.length > 0) {
    wizardData.value.llm.modelName = availableModels.value[0].value
  }
}

const getProviderName = (provider: string) => {
  const names: Record<string, string> = {
    volcengine: 'Volcano Ark',
    deepseek: 'DeepSeek',
    dashscope: 'Tongyi Qianwen',
    openai: 'OpenAI',
    google: 'Google Gemini'
  }
  return names[provider] || provider
}

const getProviderHelp = (provider: string) => {
  const helps: Record<string, string> = {
    volcengine: 'Register a Volcano Engine account, receive 25 million Tokens upon registration, and enjoy Doubao models',
    deepseek: 'Register a DeepSeek account and create it in the console API Key',
    dashscope: 'Register an Alibaba Cloud account, activate the Bailian service, and obtain the API key',
    openai: 'Register an OpenAI account and create a key on the API Keys page',
    google: 'Register a Google Cloud account and enable Gemini API'
  }
  return helps[provider] || ''
}

const getProviderUrl = (provider: string) => {
  const urls: Record<string, string> = {
    volcengine: 'https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    deepseek: 'https://platform.deepseek.com/',
    dashscope: 'https://dashscope.aliyun.com/',
    openai: 'https://platform.openai.com/',
    google: 'https://ai.google.dev/'
  }
  return urls[provider] || ''
}

const getDataSourceName = (type: string) => {
  const names: Record<string, string> = {
    akshare: 'AKShare',
    tushare: 'Tushare'
  }
  return names[type] || type
}

const handleNext = async () => {
  // Verify current step
  if (currentStep.value === 2 && !wizardData.value.llm.provider) {
    ElMessage.warning('Please select a large model provider')
    return
  }

  if (currentStep.value === 2 && !wizardData.value.llm.apiKey) {
    ElMessage.warning('Please enter API key')
    return
  }

  currentStep.value++
}

const handlePrevious = () => {
  currentStep.value--
}

const handleSkip = () => {
  visible.value = false
}

const handleComplete = () => {
  emit('complete', wizardData.value)
  visible.value = false
  ElMessage.success('The configuration wizard is complete!')
}
</script>

<style scoped lang="scss">
.config-wizard {
  .wizard-content {
    margin: 30px 0;
    min-height: 400px;

    .step-content {
      h3 {
        margin: 0 0 8px 0;
        font-size: 18px;
        color: var(--el-text-color-primary);
      }

      .step-description {
        margin: 0 0 24px 0;
        color: var(--el-text-color-regular);
      }

      &.welcome-step {
        text-align: center;
        padding: 40px 20px;

        .welcome-icon {
          margin-bottom: 24px;
        }

        h2 {
          margin: 0 0 16px 0;
          font-size: 24px;
          color: var(--el-text-color-primary);
        }

        .welcome-text {
          margin: 0 0 32px 0;
          font-size: 16px;
          color: var(--el-text-color-regular);
          line-height: 1.6;
        }
      }

      &.complete-step {
        text-align: center;
        padding: 40px 20px;

        .complete-icon {
          margin-bottom: 24px;
        }

        h2 {
          margin: 0 0 16px 0;
          font-size: 24px;
          color: var(--el-text-color-primary);
        }

        .complete-text {
          margin: 0 0 32px 0;
          font-size: 16px;
          color: var(--el-text-color-regular);
        }

        .config-summary {
          margin-bottom: 24px;
          text-align: left;

          h4 {
            margin: 0 0 16px 0;
            font-size: 16px;
            color: var(--el-text-color-primary);
          }
        }
      }
    }
  }

  .wizard-footer {
    display: flex;
    justify-content: space-between;
  }
}
</style>