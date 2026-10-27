import {
  getCurrentDataSource,
  getDataSourcesStatus,
  type ApiResponse,
  type DataSourceStatus,
} from '@/api/sync'

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
