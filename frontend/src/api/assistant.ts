/**
 * Smart Assistant API
 */

import { ApiClient, request } from './request'
import { fetchSSE } from '@/utils/fetchSSE'

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
