import request from './request'
import type { ApiResponse } from './request'
import { ApiClient } from './request'

// ============================================================================
// Module: workflow.ts
// ============================================================================

/**
 * Workflow API
 */



// type definition
export interface Position {
  x: number
  y: number
}

export interface NodeDefinition {
  id: string
  type: 'start' | 'end' | 'analyst' | 'researcher' | 'trader' | 'risk' | 'manager' | 'condition' | 'parallel' | 'merge' | 'debate' | 'tool'
  agent_id?: string
  tool_id?: string
  label: string
  position: Position
  config?: Record<string, any>
  condition?: string
}

export interface EdgeDefinition {
  id: string
  source: string
  target: string
  type?: 'normal' | 'conditional'
  condition?: string
  label?: string
  animated?: boolean
}

export interface WorkflowDefinition {
  id: string
  name: string
  description: string
  version: string
  nodes: NodeDefinition[]
  edges: EdgeDefinition[]
  created_at?: string
  updated_at?: string
  created_by?: string
  config?: Record<string, any>
  tags: string[]
  is_template: boolean
  workflow_type?: string
  input_config?: WorkflowInputConfig
  output_config?: any
}

/**
 * Input parameter control type
 */
export type InputFieldType = 'string' | 'textarea' | 'number' | 'boolean' | 'date' | 'select' | 'multiselect'

/**
 * Single input parameter definition
 */
export interface InputFieldConfig {
  name: string                  // Parameter name (key passed to the backend)
  label: string                 // form display label
  type: InputFieldType
  required: boolean
  default?: any
  description?: string          // Parameter description/tips
  placeholder?: string
  options?: any[]               // Option list (used when selecting/multiselect)
  option_labels?: string[]      // Option display name (one-to-one correspondence with options)
  min?: number
  max?: number
  group?: string                // Group labels
  order?: number
}

/**
 * Workflow input parameter configuration
 */
export interface WorkflowInputConfig {
  fields: InputFieldConfig[]
}

export interface WorkflowSummary {
  id: string
  name: string
  description: string
  version: string
  tags: string[]
  is_template: boolean
  is_default?: boolean
  workflow_type?: string
  created_at?: string
  updated_at?: string
}

/**
 * Determine whether the workflow is suitable for the analysis page (single stock/batch analysis)"Analysis process"Select from the drop-down box.
 *
 * Exclude the following processes:
 * 1. v1.0 and earlier deprecated processes (major version < 2) 
 * 2. Quick analysis flow (non-complete analysis flow)
 * 3. Blank process
 */
export function isSelectableAnalysisWorkflow(w: WorkflowSummary, expectedType: string): boolean {
  if (w.workflow_type !== expectedType) return false
  // v1.0 and earlier processes are deprecated, only the main version remains >= 2 process
  const major = parseInt((w.version || '0').split('.')[0], 10) || 0
  if (major < 2) return false
  // Exclude non-complete analysis flows such as fast analysis flows and blank flows
  const name = w.name || ''
  if (name.includes('fast') || name.includes('blank')) return false
  return true
}

export interface ValidationResult {
  is_valid: boolean
  errors: string[]
  warnings: string[]
}

export interface ExecutionResult {
  success: boolean
  task_id?: string  // v2.0 Asynchronously execute the returned task ID
  status?: string   // v2.0 Task status
  message?: string  // v2.0 Prompt message
  result?: Record<string, any>  // v1.x The result of synchronous execution
  execution?: {  // v1.x execution information
    id: string
    workflow_id: string
    state: string
    started_at?: string
    completed_at?: string
    error?: string
  }
  error?: string
}

// API method
export const workflowApi = {
  /**
   * Get a list of all workflows
   */
  async listAll(): Promise<WorkflowSummary[]> {
    const res: ApiResponse<WorkflowSummary[]> = await request.get('/api/workflows')
    return res.data || []
  },

  /**
   * Get predefined templates
   */
  async getTemplates(): Promise<WorkflowDefinition[]> {
    const res: ApiResponse<WorkflowDefinition[]> = await request.get('/api/workflows/templates')
    return res.data || []
  },

  /**
   * Get individual workflow details
   */
  async get(id: string): Promise<WorkflowDefinition | null> {
    const res: ApiResponse<WorkflowDefinition> = await request.get(`/api/workflows/${id}`)
    return res.data || null
  },

  /**
   * Create new workflow
   */
  create(data: Partial<WorkflowDefinition>): Promise<ApiResponse<WorkflowDefinition>> {
    return request.post('/api/workflows', data)
  },

  /**
   * Update workflow
   */
  update(id: string, data: Partial<WorkflowDefinition>): Promise<ApiResponse<WorkflowDefinition>> {
    return request.put(`/api/workflows/${id}`, data)
  },

  /**
   * Delete workflow
   */
  delete(id: string): Promise<{ success: boolean; error?: string }> {
    return request.delete(`/api/workflows/${id}`)
  },

  /**
   * Validate workflow definition
   */
  async validate(data: Partial<WorkflowDefinition>): Promise<ApiResponse<ValidationResult>> {
    const res: ApiResponse<ValidationResult> = await request.post('/api/workflows/validate', data)
    return res
  },

  /**
   * Execute workflow
   * NOTE: Workflow execution is a long operation (may take 5-30 minutes), set a longer timeout and disable retries
   */
  async execute(id: string, inputs: Record<string, any>): Promise<ExecutionResult> {
    const res: ApiResponse<ExecutionResult> = await request.post(`/api/workflows/${id}/execute`, inputs, {
      timeout: 30 * 60 * 1000,  // 30 minutes timeout
      retryCount: 0  // Disable retries to avoid repeated executions
    } as any)
    // Extract actual execution results from ApiResponse
    if (res.success && res.data) {
      return res.data
    }
    // If the outer layer fails, construct a failed ExecutionResult
    return {
      success: false,
      error: res.message || 'Execution failed'
    }
  },

  /**
   * Create a workflow from a template
   */
  createFromTemplate(templateId: string, name: string): Promise<ApiResponse<WorkflowDefinition>> {
    return request.post('/api/workflows/from-template', { template_id: templateId, name })
  },

  /**
   * Copy workflow
   */
  duplicate(id: string, name: string): Promise<ApiResponse<WorkflowDefinition>> {
    return request.post(`/api/workflows/${id}/duplicate`, { name })
  },

  /**
   * Set as default analysis flow
   */
  setAsDefault(id: string): Promise<ApiResponse<void>> {
    return request.post(`/api/workflows/${id}/set-default`)
  }
}

export default workflowApi

// ============================================================================
// Module: workflowGrowth.ts
// ============================================================================

export enum GrowthMemoryStatus {
  PENDING = 'pending',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  EXPIRED = 'expired'
}

export enum GrowthSuggestionStatus {
  PENDING = 'pending',
  ACCEPTED = 'accepted',
  DISMISSED = 'dismissed',
  EXPIRED = 'expired'
}

export enum GrowthMemoryScope {
  TASK_TEMP = 'task_temp',
  OBJECT_TRACKING = 'object_tracking',
  USER_PREFERENCE = 'user_preference',
  RESEARCH_ASSET = 'research_asset',
  PATTERN = 'pattern'
}

export interface GrowthEvidenceRef {
  type: string
  id: string
  label?: string
}

export interface GrowthMemoryItem {
  memory_id: string
  user_id: string
  scope: GrowthMemoryScope | string
  status: GrowthMemoryStatus | string
  review_level: string
  source_type: string
  source_id: string
  task_type?: string
  workflow_id?: string
  object_type?: string
  object_key?: string
  title: string
  summary: string
  content: string
  structured_payload?: Record<string, any>
  confidence: number
  evidence_refs: GrowthEvidenceRef[]
  created_at: string
  updated_at: string
}

export interface GrowthSuggestion {
  suggestion_id: string
  user_id: string
  suggestion_type: string
  status: GrowthSuggestionStatus | string
  source_type: string
  source_id: string
  task_type?: string
  workflow_id?: string
  object_type?: string
  object_key?: string
  title: string
  summary: string
  suggested_action?: Record<string, any>
  confidence: number
  source_refs: GrowthEvidenceRef[]
  activation_result?: {
    status?: string
    target?: string
    mode?: string
    session_id?: string
    ai_message?: string
    error?: string
  }
  created_at: string
  updated_at: string
}

export interface TaskGrowthContextPayload {
  task_id: string
  memory_items: GrowthMemoryItem[]
  suggestions: GrowthSuggestion[]
  summary: {
    memory_items_count: number
    suggestions_count: number
  }
}

export function getTaskGrowthContext(taskId: string) {
  return ApiClient.get<TaskGrowthContextPayload>(`/api/workflow-growth/tasks/${taskId}`)
}

export function approveGrowthMemory(memoryId: string) {
  return ApiClient.post<{ success: boolean; message: string }>(`/api/workflow-growth/memories/${memoryId}/approve`)
}

export function rejectGrowthMemory(memoryId: string) {
  return ApiClient.post<{ success: boolean; message: string }>(`/api/workflow-growth/memories/${memoryId}/reject`)
}

export function acceptGrowthSuggestion(suggestionId: string) {
  return ApiClient.post<GrowthSuggestion>(`/api/workflow-growth/suggestions/${suggestionId}/accept`)
}

export function dismissGrowthSuggestion(suggestionId: string) {
  return ApiClient.post<{ success: boolean; message: string }>(`/api/workflow-growth/suggestions/${suggestionId}/dismiss`)
}

export const GrowthMemoryStatusNames: Record<string, string> = {
  pending: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired'
}

export const GrowthSuggestionStatusNames: Record<string, string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  dismissed: 'Ignored',
  expired: 'Expired'
}

export const GrowthMemoryScopeNames: Record<string, string> = {
  task_temp: 'task temporary memory',
  object_tracking: 'object tracking memory',
  user_preference: 'User preferences',
  research_asset: 'research assets',
  pattern: 'experience model'
}
