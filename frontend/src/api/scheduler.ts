/**
 * Related to scheduled tasks API
 */
import { ApiClient } from './request'

// Pending execution records
export interface SuspendedExecution {
  execution_id: string
  progress: number
  processed_items?: number
  total_items?: number
  current_item?: string
  started_at?: string
  message?: string
}

export interface RunningExecution {
  execution_id: string
  progress: number
  processed_items?: number
  total_items?: number
  current_item?: string
  started_at?: string
  updated_at?: string
  message?: string
}

// Task status
export interface JobStatus {
  id: string  // The backend returns the id, not job_id
  name: string
  paused: boolean  // The backend returns paused, not enabled
  next_run_time?: string
  last_run_time?: string
  trigger?: string
  func?: string
  kwargs?: Record<string, unknown>
  display_name?: string
  description?: string
  has_suspended_execution?: boolean  // Is there any pending execution record?
  suspended_execution?: SuspendedExecution  // Pending execution record details
  has_running_execution?: boolean
  running_execution?: RunningExecution
}

// Task progress
export interface JobProgress {
  job_id: string
  execution_id?: string  // 🔥 Execution record ID, used to terminate the operation
  progress: number
  status: 'running' | 'cancelling' | 'suspended' | 'success' | 'failed' | 'cancelled' | 'unknown'
  message?: string
  current_item?: string
  total_items?: number
  processed_items?: number
  started_at?: string  // start time
  updated_at?: string   // Update time
}

export interface JobHistory {
  [key: string]: any
}

export interface JobExecution {
  [key: string]: any
}

export interface SchedulerStats {
  total_jobs: number
  running_jobs: number
  paused_jobs: number
  [key: string]: any
}

export type Job = JobStatus

// API response format
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data: T
}

/**
 * Get a list of all scheduled tasks
 */
export const getJobs = (): Promise<ApiResponse<JobStatus[]>> => {
  return ApiClient.get('/api/scheduler/jobs')
}

/**
 * Get task details
 */
export const getJobDetail = (jobId: string): Promise<ApiResponse<JobStatus>> => {
  return ApiClient.get(`/api/scheduler/jobs/${jobId}`)
}

/**
 * Get real-time progress of tasks
 */
export const getJobProgress = (jobId: string): Promise<ApiResponse<JobProgress>> => {
  return ApiClient.get(`/api/scheduler/jobs/${jobId}/progress`)
}

/**
 * Manually trigger tasks
 */
export const triggerJob = (jobId: string, options?: {
  force?: boolean
  incremental?: boolean  // Whether to incrementally synchronize (only historical data synchronization tasks are valid)
}): Promise<ApiResponse<void>> => {
  const params = new URLSearchParams()
  if (options?.force) {
    params.append('force', 'true')
  }
  if (options?.incremental !== undefined) {
    params.append('incremental', options.incremental ? 'true' : 'false')
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/trigger${queryString ? '?' + queryString : ''}`)
}

/**
 * Pause task
 */
export const pauseJob = (jobId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/pause`)
}

/**
 * recovery task
 */
export const resumeJob = (jobId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/jobs/${jobId}/resume`)
}

/**
 * Resumes suspended task execution (continues where it left off)
 */
export const resumeSuspendedExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/resume`)
}

/**
 * Cancel the pending task execution record (used when the user chooses to restart)
 */
export const cancelSuspendedExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/cancel`)
}

/**
 * Get scheduler statistics
 */
export const getSchedulerStats = (): Promise<ApiResponse<any>> => {
  return ApiClient.get('/api/scheduler/stats')
}

/**
 * Update task metadata (display name and description)
 */
export const updateJobMetadata = (
  jobId: string,
  metadata: {
    display_name?: string
    description?: string
  }
): Promise<ApiResponse<void>> => {
  return ApiClient.put(`/api/scheduler/jobs/${jobId}/metadata`, metadata)
}

/**
 * Rescheduling tasks (modifying CRON expression)
 */
export const rescheduleJob = (
  jobId: string,
  cron: string
): Promise<ApiResponse<void>> => {
  return ApiClient.put(`/api/scheduler/jobs/${jobId}/schedule`, { cron })
}

/**
 * Get task execution history (all tasks)
 */
export const getJobExecutions = (params?: {
  job_id?: string
  status?: string
  is_manual?: boolean
  limit?: number
  offset?: number
}): Promise<ApiResponse<{
  items: any[]
  total: number
  limit: number
  offset: number
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.job_id) queryParams.append('job_id', params.job_id)
  if (params?.status) queryParams.append('status', params.status)
  if (params?.is_manual !== undefined) queryParams.append('is_manual', String(params.is_manual))
  if (params?.limit) queryParams.append('limit', String(params.limit))
  if (params?.offset) queryParams.append('offset', String(params.offset))
  
  const queryString = queryParams.toString()
  return ApiClient.get(`/api/scheduler/executions${queryString ? '?' + queryString : ''}`)
}

/**
 * Get the execution history of a specified task
 */
export const getSingleJobExecutions = (
  jobId: string,
  params?: {
    status?: string
    is_manual?: boolean
    limit?: number
    offset?: number
  }
): Promise<ApiResponse<{
  items: any[]
  total: number
  limit: number
  offset: number
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.status) queryParams.append('status', params.status)
  if (params?.is_manual !== undefined) queryParams.append('is_manual', String(params.is_manual))
  if (params?.limit) queryParams.append('limit', String(params.limit))
  if (params?.offset) queryParams.append('offset', String(params.offset))
  
  const queryString = queryParams.toString()
  return ApiClient.get(`/api/scheduler/jobs/${jobId}/executions${queryString ? '?' + queryString : ''}`)
}

/**
 * Cancel execution logging (general, including pending executions)
 */
export const cancelExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.post(`/api/scheduler/executions/${executionId}/cancel`)
}

/**
 * Mark execution record as failed
 */
export const markExecutionFailed = (
  executionId: string,
  reason?: string
): Promise<ApiResponse<void>> => {
  const params = new URLSearchParams()
  if (reason) {
    params.append('reason', reason)
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/executions/${executionId}/mark-failed${queryString ? '?' + queryString : ''}`)
}

/**
 * Delete execution record
 */
export const deleteExecution = (executionId: string): Promise<ApiResponse<void>> => {
  return ApiClient.delete(`/api/scheduler/executions/${executionId}`)
}

/**
 * Retry failed stocks (retry only retryable errors, skip errors with no data)
 * Suitable for historical data synchronization tasks (Tushare/AKShare)
 */
export const retryFailedSymbols = (
  executionId: string,
  options?: {
    start_date?: string  // Start date (optional, the date of the original task is used by default)
    end_date?: string     // End date (optional, the date of the original task is used by default)
    period?: 'daily' | 'weekly' | 'monthly'  // Data period, default daily
  }
): Promise<ApiResponse<{
  total_retried: number      // Total number of stocks to retry
  success_count: number      // Number of successes
  error_count: number        // Number of failures
  no_data_count: number     // No data count (skipped)
  retryable_errors_count: number  // Number of retryable errors
}>> => {
  const params = new URLSearchParams()
  if (options?.start_date) {
    params.append('start_date', options.start_date)
  }
  if (options?.end_date) {
    params.append('end_date', options.end_date)
  }
  if (options?.period) {
    params.append('period', options.period)
  }
  const queryString = params.toString()
  return ApiClient.post(`/api/scheduler/executions/${executionId}/retry-failed${queryString ? '?' + queryString : ''}`)
}
