<template>
  <div class="config-validator">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>
            <el-icon><CircleCheck /></el-icon>
            Configuration verification
          </h3>
          <el-button
            type="primary"
            size="small"
            @click="handleValidate"
            :loading="validating"
          >
            <el-icon><Refresh /></el-icon>
            revalidate
          </el-button>
        </div>
      </template>

      <div v-loading="validating" class="validator-content">
        <!-- Summary of verification results -->
        <div v-if="validationResult" class="validation-summary">
          <!-- Required configuration errors (red) -->
          <el-alert
            v-if="!validationResult.success"
            title="Configuration verification failed"
            type="error"
            :closable="false"
            show-icon
          >
            <p v-if="envValidation?.missing_required?.length">
              missing {{ envValidation.missing_required.length }} required configuration
            </p>
            <p v-if="envValidation?.invalid_configs?.length">
              {{ envValidation.invalid_configs.length }} configuration is invalid
            </p>
          </el-alert>

          <!-- Recommended configuration warning (yellow) -->
          <el-alert
            v-else-if="hasRecommendedWarnings"
            title="Configuration verification passed (there are recommended configurations that have not been set)"
            type="warning"
            :closable="false"
            show-icon
          >
            <p v-if="envValidation?.missing_recommended?.length">
              missing {{ envValidation.missing_recommended.length }} recommended configuration
            </p>
            <p v-if="mongodbValidation?.warnings?.length">
              {{ mongodbValidation.warnings.length }} MongoDB configuration warnings
            </p>
          </el-alert>

          <!-- All configurations are normal (green) -->
          <el-alert
            v-else
            title="Configuration verification passed"
            type="success"
            :closable="false"
            show-icon
          >
            <p>All configurations are set correctly</p>
          </el-alert>
        </div>

        <!-- Required configuration -->
        <div class="config-section">
          <h4>
            <el-icon><Star /></el-icon>
            Required configuration
          </h4>
          <div class="config-items">
            <div
              v-for="item in requiredConfigs"
              :key="item.key"
              class="config-item"
              :class="{ 'is-valid': item.valid, 'is-invalid': !item.valid }"
            >
              <div class="item-icon">
                <el-icon v-if="item.valid" color="#67C23A"><CircleCheck /></el-icon>
                <el-icon v-else color="#F56C6C"><CircleClose /></el-icon>
              </div>
              <div class="item-content">
                <div class="item-name">{{ item.name }}</div>
                <div class="item-description">{{ item.description }}</div>
                <div v-if="!item.valid && item.error" class="item-error">
                  {{ item.error }}
                </div>
              </div>
              <div class="item-status">
                <el-tag :type="item.valid ? 'success' : 'danger'" size="small">
                  {{ item.valid ? 'configured' : 'Not configured' }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>

        <!-- Recommended configuration -->
        <div class="config-section">
          <h4>
            <el-icon><Warning /></el-icon>
            Recommended configuration
          </h4>
          <div class="config-items">
            <div
              v-for="item in recommendedConfigs"
              :key="item.key"
              class="config-item"
              :class="{ 'is-valid': item.valid, 'is-warning': !item.valid }"
            >
              <div class="item-icon">
                <el-icon v-if="item.valid" color="#67C23A"><CircleCheck /></el-icon>
                <el-icon v-else color="#E6A23C"><Warning /></el-icon>
              </div>
              <div class="item-content">
                <div class="item-name">{{ item.name }}</div>
                <div class="item-description">{{ item.description }}</div>
                <div v-if="!item.valid && item.help" class="item-help">
                  {{ item.help }}
                </div>
              </div>
              <div class="item-status">
                <el-tag :type="item.valid ? 'success' : 'warning'" size="small">
                  {{ item.valid ? 'configured' : 'Not configured' }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>

        <!-- MongoDB Configuration verification -->
        <div v-if="mongodbValidation" class="config-section">
          <h4>
            <el-icon><Coin /></el-icon>
            MongoDB Configuration verification
          </h4>

          <!-- Large model manufacturer configuration -->
          <div v-if="mongodbValidation.llm_providers?.length" class="mongodb-subsection">
            <h5>Large model manufacturer</h5>
            <div class="config-items">
              <div
                v-for="(item, index) in mongodbValidation.llm_providers"
                :key="index"
                class="config-item"
                :class="{
                  'is-valid': item.status === 'configured',
                  'is-warning': item.status === 'Not configured or placeholder'
                }"
              >
                <div class="item-icon">
                  <el-icon v-if="item.status === 'configured'" color="#67C23A"><CircleCheck /></el-icon>
                  <el-icon v-else color="#E6A23C"><Warning /></el-icon>
                </div>
                <div class="item-content">
                  <div class="item-name">{{ item.display_name }}</div>
                  <div class="item-description">{{ item.name }}</div>
                </div>
                <div class="item-status">
                  <el-tag
                    :type="item.status === 'configured' ? 'success' : item.is_active ? 'warning' : 'info'"
                    size="small"
                  >
                    {{ item.status }}
                  </el-tag>
                </div>
              </div>
            </div>
          </div>

          <!-- Data source configuration -->
          <div v-if="mongodbValidation.data_source_configs?.length" class="mongodb-subsection">
            <h5>Data source configuration</h5>
            <div class="config-items">
              <div
                v-for="(item, index) in mongodbValidation.data_source_configs"
                :key="index"
                class="config-item"
                :class="{
                  'is-valid': item.status === 'configured' || item.status === 'Configured (no key required)',
                  'is-warning': item.status === 'Not configured or placeholder' && item.enabled,
                  'is-disabled': !item.enabled
                }"
              >
                <div class="item-icon">
                  <el-icon v-if="item.status.includes('configured')" color="#67C23A"><CircleCheck /></el-icon>
                  <el-icon v-else-if="item.enabled" color="#E6A23C"><Warning /></el-icon>
                  <el-icon v-else color="#909399"><CircleClose /></el-icon>
                </div>
                <div class="item-content">
                  <div class="item-name">{{ item.name }}</div>
                  <div class="item-description">{{ item.type }}</div>
                </div>
                <div class="item-status">
                  <el-tag
                    :type="item.status.includes('configured') ? 'success' : item.enabled ? 'warning' : 'info'"
                    size="small"
                  >
                    {{ item.status }}
                  </el-tag>
                </div>
              </div>
            </div>
          </div>

          <!-- MongoDB Configuration warning -->
          <div v-if="mongodbValidation.warnings?.length" class="mongodb-warnings">
            <el-alert
              v-for="(warning, index) in mongodbValidation.warnings"
              :key="index"
              :title="warning"
              type="warning"
              :closable="false"
              show-icon
              class="warning-item"
            />
          </div>
        </div>

        <!-- Environment variable warning message -->
        <div v-if="envValidation?.warnings?.length" class="warnings-section">
          <h4>
            <el-icon><InfoFilled /></el-icon>
            Environment variable warning
          </h4>
          <el-alert
            v-for="(warning, index) in envValidation.warnings"
            :key="index"
            :title="warning"
            type="warning"
            :closable="false"
            show-icon
            class="warning-item"
          />
        </div>

        <!-- Help information -->
        <div class="help-section">
          <el-collapse>
            <el-collapse-item title="How to fix configuration issues?" name="1">
              <div class="help-content">
                <h5>Required configuration</h5>
                <p>Required configuration needs to be in <code>.env</code> Settings in the file:</p>
                <ol>
                  <li>Found in the project root directory <code>.env</code> file (if not, copy <code>.env.example</code>) </li>
                  <li>Follow the prompts to fill in the missing configuration items</li>
                  <li>Save the file and restart the backend service</li>
                </ol>

                <h5>Recommended configuration</h5>
                <p>The recommended configuration can be set in the following ways:</p>
                <ul>
                  <li>in <code>.env</code> Set in file (recommended)</li>
                  <li>in"Configuration management"of page"Large model configuration"or"Data source configuration"Medium settings</li>
                </ul>

                <h5>FAQ</h5>
                <p><strong>Q: Why does it still show not configured after modification?</strong></p>
                <p>A: Environment variables need to restart the backend service to take effect.</p>

                <p><strong>Q: How do I get an API key?</strong></p>
                <p>A: Please visit the official website of the corresponding service provider to register and obtain the key. See details"Configuration management"Help information for the page.</p>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  CircleClose,
  Refresh,
  Star,
  Warning,
  InfoFilled,
  Coin
} from '@element-plus/icons-vue'
import { ApiClient } from '@/api/request'

// type definition
interface ConfigItem {
  key: string
  name: string
  description: string
  valid: boolean
  error?: string
  help?: string
}

interface EnvValidationResult {
  success: boolean
  missing_required?: Array<{ key: string; description: string }>
  missing_recommended?: Array<{ key: string; description: string }>
  invalid_configs?: Array<{ key: string; error: string }>
  warnings?: string[]
}

interface MongoDBValidationResult {
  llm_providers?: Array<{
    name: string
    display_name: string
    is_active: boolean
    has_api_key: boolean
    status: string
  }>
  data_source_configs?: Array<{
    name: string
    type: string
    enabled: boolean
    has_api_key: boolean
    status: string
  }>
  warnings?: string[]
}

interface ValidationResult {
  success: boolean
  env_validation?: EnvValidationResult
  mongodb_validation?: MongoDBValidationResult
}

// Responsive data
const validating = ref(false)
const validationResult = ref<ValidationResult | null>(null)
const envValidation = ref<EnvValidationResult | null>(null)
const mongodbValidation = ref<MongoDBValidationResult | null>(null)
const requiredConfigs = ref<ConfigItem[]>([])
const recommendedConfigs = ref<ConfigItem[]>([])

// Computed properties: Is there a recommended configuration warning?
const hasRecommendedWarnings = computed(() => {
  const hasMissingRecommended = (envValidation.value?.missing_recommended?.length ?? 0) > 0
  const hasMongodbWarnings = (mongodbValidation.value?.warnings?.length ?? 0) > 0
  return hasMissingRecommended || hasMongodbWarnings
})

// method
const handleValidate = async () => {
  validating.value = true
  try {
    const response: any = await ApiClient.get('/api/system/config/validate')

    console.log('🔍 Configure verification response:', response)

    if (response.success) {
      validationResult.value = response.data

      // Extract environment variable verification results and MongoDB verification results
      envValidation.value = response.data.env_validation || null
      mongodbValidation.value = response.data.mongodb_validation || null

      console.log('🔍 Environment variable verification:', envValidation.value)
      console.log('🔍 MongoDB Verify:', mongodbValidation.value)

      updateConfigItems()

      if (validationResult.value?.success) {
        ElMessage.success('Configuration verification passed')
      } else {
        ElMessage.warning('Configuration verification failed, please check for missing configuration items')
      }
    } else {
      ElMessage.error(response.message || 'Authentication failed')
    }
  } catch (error: any) {
    console.error('Configuration verification failed:', error)
    ElMessage.error(error.response?.data?.message || 'Authentication failed')
  } finally {
    validating.value = false
  }
}

const updateConfigItems = () => {
  if (!envValidation.value) return

  // Update required configuration
  const requiredKeys = [
    { key: 'MONGODB_HOST', name: 'MongoDB Host', description: 'MongoDB Database host address' },
    { key: 'MONGODB_PORT', name: 'MongoDB port', description: 'MongoDB Database port' },
    { key: 'MONGODB_DATABASE', name: 'MongoDB database', description: 'MongoDB Database name' },
    { key: 'REDIS_HOST', name: 'Redis Host', description: 'Redis Cache host address' },
    { key: 'REDIS_PORT', name: 'Redis port', description: 'Redis cache port' },
    { key: 'JWT_SECRET', name: 'JWT key', description: 'JWT Authentication key' }
  ]

  requiredConfigs.value = requiredKeys.map(item => {
    const missing = envValidation.value?.missing_required?.find(m => m.key === item.key)
    const invalid = envValidation.value?.invalid_configs?.find(i => i.key === item.key)

    return {
      ...item,
      valid: !missing && !invalid,
      error: invalid?.error || (missing ? 'Not configured' : undefined)
    }
  })

  // Update recommended configuration
  const recommendedKeys = [
    { key: 'DEEPSEEK_API_KEY', name: 'DeepSeek API', description: 'DeepSeek Large model API key', help: 'for AI analytics capabilities' },
    { key: 'AIHUBMIX_API_KEY', name: 'AIHubMix API', description: 'AIHubMix Aggregation Platform API Key', help: 'For unified access to multi-vendor models' },
    { key: 'VOLCENGINE_API_KEY', name: 'Volcano Ark API', description: 'Volcano Ark Big Model API Key', help: 'Used for AI analysis functions (models such as bean bags)' },
    { key: 'VOLCENGINE_CODING_API_KEY', name: 'Volcano Ark Coding API', description: 'Volcano Ark Coding Private API Key', help: 'Used for code generation and programming class model access' },
    { key: 'DASHSCOPE_API_KEY', name: 'Tongyi Qianwen API', description: 'Alibaba Cloud Tongyi Qianwen API key', help: 'for AI analytics capabilities' },
    { key: 'TUSHARE_TOKEN', name: 'Tushare Token', description: 'Tushare data source Token', help: 'Used to obtain professional A-share data' }
  ]

  recommendedConfigs.value = recommendedKeys.map(item => {
    const missing = envValidation.value?.missing_recommended?.find(m => m.key === item.key)

    return {
      ...item,
      valid: !missing
    }
  })
}

// life cycle
onMounted(() => {
  handleValidate()
})
</script>

<style scoped lang="scss">
.config-validator {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    h3 {
      margin: 0;
      font-size: 16px;
      color: var(--el-text-color-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  .validator-content {
    .validation-summary {
      margin-bottom: 24px;
    }

    .config-section {
      margin-bottom: 24px;

      h4 {
        margin: 0 0 16px 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .config-items {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .config-item {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid var(--el-border-color-light);
        background: var(--el-fill-color-blank);
        transition: all 0.3s;

        &.is-valid {
          border-color: var(--el-color-success-light-5);
          background: var(--el-color-success-light-9);
        }

        &.is-invalid {
          border-color: var(--el-color-danger-light-5);
          background: var(--el-color-danger-light-9);
        }

        &.is-warning {
          border-color: var(--el-color-warning-light-5);
          background: var(--el-color-warning-light-9);
        }

        &.is-disabled {
          border-color: var(--el-border-color-lighter);
          background: var(--el-fill-color-lighter);
          opacity: 0.7;
        }

        .item-icon {
          flex-shrink: 0;
          font-size: 20px;
        }

        .item-content {
          flex: 1;

          .item-name {
            font-size: 14px;
            font-weight: 600;
            color: var(--el-text-color-primary);
            margin-bottom: 4px;
          }

          .item-description {
            font-size: 13px;
            color: var(--el-text-color-regular);
            margin-bottom: 4px;
          }

          .item-error {
            font-size: 12px;
            color: var(--el-color-danger);
            margin-top: 4px;
          }

          .item-help {
            font-size: 12px;
            color: var(--el-color-warning);
            margin-top: 4px;
          }
        }

        .item-status {
          flex-shrink: 0;
        }
      }
    }

    .mongodb-subsection {
      margin-bottom: 20px;

      h5 {
        margin: 0 0 12px 0;
        font-size: 13px;
        font-weight: 600;
        color: var(--el-text-color-secondary);
        padding-left: 8px;
        border-left: 3px solid var(--el-color-primary);
      }

      &:last-child {
        margin-bottom: 0;
      }
    }

    .mongodb-warnings {
      margin-top: 16px;

      .warning-item {
        margin-bottom: 8px;

        &:last-child {
          margin-bottom: 0;
        }
      }
    }

    .warnings-section {
      margin-bottom: 24px;

      h4 {
        margin: 0 0 16px 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .warning-item {
        margin-bottom: 8px;

        &:last-child {
          margin-bottom: 0;
        }
      }
    }

    .help-section {
      .help-content {
        h5 {
          margin: 16px 0 8px 0;
          font-size: 14px;
          color: var(--el-text-color-primary);

          &:first-child {
            margin-top: 0;
          }
        }

        p {
          margin: 8px 0;
          font-size: 13px;
          color: var(--el-text-color-regular);
          line-height: 1.6;
        }

        code {
          padding: 2px 6px;
          background: var(--el-fill-color-light);
          border-radius: 4px;
          font-family: 'Courier New', monospace;
          font-size: 12px;
        }

        ol, ul {
          margin: 8px 0;
          padding-left: 24px;

          li {
            margin: 4px 0;
            font-size: 13px;
            color: var(--el-text-color-regular);
            line-height: 1.6;
          }
        }
      }
    }
  }
}
</style>

