/**
 * Model capability management API
 */

import { request } from './request'

/**
 * Model capability information
 */
export interface ModelCapabilityInfo {
  model_name: string
  capability_level: number
  suitable_roles: string[]
  features: string[]
  recommended_depths: string[]
  performance_metrics?: {
    speed: number
    cost: number
    quality: number
  }
  description?: string
}

/**
 * Model recommended response
 */
export interface ModelRecommendationResponse {
  quick_model: string
  deep_model: string
  quick_model_info: ModelCapabilityInfo
  deep_model_info: ModelCapabilityInfo
  reason: string
}

/**
 * Model validation response
 */
export interface ModelValidationResponse {
  valid: boolean
  warnings: string[]
  recommendations: string[]
}

/**
 * badge style
 */
export interface BadgeStyle {
  text: string
  color: string
  icon: string
}

/**
 * All badge styles
 */
export interface AllBadges {
  capability_levels: Record<string, BadgeStyle>
  roles: Record<string, BadgeStyle>
  features: Record<string, BadgeStyle>
}

/**
 * Analysis depth requirements
 */
export interface DepthRequirement {
  min_capability: number
  quick_model_min: number
  deep_model_min: number
  required_features: string[]
  description: string
}

/**
 * Get all default model capability configurations
 */
export function getDefaultModelConfigs() {
  return request({
    url: '/api/model-capabilities/default-configs',
    method: 'get'
  })
}

/**
 * Get analysis depth requirements
 */
export function getDepthRequirements() {
  return request({
    url: '/api/model-capabilities/depth-requirements',
    method: 'get'
  })
}

/**
 * Get ability level description
 */
export function getCapabilityDescriptions() {
  return request({
    url: '/api/model-capabilities/capability-descriptions',
    method: 'get'
  })
}

/**
 * Get all badge styles
 */
export function getAllBadges() {
  return request({
    url: '/api/model-capabilities/badges',
    method: 'get'
  })
}

/**
 * Recommended model
 * @param researchDepth Research depth: Quick/Basic/Standard/In-depth/Comprehensive
 */
export function recommendModels(researchDepth: string) {
  return request({
    url: '/api/model-capabilities/recommend',
    method: 'post',
    data: {
      research_depth: researchDepth
    }
  })
}

/**
 * Verify model pair
 * @param quickModel quick model
 * @param deepModel deep model
 * @param researchDepth Research depth
 */
export function validateModels(quickModel: string, deepModel: string, researchDepth: string) {
  return request({
    url: '/api/model-capabilities/validate',
    method: 'post',
    data: {
      quick_model: quickModel,
      deep_model: deepModel,
      research_depth: researchDepth
    }
  })
}

/**
 * Batch initialization model capability
 * @param overwrite Whether to overwrite existing configuration
 */
export function batchInitCapabilities(overwrite: boolean = false) {
  return request({
    url: '/api/model-capabilities/batch-init',
    method: 'post',
    data: {
      overwrite
    }
  })
}

/**
 * Get capability information of a specified model
 * @param modelName Model name
 */
export function getModelCapability(modelName: string) {
  return request({
    url: `/api/model-capabilities/model/${modelName}`,
    method: 'get'
  })
}

