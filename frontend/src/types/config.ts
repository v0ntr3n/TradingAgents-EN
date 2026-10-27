// Configuration management related type definitions

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
  api_key?: string
  api_secret?: string
  extra_config?: Record<string, any>

  // 🆕 Aggregation channel support
  is_aggregator?: boolean
  aggregator_type?: string
  model_name_format?: string

  created_at?: string
  updated_at?: string
}

// Large model configuration
export interface LLMConfig {
  name: string
  provider: string
  model_name: string
  api_key?: string  // Optional, priority is given to obtaining configuration from the manufacturer.
  base_url?: string
  max_tokens?: number
  temperature?: number
  timeout?: number
  is_default?: boolean
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

// Data source configuration
export interface DataSourceConfig {
  name: string
  type: string
  config: Record<string, any>
  is_default?: boolean
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

// Database configuration
export interface DatabaseConfig {
  name: string
  type: string
  host: string
  port: number
  database: string
  username: string
  password: string
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

// System configuration
export interface SystemConfig {
  app_name: string
  version: string
  debug: boolean
  log_level: string
  max_concurrent_analyses: number
  default_timeout: number
  cache_enabled: boolean
  cache_ttl: number
}

// Configure test requests
export interface ConfigTestRequest {
  type: 'llm' | 'datasource' | 'database'
  config: Record<string, any>
}

// Configure test response
export interface ConfigTestResponse {
  success: boolean
  message: string
  details?: Record<string, any>
  latency?: number
}
