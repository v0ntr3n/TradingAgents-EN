import request from './request'

// Skill parameters
export interface SkillParameter {
  name: string
  type: string
  description: string
  required?: boolean
  default?: any
}

// Skill return value
export interface SkillReturns {
  type: string
  description: string
  json_schema?: Record<string, any>
}

// Skill realize
export interface SkillImplementation {
  type: 'python' | 'http' | 'mcp'
  // python
  module?: string
  function?: string
  script_path?: string
  skill_dir?: string
  // python / http
  timeout?: number
  // http
  url?: string
  method?: string
  headers?: Record<string, string>
  body_template?: Record<string, any>
  // mcp
  server_url?: string
  tool_name?: string
}

// Skill response
export interface SkillData {
  id: string
  name: string
  description: string
  version: string
  author: string
  category: string
  tags: string[]
  icon: string
  color: string
  when_to_use: string
  parameters: SkillParameter[]
  returns: SkillReturns | null
  implementation: SkillImplementation | null
  instructions: string
  enabled: boolean
  fc_enabled: boolean
  is_builtin: boolean
  skill_type: string      // knowledge, python, http, mcp
  is_executable: boolean
  created_at: string | null
  updated_at: string | null
}

// Skill Classification statistics
export interface SkillCategory {
  id: string
  name: string
  count: number
}

// Create/Update Skill Request
export interface SkillCreateRequest {
  name: string
  description: string
  version?: string
  author?: string
  category?: string
  tags?: string[]
  icon?: string
  color?: string
  when_to_use?: string
  parameters?: SkillParameter[]
  returns?: SkillReturns | null
  implementation?: SkillImplementation | null
  instructions?: string
  enabled?: boolean
  fc_enabled?: boolean
}

// Import SKILL.md request
export interface SkillImportRequest {
  content: string
}

// Export skill response
export interface SkillExportResponse {
  content: string
  filename: string
}

// Test Skill Request
export interface SkillTestRequest {
  skill_name: string
  args: Record<string, any>
  question?: string
  timeout?: number
}

// Test Skill Response
export interface SkillTestResult {
  success: boolean
  result?: any
  error?: string
  execution_time_ms: number
}

// GitHub in warehouse Skill
export interface GitHubRepoSkill {
  path: string
  name: string
  url: string
  raw_url: string
  size: number
}

// GitHub warehouse response
export interface GitHubRepoResponse {
  owner: string
  repo: string
  skills: GitHubRepoSkill[]
  readme?: string
}

// Import requests from GitHub
export interface ImportFromGitHubRequest {
  owner: string
  repo: string
  path: string
  test_args?: Record<string, any>
}

// Import and test the response
export interface ImportWithTestResponse {
  skill: SkillData
  test_result?: SkillTestResult
  message: string
}

// Smithery MCP Server
export interface SmitheryServer {
  id: string
  name: string
  description: string
  tools: Record<string, any>[]
  install_command: string
}

// Tencent SkillHub skills
export interface SkillHubSkill {
  skill_id: string
  display_name: string
  description: string
  category: string
  author: string
  downloads: string
  version: string
  needs_api_key: boolean
  ai_score: string
  url: string
  install_command: string
}

// SkillHub list response
export interface SkillHubListResponse {
  total: string
  skills: SkillHubSkill[]
  featured: SkillHubSkill[]
}

// Import requests from SkillHub
export interface ImportFromSkillHubRequest {
  skill_id: string
  test_args?: Record<string, any>
}

// MCP Hub China server
export interface MCPHubServer {
  server_id: number
  qualified_name: string
  display_name: string
  description: string
  creator: string
  use_count: number
  tag: string
  is_domestic: boolean
  connections: string
  package_url: string
}

// MCP Hub list response
export interface MCPHubListResponse {
  total: number
  page: number
  page_size: number
  servers: MCPHubServer[]
}

// AgentHub Resource item
export interface AgentHubItem {
  id: number
  pkg_id: string
  type: string
  display_name: string
  description: string
  version: string
  origin: string
  source_url: string
  stars: number
  downloads: number
  installs: number
  icon_url: string
}

// AgentHub search response
export interface AgentHubSearchResponse {
  total: number
  items: AgentHubItem[]
}

// Import requests from AgentHub
export interface ImportFromAgentHubRequest {
  pkg_id: string
  test_args?: Record<string, any>
}

export interface ClawHubSearchResult {
  slug: string
  display_name: string
  summary: string
  version: string
  owner_handle: string
  owner_display_name: string
  canonical_url: string
  score: number
  updated_at?: number
}

export interface ClawHubSearchResponse {
  query: string
  total: number
  results: ClawHubSearchResult[]
}

export interface ClawHubInstallResponse {
  success: boolean
  skill_name: string
  skill_dir: string
  version: string
  has_scripts: boolean
  scripts_count: number
  extracted_files_count: number
  skill_type?: string
  message: string
}

// ZIP / URL Import response
export interface ImportZipResponse {
  success: boolean
  skill_name: string
  skill_dir: string
  has_scripts: boolean
  scripts_count: number
  dependencies_installed?: boolean
  dependencies_log?: string
  message: string
}

export interface InstallDepsResponse {
  success: boolean
  installed: boolean
  log: string
  message: string
}

export interface ImportUrlRequest {
  url: string
  name?: string
}

export interface LocalSkillItem {
  name: string
  skill_dir: string
  has_scripts: boolean
  has_skill_md: boolean
  source: string
  version: string
  installed_at: string
  canonical_url: string
  imported_to_db: boolean
}

export interface CredentialRequirement {
  name: string
  description: string
  required: boolean
  config_type: 'env' | 'script_arg'
  config_command: string
  configured: boolean
  masked_value: string
}

export interface CredentialStatusResponse {
  skill_name: string
  required: CredentialRequirement[]
  extra: Array<{ name: string; masked_value: string }>
  all_configured: boolean
  missing_required: string[]
}

// API function
export const skillsApi = {
  // Get all Skill
  listSkills: async (params?: { category?: string; enabled?: boolean; skill_type?: string }): Promise<SkillData[]> => {
    return await request.get<SkillData[]>('/api/skills', { params }) as unknown as SkillData[]
  },

  // Get Skill category statistics
  listCategories: async (): Promise<SkillCategory[]> => {
    return await request.get<SkillCategory[]>('/api/skills/categories') as unknown as SkillCategory[]
  },

  // Create Skill
  createSkill: async (data: SkillCreateRequest): Promise<SkillData> => {
    return await request.post<SkillData>('/api/skills', data) as unknown as SkillData
  },

  // Import SKILL.md content
  importSkill: async (content: string): Promise<SkillData> => {
    return await request.post<SkillData>('/api/skills/import', { content }) as unknown as SkillData
  },

  // Import from URL SKILL.md
  importSkillFromUrl: async (url: string): Promise<SkillData> => {
    return await request.post<SkillData>('/api/skills/import-url', { url }) as unknown as SkillData
  },

  // Upload SKILL.md file
  importSkillFile: async (file: File): Promise<SkillData> => {
    const formData = new FormData()
    formData.append('file', file)
    return await request.post<SkillData>('/api/skills/import-file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }) as unknown as SkillData
  },

  // Get Skill details
  getSkill: async (skillName: string): Promise<SkillData> => {
    return await request.get<SkillData>(`/api/skills/${skillName}`) as unknown as SkillData
  },

  // update Skill
  updateSkill: async (skillName: string, data: SkillCreateRequest): Promise<SkillData> => {
    return await request.put<SkillData>(`/api/skills/${skillName}`, data) as unknown as SkillData
  },

  // Delete Skill
  deleteSkill: async (skillName: string): Promise<{ success?: boolean; message?: string }> => {
    return await request.delete(`/api/skills/${skillName}`) as unknown as { success?: boolean; message?: string }
  },

  // enable/disable Skill
  toggleSkill: async (skillName: string, enabled: boolean) => {
    return await request.post(`/api/skills/${skillName}/toggle`, { enabled })
  },

  // Export Skill as SKILL.md
  exportSkill: async (skillName: string): Promise<SkillExportResponse> => {
    return await request.get<SkillExportResponse>(`/api/skills/${skillName}/export`) as unknown as SkillExportResponse
  },

  // test Skill
  testSkill: async (data: SkillTestRequest): Promise<SkillTestResult> => {
    return await request.post<SkillTestResult>('/api/skills/test', data) as unknown as SkillTestResult
  },

  // Get the list of Skills in the GitHub repository
  listGitHubRepoSkills: async (owner: string, repo: string): Promise<GitHubRepoResponse> => {
    return await request.get<GitHubRepoResponse>(`/api/skills/github/repo/${owner}/${repo}`) as unknown as GitHubRepoResponse
  },

  // Import from GitHub Skill
  importFromGitHub: async (data: ImportFromGitHubRequest): Promise<ImportWithTestResponse> => {
    return await request.post<ImportWithTestResponse>('/api/skills/import-github', data) as unknown as ImportWithTestResponse
  },

  // Get Smithery MCP Server list
  listSmitheryServers: async (): Promise<SmitheryServer[]> => {
    return await request.get<SmitheryServer[]>('/api/skills/smithery/servers') as unknown as SmitheryServer[]
  },

  // Get Tencent SkillHub skill list
  listSkillHubSkills: async (params?: { keyword?: string }): Promise<SkillHubListResponse> => {
    return await request.get<SkillHubListResponse>('/api/skills/skillhub/skills', { params }) as unknown as SkillHubListResponse
  },

  // Import from SkillHub Skill
  importFromSkillHub: async (data: ImportFromSkillHubRequest): Promise<ImportWithTestResponse> => {
    return await request.post<ImportWithTestResponse>('/api/skills/import-skillhub', data) as unknown as ImportWithTestResponse
  },

  // Get MCP Hub China server list
  listMCPHubServers: async (params?: { page?: number; page_size?: number; keyword?: string }): Promise<MCPHubListResponse> => {
    return await request.get<MCPHubListResponse>('/api/skills/mcphub/servers', { params }) as unknown as MCPHubListResponse
  },

  // Search AgentHub resources
  searchAgentHub: async (params?: { q?: string; type_filter?: string; page?: number; page_size?: number }): Promise<AgentHubSearchResponse> => {
    return await request.get<AgentHubSearchResponse>('/api/skills/agenthub/search', { params }) as unknown as AgentHubSearchResponse
  },

  // Import from AgentHub Skill
  importFromAgentHub: async (data: ImportFromAgentHubRequest): Promise<ImportWithTestResponse> => {
    return await request.post<ImportWithTestResponse>('/api/skills/import-agenthub', data) as unknown as ImportWithTestResponse
  },

  // Search ClawHub Skill
  searchClawHub: async (params: { q: string; limit?: number }): Promise<ClawHubSearchResponse> => {
    return await request.get<ClawHubSearchResponse>('/api/skills/clawhub/search', { params }) as unknown as ClawHubSearchResponse
  },

  // Install from ClawHub Skill
  installClawHub: async (data: { slug: string; version?: string; tag?: string }): Promise<ClawHubInstallResponse> => {
    return await request.post<ClawHubInstallResponse>('/api/skills/install-clawhub', data) as unknown as ClawHubInstallResponse
  },

  // Upload ZIP file to import Skill
  importZip: async (file: File): Promise<ImportZipResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    return await request.post<ImportZipResponse>('/api/skills/import-zip', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }) as unknown as ImportZipResponse
  },

  // Import via URL download Skill
  importFromUrl: async (data: ImportUrlRequest): Promise<ImportZipResponse> => {
    return await request.post<ImportZipResponse>('/api/skills/import-url', data) as unknown as ImportZipResponse
  },

  // Manually install the dependencies of a Skill (requirements.txt)
  installSkillDeps: async (skillName: string): Promise<InstallDepsResponse> => {
    return await request.post<InstallDepsResponse>(
      `/api/skills/${encodeURIComponent(skillName)}/install-deps`,
      {}
    ) as unknown as InstallDepsResponse
  },

  // Import local skill package
  importLocalSkill: async (data: { skill_dir: string }) => {
    return await request.post('/api/skills/import-local', data)
  },

  // List local skill packages
  listLocalSkills: async (): Promise<LocalSkillItem[]> => {
    return await request.get<LocalSkillItem[]>('/api/skills/local') as unknown as LocalSkillItem[]
  },

  // Get Skill Credential Status
  getCredentialStatus: async (skillName: string): Promise<CredentialStatusResponse> => {
    return await request.get<CredentialStatusResponse>(`/api/skills/${skillName}/credentials`) as unknown as CredentialStatusResponse
  },

  // Save Skill Credentials
  saveCredentials: async (skillName: string, credentials: Record<string, string>) => {
    return await request.post(`/api/skills/${skillName}/credentials`, { credentials })
  },

  // Configure credentials via script commands
  configureCredentialViaScript: async (skillName: string, data: { config_command: string; credential_value: string; script_path?: string; timeout?: number }) => {
    return await request.post(`/api/skills/${skillName}/credentials/configure-script`, data)
  },
}

export default skillsApi

