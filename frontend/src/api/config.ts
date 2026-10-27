/**
 * Configuration management API
 */

import { ApiClient } from './request'

// Configure related type definitions

// Large model manufacturer
export interface LLMProvider {
  id: string
  name: string
  display_name: string
  description?: string
  website?: string
  api_doc_url?: string
  logo_url?: string
  is_active: boolean
  supported_features: string[]
  default_base_url?: string
  embedding_model?: string  // 🔥 New: Embedding model name
  test_model?: string  // 🔥 New: Test model name (used to test API connection, if not filled in, the system default value will be used)
  api_key?: string  // 🔥 New: API Key (optional, used to test connections or override environment variables)
  api_secret?: string  // 🔥 New: API Secret (required by some manufacturers, such as Baidu Qianfan)
  extra_config?: {
    has_api_key?: boolean
    source?: 'environment' | 'database'
    [key: string]: any
  }
  // 🆕 Aggregation channel support
  is_aggregator?: boolean
  aggregator_type?: string
  model_name_format?: string
  created_at?: string
  updated_at?: string
}

export interface LLMConfig {
  config_id?: string
  provider: string
  provider_name?: string
  model_name: string
  model_display_name?: string  // New: Model display name
  api_key?: string  // Optional, priority is given to obtaining configuration from the manufacturer.
  api_base?: string
  max_tokens: number
  temperature: number
  timeout: number
  retry_times: number
  enabled: boolean
  description?: string
  // Pricing configuration
  input_price_per_1k?: number
  output_price_per_1k?: number
  currency?: string
  // Advanced configuration
  enable_memory?: boolean
  enable_debug?: boolean
  priority?: number
  model_category?: string
  // 🆕 Model Capability Grading System
  capability_level?: number  // Model capability level(1-5): 1=Basics, 2=Standard, 3=Advanced, 4=Professional, 5=flagship
  suitable_roles?: string[]  // Applicable roles: quick_analysis(Quick analysis), deep_analysis(In-depth analysis), both(suitable for both)
  features?: string[]  // Model properties: tool_calling, long_context, reasoning, vision, fast_response, cost_effective
  recommended_depths?: string[]  // Recommended level of analysis depth: fast, Basics, Standard, Depth, Comprehensive
  performance_metrics?: {  // Performance indicators
    speed?: number  // speed(1-5)
    cost?: number  // cost(1-5)
    quality?: number  // quality(1-5)
  }
}

export interface FetchProviderModelsFilters {
  type?: string
  modalities?: string
  features?: string[]
  provider_names?: string[]
  model_keyword?: string
  sort_by?: string
  sort_order?: string
  limit?: number
  recommended_only?: boolean
  tools_only?: boolean
  exclude_preview?: boolean
}

export interface DataSourceConfig {
  name: string
  type: string
  api_key?: string
  api_secret?: string
  endpoint?: string
  timeout: number
  rate_limit: number
  enabled: boolean
  priority: number
  config_params: Record<string, any>
  description?: string
  // New field: Support market classification
  market_categories?: string[]  // Market category list
  display_name?: string         // display name
  provider?: string            // data provider
  created_at?: string
  updated_at?: string
}

// Market classification configuration
export interface MarketCategory {
  id: string
  name: string
  display_name: string
  description?: string
  enabled: boolean
  sort_order: number
  created_at?: string
  updated_at?: string
}

// Data source grouping relationship
export interface DataSourceGrouping {
  data_source_name: string
  market_category_id: string
  priority: number              // Priority in this category
  enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface DatabaseConfig {
  name: string
  type: string
  host: string
  port: number
  username?: string
  password?: string
  database?: string
  connection_params: Record<string, any>
  pool_size: number
  max_overflow: number
  enabled: boolean
  description?: string
}

export interface SystemConfig {
  config_name: string
  config_type: string
  llm_configs: LLMConfig[]
  default_llm?: string
  data_source_configs: DataSourceConfig[]
  default_data_source?: string
  database_configs: DatabaseConfig[]
  system_settings: Record<string, any>
  created_at: string
  updated_at: string
  version: number
  is_active: boolean
}

export interface ConfigTestRequest {
  config_type: 'llm' | 'datasource' | 'database'
  config_data: Record<string, any>
}

export interface ConfigTestResponse {
  success: boolean
  message: string
  details?: Record<string, any>
}


// Gateway Platform configuration
export interface GatewayConfig {
  platform: string
  app_id: string
  app_secret: string
  bot_secret: string
  connection_mode: string   // 'webhook' | 'websocket'
  enabled: boolean
  configured: boolean
  // Exclusive to Feishu
  verification_token?: string
  encrypt_key?: string
  // Exclusive for DingTalk
  app_key?: string
  robot_code?: string
}

export interface GatewayConfigRequest {
  app_id?: string
  app_secret?: string
  bot_secret?: string
  connection_mode?: string   // 'webhook' | 'websocket'
  enabled: boolean
  // Exclusive to Feishu
  verification_token?: string
  encrypt_key?: string
  // Exclusive for DingTalk
  app_key?: string
  robot_code?: string
}

// System settings metadata
export interface SettingMeta {
  key: string
  sensitive: boolean
  editable: boolean
  source: 'environment' | 'database' | 'default'
  has_value: boolean
}

// Configuration management API
export const configApi = {
  // Get system configuration
  getSystemConfig(): Promise<SystemConfig> {
    return ApiClient.get('/api/config/system').then((response: any) => response.data ?? response)
  },

  // ========== Large model manufacturer management ==========

  // Get all large model manufacturers
  getLLMProviders(): Promise<LLMProvider[]> {
    return ApiClient.get('/api/config/llm/providers').then((response: any) => response.data ?? response)
  },

  // Add large model manufacturer
  addLLMProvider(provider: Partial<LLMProvider>): Promise<{ message: string; id: string }> {
    return ApiClient.post('/api/config/llm/providers', provider) as any
  },

  // Update large model manufacturers
  updateLLMProvider(id: string, provider: Partial<LLMProvider>): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/llm/providers/${id}`, provider)
  },

  // Delete large model manufacturer
  deleteLLMProvider(id: string): Promise<{ message: string }> {
    return ApiClient.delete(`/api/config/llm/providers/${id}`)
  },

  // Enable/disable large model manufacturers
  toggleLLMProvider(id: string, isActive: boolean): Promise<{ message: string }> {
    return ApiClient.patch(`/api/config/llm/providers/${id}/toggle`, { is_active: isActive })
  },

  // Migrate environment variables to manufacturer management
  migrateEnvToProviders(): Promise<{ message: string; data: any }> {
    return ApiClient.post('/api/config/llm/providers/migrate-env')
  },

  // 🆕 Initialize aggregation channel manufacturer configuration
  initAggregatorProviders(): Promise<{ success: boolean; message: string; data: { added_count: number; skipped_count: number } }> {
    return ApiClient.post('/api/config/llm/providers/init-aggregators')
  },

  // Test manufacturer API
  testProviderAPI(providerId: string): Promise<{ success: boolean; message: string; data?: any }> {
    return ApiClient.post(`/api/config/llm/providers/${providerId}/test`)
  },

  // 🔥 New: Get a list of all manufacturers and models that support embedding
  getEmbeddingProviders(): Promise<Array<{
    name: string
    display_name: string
    models: string[]
  }>> {
    return ApiClient.get('/api/config/llm/providers/embedding').then((response: any) => response.data ?? response)
  },

  // Get a list of available models (grouped by manufacturer)
  getAvailableModels(): Promise<Array<{
    provider: string
    provider_name: string
    models: Array<{ name: string; display_name: string }>
  }>> {
    return ApiClient.get('/api/config/models').then((response: any) => response.data ?? response)
  },

  // ========== Model catalog management ==========

  // Get all model directories
  getModelCatalog(): Promise<Array<{
    provider: string
    provider_name: string
    models: Array<{
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
    }>
  }>> {
    return ApiClient.get('/api/config/model-catalog').then((response: any) => response.data ?? response)
  },

  // Get the model catalog of the specified manufacturer
  getProviderModelCatalog(provider: string): Promise<{
    provider: string
    provider_name: string
    models: Array<{
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
    }>
  }> {
    return ApiClient.get(`/api/config/model-catalog/${provider}`).then((response: any) => response.data ?? response)
  },

  // Save model directory
  saveModelCatalog(catalog: {
    provider: string
    provider_name: string
    models: Array<{ name: string; display_name: string; description?: string }>
  }): Promise<{ success: boolean; message: string }> {
    return ApiClient.post('/api/config/model-catalog', catalog)
  },

  // Delete model directory
  deleteModelCatalog(provider: string): Promise<{ success: boolean; message: string }> {
    return ApiClient.delete(`/api/config/model-catalog/${provider}`)
  },

  // Initialize the default model directory
  initModelCatalog(): Promise<{ success: boolean; message: string }> {
    return ApiClient.post('/api/config/model-catalog/init')
  },

  // 🔥 New: Export model directory (for download)
  exportModelCatalog(provider?: string): Promise<{
    success: boolean
    message: string
    data: {
      catalogs: Array<{
        provider: string
        provider_name: string
        models: Array<{
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
        }>
      }>
      exported_at: string
      version: string
    }
  }> {
    const url = provider
      ? `/api/config/model-catalog/export?provider=${encodeURIComponent(provider)}`
      : '/api/config/model-catalog/export'
    return ApiClient.get(url)
  },

  // 🔥 New: Get the default model catalog template
  getModelCatalogTemplate(): Promise<{
    success: boolean
    message: string
    data: {
      catalogs: Array<{
        provider: string
        provider_name: string
        models: Array<{
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
        }>
      }>
      exported_at: string
      version: string
      description: string
    }
  }> {
    return ApiClient.get('/api/config/model-catalog/template')
  },

  // 🔥 New: Import model directory (from JSON file)
  importModelCatalog(data: {
    catalogs: Array<{
      provider: string
      provider_name: string
      models: Array<{
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
      }>
    }>
    merge_mode?: 'update' | 'replace' | 'append'
  }): Promise<{
    success: boolean
    message: string
    data: {
      success_count: number
      failed_count: number
      total_count: number
      errors: string[]
    }
  }> {
    return ApiClient.post('/api/config/model-catalog/import', {
      catalogs: data.catalogs,
      merge_mode: data.merge_mode || 'update'
    })
  },

  // Get model list from manufacturer API
  fetchProviderModels(provider: string, filters?: FetchProviderModelsFilters): Promise<{
    success: boolean
    message?: string
    models?: Array<{
      id: string
      name: string
      context_length?: number
    }>
  }> {
    return ApiClient.post(`/api/config/llm/providers/${provider}/fetch-models`, filters || {})
  },

  // ========== Large model configuration management ==========

  // Get all large model configurations
  getLLMConfigs(): Promise<LLMConfig[]> {
    return ApiClient.get('/api/config/llm').then((response: any) => response.data ?? response)
  },

  // Add or update large model configuration
  updateLLMConfig(config: Partial<LLMConfig>): Promise<{ message: string; model_name: string }> {
    return ApiClient.post('/api/config/llm', config) as any
  },

  // Delete large model configuration
  deleteLLMConfig(provider: string, modelName: string): Promise<{ message: string }> {
    return ApiClient.delete(`/api/config/llm/${provider}/${modelName}`)
  },

  // Set default large model
  setDefaultLLM(name: string): Promise<{ message: string; default_llm: string }> {
    return ApiClient.post('/api/config/llm/set-default', { name }) as any
  },

  // One-click import of large model configurations (by manufacturer)
  batchImportLLMConfigs(providers?: string[]): Promise<{ success: boolean; message: string; imported: number; skipped: number; errors: string[] }> {
    return ApiClient.post('/api/config/llm/batch-import', { providers: providers || [] }) as any
  },

  // Get all data source configurations
  getDataSourceConfigs(): Promise<DataSourceConfig[]> {
    return ApiClient.get('/api/config/datasource').then((response: any) => response.data ?? response)
  },

  // Add data source configuration
  addDataSourceConfig(config: Partial<DataSourceConfig>): Promise<{ message: string; name: string }> {
    return ApiClient.post('/api/config/datasource', config) as any
  },

  // Set default data source
  setDefaultDataSource(name: string): Promise<{ message: string; default_data_source: string }> {
    return ApiClient.post('/api/config/datasource/set-default', { name }) as any
  },

  // Update data source configuration
  updateDataSourceConfig(name: string, config: Partial<DataSourceConfig>): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/datasource/${name}`, config)
  },

  // Delete data source configuration
  deleteDataSourceConfig(name: string): Promise<{ message: string }> {
    return ApiClient.delete(`/api/config/datasource/${name}`)
  },

  // Market classification management
  getMarketCategories(): Promise<MarketCategory[]> {
    return ApiClient.get('/api/config/market-categories').then((response: any) => response.data ?? response)
  },

  addMarketCategory(category: Partial<MarketCategory>): Promise<{ message: string; id: string }> {
    return ApiClient.post('/api/config/market-categories', category) as any
  },

  updateMarketCategory(id: string, category: Partial<MarketCategory>): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/market-categories/${id}`, category)
  },

  deleteMarketCategory(id: string): Promise<{ message: string }> {
    return ApiClient.delete(`/api/config/market-categories/${id}`)
  },

  // Data source group management
  getDataSourceGroupings(): Promise<DataSourceGrouping[]> {
    return ApiClient.get('/api/config/datasource-groupings').then((response: any) => response.data ?? response)
  },

  addDataSourceToCategory(dataSourceName: string, categoryId: string, priority?: number): Promise<{ message: string }> {
    return ApiClient.post('/api/config/datasource-groupings', {
      data_source_name: dataSourceName,
      market_category_id: categoryId,
      priority: priority || 0,
      enabled: true
    })
  },

  removeDataSourceFromCategory(dataSourceName: string, categoryId: string): Promise<{ message: string }> {
    return ApiClient.delete(`/api/config/datasource-groupings/${dataSourceName}/${categoryId}`)
  },

  updateDataSourceGrouping(dataSourceName: string, categoryId: string, updates: Partial<DataSourceGrouping>): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/datasource-groupings/${dataSourceName}/${categoryId}`, updates)
  },

  // Batch update data source sorting within categories
  updateCategoryDataSourceOrder(categoryId: string, orderedDataSources: Array<{name: string, priority: number}>): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/market-categories/${categoryId}/datasource-order`, {
      data_sources: orderedDataSources
    })
  },

  // Get system settings metadata
  getSystemSettingsMeta(): Promise<{ items: SettingMeta[] }> {
    return ApiClient.get('/api/config/settings/meta').then((r: any) => r.data)
  },


  // ========== Database configuration management ==========

  // Get all database configurations
  getDatabaseConfigs(): Promise<DatabaseConfig[]> {
    return ApiClient.get('/api/config/database').then((response: any) => response.data ?? response)
  },

  // Get the specified database configuration
  getDatabaseConfig(dbName: string): Promise<DatabaseConfig> {
    return ApiClient.get(`/api/config/database/${encodeURIComponent(dbName)}`).then((response: any) => response.data ?? response)
  },

  // Add database configuration
  addDatabaseConfig(config: Partial<DatabaseConfig>): Promise<{ success: boolean; message: string }> {
    return ApiClient.post('/api/config/database', config)
  },

  // Update database configuration
  updateDatabaseConfig(dbName: string, config: Partial<DatabaseConfig>): Promise<{ success: boolean; message: string }> {
    return ApiClient.put(`/api/config/database/${encodeURIComponent(dbName)}`, config)
  },

  // Delete database configuration
  deleteDatabaseConfig(dbName: string): Promise<{ success: boolean; message: string }> {
    return ApiClient.delete(`/api/config/database/${encodeURIComponent(dbName)}`)
  },

  // Test database configuration connection
  testDatabaseConfig(dbName: string): Promise<ConfigTestResponse> {
    return ApiClient.post(`/api/config/database/${encodeURIComponent(dbName)}/test`)
  },

  // Get system settings
  getSystemSettings(): Promise<Record<string, any>> {
    return ApiClient.get('/api/config/settings')
  },

  // Get default model configuration
  getDefaultModels(): Promise<{
    default_provider?: string
    quick_analysis_model: string
    quick_analysis_model_config_id?: string
    deep_analysis_model: string
    deep_analysis_model_config_id?: string
    deep_reasoning_model?: string
    deep_reasoning_model_config_id?: string
    coding_model?: string
    coding_model_config_id?: string
  }> {
    return ApiClient.get('/api/config/settings').then((settings: any) => ({
      default_provider: settings.data?.default_provider || settings.default_provider || '',
      quick_analysis_model: settings.data?.quick_analysis_model || settings.quick_analysis_model || 'qwen-turbo',
      quick_analysis_model_config_id: settings.data?.quick_analysis_model_config_id || settings.quick_analysis_model_config_id || '',
      deep_analysis_model: settings.data?.deep_analysis_model || settings.deep_analysis_model || 'qwen-max',
      deep_analysis_model_config_id: settings.data?.deep_analysis_model_config_id || settings.deep_analysis_model_config_id || '',
      deep_reasoning_model: settings.data?.deep_reasoning_model || settings.deep_reasoning_model || '',
      deep_reasoning_model_config_id: settings.data?.deep_reasoning_model_config_id || settings.deep_reasoning_model_config_id || '',
      coding_model: settings.data?.coding_model || settings.coding_model || '',
      coding_model_config_id: settings.data?.coding_model_config_id || settings.coding_model_config_id || ''
    }))
  },

  // Update system settings
  updateSystemSettings(settings: Record<string, any>): Promise<{ success: boolean; data: any; message: string; timestamp: string }> {
    return ApiClient.put('/api/config/settings', settings) as any
  },

  // Test configuration connection
  testConfig(testRequest: ConfigTestRequest): Promise<ConfigTestResponse> {
    return ApiClient.post('/api/config/test', testRequest)
  },

  // Test proxy connection
  testProxyConnection(proxyConfig: { http_proxy?: string; https_proxy?: string }): Promise<{ success: boolean; data: { response_time: number }; message: string; timestamp: string }> {
    return ApiClient.post('/api/config/test-proxy', proxyConfig) as any
  },

  // Export configuration
  exportConfig(): Promise<{ message: string; data: any; exported_at: string }> {
    return ApiClient.post('/api/config/export') as any
  },

  // Import configuration
  importConfig(configData: Record<string, any>): Promise<{ message: string }> {
    return ApiClient.post('/api/config/import', configData)
  },

  // Migrate legacy configuration
  migrateLegacyConfig(): Promise<{ message: string }> {
    return ApiClient.post('/api/config/migrate-legacy')
  },

  // Configuration reload
  reloadConfig(): Promise<{ success: boolean; message: string; data?: any }> {
    return ApiClient.post('/api/config/reload')
  },

  // ========== Gateway Platform configuration management ==========

  // Get Gateway platform configuration
  getGatewayConfig(platform: string): Promise<GatewayConfig> {
    return ApiClient.get(`/api/config/gateway/${platform}`).then((r: any) => r.data)
  },

  // Update Gateway platform configuration
  updateGatewayConfig(platform: string, config: GatewayConfigRequest): Promise<{ message: string }> {
    return ApiClient.put(`/api/config/gateway/${platform}`, config)
  },

  // Test Gateway platform connection
  testGatewayConnection(platform: string): Promise<{ success: boolean; data?: any; message: string }> {
    return ApiClient.post(`/api/config/gateway/${platform}/test`)
  },

  // ========== vector migration ==========

  // Get the list of all collections in Qdrant (main storage + mem0) , Contains migration status
  getQdrantCollections(): Promise<{
    main: Array<{
      name: string
      point_count: number
      dimensions: number
      source: string
      migration_status: 'pending' | 'migrated' | 'outdated'
      current_model: string
      last_migration: string | null
    }>
    mem0: Array<{
      name: string
      point_count: number
      dimensions: number
      source: string
      migration_status: 'pending' | 'migrated' | 'outdated'
      current_model: string
      last_migration: string | null
    }>
  }> {
    return ApiClient.get('/api/config/qdrant/collections').then((response: any) => response.data ?? response)
  },

  // Get the list of all mem0 collections in Qdrant (compatible with old interfaces)
  getMem0Collections(): Promise<Array<{
    name: string
    point_count: number
    dimensions: number
    is_current: boolean
  }>> {
    return ApiClient.get('/api/config/memory/collections').then((response: any) => response.data ?? response)
  },

  // Migrate collection vector data (main storage in-place recoding/mem0 cross-collection migration)
  migrateCollection(collection_name: string, source: 'main' | 'mem0', dry_run?: boolean): Promise<{
    success: boolean
    collection_name?: string
    source_collection?: string
    target_collection?: string
    total_seen: number
    migrated: number
    skipped: number
    dry_run: boolean
    model_used?: string
  }> {
    return ApiClient.post('/api/config/qdrant/migrate', { collection_name, source, dry_run: !!dry_run }) as any
  },

  // Migrate the old mem0 collection to the current collection (compatible with the old interface)
  migrateMem0Collection(source_collection: string, dry_run?: boolean): Promise<{
    success: boolean
    source_collection: string
    target_collection: string
    total_seen: number
    migrated: number
    skipped: number
    dry_run: boolean
  }> {
    return ApiClient.post('/api/config/memory/migrate', { source_collection, dry_run: !!dry_run }) as any
  },

  // delete empty collection
  deleteCollection(collection_name: string, source: 'main' | 'mem0'): Promise<{ success: boolean; message: string }> {
    return ApiClient.post('/api/config/qdrant/delete-collection', { collection_name, source }) as any
  },

  // ========== JD Cloud Cooperation Edition ==========

  // Get JD Cloud configuration status
  getJdyunStatus(): Promise<{
    jdyun_mode: boolean
    api_base: string
    api_key_configured: boolean
    current_model: string
    available_models: string[]
    embedding_model: string
    embedding_dims: number
    tushare_token_configured: boolean
    akshare_available: boolean
  }> {
    return ApiClient.get('/api/config/jdyun/status').then((response: any) => response.data ?? response)
  }
}

// Configuration related constants
export const CONFIG_PROVIDERS = {
  OPENAI: 'openai',
  QWEN: 'qwen',
  GLM: 'glm',
  GEMINI: 'gemini',
  CLAUDE: 'claude'
} as const

/**
 * Data source type constant
 *
 * NOTE: These constants are kept in sync with the backend DataSourceType enumeration
 * When adding a new data source, please first register it in the backend tradingagents/constants/data_sources.py
 */
export const DATA_SOURCE_TYPES = {
  // cache data source
  MONGODB: 'mongodb',

  // China market data source
  TUSHARE: 'tushare',
  AKSHARE: 'akshare',
  BAOSTOCK: 'baostock',

  // US stock data source
  FINNHUB: 'finnhub',
  YAHOO_FINANCE: 'yahoo_finance',
  ALPHA_VANTAGE: 'alpha_vantage',
  IEX_CLOUD: 'iex_cloud',

  // Professional data source
  WIND: 'wind',
  CHOICE: 'choice',
  QMT: 'qmt',

  // Other data sources
  QUANDL: 'quandl',
  LOCAL_FILE: 'local_file',
  LOCAL: 'local',  // Local data (users import via API)
  CUSTOM: 'custom'
} as const

export const DATABASE_TYPES = {
  MONGODB: 'mongodb',
  REDIS: 'redis',
  MYSQL: 'mysql',
  POSTGRESQL: 'postgresql'
} as const

// Default configuration template
export const DEFAULT_LLM_CONFIG: Partial<LLMConfig> = {
  max_tokens: 4000,
  temperature: 0.2,  // Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
  timeout: 60,
  retry_times: 3,
  enabled: true
}

export const DEFAULT_DATA_SOURCE_CONFIG: Partial<DataSourceConfig> = {
  timeout: 30,
  rate_limit: 100,
  enabled: true,
  priority: 0,
  config_params: {},
  market_categories: []
}

// Default market category
export const DEFAULT_MARKET_CATEGORIES: Partial<MarketCategory>[] = [
  {
    id: 'a_shares',
    name: 'a_shares',
    display_name: 'A shares',
    description: 'China A-share market data source',
    enabled: true,
    sort_order: 1
  },
  {
    id: 'crypto',
    name: 'crypto',
    display_name: 'digital currency',
    description: 'Digital currency market data source',
    enabled: true,
    sort_order: 4
  },
  {
    id: 'futures',
    name: 'futures',
    display_name: 'Futures',
    description: 'Futures market data source',
    enabled: true,
    sort_order: 5
  }
]

export const DEFAULT_DATABASE_CONFIG: Partial<DatabaseConfig> = {
  pool_size: 10,
  max_overflow: 20,
  enabled: true,
  connection_params: {}
}

// Configure verification function
export const validateLLMConfig = (config: Partial<LLMConfig>): string[] => {
  const errors: string[] = []

  if (!config.provider) errors.push('Supplier cannot be empty')
  if (!config.model_name) errors.push('Model name cannot be empty')
  // NOTE: The API key is not verified here as it is managed in the factory configuration
  if (config.max_tokens && config.max_tokens <= 0) errors.push('The maximum number of Tokens must be greater than 0')
  if (config.temperature && (config.temperature < 0 || config.temperature > 2)) {
    errors.push('Temperature parameter must be between 0-2')
  }

  return errors
}

export const validateDataSourceConfig = (config: Partial<DataSourceConfig>): string[] => {
  const errors: string[] = []

  if (!config.name) errors.push('Data source name cannot be empty')
  if (!config.type) errors.push('Data source type cannot be empty')
  if (config.timeout && config.timeout <= 0) errors.push('The timeout must be greater than 0')
  if (config.rate_limit && config.rate_limit <= 0) errors.push('Rate limit must be greater than 0')

  return errors
}

export const validateDatabaseConfig = (config: Partial<DatabaseConfig>): string[] => {
  const errors: string[] = []

  if (!config.name) errors.push('Database name cannot be empty')
  if (!config.type) errors.push('Database type cannot be empty')
  if (!config.host) errors.push('Host address cannot be empty')
  if (!config.port || config.port <= 0) errors.push('The port number must be greater than 0')
  if (config.pool_size && config.pool_size <= 0) errors.push('The connection pool size must be greater than 0')

  return errors
}
