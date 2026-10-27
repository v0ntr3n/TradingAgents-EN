<template>
  <div class="model-catalog-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Model catalog management</span>
          <el-button type="primary" @click="handleAdd">
            <el-icon><Plus /></el-icon>
            Add manufacturer model directory
          </el-button>
        </div>
      </template>

      <el-alert
        title="Description"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        The model catalog is used to provide an optional list of models when adding a large model configuration. You can manage the models supported by each manufacturer here.
      </el-alert>

      <el-table
        :data="catalogs"
        v-loading="loading"
        border
        style="width: 100%"
      >
        <el-table-column prop="provider" label="Manufacturer s logo" width="150" />
        <el-table-column prop="provider_name" label="Manufacturer name" width="150" />
        <el-table-column label="Number of models" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.models.length }} models</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Model list">
          <template #default="{ row }">
            <el-tag
              v-for="model in row.models.slice(0, 3)"
              :key="model.name"
              size="small"
              style="margin-right: 5px"
            >
              {{ model.display_name }}
            </el-tag>
            <span v-if="row.models.length > 3">
              ... Also {{ row.models.length - 3 }} a
            </span>
          </template>
        </el-table-column>
        <el-table-column label="Update time" width="180">
          <template #default="{ row }">
            {{ formatDate(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="handleEdit(row)"
            >
              Edit
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              Delete
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? 'Edit model directory' : 'Add model directory'"
      width="1200px"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item label="Manufacturer s logo" prop="provider">
          <div style="display: flex; gap: 8px; align-items: flex-start;">
            <el-select
              v-model="formData.provider"
              placeholder="Please select manufacturer"
              :disabled="isEdit"
              filterable
              @change="handleProviderChange"
              style="flex: 1"
            >
              <el-option
                v-for="provider in availableProviders"
                :key="provider.name"
                :label="`${provider.display_name} (${provider.name})`"
                :value="provider.name"
              />
            </el-select>
            <el-button
              :icon="Refresh"
              :loading="providersLoading"
              @click="() => loadProviders(true)"
              title="Refresh manufacturer list"
            />
          </div>
          <div class="form-tip">
            Select the configured manufacturer. If you do not find the required manufacturer, please first"Factory management"Add it in and click the refresh button
          </div>
        </el-form-item>
        <el-form-item label="Manufacturer name" prop="provider_name">
          <el-input
            v-model="formData.provider_name"
            placeholder="Such as: Tongyi Qianwen"
            :disabled="true"
          />
          <div class="form-tip">
            Automatically obtained from selected manufacturers
          </div>
        </el-form-item>
        <el-form-item label="Model list">
          <div style="margin-bottom: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
            <el-button
              type="primary"
              size="small"
              @click="handleAddModel"
            >
              <el-icon><Plus /></el-icon>
              Add model manually
            </el-button>

            <!-- 🔥 New: Import model directory (for current manufacturers) -->
            <el-button
              type="warning"
              size="small"
              @click="handleImportForProvider"
              :loading="importingForProvider"
            >
              <el-icon><Upload /></el-icon>
              Import model directory
            </el-button>

            <!-- 🔥 New: Export model directory (for current manufacturers) -->
            <el-button
              type="success"
              size="small"
              @click="handleExportForProvider"
              :loading="exportingForProvider"
              :disabled="!formData.provider || formData.models.length === 0"
            >
              <el-icon><Download /></el-icon>
              Export model directory
            </el-button>

            <!-- Special functions of aggregation platform -->
            <template v-if="isAggregatorProvider">
              <el-button
                type="success"
                size="small"
                @click="handleFetchModelsFromAPI"
                :loading="fetchingModels"
              >
                <el-icon><Refresh /></el-icon>
                Get a list of models from the API
              </el-button>
              <el-button
                type="info"
                size="small"
                @click="handleUsePresetModels"
              >
                <el-icon><Document /></el-icon>
                Use preset templates
              </el-button>
            </template>
          </div>

          <el-alert
            title="💡 Important tips"
            type="info"
            :closable="false"
            style="margin-bottom: 10px"
          >
            <div>
              <p style="margin: 0 0 8px 0;"><strong>Model catalog update instructions:</strong></p>
              <ul style="margin: 0 0 8px 20px; padding: 0;">
                <li>The model catalog is only used to provide a list of optional models when adding a large model configuration</li>
                <li>Import or update model catalog<strong>will not affect</strong>Configured large model configuration</li>
                <li>Large configured models still work fine even if the model is removed from the catalog</li>
                <li><strong>Export function:</strong>You can export the current manufacturer s model directory as a JSON file and share it with other users.</li>
                <li><strong>Import function:</strong>A single manufacturer s model directory can be imported from a JSON file</li>
                <li><strong>Import mode description:</strong>
                  <ul style="margin: 4px 0 0 20px; padding: 0;">
                    <li><strong>update (Recommended)</strong>: Update existing models, add new models,<strong>Keep the models in the original model that are not in the new data</strong> (will not be deleted)</li>
                    <li><strong>replace</strong>: Replace the entire directory (models in the original model that are not in the new data will be deleted)</li>
                    <li><strong>append</strong>: Only append new models (do not update existing models)</li>
                  </ul>
                </li>
                <li>If you need to delete outdated models, please use update mode to manually delete unnecessary models after importing them.</li>
              </ul>
              <template v-if="isAggregatorProvider">
                <p style="margin: 8px 0 4px 0;"><strong>Special functions of aggregation platform:</strong></p>
                <ul style="margin: 0 0 0 20px; padding: 0;">
                  <li>Click"Get a list of models from the API"Automatically obtain (requires configuring API Key)</li>
                  <li>Click"Use preset templates"Quickly import commonly used models</li>
                  <li>Click"Add model manually"Add one by one</li>
                </ul>
              </template>
            </div>
          </el-alert>

          <el-table :data="formData.models" border max-height="400">
            <el-table-column label="Model name" width="200">
              <template #default="{ row }">
                <el-input
                  v-model="row.name"
                  placeholder="Such as: qwen-turbo"
                  size="small"
                />
              </template>
            </el-table-column>
            <el-table-column label="display name" width="280">
              <template #default="{ row }">
                <el-input
                  v-model="row.display_name"
                  placeholder="Such as: Qwen Turbo - Fast and economical"
                  size="small"
                />
              </template>
            </el-table-column>
            <el-table-column label="Enter price/1K" width="180">
              <template #default="{ row }">
                <div style="display: flex; align-items: center; gap: 4px;">
                  <el-input-number
                    v-model="row.input_price_per_1k"
                    :min="0"
                    :step="0.0001"
                    size="small"
                    :controls="false"
                    style="width: 110px;"
                  />
                  <span style="color: #909399; font-size: 12px; white-space: nowrap;">{{ row.currency || 'CNY' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="output price/1K" width="180">
              <template #default="{ row }">
                <div style="display: flex; align-items: center; gap: 4px;">
                  <el-input-number
                    v-model="row.output_price_per_1k"
                    :min="0"
                    :step="0.0001"
                    size="small"
                    :controls="false"
                    style="width: 110px;"
                  />
                  <span style="color: #909399; font-size: 12px; white-space: nowrap;">{{ row.currency || 'CNY' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="context length" width="150">
              <template #default="{ row }">
                <el-input
                  v-model.number="row.context_length"
                  placeholder="1000000"
                  size="small"
                  type="number"
                />
              </template>
            </el-table-column>
            <el-table-column label="currency unit" width="120">
              <template #default="{ row }">
                <el-select
                  v-model="row.currency"
                  size="small"
                  placeholder="Select currency"
                >
                  <el-option label="CNY" value="CNY" />
                  <el-option label="USD" value="USD" />
                  <el-option label="EUR" value="EUR" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="100" fixed="right">
              <template #default="{ $index }">
                <el-button
                  type="danger"
                  size="small"
                  @click="handleRemoveModel($index)"
                >
                  Delete
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          save
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="fetchDialogVisible"
      title="Get a list of models from the API"
      width="1200px"
      append-to-body
    >
      <el-form :model="fetchForm" label-width="110px">
        <el-form-item
          v-if="fetchingProvider?.name === 'aihubmix'"
          label="model manufacturer"
        >
          <el-select
            v-model="fetchForm.provider_names"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="Please select the model manufacturer to retain"
            style="width: 100%"
          >
            <el-option
              v-for="option in aihubmixProviderOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="form-tip">You can select multiple options, such as keeping OpenAI, DeepSeek, and Qwen at the same time.</div>
        </el-form-item>

        <el-form-item label="Model keywords">
          <el-input
            v-model="fetchForm.model_keyword"
            placeholder="Optional, fuzzy filter by model name"
            clearable
          />
        </el-form-item>

        <el-form-item label="Return quantity">
          <el-input-number
            v-model="fetchForm.limit"
            :min="1"
            :max="200"
          />
        </el-form-item>

        <el-form-item label="Additional filtering">
          <div style="display: flex; gap: 16px; flex-wrap: wrap;">
            <el-checkbox v-model="fetchForm.tools_only">Tool calls only</el-checkbox>
            <el-checkbox v-model="fetchForm.exclude_preview">Exclude preview/test models</el-checkbox>
            <el-checkbox v-model="fetchForm.recommended_only">Only mainstream models are recommended</el-checkbox>
          </div>
        </el-form-item>
      </el-form>

      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <div class="form-tip">
          returned {{ fetchedModels.length }} models, selected {{ selectedFetchedModels.length }} a
        </div>
        <div style="display: flex; gap: 8px;">
          <el-button size="small" @click="handleSelectAllFetchedModels" :disabled="fetchedModels.length === 0">Select all</el-button>
          <el-button size="small" @click="handleClearFetchedModelsSelection" :disabled="selectedFetchedModels.length === 0">Clear selection</el-button>
          <el-button type="primary" size="small" @click="handleRunFetchModels" :loading="fetchingModels">Pull model</el-button>
        </div>
      </div>

      <el-table
        ref="fetchedModelsTableRef"
        :data="fetchedModels"
        border
        max-height="420"
        @selection-change="handleFetchedModelsSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="name" label="Model name" min-width="220" />
        <el-table-column prop="provider_vendor" label="model manufacturer" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ providerVendorLabelMap[row.provider_vendor] || row.provider_vendor || 'Others' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="context_length" label="context" width="120" />
        <el-table-column prop="input_price_per_1k" label="input/1K" width="110" />
        <el-table-column prop="output_price_per_1k" label="output/1K" width="110" />
        <el-table-column label="Ability" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="cap in (row.capabilities || []).slice(0, 3)"
              :key="cap"
              size="small"
              style="margin-right: 4px;"
            >
              {{ cap }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="fetchDialogVisible = false">Cancel</el-button>
        <el-button
          type="primary"
          @click="handleImportFetchedModels"
          :disabled="selectedFetchedModels.length === 0"
        >
          Import selected model
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Document, Download, Upload } from '@element-plus/icons-vue'
import { configApi, type FetchProviderModelsFilters, type LLMProvider } from '@/api/config'

// data
const loading = ref(false)
const catalogs = ref<any[]>([])
const dialogVisible = ref(false)
const fetchDialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
const availableProviders = ref<LLMProvider[]>([])
const providersLoading = ref(false)
const fetchingModels = ref(false)
const fetchingProvider = ref<LLMProvider | null>(null)
const fetchedModels = ref<any[]>([])
const selectedFetchedModels = ref<any[]>([])
const fetchedModelsTableRef = ref()
const importingForProvider = ref(false)
const exportingForProvider = ref(false)

// List of aggregation platforms
const aggregatorProviders = ['302ai', 'aihubmix', 'oneapi', 'newapi', 'openrouter', 'volcengine', 'volcengine_coding', 'custom_aggregator']

// Computed attributes: Determine whether the currently selected one is an aggregation platform
const isAggregatorProvider = computed(() => {
  return aggregatorProviders.includes(formData.value.provider)
})

interface ModelInfo {
  name: string
  display_name: string
  input_price_per_1k?: number | null
  output_price_per_1k?: number | null
  context_length?: number | null
  max_tokens?: number | null
  currency?: string
  description?: string
  is_deprecated?: boolean
  release_date?: string
  capabilities?: string[]
}

interface FetchDialogForm extends FetchProviderModelsFilters {
  provider_names: string[]
}

const formData = ref({
  provider: '',
  provider_name: '',
  models: [] as ModelInfo[]
})

const fetchForm = ref<FetchDialogForm>({
  type: 'llm',
  modalities: 'text',
  features: [],
  provider_names: [],
  model_keyword: '',
  sort_by: 'order',
  sort_order: 'asc',
  limit: 40,
  recommended_only: false,
  tools_only: false,
  exclude_preview: false
})

const aihubmixProviderOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Google', value: 'google' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'Qwen', value: 'qwen' },
  { label: 'GLM', value: 'glm' },
  { label: 'Kimi', value: 'kimi' },
  { label: 'bean bag', value: 'doubao' },
  { label: 'MiniMax', value: 'minimax' },
  { label: 'Mistral', value: 'mistral' },
  { label: 'Meta', value: 'meta' },
  { label: 'Jina', value: 'jina' }
]

const providerVendorLabelMap: Record<string, string> = Object.fromEntries(
  aihubmixProviderOptions.map(option => [option.value, option.label])
)

const rules: FormRules = {
  provider: [{ required: true, message: 'Please enter manufacturer ID', trigger: 'blur' }],
  provider_name: [{ required: true, message: 'Please enter manufacturer name', trigger: 'blur' }]
}

// method
const loadCatalogs = async () => {
  loading.value = true
  try {
    const response = await configApi.getModelCatalog()
    catalogs.value = sortCatalogsByNewest(response)
  } catch (error) {
    console.error('Failed to load model directory:', error)
    ElMessage.error('Failed to load model directory')
  } finally {
    loading.value = false
  }
}

const sortCatalogsByNewest = (catalogList: any[]) => {
  const getTimestamp = (catalog: any) => {
    const timeValue = catalog.created_at || catalog.updated_at
    const timestamp = timeValue ? new Date(timeValue).getTime() : 0
    return Number.isNaN(timestamp) ? 0 : timestamp
  }

  return [...catalogList].sort((a, b) => getTimestamp(b) - getTimestamp(a))
}

// Load a list of available manufacturers
const loadProviders = async (showSuccessMessage = false) => {
  providersLoading.value = true
  try {
    const providers = await configApi.getLLMProviders()
    availableProviders.value = sortProvidersByNewest(providers)
    console.log('✅ Loading manufacturer list successfully:', availableProviders.value.length)
    if (showSuccessMessage) {
      ElMessage.success(`The manufacturer list has been refreshed, a total of ${providers.length} manufacturers`)
    }
  } catch (error) {
    console.error('❌ Failed to load manufacturer list:', error)
    ElMessage.error('Failed to load manufacturer list')
  } finally {
    providersLoading.value = false
  }
}

const sortProvidersByNewest = (providers: LLMProvider[]) => {
  const getTimestamp = (provider: LLMProvider) => {
    const timeValue = provider.created_at || provider.updated_at
    const timestamp = timeValue ? new Date(timeValue).getTime() : 0
    return Number.isNaN(timestamp) ? 0 : timestamp
  }

  return [...providers].sort((a, b) => getTimestamp(b) - getTimestamp(a))
}

// Handle manufacturer selection
const handleProviderChange = (providerName: string) => {
  const provider = availableProviders.value.find(p => p.name === providerName)
  if (provider) {
    formData.value.provider_name = provider.display_name
  }
}

const buildFetchModelFilters = (providerName: string): FetchDialogForm => {
  if (providerName === 'aihubmix') {
    return {
      type: 'llm',
      modalities: 'text',
      features: [],
      provider_names: ['openai', 'deepseek'],
      model_keyword: '',
      sort_by: 'order',
      sort_order: 'asc',
      limit: 40,
      recommended_only: false,
      tools_only: false,
      exclude_preview: false
    }
  }

  return {
    type: 'llm',
    modalities: 'text',
    features: [],
    provider_names: [],
    model_keyword: '',
    sort_by: 'order',
    sort_order: 'asc',
    limit: 40,
    recommended_only: false,
    tools_only: false,
    exclude_preview: false
  }
}

const handleAdd = async () => {
  isEdit.value = false
  formData.value = {
    provider: '',
    provider_name: '',
    models: []
  }
  // Refresh the manufacturer list before opening the dialog box to ensure that the latest added manufacturer is displayed
  await loadProviders()
  dialogVisible.value = true
}

const handleEdit = async (row: any) => {
  isEdit.value = true
  formData.value = {
    provider: row.provider,
    provider_name: row.provider_name,
    models: JSON.parse(JSON.stringify(row.models))
  }
  // Refresh the manufacturer list before opening the dialog box
  await loadProviders()
  dialogVisible.value = true
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete the manufacturer ${row.provider_name} model directory?`,
      'Confirm deletion',
      {
        type: 'warning'
      }
    )
    
    await configApi.deleteModelCatalog(row.provider)
    ElMessage.success('Delete successfully')
    await loadCatalogs()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Delete failed:', error)
      ElMessage.error('Delete failed')
    }
  }
}

const handleAddModel = () => {
  formData.value.models.push({
    name: '',
    display_name: '',
    input_price_per_1k: null,
    output_price_per_1k: null,
    context_length: null,
    currency: 'CNY'
  })
}

const handleRemoveModel = (index: number) => {
  formData.value.models.splice(index, 1)
}

// Get a list of models from the API
const handleFetchModelsFromAPI = async () => {
  try {
    // Check if the manufacturer is selected
    if (!formData.value.provider) {
      ElMessage.warning('Please select the manufacturer first')
      return
    }

    // Get manufacturer information
    const provider = availableProviders.value.find(p => p.name === formData.value.provider)
    if (!provider) {
      ElMessage.error('No manufacturer information found')
      return
    }

    // Check whether it is configured base_url
    if (!provider.default_base_url) {
      ElMessage.warning('This manufacturer has not configured the API base address')
      return
    }

    fetchingProvider.value = provider
    fetchForm.value = buildFetchModelFilters(provider.name)
    fetchedModels.value = []
    selectedFetchedModels.value = []
    fetchDialogVisible.value = true
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to get model list:', error)
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to get model list'
      ElMessage.error(errorMsg)
    }
  }
}

const handleRunFetchModels = async () => {
  if (!fetchingProvider.value) return

  try {
    fetchingModels.value = true
    const requestPayload = {
      ...fetchForm.value,
      features: fetchForm.value.tools_only ? ['tools', 'function_calling'] : fetchForm.value.features
    }
    console.log('🔍 [fetch-models] provider=', fetchingProvider.value)
    console.log('🔍 [fetch-models] payload=', requestPayload)
    const response = await configApi.fetchProviderModels(fetchingProvider.value.id, requestPayload)
    console.log('📦 [fetch-models] response=', response)

    if (response.success && response.models && response.models.length > 0) {
      const mappedModels = response.models.map((model: any) => ({
        name: model.id || model.name,
        display_name: model.name || model.id,
        provider_vendor: normalizeFetchedModelVendor(model.provider_vendor || inferProviderVendor(model.id || model.name)),
        input_price_per_1k: model.input_price_per_1k || null,
        output_price_per_1k: model.output_price_per_1k || null,
        context_length: model.context_length || null,
        max_tokens: model.max_tokens || null,
        description: model.description || '',
        capabilities: model.capabilities || [],
        currency: model.currency || 'USD'
      }))

      const selectedProviders = new Set((fetchForm.value.provider_names || []).map(item => normalizeFetchedModelVendor(item)))
      fetchedModels.value = selectedProviders.size > 0
        ? mappedModels.filter(model => selectedProviders.has(normalizeFetchedModelVendor(model.provider_vendor)))
        : mappedModels

      selectedFetchedModels.value = []
      if (fetchedModels.value.length === 0) {
        ElMessage.warning('The model has been pulled, but there are no matching results after filtering by current manufacturer. Please adjust the filtering conditions.')
        return
      }
      ElMessage.success(`Pulled successfully ${fetchedModels.value.length} model, please select it and import it.`)
    } else {
      fetchedModels.value = []
      selectedFetchedModels.value = []
      ElMessage.error(response.message || 'Failed to get the model list or the list is empty')
    }
  } catch (error: any) {
    console.error('Failed to get model list:', error)
    const errorMsg = error.response?.data?.detail || error.message || 'Failed to get model list'
    ElMessage.error(errorMsg)
  } finally {
    fetchingModels.value = false
  }
}

const handleFetchedModelsSelectionChange = (rows: any[]) => {
  selectedFetchedModels.value = rows
}

const handleSelectAllFetchedModels = () => {
  fetchedModelsTableRef.value?.toggleAllSelection?.()
}

const handleClearFetchedModelsSelection = () => {
  fetchedModelsTableRef.value?.clearSelection?.()
  selectedFetchedModels.value = []
}

const handleImportFetchedModels = async () => {
  if (selectedFetchedModels.value.length === 0) {
    ElMessage.warning('Please check at least one model')
    return
  }

  const importedModels = selectedFetchedModels.value.map((model: any) => ({
    name: model.name,
    display_name: model.display_name,
    input_price_per_1k: model.input_price_per_1k,
    output_price_per_1k: model.output_price_per_1k,
    context_length: model.context_length,
    max_tokens: model.max_tokens,
    description: model.description,
    capabilities: model.capabilities,
    currency: model.currency || 'USD'
  }))

  const mergedModels = [...formData.value.models]
  const indexByName = new Map(
    mergedModels.map((model, index) => [String(model.name || '').trim().toLowerCase(), index])
  )

  for (const importedModel of importedModels) {
    const modelKey = String(importedModel.name || '').trim().toLowerCase()
    if (!modelKey) continue

    const existingIndex = indexByName.get(modelKey)
    if (existingIndex !== undefined) {
      mergedModels[existingIndex] = {
        ...mergedModels[existingIndex],
        ...importedModel
      }
    } else {
      indexByName.set(modelKey, mergedModels.length)
      mergedModels.push(importedModel)
    }
  }

  formData.value.models = mergedModels

  fetchDialogVisible.value = false
  ElMessage.success(`Imported ${importedModels.length} selected models, currently a total of ${formData.value.models.length} models`)
}

const normalizeFetchedModelVendor = (vendor: string) => {
  return String(vendor || '').trim().toLowerCase()
}

const inferProviderVendor = (modelName: string) => {
  const name = String(modelName || '').toLowerCase()
  if (name.startsWith('gpt-') || name.startsWith('o1') || name.startsWith('o3') || name.startsWith('o4') || name.startsWith('chatgpt-')) return 'openai'
  if (name.startsWith('claude-')) return 'anthropic'
  if (name.startsWith('gemini')) return 'google'
  if (name.startsWith('deepseek')) return 'deepseek'
  if (name.startsWith('qwen')) return 'qwen'
  if (name.startsWith('glm') || name.startsWith('chatglm') || name.startsWith('zhipu')) return 'glm'
  if (name.startsWith('kimi') || name.startsWith('moonshot')) return 'kimi'
  if (name.startsWith('doubao')) return 'doubao'
  if (name.startsWith('minimax') || name.startsWith('mimo-') || name.startsWith('abab')) return 'minimax'
  if (name.startsWith('mistral')) return 'mistral'
  if (name.startsWith('meta/') || name.startsWith('meta-') || name.startsWith('llama-')) return 'meta'
  if (name.startsWith('jina')) return 'jina'
  return 'other'
}

// Import the model directory of the current manufacturer
const handleImportForProvider = () => {
  // Check if the manufacturer is selected
  if (!formData.value.provider) {
    ElMessage.warning('Please select the manufacturer first')
    return
  }

  // Create file input element
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e: Event) => {
    const target = e.target as HTMLInputElement
    const file = target.files?.[0]
    if (!file) return

    try {
      importingForProvider.value = true
      
      // Read file contents
      const text = await file.text()
      let catalogsData: any[]
      
      try {
        catalogsData = JSON.parse(text)
      } catch (parseError) {
        ElMessage.error('JSON File format error, please check the file content')
        return
      }

      // Verify data format
      if (!Array.isArray(catalogsData)) {
        ElMessage.error('Import data format error: should be in array format')
        return
      }

      // Find data for current manufacturer
      const currentProviderCatalog = catalogsData.find(
        (catalog: any) => catalog.provider === formData.value.provider
      )

      if (!currentProviderCatalog) {
        ElMessage.warning(
          `Manufacturer not found in import file "${formData.value.provider}" model directory.` +
          `Manufacturers included in the file:${catalogsData.map((c: any) => c.provider).join(', ')}`
        )
        return
      }

      // Ask user to select merge mode
      const { value: mergeModeInput } = await ElMessageBox.prompt(
        `will be for the manufacturer "${formData.value.provider_name}" import ${currentProviderCatalog.models?.length || 0} model.\n\n` +
        'Please enter the import mode:update / replace / append\n\n' +
        '• update: Update existing models, add new models, retain original models (recommended)\n' +
        '• replace: Replace entire directory\n' +
        '• append: Only append new models',
        'Select import mode',
        {
          confirmButtonText: 'OK',
          cancelButtonText: 'Cancel',
          inputValue: 'update',
          inputPattern: /^(update|replace|append)$/,
          inputErrorMessage: 'Please enter update, replace or append'
        }
      )
      const mergeMode = mergeModeInput as 'update' | 'replace' | 'append'

      // Call the import interface (only import the current manufacturer)
      const response = await configApi.importModelCatalog({
        catalogs: [currentProviderCatalog],
        merge_mode: mergeMode
      })

      if (response.success) {
        const successCount = response.data?.success_count || 0
        const failedCount = response.data?.failed_count || 0
        
        if (successCount > 0) {
          ElMessage.success(`Import successful! success: ${successCount}, failed: ${failedCount}`)
          
          // Show detailed results
          if (response.data?.errors && response.data.errors.length > 0) {
            console.warn('Error during import:', response.data.errors)
            ElMessage.warning(`Partial import failed, please check the console for details`)
          }
          
          // Reload currently edited directory data
          if (isEdit.value) {
            // If it is in edit mode, reacquire the data
            const updatedCatalog = await configApi.getProviderModelCatalog(formData.value.provider)
            if (updatedCatalog) {
              formData.value.models = updatedCatalog.models || []
              ElMessage.info('Model list refreshed')
            }
          } else {
            // If it is a new mode, use the imported data directly.
            if (currentProviderCatalog.models) {
              formData.value.models = currentProviderCatalog.models.map((m: any) => ({
                name: m.name || '',
                display_name: m.display_name || m.name || '',
                input_price_per_1k: m.input_price_per_1k || null,
                output_price_per_1k: m.output_price_per_1k || null,
                context_length: m.context_length || null,
                max_tokens: m.max_tokens || null,
                currency: m.currency || 'CNY',
                description: m.description || '',
                is_deprecated: m.is_deprecated || false,
                release_date: m.release_date || '',
                capabilities: m.capabilities || []
              }))
              ElMessage.info('The imported model list has been loaded, please check and save')
            }
          }
        } else {
          ElMessage.error('Import failed, please check whether the file format and manufacturer identification are correct.')
        }
      } else {
        ElMessage.error(response.message || 'Import failed')
      }
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('Import failed:', error)
        ElMessage.error(error.response?.data?.detail || error.message || 'Import failed')
      }
    } finally {
      importingForProvider.value = false
    }
  }
  
  input.click()
}

// Export the model directory of the current manufacturer
const handleExportForProvider = async () => {
  // Check if the manufacturer is selected
  if (!formData.value.provider) {
    ElMessage.warning('Please select the manufacturer first')
    return
  }

  // Check if there is model data
  if (!formData.value.models || formData.value.models.length === 0) {
    ElMessage.warning('There is currently no model data to export')
    return
  }

  try {
    exportingForProvider.value = true

    // Build export data (data in current dialog box)
    const catalogData = {
      provider: formData.value.provider,
      provider_name: formData.value.provider_name,
      models: formData.value.models.map((m: ModelInfo) => ({
        name: m.name,
        display_name: m.display_name,
        description: m.description || '',
        context_length: m.context_length || null,
        max_tokens: m.max_tokens || null,
        input_price_per_1k: m.input_price_per_1k || null,
        output_price_per_1k: m.output_price_per_1k || null,
        currency: m.currency || 'CNY',
        is_deprecated: m.is_deprecated || false,
        release_date: m.release_date || '',
        capabilities: m.capabilities || []
      }))
    }

    // Convert data to JSON format and download
    const jsonData = JSON.stringify([catalogData], null, 2)
    const blob = new Blob([jsonData], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    
    // Generate file name: manufacturer name_date.json
    const dateStr = new Date().toISOString().split('T')[0]
    const fileName = `model_catalog_${formData.value.provider}_${dateStr}.json`
    link.download = fileName
    
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    ElMessage.success(
      `Exported successfully ${formData.value.provider_name} model directory,` +
      `contains ${formData.value.models.length} models`
    )
  } catch (error: any) {
    console.error('Export failed:', error)
    ElMessage.error(error.message || 'Export failed')
  } finally {
    exportingForProvider.value = false
  }
}

// Use preset templates
const handleUsePresetModels = async () => {
  try {
    if (!formData.value.provider) {
      ElMessage.warning('Please select the manufacturer first')
      return
    }

    await ElMessageBox.confirm(
      'This operation will use the preset template and overwrite the current model list. Do you want to continue?',
      'Confirm action',
      { type: 'warning' }
    )

    // Provide different preset templates according to different aggregation platforms
    const presetModels = getPresetModels(formData.value.provider)

    if (presetModels.length > 0) {
      formData.value.models = presetModels
      ElMessage.success(`Imported ${presetModels.length} default model`)
    } else {
      ElMessage.warning('This manufacturer currently has no preset templates')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to import preset template:', error)
    }
  }
}

// Get a list of preset models
const getPresetModels = (providerName: string): ModelInfo[] => {
  const presets: Record<string, ModelInfo[]> = {
    '302ai': [
      // OpenAI model
      { name: 'gpt-4o', display_name: 'GPT-4o', input_price_per_1k: 0.005, output_price_per_1k: 0.015, context_length: 128000, currency: 'USD' },
      { name: 'gpt-4o-mini', display_name: 'GPT-4o Mini', input_price_per_1k: 0.00015, output_price_per_1k: 0.0006, context_length: 128000, currency: 'USD' },
      { name: 'gpt-4-turbo', display_name: 'GPT-4 Turbo', input_price_per_1k: 0.01, output_price_per_1k: 0.03, context_length: 128000, currency: 'USD' },
      { name: 'gpt-3.5-turbo', display_name: 'GPT-3.5 Turbo', input_price_per_1k: 0.0005, output_price_per_1k: 0.0015, context_length: 16385, currency: 'USD' },

      // Anthropic model
      { name: 'claude-3-5-sonnet-20241022', display_name: 'Claude 3.5 Sonnet', input_price_per_1k: 0.003, output_price_per_1k: 0.015, context_length: 200000, currency: 'USD' },
      { name: 'claude-3-5-haiku-20241022', display_name: 'Claude 3.5 Haiku', input_price_per_1k: 0.001, output_price_per_1k: 0.005, context_length: 200000, currency: 'USD' },
      { name: 'claude-3-opus-20240229', display_name: 'Claude 3 Opus', input_price_per_1k: 0.015, output_price_per_1k: 0.075, context_length: 200000, currency: 'USD' },

      // Google model
      { name: 'gemini-2.0-flash-exp', display_name: 'Gemini 2.0 Flash', input_price_per_1k: 0, output_price_per_1k: 0, context_length: 1000000, currency: 'USD' },
      { name: 'gemini-1.5-pro', display_name: 'Gemini 1.5 Pro', input_price_per_1k: 0.00125, output_price_per_1k: 0.005, context_length: 2000000, currency: 'USD' },
      { name: 'gemini-1.5-flash', display_name: 'Gemini 1.5 Flash', input_price_per_1k: 0.000075, output_price_per_1k: 0.0003, context_length: 1000000, currency: 'USD' },
    ],
    'aihubmix': [
      { name: 'gpt-4o', display_name: 'GPT-4o', input_price_per_1k: 0.005, output_price_per_1k: 0.015, context_length: 128000, currency: 'USD' },
      { name: 'gpt-4o-mini', display_name: 'GPT-4o Mini', input_price_per_1k: 0.00015, output_price_per_1k: 0.0006, context_length: 128000, currency: 'USD' },
      { name: 'claude-3-5-sonnet-latest', display_name: 'Claude 3.5 Sonnet', input_price_per_1k: 0.003, output_price_per_1k: 0.015, context_length: 200000, currency: 'USD' },
      { name: 'gemini-2.0-flash', display_name: 'Gemini 2.0 Flash', input_price_per_1k: 0, output_price_per_1k: 0, context_length: 1000000, currency: 'USD' },
      { name: 'deepseek-chat', display_name: 'DeepSeek Chat', input_price_per_1k: 0.00027, output_price_per_1k: 0.0011, context_length: 64000, currency: 'USD' },
    ],
    'openrouter': [
      // OpenAI model
      { name: 'openai/gpt-4o', display_name: 'GPT-4o', input_price_per_1k: 0.005, output_price_per_1k: 0.015, context_length: 128000, currency: 'USD' },
      { name: 'openai/gpt-4o-mini', display_name: 'GPT-4o Mini', input_price_per_1k: 0.00015, output_price_per_1k: 0.0006, context_length: 128000, currency: 'USD' },
      { name: 'openai/gpt-3.5-turbo', display_name: 'GPT-3.5 Turbo', input_price_per_1k: 0.0005, output_price_per_1k: 0.0015, context_length: 16385, currency: 'USD' },

      // Anthropic model
      { name: 'anthropic/claude-3.5-sonnet', display_name: 'Claude 3.5 Sonnet', input_price_per_1k: 0.003, output_price_per_1k: 0.015, context_length: 200000, currency: 'USD' },
      { name: 'anthropic/claude-3-opus', display_name: 'Claude 3 Opus', input_price_per_1k: 0.015, output_price_per_1k: 0.075, context_length: 200000, currency: 'USD' },

      // Google model
      { name: 'google/gemini-2.0-flash-exp', display_name: 'Gemini 2.0 Flash', input_price_per_1k: 0, output_price_per_1k: 0, context_length: 1000000, currency: 'USD' },
      { name: 'google/gemini-pro-1.5', display_name: 'Gemini 1.5 Pro', input_price_per_1k: 0.00125, output_price_per_1k: 0.005, context_length: 2000000, currency: 'USD' },
    ]
  }

  return presets[providerName] || []
}

const handleSave = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    if (formData.value.models.length === 0) {
      ElMessage.warning('Please add at least one model')
      return
    }
    
    saving.value = true
    try {
      await configApi.saveModelCatalog(formData.value)
      ElMessage.success('Saved successfully')
      dialogVisible.value = false
      await loadCatalogs()
    } catch (error) {
      console.error('Save failed:', error)
      ElMessage.error('Save failed')
    } finally {
      saving.value = false
    }
  })
}

const formatDate = (date: string) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

onMounted(() => {
  loadCatalogs()
  loadProviders()
})
</script>

<style lang="scss" scoped>
.model-catalog-management {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .form-tip {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
    margin-top: 4px;
  }
}
</style>

