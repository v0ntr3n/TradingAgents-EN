import {
  getCurrentDataSource,
  getDataSourcesStatus,
  type ApiResponse,
  type DataSourceStatus,
} from '@/api/sync'
import { ElMessageBox } from 'element-plus'
import type { Router } from 'vue-router'
import { useLicenseStore, type ProFeature } from '@/stores/license'

// ============================================================================
// Module: config.ts
// ============================================================================

/**
 * Front-end configuration tool
 */

/**
 * Detect whether it is JD Cloud cooperation version mode
 * Controlled by the environment variable VITE_JDYUN_MODE injected at build time
 */
export const isJdyunMode = (): boolean => {
  return import.meta.env.VITE_JDYUN_MODE === 'true'
}

/**
 * JD Cloud dialogue model list (default value)
 *
 * 🔥 When running, it will be backend `/api/config/jdyun/status` The returned available_models override,
 * Avoid inconsistency between the front-end hard-coded model list and the back-end OPENAI_MODEL environment variable.
 */
export let JDYUN_CHAT_MODELS: string[] = [
  'GLM-5',
  'GLM-5.1',
  'GLM-5.2',
  'DeepSeek-V4-Flash',
]

let _jdyunModelsLoaded = false

/**
 * Load the list of JD Cloud available models from the backend (called once during startup/initialization)
 *
 * In JD Cloud mode, the model list is based on the back-end OPENAI_MODEL environment variable (comma separated).
 * The front end only needs to call this function when the page is initialized to be consistent with the back end.
 * Return to the default list in non-JD Cloud mode or when loading fails.
 */
export const loadJdyunChatModels = async (): Promise<string[]> => {
  if (!isJdyunMode() || _jdyunModelsLoaded) return JDYUN_CHAT_MODELS
  try {
    // Dynamic import breaks circular dependencies:config -> request -> auth -> config
    const { ApiClient } = await import('@/api/request')
    const resp: any = await ApiClient.get('/api/config/jdyun/status', undefined, { skipErrorHandler: true })
    const data = resp?.data || resp
    const models = data?.available_models
    if (Array.isArray(models) && models.length > 0) {
      JDYUN_CHAT_MODELS = models
    }
  } catch (e) {
    console.warn('Failed to load JD Cloud model list, use default list:', e)
  } finally {
    _jdyunModelsLoaded = true
  }
  return JDYUN_CHAT_MODELS
}

/**
 * Get a list of available models
 * Returns the preset model in JD Cloud mode, returns null in non-JD Cloud mode (indicating the model configured using the database)
 */
export const getAvailableModels = (): string[] | null => {
  if (isJdyunMode()) {
    return [...JDYUN_CHAT_MODELS]
  }
  return null
}

// ============================================================================
// Module: dataSource.ts
// ============================================================================

export type ManualSyncDataSource = 'tushare' | 'akshare' | 'qmt'

export interface CurrentDataSourceInfo {
  name: string
  priority: number
  description: string
  token_source?: 'database' | 'env'
  token_source_display?: string
}

export interface ManualSyncSourceState {
  preferredSource: ManualSyncDataSource | null
  availableSources: Record<ManualSyncDataSource, boolean>
}

const MANUAL_SYNC_SOURCES: ManualSyncDataSource[] = ['tushare', 'akshare', 'qmt']

const normalizeManualSyncSource = (value: unknown): ManualSyncDataSource | null => {
  const normalized = String(value || '').toLowerCase()
  return MANUAL_SYNC_SOURCES.find(source => source === normalized) ?? null
}

const pickManualSourceFromStatuses = (statuses: DataSourceStatus[]): ManualSyncDataSource | null => {
  return statuses
    .map(item => ({
      name: normalizeManualSyncSource(item.name),
      available: !!item.available,
      priority: Number(item.priority || 0),
    }))
    .filter((item): item is { name: ManualSyncDataSource; available: boolean; priority: number } => !!item.name)
    .filter(item => item.available)
    .sort((left, right) => right.priority - left.priority)[0]?.name ?? null
}

export const loadCurrentDataSourceInfo = async (): Promise<CurrentDataSourceInfo | null> => {
  try {
    const response = await getCurrentDataSource()
    if (response.success && response.data) {
      return response.data
    }
  } catch (error) {
    console.warn('Failed to obtain current data source', error)
  }

  return null
}

export const loadManualSyncSourceState = async (): Promise<ManualSyncSourceState> => {
  const availableSources: Record<ManualSyncDataSource, boolean> = {
    tushare: false,
    akshare: false,
    qmt: false,
  }

  let preferredSource: ManualSyncDataSource | null = null
  let statuses: DataSourceStatus[] = []

  try {
    const [currentResponse, statusResponse] = await Promise.all([
      getCurrentDataSource(),
      getDataSourcesStatus(),
    ])

    if (currentResponse.success && currentResponse.data) {
      preferredSource = normalizeManualSyncSource(currentResponse.data.name)
    }

    statuses = ((statusResponse as ApiResponse<DataSourceStatus[]>)?.data || []) as DataSourceStatus[]
  } catch (error) {
    console.warn('Failed to obtain data source information in parallel, try downgraded loading', error)

    const currentInfo = await loadCurrentDataSourceInfo()
    preferredSource = normalizeManualSyncSource(currentInfo?.name)

    try {
      const statusResponse = await getDataSourcesStatus()
      statuses = ((statusResponse as ApiResponse<DataSourceStatus[]>)?.data || []) as DataSourceStatus[]
    } catch (statusError) {
      console.warn('Failed to get data source status', statusError)
    }
  }

  for (const item of statuses) {
    const manualSource = normalizeManualSyncSource(item.name)
    if (manualSource) {
      availableSources[manualSource] = !!item.available
    }
  }

  if (preferredSource && availableSources[preferredSource]) {
    return {
      preferredSource,
      availableSources,
    }
  }

  return {
    preferredSource: pickManualSourceFromStatuses(statuses),
    availableSources,
  }
}

// ============================================================================
// Module: modelSelection.ts
// ============================================================================

const MODEL_SELECTION_DELIMITER = '::'

type ModelLike = {
  provider?: string
  model_name?: string
  model_display_name?: string
}

export interface ParsedModelSelection {
  provider: string
  modelName: string
}

export const normalizeModelProvider = (provider?: string | null): string => {
  return String(provider || '').trim().toLowerCase()
}

export const encodeModelSelection = (model: ModelLike): string => {
  const provider = normalizeModelProvider(model.provider)
  const modelName = String(model.model_name || '').trim()

  if (!provider || !modelName) {
    return modelName
  }

  return `${provider}${MODEL_SELECTION_DELIMITER}${modelName}`
}

export const parseModelSelection = (value?: string | null): ParsedModelSelection => {
  const raw = String(value || '').trim()
  if (!raw) {
    return { provider: '', modelName: '' }
  }

  const delimiterIndex = raw.indexOf(MODEL_SELECTION_DELIMITER)
  if (delimiterIndex <= 0) {
    return { provider: '', modelName: raw }
  }

  return {
    provider: normalizeModelProvider(raw.slice(0, delimiterIndex)),
    modelName: raw.slice(delimiterIndex + MODEL_SELECTION_DELIMITER.length).trim(),
  }
}

export const matchesModelSelection = (model: ModelLike, selection?: string | null): boolean => {
  const { provider, modelName } = parseModelSelection(selection)
  const currentModelName = String(model.model_name || '').trim()

  if (!modelName || currentModelName !== modelName) {
    return false
  }

  if (!provider) {
    return true
  }

  return normalizeModelProvider(model.provider) === provider
}

export const findModelBySelection = <T extends ModelLike>(models: T[], selection?: string | null): T | undefined => {
  return models.find(model => matchesModelSelection(model, selection))
}

export const resolveModelSelection = <T extends ModelLike>(
  selection: string | undefined | null,
  models: T[],
  preferredProvider?: string | null
): string => {
  const raw = String(selection || '').trim()
  if (!raw) {
    return ''
  }

  const parsed = parseModelSelection(raw)
  if (parsed.provider) {
    const exactMatch = findModelBySelection(models, raw)
    return exactMatch ? encodeModelSelection(exactMatch) : raw
  }

  const matches = models.filter(model => String(model.model_name || '').trim() === parsed.modelName)
  if (matches.length === 0) {
    return raw
  }

  const normalizedPreferredProvider = normalizeModelProvider(preferredProvider)
  if (normalizedPreferredProvider) {
    const preferredMatch = matches.find(model => normalizeModelProvider(model.provider) === normalizedPreferredProvider)
    if (preferredMatch) {
      return encodeModelSelection(preferredMatch)
    }
  }

  if (matches.length === 1) {
    return encodeModelSelection(matches[0])
  }

  return raw
}

export const getModelOptionLabel = (model: ModelLike): string => {
  const baseName = String(model.model_display_name || model.model_name || '').trim()
  const provider = String(model.provider || '').trim()

  if (!provider) {
    return baseName
  }

  return `${baseName} (${provider})`
}

// ============================================================================
// Module: featureAccess.ts
// ============================================================================

interface FeatureAccessOptions {
  title?: string
  message?: string
  redirectTo?: string
  confirmButtonText?: string
  cancelButtonText?: string
}

export async function ensureFeatureAccess(
  feature: ProFeature,
  router: Router,
  options: FeatureAccessOptions = {}
) {
  const licenseStore = useLicenseStore()

  if (!licenseStore.licenseInfo) {
    await licenseStore.verifyLicense()
  }

  if (licenseStore.hasFeature(feature)) {
    return true
  }

  try {
    await ElMessageBox.confirm(
      options.message || 'This function is exclusive for advanced students, please go to authorization management to complete the certification.',
      options.title || 'Limited functionality',
      {
        confirmButtonText: options.confirmButtonText || 'Go to authorization management',
        cancelButtonText: options.cancelButtonText || 'Talk to you later',
        type: 'warning'
      }
    )
    await router.push(options.redirectTo || '/settings/license')
  } catch {
    // No additional processing will be done when the user cancels
  }

  return false
}

export function ensureReportExportAccess(router: Router) {
  return ensureFeatureAccess('export_reports', router, {
    message: 'Report downloading and exporting are exclusive to advanced students. Please go to Authorization Management to complete the certification.'
  })
}
