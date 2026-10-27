/**
 * unified mission center API
 *
 * docking backend /api/v2/tasks/* endpoint
 * Supports all types of analysis tasks (stock analysis, position analysis, transaction review, etc.)
 */

import { ApiClient } from './request'

export type TaskTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

// ==================== type definition ====================

/**
 * Task type enum
 */
export enum TaskType {
  STOCK_ANALYSIS = 'stock_analysis',
  ETF_ANALYSIS = 'etf_analysis',
  POSITION_ANALYSIS = 'position_analysis',
  TRADE_REVIEW = 'trade_review',
  PORTFOLIO_HEALTH = 'portfolio_health',
  RISK_ASSESSMENT = 'risk_assessment',
  MARKET_OVERVIEW = 'market_overview',
  SECTOR_ANALYSIS = 'sector_analysis'
}

/**
 * Task status enum
 */
export enum TaskStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  SUSPENDED = 'suspended'  // Pending status (unfinished tasks after service restart)
}

/**
 * task list item
 */
export interface TaskListItem {
  task_id: string
  task_type: TaskType
  status: TaskStatus
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  
  // Task parameters (for display)
  symbol?: string
  code?: string
  market?: string
}

/**
 * Mission details
 */
export interface TaskDetail {
  task_id: string
  user_id: string
  task_type: TaskType
  task_params: Record<string, any>
  workflow_id?: string
  engine_type: string
  preference_type: string
  status: TaskStatus
  progress: number
  current_step?: string
  result?: Record<string, any>
  created_at: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  retry_count: number
  max_retries: number
  tokens_used: number
  cost: number
  growth_context?: {
    memory_items_count: number
    suggestions_count: number
    memory_item_ids: string[]
    suggestion_ids: string[]
    extracted_at: string
    source_type: string
    source_id?: string
  } | null
}

/**
 * Task statistics
 */
export interface TaskStatistics {
  total: number
  pending: number
  processing: number
  completed: number
  failed: number
  cancelled: number
}

/**
 * Task list query parameters
 */
export interface TaskListParams {
  task_type?: TaskType
  status?: TaskStatus
  symbol?: string
  limit?: number
  skip?: number
}

// ==================== API method ====================

/**
 * Get task list
 */
export function getTaskList(params?: TaskListParams) {
  return ApiClient.get<{
    tasks: TaskListItem[]
    total: number
    limit: number
    skip: number
  }>('/api/v2/tasks/list', params)
}

/**
 * Get task statistics
 */
export function getTaskStatistics() {
  return ApiClient.get<TaskStatistics>('/api/v2/tasks/statistics')
}

/**
 * Get task details
 */
export function getTaskDetail(taskId: string) {
  return ApiClient.get<TaskDetail>(`/api/v2/tasks/${taskId}`)
}

/**
 * Cancel task
 */
export function cancelTask(taskId: string) {
  return ApiClient.delete<{ success: boolean; message: string }>(`/api/v2/tasks/${taskId}`)
}

/**
 * Resume a suspended task
 */
export function resumeTask(taskId: string) {
  return ApiClient.post<{ success: boolean; message: string }>(`/api/v2/tasks/${taskId}/resume`)
}

/**
 * Task type Chinese name mapping
 */
export const TaskTypeNames: Record<TaskType, string> = {
  [TaskType.STOCK_ANALYSIS]: 'stock analysis',
  [TaskType.ETF_ANALYSIS]: 'ETF analysis',
  [TaskType.POSITION_ANALYSIS]: 'Position analysis',
  [TaskType.TRADE_REVIEW]: 'Transaction review',
  [TaskType.PORTFOLIO_HEALTH]: 'Combination health',
  [TaskType.RISK_ASSESSMENT]: 'risk assessment',
  [TaskType.MARKET_OVERVIEW]: 'Market overview',
  [TaskType.SECTOR_ANALYSIS]: 'Sector analysis'
}

/**
 * Task status Chinese name mapping
 */
export const TaskStatusNames: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: 'Waiting',
  [TaskStatus.PROCESSING]: 'In progress',
  [TaskStatus.COMPLETED]: 'Completed',
  [TaskStatus.FAILED]: 'failed',
  [TaskStatus.CANCELLED]: 'Canceled',
  [TaskStatus.SUSPENDED]: 'Pending'
}

/**
 * Task status color mapping
 */
export const TaskStatusColors: Record<TaskStatus, TaskTagType> = {
  [TaskStatus.PENDING]: 'info',
  [TaskStatus.PROCESSING]: 'warning',
  [TaskStatus.COMPLETED]: 'success',
  [TaskStatus.FAILED]: 'danger',
  [TaskStatus.CANCELLED]: 'info',
  [TaskStatus.SUSPENDED]: 'warning'
}


// ==================== Dedicated to general research tasks API ====================

/**
 * Common research task list items
 */
export interface GeneralTaskListItem {
  task_id: string
  task_type: string
  status: string
  progress: number
  workflow_id?: string
  analysis_target: string
  research_depth?: string
  created_at?: string
  started_at?: string
  completed_at?: string
  execution_time: number
  error_message?: string
  current_step?: string
}

/**
 * Common research task query parameters
 */
export interface GeneralTaskListParams {
  workflow_id?: string
  date_start?: string
  date_end?: string
  keyword?: string
  status?: string
  limit?: number
  skip?: number
}

/**
 * Get a list of general research tasks
 */
export function getGeneralTaskList(params?: GeneralTaskListParams) {
  return ApiClient.get<{
    tasks: GeneralTaskListItem[]
    total: number
    limit: number
    skip: number
  }>('/api/v2/tasks/general/list', params)
}

/**
 * Get general research task statistics
 */
export function getGeneralTaskStatistics() {
  return ApiClient.get<{
    total: number
    completed: number
    failed: number
    processing: number
    pending: number
  }>('/api/v2/tasks/general/statistics')
}

/**
 * Chinese name of general research task status
 */
export const GeneralTaskStatusNames: Record<string, string> = {
  pending: 'Waiting',
  processing: 'In progress',
  completed: 'Completed',
  failed: 'failed',
  cancelled: 'Canceled',
  suspended: 'Pending'
}

/**
 * Common research task status colors
 */
export const GeneralTaskStatusColors: Record<string, TaskTagType> = {
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
  cancelled: 'info',
  suspended: 'warning'
}

