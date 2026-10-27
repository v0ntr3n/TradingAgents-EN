<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? 'Edit large model configuration' : 'Add large model configuration'"
    width="600px"
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
    >
      <!-- Basic configuration -->
      <el-form-item label="supplier" prop="provider">
        <div style="display: flex; gap: 8px; align-items: flex-start; width: 100%;">
          <el-select
            v-model="formData.provider"
            placeholder="Select supplier"
            @change="handleProviderChange"
            :loading="providersLoading"
            style="flex: 1; min-width: 0;"
          >
            <el-option
              v-for="provider in availableProviders"
              :key="provider.name"
              :label="provider.display_name"
              :value="provider.name"
            />
          </el-select>
          <el-button
            :icon="Refresh"
            :loading="providersLoading"
            @click="() => loadProviders(true)"
            title="Refresh supplier list"
          />
        </div>
        <div class="form-tip">
          If you do not find the required supplier, please first"Factory management"Add it in and click the refresh button
        </div>
      </el-form-item>

      <el-form-item label="Select model" v-if="modelOptions.length > 0">
        <el-select
          v-model="selectedModelKey"
          placeholder="Select model from list"
          filterable
          clearable
          @change="handleModelSelect"
        >
          <el-option
            v-for="model in modelOptions"
            :key="model.value"
            :label="model.label"
            :value="model.value"
          >
            <div style="display: flex; flex-direction: column;">
              <span>{{ model.label }}</span>
              <span style="font-size: 12px; color: #909399;">code: {{ model.value }}</span>
            </div>
          </el-option>
        </el-select>
        <div class="form-tip">
          💡 Select a model from the list and the display name and model code below will automatically populate
        </div>
      </el-form-item>

      <el-form-item label="Model display name" prop="model_display_name">
        <el-input
          v-model="formData.model_display_name"
          placeholder="Enter the display name of the model, such as: Qwen3 Series Flash Model - Fast and Economical"
        />
        <div class="form-tip">
          💡 Friendly name for display on the interface
        </div>
      </el-form-item>

      <el-form-item label="model code" prop="model_name">
        <el-input
          v-model="formData.model_name"
          placeholder="Enter the API call code of the model, such as:qwen-turbo"
        />
        <div class="form-tip">
          💡 The model identifier used when actually calling the API
        </div>
      </el-form-item>

      <el-form-item label="API Basics URL" prop="api_base">
        <el-input
          v-model="formData.api_base"
          placeholder="Optional, custom API endpoint (leave blank to use the manufacturer s default address)"
        />
        <div class="form-tip">
          💡 API The key has been set in the factory configuration, you only need to configure the model parameters here
        </div>
      </el-form-item>

      <!-- Model parameters -->
      <el-divider content-position="left">Model parameters</el-divider>

      <el-form-item label="Maximum number of tokens" prop="max_tokens">
        <el-input-number
          v-model="formData.max_tokens"
          :min="100"
          :max="32000"
          :step="100"
        />
      </el-form-item>

      <el-form-item label="Temperature parameter" prop="temperature">
        <el-input-number
          v-model="formData.temperature"
          :min="0"
          :max="2"
          :step="0.1"
          :precision="1"
        />
      </el-form-item>

      <el-form-item label="timeout" prop="timeout">
        <el-input-number
          v-model="formData.timeout"
          :min="10"
          :max="300"
          :step="10"
        />
        <span class="ml-2 text-gray-500">seconds</span>
      </el-form-item>

      <el-form-item label="Number of retries" prop="retry_times">
        <el-input-number
          v-model="formData.retry_times"
          :min="0"
          :max="10"
        />
      </el-form-item>

      <!-- Pricing configuration -->
      <el-divider content-position="left">Pricing configuration</el-divider>

      <el-form-item label="Enter price" prop="input_price_per_1k">
        <el-input-number
          v-model="formData.input_price_per_1k"
          :min="0"
          :step="0.0001"
          :controls="false"
          placeholder="Price per 1000 tokens"
        />
        <span class="ml-2 text-gray-500">{{ formData.currency || 'CNY' }}/1K tokens</span>
      </el-form-item>

      <el-form-item label="output price" prop="output_price_per_1k">
        <el-input-number
          v-model="formData.output_price_per_1k"
          :min="0"
          :step="0.0001"
          :controls="false"
          placeholder="Price per 1000 tokens"
        />
        <span class="ml-2 text-gray-500">{{ formData.currency || 'CNY' }}/1K tokens</span>
      </el-form-item>

      <el-form-item label="currency unit" prop="currency">
        <el-select v-model="formData.currency" placeholder="Select currency unit">
          <el-option label="RMB (CNY)" value="CNY" />
          <el-option label="US dollars (USD)" value="USD" />
          <el-option label="Euro (EUR)" value="EUR" />
        </el-select>
      </el-form-item>

      <!-- Advanced settings -->
      <el-divider content-position="left">Advanced settings</el-divider>

      <el-form-item label="enable model">
        <el-switch v-model="formData.enabled" />
      </el-form-item>

      <el-form-item label="Enable memory function">
        <el-switch v-model="formData.enable_memory" />
      </el-form-item>

      <el-form-item label="Enable debug mode">
        <el-switch v-model="formData.enable_debug" />
      </el-form-item>

      <el-form-item label="priority" prop="priority">
        <el-input-number
          v-model="formData.priority"
          :min="0"
          :max="100"
        />
        <span class="ml-2 text-gray-500">The larger the value, the higher the priority.</span>
      </el-form-item>

      <el-form-item label="Model category" prop="model_category">
        <el-input
          v-model="formData.model_category"
          placeholder="Optional, used for classification such as OpenRouter"
        />
      </el-form-item>

      <el-form-item label="Description" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="Optional, configuration description"
        />
      </el-form-item>

      <!-- 🆕 Model capability configuration -->
      <el-divider content-position="left">Model capability configuration</el-divider>

      <el-form-item label="Ability level" prop="capability_level">
        <el-select v-model="formData.capability_level" placeholder="Select model capability level">
          <el-option :value="1" label="1 Level - Base Model (Quick Analysis)">
            <span>1 Level - base model</span>
            <span class="text-gray-400 text-xs ml-2">Ideal for quick analysis and simple tasks</span>
          </el-option>
          <el-option :value="2" label="2 Level - Standard model (daily use)">
            <span>2 Class - Standard Model</span>
            <span class="text-gray-400 text-xs ml-2">Suitable for daily analysis and routine tasks</span>
          </el-option>
          <el-option :value="3" label="3 Level - Advanced Model (In-depth Analysis)">
            <span>3 Level - Advanced Model</span>
            <span class="text-gray-400 text-xs ml-2">Suitable for in-depth analysis and complex reasoning</span>
          </el-option>
          <el-option :value="4" label="4 Level - Professional Model (Professional Analysis)">
            <span>4 Level - Professional Model</span>
            <span class="text-gray-400 text-xs ml-2">Ideal for professional-level analysis and multi-round debates</span>
          </el-option>
          <el-option :value="5" label="5 Class - Flagship Model (Comprehensive Analysis)">
            <span>5 Class - flagship model</span>
            <span class="text-gray-400 text-xs ml-2">The strongest ability, suitable for comprehensive analysis</span>
          </el-option>
        </el-select>
        <div class="form-tip">
          💡 The capability level determines the upper limit of the depth of analysis that the model can handle.
        </div>
      </el-form-item>

      <el-form-item label="Applicable roles" prop="suitable_roles">
        <el-select
          v-model="formData.suitable_roles"
          multiple
          placeholder="Select the role for which the model applies"
          style="width: 100%"
        >
          <el-option value="quick_analysis" label="Quick analysis">
            <span>Quick analysis</span>
            <span class="text-gray-400 text-xs ml-2">Data collection, tool invocation</span>
          </el-option>
          <el-option value="deep_analysis" label="In-depth analysis">
            <span>In-depth analysis</span>
            <span class="text-gray-400 text-xs ml-2">reasoning, decision-making</span>
          </el-option>
          <el-option value="both" label="suitable for both">
            <span>suitable for both</span>
            <span class="text-gray-400 text-xs ml-2">All-purpose model</span>
          </el-option>
        </el-select>
        <div class="form-tip">
          💡 Quick analysis focuses on data collection, while in-depth analysis focuses on reasoning and decision-making.
        </div>
      </el-form-item>

      <el-form-item label="Recommended analysis depth" prop="recommended_depths">
        <el-select
          v-model="formData.recommended_depths"
          multiple
          placeholder="Select the recommended level of analysis depth"
          style="width: 100%"
        >
          <el-option value="fast" label="Fast (Level 1)">
            <span>Fast (Level 1)</span>
            <span class="text-gray-400 text-xs ml-2">Any model will do</span>
          </el-option>
          <el-option value="Basics" label="Basics (Level 2)">
            <span>Basics (Level 2)</span>
            <span class="text-gray-400 text-xs ml-2">Basic level and above</span>
          </el-option>
          <el-option value="Standard" label="Standard (Level 3)">
            <span>Standard (Level 3)</span>
            <span class="text-gray-400 text-xs ml-2">Standard level and above</span>
          </el-option>
          <el-option value="Depth" label="Depth (Level 4)">
            <span>Depth (Level 4)</span>
            <span class="text-gray-400 text-xs ml-2">Advanced level or above, reasoning ability required</span>
          </el-option>
          <el-option value="Comprehensive" label="Comprehensive (Level 5)">
            <span>Comprehensive (Level 5)</span>
            <span class="text-gray-400 text-xs ml-2">Professional level or above, strong reasoning ability</span>
          </el-option>
        </el-select>
        <div class="form-tip">
          💡 Based on the model capability level, the system will automatically recommend the appropriate analysis depth.
        </div>
      </el-form-item>

      <el-form-item label="Model properties" prop="features">
        <el-select
          v-model="formData.features"
          multiple
          placeholder="Select features supported by the model"
          style="width: 100%"
        >
          <el-option value="tool_calling" label="Tool call">
            <span>Tool call</span>
            <span class="text-gray-400 text-xs ml-2">required characteristics</span>
          </el-option>
          <el-option value="long_context" label="long context">
            <span>long context</span>
            <span class="text-gray-400 text-xs ml-2">Support a large amount of historical information</span>
          </el-option>
          <el-option value="reasoning" label="Strong reasoning ability">
            <span>Strong reasoning ability</span>
            <span class="text-gray-400 text-xs ml-2">Required for in-depth analysis</span>
          </el-option>
          <el-option value="vision" label="visual input">
            <span>visual input</span>
            <span class="text-gray-400 text-xs ml-2">Support chart analysis</span>
          </el-option>
          <el-option value="fast_response" label="Quick response">
            <span>Quick response</span>
            <span class="text-gray-400 text-xs ml-2">Fast response</span>
          </el-option>
          <el-option value="cost_effective" label="Cost effective">
            <span>Cost effective</span>
            <span class="text-gray-400 text-xs ml-2">High cost performance</span>
          </el-option>
        </el-select>
        <div class="form-tip">
          💡 Tool calling is a required feature, and reasoning capabilities are important for in-depth analysis
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">Cancel</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="loading">
          {{ isEdit ? 'update' : 'add' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { configApi, type LLMProvider, type LLMConfig, validateLLMConfig } from '@/api/config'

// Props
interface Props {
  visible: boolean
  config?: LLMConfig | null
}

const props = withDefaults(defineProps<Props>(), {
  config: null
})

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

// Refs
const formRef = ref<FormInstance>()
const loading = ref(false)
const providersLoading = ref(false)
const availableProviders = ref<LLMProvider[]>([])

// Computed
const isEdit = computed(() => !!props.config)

// form data
const defaultFormData = {
  provider: '',
  model_name: '',
  model_display_name: '',  // New: Model display name
  api_base: '',
  max_tokens: 8000,
  temperature: 0.2,  // Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
  timeout: 180,  // Default timeout changed to 180 seconds
  retry_times: 3,
  enabled: true,
  enable_memory: false,
  enable_debug: false,
  priority: 0,
  model_category: '',
  description: '',
  input_price_per_1k: 0,
  output_price_per_1k: 0,
  currency: 'CNY',
  // 🆕 Model capability configuration
  capability_level: 2,  // Default standard level
  suitable_roles: ['both'],  // Both are suitable by default
  features: ['tool_calling'],  // Support tool calling by default
  recommended_depths: ['fast', 'Basics', 'Standard'],  // Level 1-3 analysis is recommended by default
  performance_metrics: {
    speed: 3,
    cost: 3,
    quality: 3
  }
}

const formData = ref({ ...defaultFormData })

const normalizePerformanceMetrics = (metrics?: { speed?: number; cost?: number; quality?: number }) => ({
  speed: metrics?.speed ?? defaultFormData.performance_metrics.speed,
  cost: metrics?.cost ?? defaultFormData.performance_metrics.cost,
  quality: metrics?.quality ?? defaultFormData.performance_metrics.quality,
})

// Model used to track the current selection (used in dropdown lists)
const selectedModelKey = ref<string>('')

// form validation rules
const rules: FormRules = {
  provider: [{ required: true, message: 'Please select a supplier', trigger: 'change' }],
  model_name: [{ required: true, message: 'Please enter model name', trigger: 'blur' }],
  max_tokens: [{ required: true, message: 'Please enter the maximum number of Tokens', trigger: 'blur' }],
  temperature: [{ required: true, message: 'Please enter temperature parameters', trigger: 'blur' }],
  timeout: [{ required: true, message: 'Please enter the timeout', trigger: 'blur' }],
  retry_times: [{ required: true, message: 'Please enter the number of retries', trigger: 'blur' }],
  priority: [{ required: true, message: 'Please enter priority', trigger: 'blur' }]
}

// Model options
const modelOptions = ref<Array<{ label: string; value: string }>>([])

// Model directory obtained from the backend (contains complete information)
interface ModelInfo {
  name: string
  display_name: string
  description?: string
  context_length?: number
  max_tokens?: number
  input_price_per_1k?: number
  output_price_per_1k?: number
  currency?: string
  is_deprecated?: boolean
  release_date?: string
  capabilities?: string[]
}

const modelCatalog = ref<Record<string, Array<ModelInfo>>>({})

// Load model directory
const loadModelCatalog = async () => {
  try {
    const catalog = await configApi.getModelCatalog()
    // Convert to provider -> models mapping
    const catalogMap: Record<string, Array<ModelInfo>> = {}
    catalog.forEach(item => {
      catalogMap[item.provider] = item.models
    })
    modelCatalog.value = catalogMap
    console.log('✅ Model directory loaded successfully:', Object.keys(catalogMap))
  } catch (error) {
    console.error('❌ Failed to load model directory:', error)
    ElMessage.warning('Failed to load model list, default list will be used')
    // Use an empty directory on failure, allowing manual user input
    modelCatalog.value = {}
  }
}

// Get model options based on supplier
const getModelOptions = (provider: string) => {
  // Prioritize searching in the directory obtained from the backend
  const models = modelCatalog.value[provider]
  if (models && models.length > 0) {
    return models.map(m => ({
      label: m.display_name,
      value: m.name
    }))
  }

  // If there is no data in the backend, return an empty array (allowing the user to enter manually)
  return []
}

// Get model details based on vendor and model name
const getModelInfo = (provider: string, modelName: string): ModelInfo | null => {
  const models = modelCatalog.value[provider]
  if (!models) return null

  return models.find(m => m.name === modelName) || null
}

// Handle supplier changes
const handleProviderChange = async (provider: string) => {
  // First try to get from the loaded directory
  modelOptions.value = getModelOptions(provider)

  // If the model is not found, reload the model directory
  if (modelOptions.value.length === 0) {
    console.log(`⚠️ supplier ${provider} No model data, reload the model directory...`)
    await loadModelCatalog()
    // Retrieve model options
    modelOptions.value = getModelOptions(provider)

    if (modelOptions.value.length > 0) {
      ElMessage.success(`Loaded ${modelOptions.value.length} available models`)
    } else {
      ElMessage.warning('There are currently no models available from this supplier, please check"Model catalog management"Add in')
    }
  }

  formData.value.model_name = ''
  // Clear price information
  formData.value.input_price_per_1k = 0
  formData.value.output_price_per_1k = 0
  formData.value.currency = 'CNY'
}

// Handling model selection from dropdown list
const handleModelSelect = (modelCode: string) => {
  if (!modelCode) {
    // Clear selection
    selectedModelKey.value = ''
    return
  }

  // Find selected model information
  const selectedModel = modelOptions.value.find(m => m.value === modelCode)
  if (selectedModel) {
    // Automatically populate model code and display name
    formData.value.model_name = selectedModel.value
    formData.value.model_display_name = selectedModel.label

    console.log('📋 Select model:', {
      code: selectedModel.value,
      display_name: selectedModel.label
    })

    // Autofill price information
    const modelInfo = getModelInfo(formData.value.provider, modelCode)
    if (modelInfo) {
      console.log('📋 Automatically populate model information:', modelInfo)

      if (modelInfo.input_price_per_1k !== undefined) {
        formData.value.input_price_per_1k = modelInfo.input_price_per_1k
      }
      if (modelInfo.output_price_per_1k !== undefined) {
        formData.value.output_price_per_1k = modelInfo.output_price_per_1k
      }
      if (modelInfo.currency) {
        formData.value.currency = modelInfo.currency
      }

      ElMessage.success('Model information and price automatically populated')
    } else {
      ElMessage.success('Model name populated')
    }
  }
}

// Listen for configuration changes
watch(
  () => props.config,
  (config) => {
    if (config) {
      // Edit mode: Use default values first, then overwrite them with configuration
      // NOTE: For numeric type fields, even 0 should be retained
      formData.value = {
        ...defaultFormData,
        ...config,
        // Make sure the price field loads correctly, even if it is 0 it is retained
        input_price_per_1k: config.input_price_per_1k ?? defaultFormData.input_price_per_1k,
        output_price_per_1k: config.output_price_per_1k ?? defaultFormData.output_price_per_1k,
        currency: config.currency || defaultFormData.currency,
        // Make sure display names are loaded correctly
        model_display_name: config.model_display_name || '',
        // 🆕 Ensure model capability fields are loaded correctly
        capability_level: config.capability_level ?? defaultFormData.capability_level,
        suitable_roles: config.suitable_roles || defaultFormData.suitable_roles,
        features: config.features || defaultFormData.features,
        recommended_depths: config.recommended_depths || defaultFormData.recommended_depths,
        performance_metrics: normalizePerformanceMetrics(config.performance_metrics)
      }
      modelOptions.value = getModelOptions(config.provider)

      // If there is a model_name, try selecting it in the dropdown
      if (config.model_name) {
        selectedModelKey.value = config.model_name
      }

      console.log('📝 Load configuration in edit mode:', formData.value)
    } else {
      formData.value = { ...defaultFormData }
      modelOptions.value = getModelOptions('dashscope')
      selectedModelKey.value = ''
    }
  },
  { immediate: true }
)

// Monitor visible changes
watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      // Refresh the supplier list and model catalog when the dialog opens to ensure the latest data is displayed
      await Promise.all([
        loadProviders(),
        loadModelCatalog()
      ])

      if (props.config) {
        // Edit mode: Use default values first, then overwrite them with configuration
        formData.value = {
          ...defaultFormData,
          ...props.config,
          // Make sure the price field loads correctly, even if it is 0 it is retained
          input_price_per_1k: props.config.input_price_per_1k ?? defaultFormData.input_price_per_1k,
          output_price_per_1k: props.config.output_price_per_1k ?? defaultFormData.output_price_per_1k,
          currency: props.config.currency || defaultFormData.currency,
          // Make sure display names are loaded correctly
          model_display_name: props.config.model_display_name || '',
          // 🆕 Ensure model capability fields are loaded correctly
          capability_level: props.config.capability_level ?? defaultFormData.capability_level,
          suitable_roles: props.config.suitable_roles || defaultFormData.suitable_roles,
          features: props.config.features || defaultFormData.features,
          recommended_depths: props.config.recommended_depths || defaultFormData.recommended_depths,
          performance_metrics: normalizePerformanceMetrics(props.config.performance_metrics)
        }
        modelOptions.value = getModelOptions(props.config.provider)

        // If there is a model_name, try selecting it in the dropdown
        if (props.config.model_name) {
          selectedModelKey.value = props.config.model_name
        }

        console.log('📝 The dialog box opens and the configuration is loaded.:', formData.value)
      } else {
        // New mode: use default value
        formData.value = { ...defaultFormData }
        // If there is a supplier, load its model list
        if (formData.value.provider) {
          modelOptions.value = getModelOptions(formData.value.provider)
        } else {
          modelOptions.value = []
        }
        selectedModelKey.value = ''
      }
    }
  }
)

// Handle visibility changes
const handleVisibleChange = (value: boolean) => {
  emit('update:visible', value)
}

// processing closed
const handleClose = () => {
  emit('update:visible', false)
  formRef.value?.resetFields()
}

// Handle submission
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()

    // Verify configuration data
    const errors = validateLLMConfig(formData.value)
    if (errors.length > 0) {
      ElMessage.error(`Configuration verification failed: ${errors.join(', ')}`)
      return
    }

    loading.value = true

    // Prepare to submit data and remove the api_key field (obtained from the manufacturer configuration by the backend)
    const submitData = { ...formData.value }
    // Use a type-safe way to remove the api_key field (if it exists)
    if ('api_key' in submitData) {
      delete (submitData as any).api_key  // Do not send api_key, let the backend obtain it from the manufacturer configuration
    }

    console.log('🚀 Submit large model configuration:', submitData)

    // call API
    await configApi.updateLLMConfig(submitData)

    ElMessage.success(isEdit.value ? 'Model configuration updated successfully' : 'Model configuration added successfully')
    emit('success')
    handleClose()
  } catch (error) {
    console.error('❌ Failed to submit large model configuration:', error)
    ElMessage.error(isEdit.value ? 'Model configuration update failed' : 'Model configuration failed to add')
  } finally {
    loading.value = false
  }
}

// Load a list of available manufacturers
const loadProviders = async (showSuccessMessage = false) => {
  providersLoading.value = true
  try {
    const providers = await configApi.getLLMProviders()
    // Only show enabled manufacturers
    availableProviders.value = providers.filter(p => p.is_active)
    console.log('✅ Loading manufacturer list successfully:', availableProviders.value.length)

    if (showSuccessMessage) {
      ElMessage.success(`The supplier list has been refreshed, a total of ${availableProviders.value.length} enabled vendors`)
    }

    // If it is a new mode and no supplier is selected, the first one will be selected by default.
    if (!isEdit.value && !formData.value.provider && availableProviders.value.length > 0) {
      formData.value.provider = availableProviders.value[0].name
      await handleProviderChange(formData.value.provider)
    }
  } catch (error) {
    console.error('❌ Failed to load manufacturer list:', error)
    ElMessage.error('Failed to load manufacturer list')
  } finally {
    providersLoading.value = false
  }
}

// Load the manufacturer data and model directory when mounting the component
onMounted(() => {
  loadProviders()
  loadModelCatalog()
})
</script>

<style lang="scss" scoped>
.dialog-footer {
  text-align: right;
}

.ml-2 {
  margin-left: 8px;
}

.text-gray-500 {
  color: #6b7280;
  font-size: 12px;
}

.text-gray-400 {
  color: #9ca3af;
}

.text-xs {
  font-size: 11px;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}

// 🆕 Model capability configuration style
:deep(.el-select-dropdown__item) {
  height: auto;
  line-height: 1.5;
  padding: 8px 20px;

  span {
    display: inline-block;
  }
}
</style>
