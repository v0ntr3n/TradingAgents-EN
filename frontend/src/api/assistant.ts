import { ApiClient, request } from './request'
import { fetchSSE } from '@/utils/fetchSSE'
import { request } from './request'
import { ApiClient, type ApiResponse } from './request'

// ============================================================================
// Module: assistant.ts
// ============================================================================

/**
 * Smart Assistant API
 */




export interface StockScopeReport {
  task_id?: string
  analysis_id?: string
  completed_at?: string
  is_stale?: boolean
  stale_hours?: number
  summary?: string
  recommendation?: string
  conclusion?: string
  action?: string
  confidence?: number | null
}

export interface StockScope {
  code?: string
  stock_name?: string
  thread_id?: string
  reports?: {
    stock_report?: StockScopeReport
    position_report?: StockScopeReport
  }
  review_summary?: StockScopeReport & {
    trade_count?: number | null
  }
  current_quote?: {
    price?: number
    change_percent?: number
  }
}

export interface UserContext {
  current_route?: string
  is_jdyun_mode?: boolean
  guide_completed?: boolean
  recent_console_errors?: string[]
  /** Stock details page context (only used when the general role enters from the details page, used for topic limitation and report aggregation interpretation) */
  stock_scope?: StockScope
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  model?: string
  model_config_id?: string
  /** Assistant role:general=Universal Analysis Assistant (default)/ usage_helper=Use a Q&A bot */
  assistant_role?: 'general' | 'usage_helper'
  /** Front-end context (page status is passed in usage_helper mode, stock_scope is passed when entering from the details page in general mode) */
  user_context?: UserContext
}

export interface ChatResponse {
  reply: string
  tools_used: string[]
  data_refs?: unknown[]
  conversation_id?: string
}

export interface PlannedAnalysisResponse extends ChatResponse {
  plan?: {
    question: string
    template_id?: string
    source: string
    steps: Array<{
      id: number
      tool: string
      args: Record<string, any>
      intent: string
      depends_on: number[]
    }>
  }
  step_results?: Array<{
    step_id: number
    tool: string
    intent: string
    success: boolean
    result?: any
    error?: string
    duration_ms: number
  }>
  source: 'seed_flow' | 'llm_plan' | 'react'
  supplemented: boolean
}

export interface PlannedAnalysisPlan {
  question: string
  template_id?: string
  source: string
  steps: Array<{
    id: number
    tool: string
    args: Record<string, any>
    intent: string
    depends_on: number[]
  }>
}

export interface PlannedStepResult {
  step_id: number
  tool: string
  intent: string
  success: boolean
  result?: any
  error?: string
  duration_ms: number
}

export interface MessageItem {
  role: 'user' | 'assistant'
  content: string
  tools_used?: string[]
}

export interface ConversationResponse {
  messages: MessageItem[]
  conversation_id?: string
}

export interface AssistantThreadSummary {
  abstract: string
  confirmed_facts: string[]
  open_questions: string[]
  next_actions: string[]
  focus_score: number
}

export interface AssistantThreadReportRef {
  ref_type: string
  report_key: string
  source_collection: string
  title: string
  symbol?: string | null
  summary: string
  status?: string | null
  task_id?: string | null
  analysis_id?: string | null
  created_at?: string | null
  linked_at?: string | null
}

export interface AssistantThreadReportDetail {
  ref_type: string
  report_key: string
  title: string
  symbol?: string | null
  status?: string | null
  task_id?: string | null
  analysis_id?: string | null
  created_at?: string | null
  linked_at?: string | null
  content: string
  content_format: string
}

export interface AssistantThreadReportDetailResponse {
  detail: AssistantThreadReportDetail
}

export interface AssistantThreadReportSearchResponse {
  items: AssistantThreadReportRef[]
  total: number
}

export interface AssistantThreadAttachReportResponse {
  success: boolean
  attached_ref: AssistantThreadReportRef
}

export interface AssistantThreadItem {
  thread_id: string
  title: string
  parent_thread_id?: string | null
  topic_type: string
  pinned: boolean
  archived: boolean
  message_count: number
  last_user_message: string
  updated_at?: string
  report_refs: AssistantThreadReportRef[]
  current_summary?: AssistantThreadSummary
}

export interface AssistantThreadListResponse {
  items: AssistantThreadItem[]
  total: number
}

export interface AssistantThreadMessagesResponse extends ConversationResponse {
  thread?: AssistantThreadItem
}

export interface ThreadSummarizeResponse {
  conversation_id: string
  summary: AssistantThreadSummary
}

export interface ThreadDeleteResponse {
  success: boolean
  deleted_thread_ids: string[]
}

export interface StreamCallbacks {
  onToken?: (content: string) => void
  onToolEvent?: (event: Record<string, any>) => void
  onDone?: (data: {
    tools_used: string[]
    conversation_id?: string
    plan?: PlannedAnalysisPlan
    step_results?: PlannedStepResult[]
    source?: 'seed_flow' | 'llm_plan' | 'react'
    supplemented?: boolean
    error?: boolean
    reply?: string
  }) => void
  onError?: (message: string) => void
}

function createAssistantStream(
  path: string,
  payload: ChatRequest,
  callbacks?: StreamCallbacks,
): AbortController {
  return fetchSSE(path, {
    method: 'POST',
    body: payload,
    onEvent: (eventType, data) => {
      if (eventType === 'token') {
        callbacks?.onToken?.(data.content || '')
      } else {
        callbacks?.onToolEvent?.({ ...data, event: eventType || data.event })
      }
    },
    onDone: (data) => {
      callbacks?.onDone?.(data || { tools_used: [] })
    },
    onError: (message) => {
      callbacks?.onError?.(message)
    },
  })
}

export const assistantApi = {
  /** Get list of topics */
  async getThreads(): Promise<AssistantThreadListResponse> {
    const res = await request.get<AssistantThreadListResponse>('/api/assistant/threads')
    return res as unknown as AssistantThreadListResponse
  },

  /** Create new topic */
  async createThread(title?: string, parentThreadId?: string): Promise<AssistantThreadItem> {
    const res = await request.post<AssistantThreadItem>('/api/assistant/threads', {
      title,
      parent_thread_id: parentThreadId
    })
    return res as unknown as AssistantThreadItem
  },

  /** Delete a topic and its subtopics */
  async deleteThread(threadId: string): Promise<ThreadDeleteResponse> {
    const res = await request.delete<ThreadDeleteResponse>(`/api/assistant/threads/${threadId}`)
    return res as unknown as ThreadDeleteResponse
  },

  /** Get the specified topic message */
  async getThreadMessages(threadId: string): Promise<AssistantThreadMessagesResponse> {
    const res = await request.get<AssistantThreadMessagesResponse>(`/api/assistant/threads/${threadId}/messages`)
    return res as unknown as AssistantThreadMessagesResponse
  },

  /** Get topic correlation report details */
  async getThreadReportDetail(threadId: string, refType: string, reportKey: string): Promise<AssistantThreadReportDetailResponse> {
    const encodedRefType = encodeURIComponent(refType)
    const encodedReportKey = encodeURIComponent(reportKey)
    const res = await request.get<AssistantThreadReportDetailResponse>(
      `/api/assistant/threads/${threadId}/reports/${encodedRefType}/${encodedReportKey}`
    )
    return res as unknown as AssistantThreadReportDetailResponse
  },

  /** Search can relate old reports */
  async getThreadReportCandidates(threadId: string, refType: string, keyword?: string, limit = 8): Promise<AssistantThreadReportSearchResponse> {
    const res = await request.get<AssistantThreadReportSearchResponse>(`/api/assistant/threads/${threadId}/report-candidates`, {
      params: {
        ref_type: refType,
        keyword,
        limit,
      }
    })
    return res as unknown as AssistantThreadReportSearchResponse
  },

  /** Manually link old reports */
  async attachThreadReport(threadId: string, refType: string, reportKey: string): Promise<AssistantThreadAttachReportResponse> {
    const res = await request.post<AssistantThreadAttachReportResponse>(`/api/assistant/threads/${threadId}/report-links`, {
      ref_type: refType,
      report_key: reportKey,
    })
    return res as unknown as AssistantThreadAttachReportResponse
  },

  /** Clear the specified topic */
  async clearThreadMessages(threadId: string): Promise<void> {
    await request.delete(`/api/assistant/threads/${threadId}/messages`)
  },

  /** Manually summarize specified topics */
  async summarizeThread(threadId: string): Promise<ThreadSummarizeResponse> {
    const res = await request.post<ThreadSummarizeResponse>(`/api/assistant/threads/${threadId}/summarize`)
    return res as unknown as ThreadSummarizeResponse
  },

  /** Get session history */
  async getConversation(): Promise<ConversationResponse> {
    const res = await request.get<ConversationResponse>('/api/assistant/conversation')
    return res as unknown as ConversationResponse
  },

  /** clear session */
  async clearConversation(): Promise<void> {
    await request.delete('/api/assistant/conversation')
  },

  /** Send conversation message */
  async chat(message: string, conversationId?: string, model?: string, modelConfigId?: string): Promise<ChatResponse> {
    const res = await request.post<ChatResponse>('/api/assistant/chat', {
      message,
      conversation_id: conversationId,
      model,
      model_config_id: modelConfigId,
    })
    return res as unknown as ChatResponse
  },

  /** Planning analysis (Plan-then-Execute mode) */
  async plannedAnalysis(message: string, conversationId?: string, model?: string, modelConfigId?: string): Promise<PlannedAnalysisResponse> {
    const res = await request.post<PlannedAnalysisResponse>('/api/assistant/planned-analysis', {
      message,
      conversation_id: conversationId,
      model,
      model_config_id: modelConfigId,
    })
    return res as unknown as PlannedAnalysisResponse
  },

  /** Streaming Conversations (SSE)— Use quick conversation mode
   * extraPayload: Optional additional request fields for usage_helper mode passing assistant_role and user_context
   */
  chatStream(
    message: string,
    conversationId?: string,
    model?: string,
    modelConfigId?: string,
    callbacks?: StreamCallbacks,
    extraPayload?: Partial<ChatRequest>,
  ): AbortController {
    return createAssistantStream(
      '/api/assistant/chat/stream',
      {
        message,
        conversation_id: conversationId,
        model,
        model_config_id: modelConfigId,
        ...extraPayload,
      },
      callbacks,
    )
  },

  plannedAnalysisStream(
    message: string,
    conversationId?: string,
    model?: string,
    modelConfigId?: string,
    callbacks?: StreamCallbacks,
  ): AbortController {
    return createAssistantStream(
      '/api/assistant/planned-analysis/stream',
      {
        message,
        conversation_id: conversationId,
        model,
        model_config_id: modelConfigId,
      },
      callbacks,
    )
  },

  // ---- mem0 unified memory layer ----

  async getMemoryHealth() {
    try {
      return await ApiClient.get<{ ok: boolean; mem0_version?: string; error?: string }>(
        '/api/memory/health',
        undefined,
        { skipErrorHandler: true },
      )
    } catch (error: any) {
      return error?.response?.data ?? {
        success: false,
        data: { ok: false, error: error?.message || 'Memory layer is not available' },
        message: error?.message || 'Memory layer is not available',
      }
    }
  },

  getMemoryStats() {
    return request.get<{
      enabled: boolean
      available?: boolean
      user_id?: string
      scopes?: Record<string, number>
      message?: string
    }>('/api/memory/stats')
  },

  /** Reinitialize and rebuild user manual vector index (manual remedy when semantic retrieval is not available using Q&A Assistant) */
  async rebuildUserManualIndex(): Promise<{
    success: boolean
    rebuilt?: boolean
    sections_count?: number
    manuals_count?: number
    signature?: string
  }> {
    const res = await request.post<{
      success: boolean
      rebuilt?: boolean
      sections_count?: number
      manuals_count?: number
      signature?: string
    }>('/api/assistant/user-manual-index/rebuild')
    return res as unknown as {
      success: boolean
      rebuilt?: boolean
      sections_count?: number
      manuals_count?: number
      signature?: string
    }
  },
}

// ============================================================================
// Module: embeddedNanobot.ts
// ============================================================================

export interface EmbeddedNanobotStatusResponse {
  enabled: boolean
  user_id: string
  workspace: string
}

export interface EmbeddedNanobotChatRequest {
  message: string
  display_message?: string
  session_key?: string
  model?: string
  channel?: string
  chat_id?: string
  media?: string[]
  skill_names?: string[]
  thread_context?: EmbeddedNanobotThreadContext
}

export interface EmbeddedNanobotThreadContext {
  spec_id?: string
  spec_name?: string
  workshop_session_id?: string
  version_id?: string
  version_status?: string
  workflow_id?: string
  node_id?: string
  preference_id?: string
  debug_template_id?: string
  has_blocking_gaps?: boolean
  evaluation_status?: string
  intent?: Record<string, any>
}

export interface EmbeddedNanobotChatResponse {
  content: string
  session_key: string
  thread_id?: string
  stop_reason?: string
  tools_used: string[]
  usage: Record<string, number>
  tool_events: Array<Record<string, any>>
  thread_context?: EmbeddedNanobotThreadContext
}

export interface EmbeddedNanobotThreadItem {
  thread_id: string
  title: string
  session_key: string
  channel: string
  archived: boolean
  message_count: number
  last_user_message: string
  summary: string
  created_at?: string
  updated_at?: string
  thread_context?: EmbeddedNanobotThreadContext
}

export interface EmbeddedNanobotMessageItem {
  message_id: string
  role: string
  content: string
  tools_used: string[]
  stop_reason?: string
  usage: Record<string, number>
  tool_events: Array<Record<string, any>>
  created_at?: string
}

export interface EmbeddedNanobotStreamCallbacks {
  onStarted?: (data: { message?: string; session_key?: string }) => void
  onProgress?: (data: { message?: string; session_key?: string }) => void
  onToken?: (content: string) => void
  onToolEvent?: (event: Record<string, any>) => void
  onStepEvent?: (event: Record<string, any>) => void
  onDone?: (data: EmbeddedNanobotChatResponse) => void
  onError?: (message: string) => void
  onAbort?: () => void
}

function createEmbeddedNanobotStream(
  path: string,
  payload: EmbeddedNanobotChatRequest,
  callbacks?: EmbeddedNanobotStreamCallbacks,
): AbortController {
  return fetchSSE(path, {
    method: 'POST',
    body: payload,
    onEvent: (eventType, data) => {
      switch (eventType) {
        case 'started':
          callbacks?.onStarted?.(data)
          break
        case 'progress':
          callbacks?.onProgress?.(data)
          break
        case 'token':
          callbacks?.onToken?.(data.content || '')
          break
        case 'tool_event':
          callbacks?.onToolEvent?.(data)
          break
        case 'step_event':
          callbacks?.onStepEvent?.(data)
          break
      }
    },
    onDone: (data) => {
      callbacks?.onDone?.(data as EmbeddedNanobotChatResponse)
    },
    onError: (message) => {
      callbacks?.onError?.(message)
    },
    onAbort: () => {
      callbacks?.onAbort?.()
    },
  })
}

export const embeddedNanobotApi = {
  async getStatus(): Promise<EmbeddedNanobotStatusResponse> {
    return await request.get('/api/embedded-nanobot/status') as unknown as EmbeddedNanobotStatusResponse
  },

  async listThreads(limit = 50, archivedOnly = false): Promise<{ items: EmbeddedNanobotThreadItem[]; total: number }> {
    return await request.get(`/api/embedded-nanobot/threads?limit=${limit}&archived_only=${archivedOnly}`) as unknown as { items: EmbeddedNanobotThreadItem[]; total: number }
  },

  async getThreadMessages(threadId: string): Promise<{ thread: EmbeddedNanobotThreadItem | null; messages: EmbeddedNanobotMessageItem[] }> {
    return await request.get(`/api/embedded-nanobot/threads/${encodeURIComponent(threadId)}/messages`) as unknown as { thread: EmbeddedNanobotThreadItem | null; messages: EmbeddedNanobotMessageItem[] }
  },

  async deleteThread(threadId: string): Promise<{ archived: boolean; thread_id: string; deleted_messages: number }> {
    return await request.delete(`/api/embedded-nanobot/threads/${encodeURIComponent(threadId)}`) as unknown as { archived: boolean; thread_id: string; deleted_messages: number }
  },

  async restoreThread(threadId: string): Promise<{ restored: boolean; thread_id: string; archived: boolean }> {
    return await request.post(`/api/embedded-nanobot/threads/${encodeURIComponent(threadId)}/restore`) as unknown as { restored: boolean; thread_id: string; archived: boolean }
  },

  async updateThreadContext(
    threadId: string,
    payload: { session_key?: string; channel?: string; thread_context: EmbeddedNanobotThreadContext },
  ): Promise<{ thread: EmbeddedNanobotThreadItem | null; messages: EmbeddedNanobotMessageItem[] }> {
    return await request.put(
      `/api/embedded-nanobot/threads/${encodeURIComponent(threadId)}/context`,
      payload,
      {
        skipAuthError: true,
        skipErrorHandler: true,
      },
    ) as unknown as { thread: EmbeddedNanobotThreadItem | null; messages: EmbeddedNanobotMessageItem[] }
  },

  async chat(payload: EmbeddedNanobotChatRequest): Promise<EmbeddedNanobotChatResponse> {
    return await request.post('/api/embedded-nanobot/chat', payload) as unknown as EmbeddedNanobotChatResponse
  },

  chatStream(payload: EmbeddedNanobotChatRequest, callbacks?: EmbeddedNanobotStreamCallbacks): AbortController {
    return createEmbeddedNanobotStream('/api/embedded-nanobot/chat/stream', payload, callbacks)
  },
}

export default embeddedNanobotApi

// ============================================================================
// Module: memory.ts
// ============================================================================

/**
 * mem0 unified memory layer API
 */



export interface MemoryItem {
  id: string
  memory: string
  user_id: string
  agent_id: string
  scope: string
  score: number
  metadata: Record<string, any>
  created_at: string
  updated_at: string
  object_type?: string
  object_key?: string
  symbol?: string
  market?: string
  memory_kind?: string
}

export interface MemoryQueryParams {
  scope?: string
  page?: number
  page_size?: number
  object_type?: string
  symbol?: string
  market?: string
  memory_kind?: string
}

export interface MemoryStatsData {
  enabled: boolean
  available?: boolean
  user_id?: string
  total?: number
  scopes?: Record<string, number>
  message?: string
}

export interface MemoryListData {
  items: MemoryItem[]
  total: number
  page: number
  page_size: number
}

export interface MemoryRecallData {
  count: number
  items: MemoryItem[]
}

/** Intelligent Assistant Fact Memory (assistant_memory_facts) */
export interface AssistantFactItem {
  id: string
  topic: string
  content: string
  symbol?: string
  related_terms?: string[]
  tool_id?: string
  fetched_at?: string
  category?: string
  valid_until?: string
  thread_id?: string
}

export interface AssistantFactListData {
  items: AssistantFactItem[]
  total: number
  page: number
  page_size: number
}

export const FACT_CATEGORY_LABELS: Record<string, string> = {
  realtime_quote: 'Real-time quotes',
  industry_metric: 'Industry indicators',
  company_financial: 'corporate finance',
  company_static: 'Company information',
  default: 'Universal',
}

export const SCOPE_LABELS: Record<string, string> = {
  conversation: 'dialogue memory',
  user_preference: 'User preferences',
  analysis_insight: 'Analytical Insights',
  skill_lesson: 'Skills experience',
  agent_experience: 'Agent experience',
  trade_pattern: 'trading model',
}

export const SCOPE_COLORS: Record<string, string> = {
  conversation: '',
  user_preference: 'success',
  analysis_insight: 'warning',
  skill_lesson: 'danger',
  agent_experience: 'info',
  trade_pattern: 'success',
}

export const memoryApi = {
  async getHealth() {
    try {
      const res = await ApiClient.get<{ ok: boolean; mem0_version?: string; error?: string }>(
        '/api/memory/health',
        undefined,
        { skipErrorHandler: true },
      )
      return (res as any)?.data ?? res
    } catch (error: any) {
      const responseData = error?.response?.data
      return responseData?.data ?? {
        ok: false,
        error: responseData?.message || error?.message || 'Memory layer is not available',
      }
    }
  },

  async getStats(): Promise<MemoryStatsData> {
    const res: any = await request.get('/api/memory/stats')
    return res?.data ?? res
  },

  async getList(params: MemoryQueryParams = {}): Promise<MemoryListData> {
    const res: any = await request.get('/api/memory/list', { params })
    return res?.data ?? res
  },

  async recall(query: string, params: MemoryQueryParams = {}, limit = 10): Promise<MemoryRecallData> {
    const res: any = await request.get('/api/memory/recall', {
      params: { query, limit, ...params },
    })
    return res?.data ?? res
  },

  async deleteMemory(memoryId: string): Promise<boolean> {
    const res: any = await request.delete(`/api/memory/${encodeURIComponent(memoryId)}`)
    return res?.success ?? false
  },

  async batchDelete(memoryIds: string[]): Promise<{ deleted: number; requested: number }> {
    const res: any = await request.post('/api/memory/batch-delete', { memory_ids: memoryIds })
    return res?.data ?? { deleted: 0, requested: memoryIds.length }
  },

  async deleteAll(): Promise<{ deleted: number }> {
    const res: any = await request.delete('/api/memory/clear-all')
    return res?.data ?? { deleted: 0 }
  },

  // ── Intelligent Assistant Fact Memory (assistant_memory_facts)───────────────────────────
  async getAssistantFacts(
    params: { q?: string; symbol?: string; category?: string; page?: number; page_size?: number } = {},
  ): Promise<AssistantFactListData> {
    const res: any = await request.get('/api/memory/assistant-facts', { params })
    return res?.data ?? res
  },

  async deleteAssistantFact(factId: string): Promise<boolean> {
    const res: any = await request.delete(`/api/memory/assistant-facts/${encodeURIComponent(factId)}`)
    return res?.success ?? false
  },

  async batchDeleteAssistantFacts(factIds: string[]): Promise<{ deleted: number; requested: number }> {
    const res: any = await request.post('/api/memory/assistant-facts/batch-delete', { fact_ids: factIds })
    return res?.data ?? { deleted: 0, requested: factIds.length }
  },
}

// ============================================================================
// Module: advancedCourses.ts
// ============================================================================

export interface AdvancedLessonContentPayload {
  filename: string
  content: string
}

export interface AdvancedSampleContentPayload {
  sample_id: string
  filename: string
  content: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export function getAdvancedLessonContent(filename: string): Promise<ApiResponse<AdvancedLessonContentPayload>> {
  return ApiClient.get('/api/learning/advanced-courses/lessons/content', { filename })
}

export function downloadAdvancedLesson(filename: string) {
  return ApiClient.download(
    `/api/learning/advanced-courses/lessons/download?filename=${encodeURIComponent(filename)}`,
    filename
  )
}

export function getAdvancedSampleContent(sampleId: string): Promise<ApiResponse<AdvancedSampleContentPayload>> {
  return ApiClient.get(`/api/learning/advanced-courses/samples/${encodeURIComponent(sampleId)}`)
}

export function downloadAdvancedSample(sampleId: string, filename: string) {
  return ApiClient.download(
    `/api/learning/advanced-courses/samples/${encodeURIComponent(sampleId)}/download`,
    filename
  )
}

export function getAdvancedCourseImageUrl(imagePath: string) {
  const encodedPath = imagePath
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/')

  return `${API_BASE_URL}/api/learning/advanced-courses/images/${encodedPath}`
}
