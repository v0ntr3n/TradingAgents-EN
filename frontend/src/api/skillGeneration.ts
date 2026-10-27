import request from './request'

// ==================== type definition ====================

/** Start session request */
export interface StartSessionRequest {
  description: string
  user_id?: string
  handoff_context?: SkillHandoffContext
  iterate_skill_id?: string
  provider?: string
  model?: string
  /** Requirements analysis model (overrides the system s default in-depth reasoning model) */
  reasoning_model?: string
  /** Code generation model (overrides the system s default programming model) */
  coding_model?: string
}

export interface SkillHandoffContext {
  source: string
  source_spec_id?: string
  source_name?: string
  target_capability?: string
  handoff_intent?: string
}

/** Available model items */
export interface AvailableModelItem {
  model_name: string
  display_name: string
  provider: string
  enabled: boolean
}

/** model list response */
export interface AvailableModelsResult {
  models: AvailableModelItem[]
  default_reasoning_model: string | null
  default_coding_model: string | null
}

/** session response */
export interface SessionStartResult {
  session_id: string
  ai_message: string
  clarity_level: string
  boundary_check: BoundaryCheck | null
  current_round: number
  expected_rounds: number
}

/** Conversation reply results */
export interface SessionRespondResult {
  session_id: string
  ai_message: string
  current_round: number
  expected_rounds: number
  is_final_round: boolean
  boundary_check?: BoundaryCheck | null
}

/** Confirm the generated results */
export interface ConfirmResult {
  status: string
  session_id: string
  skill_id: string | null
  spec: Record<string, any> | null
  success: boolean
  total_rounds: number
  total_time: number
  final_score: number | null
  error: string | null
  /** Instructions for external interface preflight interception */
  message?: string | null
  interface_preflight?: InterfacePreflightResult | null
}

export interface RepairPlanResult {
  status: string
  session_id: string
  ai_message: string
}

export interface IterationRoundDetail {
  round_number: number
  feedback?: string
  decision?: string
  validation?: {
    passed?: boolean
    errors?: string[]
    warnings?: string[]
  } | null
  sandbox?: {
    success?: boolean
    error?: string | null
    stdout?: string
    stderr?: string
  } | null
  eval_score?: {
    executability?: number
    authenticity?: number
    completeness?: number
    relevance?: number
    format_quality?: number
    total?: number
  } | null
}

export interface PipelineResultDetail {
  success?: boolean
  tool_id?: string
  final_code?: string
  final_metadata?: Record<string, any>
  iterations?: IterationRoundDetail[]
  total_rounds?: number
  total_time?: number
  error?: string | null
}

/** Real-time results of quality assessment (Judge white box scoring) */
export interface PipelineEvalResult {
  executability: number
  authenticity: number
  completeness: number
  relevance: number
  format_quality: number
  total: number
  /** Which round of evaluation (starting from 1) */
  round?: number
  /** Whether the passing threshold is reached */
  passed: boolean
  /** Judge One word comment from an expert */
  expert_comment?: string
  /** Whether the business acceptance (black box) is passed, it may be returned under the agent path */
  business_passed?: boolean
}

/** Boundary detection */
export interface BoundaryCheck {
  within_boundary: boolean
  complexity_score: number
  concerns: string[]
  decomposition_suggestions: string[]
}

export interface SkillAgentUsage {
  version_id: string
  spec_id: string
  version?: number | null
  status: string
  agent_name: string
  published_from_session_id?: string
  updated_at?: string
}

/** external Skill */
export interface ExternalSkill {
  tool_id: string
  display_name: string
  description: string
  category: string
  data_source: string
  parameters: SkillParameter[]
  code: string
  status: string
  source: string
  origin_source?: string
  origin_workshop_session_id?: string
  origin_spec_id?: string
  origin_version_id?: string
  origin_gap_id?: string
  origin_agent_name?: string
  used_by_agents?: SkillAgentUsage[]
  session_id: string
  generation_rounds: number
  generation_time: number
  final_score: number | null
  generation_context?: SkillGenerationRecommendations | null
  created_at: string
  updated_at: string
}

/** Skill parameters */
export interface SkillParameter {
  name: string
  type: string
  description: string
  required: boolean
  default?: any
}

export interface StockDataCatalogField {
  name: string
  type: string
  description: string
}

export interface StockDataCatalogCollection {
  collection: string
  purpose: string
  preferred_access: string[]
  query_keys: string[]
  notes: string[]
  fields: StockDataCatalogField[]
}

export interface StockDataCatalogResult {
  collections: StockDataCatalogCollection[]
  doc: string
}

export interface ExternalDataSourceCatalogItem {
  source_id: string
  display_name: string
  source_type: string
  markets: string[]
  categories: string[]
  preferred_for: string[]
  interfaces: string[]
  constraints: string[]
  notes: string[]
}

export interface ExternalDataSourceCatalogResult {
  sources: ExternalDataSourceCatalogItem[]
  doc: string
}

export interface SkillGenerationRecommendations {
  category_hint: string
  data_source_hint: string
  stock_collections: string[]
  external_sources: string[]
  /** The name of the data source outside the directory (such as dongchedi); non-empty indicates that the requirement specifies a source outside the system directory */
  unknown_data_source?: string
  /** Requirement type: external_api (external API integration, does not evaluate local/catalog assets) / local_data (default) */
  requirement_mode?: 'external_api' | 'local_data'
}

export interface ReconToolTrace {
  tool_name: string
  arguments: Record<string, any>
  success: boolean
  duration_ms: number
  result_preview: string
  error?: string
}

/** External interface pre-check results (connectivity verification in the specification confirmation phase) */
export interface InterfacePreflightResult {
  /** verified=Connected and data available / warning=Reachable but no data / failed=Not available */
  status: 'verified' | 'warning' | 'failed'
  message: string
  url?: string
  http_status?: number
  data_items?: number
  sample_fields?: string[]
  /** Differential test: measured parameters ignored by the interface (the same data is returned whether passed in or not, local filtering is required) */
  ignored_params?: string[]
  /** Differential testing: Actual testing will change the business parameters returned by the interface (server-side filtering is suspected to be effective, you can spell the URL) */
  server_filter_params?: string[]
  /** Available query parameters verified by actual testing (user URL documented query parameters) */
  probed_params?: Record<string, any>
  checked_at?: string
}

export interface ImplementationFactReportView {
  task_summary: string
  recommended_strategy: string
  available_helpers: Array<{ module: string; name: string; reason?: string; signature?: string; data_source_handling?: string }>
  sample_fields: Record<string, string[]>
  validation_checks: Array<{ name: string; description: string; field?: string }>
  notes: string[]
  tool_traces: ReconToolTrace[]
  confidence: number
}

/** Paginated list */
export interface PaginatedSkills {
  total: number
  page: number
  page_size: number
  items: ExternalSkill[]
}

/** Sandbox test results */
export interface TestResult {
  success: boolean
  output: any
  stdout: string
  stderr: string
  execution_time: number
  error: string | null
}

/** dialogue turns */
export interface ConversationRound {
  round_number: number
  ai_message: string
  user_message: string
  timestamp: string
}

/** Session details */
export interface SessionDetail {
  session_id: string
  user_id: string
  status: string
  rounds: ConversationRound[]
  current_round: number
  clarity_level: string | null
  boundary_check: BoundaryCheck | null
  handoff_context?: SkillHandoffContext | null
  spec: Record<string, any> | null
  fact_report?: ImplementationFactReportView | null
  spec_confirmed: boolean
  recommendations?: SkillGenerationRecommendations | null
  pipeline_result: Record<string, any> | null
  pipeline_stage?: string
  pipeline_message?: string
  pipeline_iteration?: number
  pipeline_progress?: number
  /** Real-time thinking process for code generation (reasoning_content tail snippet) */
  pipeline_thinking?: string
  /** The results of the latest round of quality assessment (Judge score, which appears when the assessment is completed) */
  pipeline_eval_result?: PipelineEvalResult | null
  pipeline_details?: Array<{
    stage: string
    message: string
    iteration: number
    progress: number
    timestamp?: string
    eval_result?: PipelineEvalResult
  }>
  created_at: string
  updated_at: string
}

/** Optimize results */
export interface OptimizeResult {
  status: string
  skill_id: string
  optimize_session_id: string
  success: boolean
  version: number
  total_rounds: number
  total_time: number
  final_score: number | null
  generation_context?: SkillGenerationRecommendations | null
  error: string | null
}

/** Communication history segmentation (creation/optimization) */
export interface HistorySection {
  type: 'creation' | 'optimize'
  label: string
  session_id: string
  rounds: ConversationRound[]
  created_at: string
  feedback?: string
}

/** Skill Complete communication history */
export interface SkillHistory {
  skill_id: string
  display_name: string
  sections: HistorySection[]
}

/** Standard API response wrapper */
interface ApiOk<T> {
  success: boolean
  data: T
  message: string
}

// ==================== API function ====================

const BASE = '/api/skill-generation'

// LLM Dedicated configuration for slow interface:
// - Timeout increased to 20 minutes: requirements dialogue/spec generation involves multiple LLM calls, which may exceed the global default of 600s,
//   Timeout truncation will cause the backend to still run, but the frontend will report an error (old sessions will be retransmitted continuously as a result)
// - retryCount: 0 Disable automatic retransmission after timeout: These POSTs are non-idempotent (will create a new session/advance rounds/trigger generation),
//   Automatic retransmission will accumulate repeated long-term tasks in the backend and trigger LLM current limiting
const SLOW_LLM_OP_CONFIG = { timeout: 1200000, retryCount: 0 }

export const skillGenerationApi = {
  // ---------- Model selection ----------

  /** Get the Skill to generate a list of available models (for drop-down selection) */
  listAvailableModels: async (): Promise<AvailableModelsResult> => {
    const res = await request.get<ApiOk<AvailableModelsResult>>(`${BASE}/models`)
    return (res as any).data
  },

  /** Get stock data collection directory */
  getStockDataCatalog: async (): Promise<StockDataCatalogResult> => {
    const res = await request.get<ApiOk<StockDataCatalogResult>>(`${BASE}/catalog/stock-data`)
    return (res as any).data
  },

  /** Get the external interface and data source directory */
  getExternalDataSourceCatalog: async (): Promise<ExternalDataSourceCatalogResult> => {
    const res = await request.get<ApiOk<ExternalDataSourceCatalogResult>>(`${BASE}/catalog/external-data-sources`)
    return (res as any).data
  },

  // ---------- Requirements communication ----------

  /** Start creating a session */
  startSession: async (data: StartSessionRequest): Promise<SessionStartResult> => {
    const res = await request.post<ApiOk<SessionStartResult>>(`${BASE}/sessions/start`, data, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** Reply to conversation */
  respondToSession: async (sessionId: string, message: string): Promise<SessionRespondResult> => {
    const res = await request.post<ApiOk<SessionRespondResult>>(`${BASE}/sessions/${sessionId}/respond`, { message }, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** Preview specs (without executing the pipeline) for spec confirmation steps */
  previewSpec: async (sessionId: string, message: string = 'Confirm'): Promise<{ spec: Record<string, any>; recommendations?: SkillGenerationRecommendations | null; fact_report?: ImplementationFactReportView | null; interface_preflight?: InterfacePreflightResult | null; upgrade_change_points?: string[] | null }> => {
    const res = await request.post<ApiOk<{ spec: Record<string, any>; recommendations?: SkillGenerationRecommendations | null; fact_report?: ImplementationFactReportView | null; interface_preflight?: InterfacePreflightResult | null; upgrade_change_points?: string[] | null }>>(`${BASE}/sessions/${sessionId}/preview-spec`, { message }, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** Confirm the specifications and generate (asynchronous, after returning generating you need to poll getSession to get the final result) */
  confirmSpec: async (sessionId: string, message: string = 'Confirm', codegenTimeout?: number): Promise<ConfirmResult> => {
    const res = await request.post<ApiOk<ConfirmResult>>(`${BASE}/sessions/${sessionId}/confirm`, { message, codegen_timeout: codegenTimeout ?? null }, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** First let the AI explain the problem it understands and its correction plan */
  previewRepairSession: async (sessionId: string, feedback: string): Promise<RepairPlanResult> => {
    const res = await request.post<ApiOk<RepairPlanResult>>(`${BASE}/sessions/${sessionId}/repair-plan`, { feedback }, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** After the correction plan is confirmed, it will be regenerated. */
  repairSession: async (sessionId: string, feedback: string, repairPlan: string = '', codegenTimeout?: number): Promise<ConfirmResult> => {
    const res = await request.post<ApiOk<ConfirmResult>>(`${BASE}/sessions/${sessionId}/repair`, { feedback, repair_plan: repairPlan, codegen_timeout: codegenTimeout ?? null }, SLOW_LLM_OP_CONFIG)
    return (res as any).data
  },

  /** List sessions (draft/incomplete) */
  listSessions: async (params?: {
    status?: string
    user_id?: string
    page?: number
    page_size?: number
  }): Promise<{ total: number; page: number; page_size: number; items: SessionDetail[] }> => {
    const res = await request.get<ApiOk<any>>(`${BASE}/sessions`, { params })
    return (res as any).data
  },

  /** Get session details (including conversation turns) */
  getSession: async (sessionId: string): Promise<SessionDetail> => {
    const res = await request.get<ApiOk<SessionDetail>>(`${BASE}/sessions/${sessionId}`)
    return (res as any).data
  },

  /** Delete draft conversation */
  deleteSession: async (sessionId: string): Promise<any> => {
    const res = await request.delete<ApiOk<any>>(`${BASE}/sessions/${sessionId}`)
    return (res as any).data
  },

  // ---------- Skill management ----------

  /** list external Skill */
  listSkills: async (params?: { category?: string; status?: string; source?: string; page?: number; page_size?: number }): Promise<PaginatedSkills> => {
    const res = await request.get<ApiOk<PaginatedSkills>>(`${BASE}/skills`, { params })
    return (res as any).data
  },

  /** Get Skill details */
  getSkill: async (skillId: string): Promise<ExternalSkill> => {
    const res = await request.get<ApiOk<ExternalSkill>>(`${BASE}/skills/${skillId}`)
    return (res as any).data
  },

  /** View Skill source code */
  getSkillCode: async (skillId: string): Promise<{ tool_id: string; code: string }> => {
    const res = await request.get<ApiOk<{ tool_id: string; code: string }>>(`${BASE}/skills/${skillId}/code`)
    return (res as any).data
  },

  /** Get Skill complete communication history (create + All optimizations) */
  getSkillHistory: async (skillId: string): Promise<SkillHistory> => {
    const res = await request.get<ApiOk<SkillHistory>>(`${BASE}/skills/${skillId}/history`)
    return (res as any).data
  },

  /** Update skill status */
  updateSkillStatus: async (skillId: string, status: string): Promise<any> => {
    const res = await request.put<ApiOk<any>>(`${BASE}/skills/${skillId}/status`, { status })
    return (res as any).data
  },

  /** Update Skill display name and function description */
  updateSkillInfo: async (
    skillId: string,
    displayName: string,
    description: string,
  ): Promise<{ tool_id: string; display_name: string; description: string }> => {
    const res = await request.put<ApiOk<any>>(`${BASE}/skills/${skillId}/info`, {
      display_name: displayName,
      description: description,
    })
    return (res as any).data
  },

  /** Delete Skill */
  deleteSkill: async (skillId: string): Promise<any> => {
    const res = await request.delete<ApiOk<any>>(`${BASE}/skills/${skillId}`)
    return (res as any).data
  },

  /** test Skill */
  testSkill: async (skillId: string, args?: Record<string, any>): Promise<TestResult> => {
    const res = await request.post<ApiOk<TestResult>>(`${BASE}/skills/${skillId}/test`, { args: args || {} })
    return (res as any).data
  },

  /** Optimize Skill */
  optimizeSkill: async (skillId: string, feedback: string): Promise<OptimizeResult> => {
    const res = await request.post<ApiOk<OptimizeResult>>(`${BASE}/skills/${skillId}/optimize`, { feedback })
    return (res as any).data
  },
}

export default skillGenerationApi

