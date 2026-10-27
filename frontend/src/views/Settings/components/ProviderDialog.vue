<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? 'Edit manufacturer information' : 'Add manufacturer'"
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
      <!-- Default manufacturer selection -->
      <el-form-item v-if="!isEdit" label="Quick selection">
        <el-select
          v-model="selectedPreset"
          placeholder="Select a default manufacturer or fill in manually"
          clearable
          @change="handlePresetChange"
        >
          <el-option
            v-for="preset in presetProviders"
            :key="preset.name"
            :label="preset.display_name"
            :value="preset.name"
          />
        </el-select>
      </el-form-item>

      <!-- 🆕 Registration guide prompts -->
      <el-alert
        v-if="selectedPreset && currentPresetInfo?.register_url"
        :title="`📝 ${currentPresetInfo.display_name} Registration guide`"
        type="info"
        :closable="false"
        class="mb-4"
      >
        <template #default>
          <div class="register-guide">
            <p>{{ currentPresetInfo.register_guide || 'If you don t have an account yet, please register first:' }}</p>
            <el-button
              type="primary"
              size="small"
              link
              @click="openRegisterUrl"
            >
              <el-icon><Link /></el-icon>
              Go to register {{ currentPresetInfo.display_name }}
            </el-button>
          </div>
        </template>
      </el-alert>

      <el-form-item label="Manufacturer ID" prop="name">
        <el-input 
          v-model="formData.name" 
          placeholder="Such as: openai, anthropic"
          :disabled="isEdit"
        />
        <div class="form-tip">The unique identifier of the manufacturer, which cannot be modified after creation.</div>
      </el-form-item>

      <el-form-item label="display name" prop="display_name">
        <el-input 
          v-model="formData.display_name" 
          placeholder="Such as: OpenAI, Anthropic"
        />
      </el-form-item>

      <el-form-item label="Description" prop="description">
        <el-input 
          v-model="formData.description" 
          type="textarea"
          :rows="3"
          placeholder="Manufacturer profile and features"
        />
      </el-form-item>

      <el-form-item label="Official website" prop="website">
        <el-input 
          v-model="formData.website" 
          placeholder="https://openai.com"
        />
      </el-form-item>

      <el-form-item label="API Documentation" prop="api_doc_url">
        <el-input 
          v-model="formData.api_doc_url" 
          placeholder="https://platform.openai.com/docs"
        />
      </el-form-item>

      <el-form-item label="Default API address" prop="default_base_url">
        <el-input
          v-model="formData.default_base_url"
          placeholder="https://api.openai.com/v1"
        />
      </el-form-item>

      <el-alert
        title="🔒 Safety tips"
        type="info"
        description="Sensitive keys are injected through environment variables/operation configuration. For security reasons, the real keys are not stored or displayed here."
        show-icon
        :closable="false"
        class="mb-2"
      />
      <el-form-item label="Key status">
        <el-tag :type="(props.provider?.extra_config?.has_api_key ? 'success' : 'danger')" size="small">
          {{ props.provider?.extra_config?.has_api_key ? 'configured' : 'Not configured' }}
        </el-tag>
        <el-tag v-if="props.provider?.extra_config?.has_api_key" :type="props.provider?.extra_config?.source === 'environment' ? 'warning' : 'success'" size="small" class="ml-2">
          {{ props.provider?.extra_config?.source === 'environment' ? 'ENV' : 'configured' }}
        </el-tag>
      </el-form-item>

      <!-- 🔥 New: API Key input box -->
      <el-form-item 
        v-if="!isLocalModel" 
        label="API Key" 
        prop="api_key"
      >
        <el-input
          v-model="formData.api_key"
          type="password"
          placeholder="Enter API Key (optional, leave blank to use environment variables)"
          show-password
          clearable
        />
        <div class="form-tip">
          Priority: Database Configuration > environment variables. Leave blank to use the configuration in the .env file
        </div>
      </el-form-item>
      
      <!-- 🔥 Local model hints -->
      <el-alert
        v-if="isLocalModel"
        title="💡 Local model hints"
        type="info"
        :closable="false"
        class="mb-2"
      >
        <template #default>
          <div>
            <p>Local models (such as Ollama, LocalAI) generally do not require an API Key.</p>
            <p v-if="formData.name === 'ollama'">
              • Make sure the Ollama service is running (default address:http://localhost:11434) <br/>
              • Make sure you have downloaded the required models (e.g.:<code>ollama pull qwen2.5</code> or <code>ollama pull nomic-embed-text</code>) 
            </p>
            <p v-if="formData.name === 'localai'">
              • Make sure the LocalAI service is running (default address:http://localhost:8080) <br/>
              • Make sure the LocalAI service is configured and started
            </p>
          </div>
        </template>
      </el-alert>

      <!-- 🔥 New: API Secret input box (required by some manufacturers) -->
      <el-form-item v-if="needsApiSecret" label="API Secret" prop="api_secret">
        <el-input
          v-model="formData.api_secret"
          type="password"
          placeholder="Enter API Secret (optional)"
          show-password
          clearable
        />
        <div class="form-tip">
          Some manufacturers (such as Baidu Qianfan) require additional Secret Key
        </div>
      </el-form-item>

      <el-form-item label="Support functions" prop="supported_features">
        <el-checkbox-group v-model="formData.supported_features">
          <el-checkbox label="chat">dialogue</el-checkbox>
          <el-checkbox label="completion">text completion</el-checkbox>
          <el-checkbox label="embedding">vectorization</el-checkbox>
          <el-checkbox label="image">image generation</el-checkbox>
          <el-checkbox label="vision">Image understanding</el-checkbox>
          <el-checkbox label="function_calling">function call</el-checkbox>
          <el-checkbox label="streaming">Streaming output</el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <!-- 🔥 New: Embedding model configuration (only displayed when embedding function is supported) -->
      <el-form-item 
        v-if="formData.supported_features?.includes('embedding')" 
        label="Embedding model" 
        prop="embedding_model"
      >
        <el-input
          v-model="formData.embedding_model"
          placeholder="Enter the Embedding model name, such as:text-embedding-v3, text-embedding-3-small"
          clearable
        />
        <div class="form-tip">
          💡 If vectorization is supported, configure the Embedding model name. Leave blank to use the default model
        </div>
      </el-form-item>

      <!-- 🔥 New: Test model configuration -->
      <el-form-item label="test model" prop="test_model">
        <el-input
          v-model="formData.test_model"
          placeholder="Enter the test model name, such as:gpt-3.5-turbo, glm-4.5-flash (Leave blank to use system default value)"
          clearable
        />
        <div class="form-tip">
          💡 The model name used when testing API connections. If not filled in, the system will automatically select a default test model based on the manufacturer type.
        </div>
      </el-form-item>

      <el-form-item label="Status">
        <el-switch 
          v-model="formData.is_active"
          active-text="enable"
          inactive-text="Disable"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">Cancel</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ isEdit ? 'update' : 'add' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Link } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { configApi, type LLMProvider } from '@/api/config'

// Form data type (extends LLMProvider, adds temporary fields)
interface ProviderFormData extends Partial<LLMProvider> {
  api_key?: string
  api_secret?: string
}

interface Props {
  visible: boolean
  provider?: Partial<LLMProvider>
}

const props = withDefaults(defineProps<Props>(), {
  provider: () => ({})
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

// form reference
const formRef = ref<FormInstance>()
const submitting = ref(false)
const selectedPreset = ref('')

// Is it in edit mode?
const isEdit = computed(() => !!props.provider?.id)

// Whether API Secret is required (required by some manufacturers)
const needsApiSecret = computed(() => {
  const providersNeedSecret = ['baidu', 'dashscope', 'qianfan']
  return providersNeedSecret.includes(formData.value.name || '')
})

// 🔥 Local model (no API key required)
const isLocalModel = computed(() => {
  const localProviders = ['ollama', 'localai']
  return localProviders.includes(formData.value.name || '')
})

// Currently selected default manufacturer information
const currentPresetInfo = computed(() => {
  if (!selectedPreset.value) return null
  return presetProviders.find(p => p.name === selectedPreset.value)
})

// Open registration link
const openRegisterUrl = () => {
  if (currentPresetInfo.value?.register_url) {
    window.open(currentPresetInfo.value.register_url, '_blank')
  }
}

// Default manufacturer data
const presetProviders = [
  {
    name: 'volcengine',
    display_name: 'Volcano Ark',
    description: 'Volcano Engine Volcano Ark large model service platform, providing bean bags and other models, OpenAI compatible interface',
    website: 'https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    api_doc_url: 'https://docs.volcengine.com/docs/82379/2373738?lang=zh&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    default_base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    embedding_model: 'doubao-embedding-vision-251215',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    register_guide: 'Register and receive 25 million Tokens, go now'
  },
  {
    name: 'volcengine_coding',
    display_name: 'Volcano Ark (Coding)',
    description: 'Volcano Ark Coding dedicated channel for code generation and programming class model access',
    website: 'https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    api_doc_url: 'https://docs.volcengine.com/docs/82379/2373738?lang=zh&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    default_base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    embedding_model: 'doubao-embedding-vision-251215',
    supported_features: ['chat', 'completion', 'function_calling', 'streaming'],
    register_url: 'https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN',
    register_guide: 'Register and receive 25 million Tokens, go now'
  },
  {
    name: 'aihubmix',
    display_name: 'AIHubMix',
    description: 'AIHubMix Deeply adapted to the world s top models such as OpenAI, Claude, Gemini, DeepSeek, Zhipu, Qianwen, etc., multi-model cross-validation makes analysis conclusions more reliable; unlimited concurrency is always online, and A-share market conditions can be analyzed at any time without lag or queues; multiple free models such as coding-glm-5.1-free are built-in to experience AI analysis at zero cost; pay-as-you-go, price transparency, long-term use cost-effectiveness far exceeds that of a single manufacturer.',
    website: 'https://aihubmix.com/?aff=2rIi',
    api_doc_url: 'https://docs.aihubmix.com/cn/quick-start',
    default_base_url: 'https://aihubmix.com/v1',
    supported_features: ['chat', 'completion', 'embedding', 'vision', 'function_calling', 'streaming'],
    register_url: 'https://aihubmix.com/?aff=2rIi',
    register_guide: 'If you don t have an AIHubMix account yet, please register first and get the API Key:'
  },
  {
    name: 'dashscope',
    display_name: 'Alibaba Cloud Bailian',
    description: 'Alibaba Cloud Bailian large model service platform provides Tongyi Qianwen and other models',
    website: 'https://bailian.console.aliyun.com',
    api_doc_url: 'https://help.aliyun.com/zh/dashscope/',
    default_base_url: 'https://dashscope.aliyuncs.com/api/v1',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://account.aliyun.com/register/qr_register.htm',
    register_guide: 'If you do not have an Alibaba Cloud account, please register and activate the Bailian service first:'
  },
  {
    name: '302ai',
    display_name: '302.AI',
    description: '302.AI It is an enterprise-level AI aggregation platform that provides unified interfaces for a variety of mainstream large models.',
    website: 'https://302.ai',
    api_doc_url: 'https://doc.302.ai',
    default_base_url: 'https://api.302.ai/v1',
    supported_features: ['chat', 'completion', 'embedding', 'image', 'vision', 'function_calling', 'streaming'],
    register_url: 'https://share.302.ai/DUjftK',
    register_guide: 'If you don t have a 302.AI account yet, please register first and get the API Key:'
  },
  {
    name: 'deepseek',
    display_name: 'DeepSeek',
    description: 'DeepSeek Provide high-performance AI inference services',
    website: 'https://www.deepseek.com',
    api_doc_url: 'https://platform.deepseek.com/api-docs',
    default_base_url: 'https://api.deepseek.com',
    supported_features: ['chat', 'completion', 'function_calling', 'streaming'],
    register_url: 'https://platform.deepseek.com/sign_up',
    register_guide: 'If you don t have a DeepSeek account yet, please register first and get the API Key:'
  },
  {
    name: 'openai',
    display_name: 'OpenAI',
    description: 'OpenAI Is a leading company in the field of artificial intelligence, providing GPT series models',
    website: 'https://openai.com',
    api_doc_url: 'https://platform.openai.com/docs',
    default_base_url: 'https://api.openai.com/v1',
    supported_features: ['chat', 'completion', 'embedding', 'image', 'vision', 'function_calling', 'streaming'],
    register_url: 'https://platform.openai.com/signup',
    register_guide: 'If you don t have an OpenAI account yet, please register first and get an API Key:'
  },
  {
    name: 'anthropic',
    display_name: 'Anthropic',
    description: 'Anthropic Focus on AI security research and provide Claude series models',
    website: 'https://anthropic.com',
    api_doc_url: 'https://docs.anthropic.com',
    default_base_url: 'https://api.anthropic.com',
    supported_features: ['chat', 'completion', 'function_calling', 'streaming'],
    register_url: 'https://console.anthropic.com/signup',
    register_guide: 'If you don t have an Anthropic account yet, please register first and get an API Key:'
  },
  {
    name: 'google',
    display_name: 'Google AI',
    description: 'Google Artificial intelligence platform, providing Gemini series models',
    website: 'https://ai.google.dev',
    api_doc_url: 'https://ai.google.dev/docs',
    default_base_url: 'https://generativelanguage.googleapis.com/v1',
    supported_features: ['chat', 'completion', 'embedding', 'vision', 'function_calling', 'streaming'],
    register_url: 'https://makersuite.google.com/app/apikey',
    register_guide: 'If you don t have a Google AI account yet, please log in to your Google account first and get the API Key:'
  },
  {
    name: 'azure',
    display_name: 'Azure OpenAI',
    description: 'Microsoft Azure OpenAI services on the platform',
    website: 'https://azure.microsoft.com/en-us/products/ai-services/openai-service',
    api_doc_url: 'https://learn.microsoft.com/en-us/azure/ai-services/openai/',
    default_base_url: 'https://your-resource.openai.azure.com',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://azure.microsoft.com/en-us/free/',
    register_guide: 'If you don t have an Azure account yet, please register and apply for the Azure OpenAI service:'
  },
  {
    name: 'zhipu',
    display_name: 'Wisdom spectrum AI',
    description: 'Zhipu AI provides GLM series Chinese large models',
    website: 'https://zhipuai.cn',
    api_doc_url: 'https://open.bigmodel.cn/doc',
    default_base_url: 'https://open.bigmodel.cn/api/paas/v4',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://open.bigmodel.cn/login',
    register_guide: 'If you do not have a Zhipu AI account, please register first and obtain the API Key:'
  },
  {
    name: 'baidu',
    display_name: 'Baidu Smart Cloud',
    description: 'AI services such as Wen Xin Yi Yan provided by Baidu',
    website: 'https://cloud.baidu.com',
    api_doc_url: 'https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html',
    default_base_url: 'https://aip.baidubce.com',
    supported_features: ['chat', 'completion', 'embedding', 'streaming'],
    register_url: 'https://login.bce.baidu.com/new-reg',
    register_guide: 'If you do not have a Baidu Smart Cloud account, please register and activate Wenxin Yiyan service first:'
  },
  {
    name: 'ollama',
    display_name: 'Ollama (local model)',
    description: 'Ollama It is a tool for running large models locally. It is completely offline and does not require API Key',
    website: 'https://ollama.com',
    api_doc_url: 'https://github.com/ollama/ollama/blob/main/docs/api.md',
    default_base_url: 'http://localhost:11434/v1',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://ollama.com/download',
    register_guide: 'Please download and install Ollama first, and then pull the required model (for example: ollama pull qwen2.5)'
  },
  {
    name: 'localai',
    display_name: 'LocalAI (local model)',
    description: 'LocalAI It is an API service for running large models locally and is compatible with OpenAI API',
    website: 'https://localai.io',
    api_doc_url: 'https://localai.io/basics/getting_started/',
    default_base_url: 'http://localhost:8080/v1',
    supported_features: ['chat', 'completion', 'embedding', 'function_calling', 'streaming'],
    register_url: 'https://localai.io/basics/installation/',
    register_guide: 'Please install and start the LocalAI service first, and then configure the API address'
  },
  {
    name: 'openai_compatible',
    display_name: 'OpenAI Compatible (Universal)',
    description: 'Universal OpenAI compatible API service, suitable for any service provider compatible with the OpenAI API format',
    website: '',
    api_doc_url: 'https://platform.openai.com/docs',
    default_base_url: '',
    supported_features: ['chat', 'completion', 'embedding', 'image', 'vision', 'function_calling', 'streaming'],
    register_url: '',
    register_guide: 'Please configure the API address and key of your OpenAI compatible service'
  }
]

// form data
const formData = ref<ProviderFormData>({
  name: '',
  display_name: '',
  description: '',
  website: '',
  api_doc_url: '',
  default_base_url: '',
  api_key: '',
  api_secret: '',
  embedding_model: '',  // 🔥 New: Embedding model field
  test_model: '',  // 🔥 New: Test model fields
  supported_features: [],
  is_active: true
})

// form validation rules
const rules: FormRules = {
  name: [
    { required: true, message: 'Please enter manufacturer ID', trigger: 'blur' },
    { pattern: /^[a-z0-9_-]+$/, message: 'Can only contain lowercase letters, numbers, underscores, and hyphens', trigger: 'blur' }
  ],
  display_name: [
    { required: true, message: 'Please enter a display name', trigger: 'blur' }
  ],
  supported_features: [
    { type: 'array', min: 1, message: 'Please select at least one supported feature', trigger: 'change' }
  ]
}

// Reset form
const resetForm = () => {
  formData.value = {
    name: '',
    display_name: '',
    description: '',
    website: '',
    api_doc_url: '',
    default_base_url: '',
    api_key: '',
    api_secret: '',
    embedding_model: '',  // 🔥 New: Embedding model field
    test_model: '',  // 🔥 New: Test model fields
    supported_features: [],
    is_active: true
  }
  selectedPreset.value = ''
}

// Monitor props changes and update form data
watch(() => props.provider, (newProvider) => {
  if (newProvider && Object.keys(newProvider).length > 0) {
    formData.value = { ...newProvider }
  } else {
    resetForm()
  }
}, { immediate: true, deep: true })

// Handle preset selections
const handlePresetChange = (presetName: string) => {
  if (!presetName) return

  const preset = presetProviders.find(p => p.name === presetName)
  if (preset) {
    formData.value = {
      ...preset,
      is_active: true
    }
  }
}

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
  try {
    await formRef.value?.validate()
    submitting.value = true

    // 🔥 Modification: Handling the submission logic of API Key
    const payload: any = { ...formData.value }

    // Process API Key
    if ('api_key' in payload) {
      const apiKey = payload.api_key || ''

      // If it is a truncated key (containing "...") , Indicates that the user has not modified the field and deletes the field (does not update)
      if (apiKey.includes('...')) {
        delete payload.api_key
      }
      // If it is a placeholder, delete the field (do not update)
      else if (apiKey.startsWith('your_') || apiKey.startsWith('your-')) {
        delete payload.api_key
      }
      // If it is an empty string, keep it (indicating that the user wants to clear the key)
      // If it is a valid full key, keep it (indicating that the user wants to update the key)
    }

    // Handle API Secret (same logic)
    if ('api_secret' in payload) {
      const apiSecret = payload.api_secret || ''

      if (apiSecret.includes('...') || apiSecret.startsWith('your_') || apiSecret.startsWith('your-')) {
        delete payload.api_secret
      }
    }

    if (isEdit.value) {
      await configApi.updateLLMProvider(formData.value.id!, payload)
      ElMessage.success('Manufacturer information updated successfully')
    } else {
      await configApi.addLLMProvider(payload)
      ElMessage.success('Manufacturer added successfully')
    }

    emit('success')
    handleClose()
  } catch (error) {
    console.error('Submission failed:', error)
    ElMessage.error(isEdit.value ? 'Update failed' : 'Add failed')
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.form-tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}

.dialog-footer {
  text-align: right;
}

.mb-4 {
  margin-bottom: 16px;
}

.register-guide {
  p {
    margin: 0 0 12px 0;
    font-size: 15px;
    line-height: 1.6;
    color: var(--el-text-color-regular);
  }

  :deep(.el-button) {
    font-size: 15px;
    padding: 8px 16px;
  }
}
</style>
