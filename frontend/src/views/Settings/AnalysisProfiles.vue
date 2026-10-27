<template>
  <div class="analysis-profiles-container">
    <el-alert type="info" :closable="false" show-icon class="page-alert">
      <template #title>
        <span class="alert-title">
          <el-tag type="info" size="small" effect="dark">Smart</el-tag>
          <span>Industry/Stock Analysis Dimension Configuration — Use chat-style collaboration to generate industry analysis drafts and transparently display data coverage and external dependencies before saving</span>
        </span>
      </template>
    </el-alert>

    <div class="workspace-grid">
      <el-card class="workspace-card chat-card">
        <template #header>
          <div class="card-header">
            <div>
              <div class="card-title">🤖 Industry Configuration Assistant</div>
              <div class="card-subtitle">Multiple rounds of communication generate a draft, and finally confirm whether to save it.</div>
            </div>
            <div class="header-actions">
              <el-tag type="info" effect="plain">Current industry:{{ currentIndustryLabel }}</el-tag>
              <el-button text @click="resetConversation()">
                <el-icon><RefreshRight /></el-icon>
                New conversation
              </el-button>
            </div>
          </div>
        </template>

        <div class="session-toolbar">
          <el-select
            v-model="chatIndustry"
            filterable
            clearable
            placeholder="Select an industry first, or mention the industry name directly in the chat below"
            class="industry-select"
            :loading="industryListLoading"
          >
            <el-option v-for="name in industryList" :key="name" :label="name" :value="name" />
          </el-select>
          <div class="toolbar-actions">
            <el-button type="primary" plain :disabled="!chatIndustry" :loading="generating" @click="startDraftGeneration">
              <el-icon><MagicStick /></el-icon>
              Generate first draft
            </el-button>
            <el-button :disabled="!draftPreview" @click="openDraftInEditor">
              <el-icon><Edit /></el-icon>
              Manual finishing
            </el-button>
          </div>
        </div>

        <div class="chat-body">
          <div ref="messagesContainer" class="messages-container">
            <div class="messages-list">
              <div
                v-for="(msg, idx) in messages"
                :key="idx"
                :class="['message-item', msg.role === 'user' ? 'message-user' : 'message-assistant']"
              >
                <template v-if="msg.role === 'user'">
                  <div class="message-content">
                    <div class="message-text">{{ msg.content }}</div>
                  </div>
                  <div class="message-avatar">
                    <el-icon><User /></el-icon>
                  </div>
                </template>
                <template v-else>
                  <div class="message-avatar">
                    <el-icon><ChatDotRound /></el-icon>
                  </div>
                  <div class="message-content assistant-content">
                    <div class="message-text">{{ msg.content }}</div>
                  </div>
                </template>
              </div>

              <div v-if="generating" class="message-item message-assistant thinking-bubble">
                <div class="message-avatar">
                  <el-icon><ChatDotRound /></el-icon>
                </div>
                <div class="message-content thinking-content">
                  <span class="thinking-text">The industry draft is being revised based on your request</span>
                  <span class="thinking-dots">
                    <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="draftPreview" class="quick-actions">
            <span class="quick-actions-title">Quick adjustment</span>
            <el-button size="small" @click="sendQuickPrompt('Delete dimensions and indicators that require external data in the current draft and retain content that is easier to implement.')">Delete required external data items</el-button>
            <el-button size="small" @click="sendQuickPrompt('Supplementary profit, cash flow, capital expenditure and earnings quality related dimensions')">Supplementary profit/cash flow</el-button>
            <el-button size="small" @click="sendQuickPrompt('Keep operational indicators, but emphasize the need for MCP, Skill or external import support in the description')">Preserve and mark external dependencies</el-button>
            <el-button size="small" @click="sendQuickPrompt('Condensing the current draft into the 5 most critical core dimensions')">Converged into 5 core dimensions</el-button>
            <el-button size="small" type="warning" plain @click="pruneUnsupported">One-click cropping does not support items</el-button>
            <el-button size="small" type="success" @click="handleSaveDraft">Save current configuration</el-button>
          </div>

          <div class="input-area">
            <div class="input-row">
              <el-input
                v-model="chatInput"
                type="textarea"
                :rows="3"
                :autosize="{ minRows: 3, maxRows: 6 }"
                placeholder="For example: give me a draft version of the Internet industry first; delete indicators without data sources; increase cash flow and profit quality; retain user data indicators but mark the need for external data."
                :disabled="generating"
                @keydown.enter.ctrl.prevent="handleSend"
              />
              <el-button
                type="primary"
                class="send-btn"
                :loading="generating"
                :disabled="!chatInput.trim()"
                @click="handleSend"
              >
                <el-icon><Promotion /></el-icon>
                send
              </el-button>
            </div>
            <span class="input-tip">Ctrl + Enter Send. You can continue to ask for Delete unsupported items/Add certain types of indicators/Converge to a more streamlined framework/Save now . </span>
          </div>
        </div>
      </el-card>

      <el-card class="workspace-card draft-card">
        <template #header>
          <div class="card-header">
            <div>
              <div class="card-title">📋 current draft</div>
              <div class="card-subtitle">View the current version in a structured way and fine-tune it at any time before saving it.</div>
            </div>
            <el-tag v-if="draftPreview" :type="overallBadgeType" effect="dark">{{ draftPreview.coverage_summary.overall_label }}</el-tag>
          </div>
        </template>

        <div v-if="draftPreview" class="draft-scroll">
          <el-descriptions :column="2" border size="small" class="summary-descriptions">
            <el-descriptions-item label="Industry">{{ draftPreview.profile.display_name || draftPreview.profile.industry }}</el-descriptions-item>
            <el-descriptions-item label="number of dimensions">{{ draftPreview.profile.analysis_dimensions.length }} item</el-descriptions-item>
            <el-descriptions-item label="key indicators">{{ draftPreview.profile.key_metrics.length }} item</el-descriptions-item>
            <el-descriptions-item label="Comparable companies">{{ draftPreview.profile.comparable_companies.length }} home</el-descriptions-item>
            <el-descriptions-item label="Built-in data source">{{ draftPreview.capability_snapshot.counts.builtin_sources }} class</el-descriptions-item>
            <el-descriptions-item label="MCP / Skill">
              {{ draftPreview.capability_snapshot.counts.enabled_mcp_servers }} / {{ draftPreview.capability_snapshot.counts.active_skills }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert :type="overallAlertType" :closable="false" show-icon class="summary-alert">
            <template #title>{{ draftPreview.coverage_summary.overall_label }}</template>
            <template #default>
              <ul class="summary-list">
                <li v-for="(rec, idx) in draftPreview.coverage_summary.recommendations" :key="idx">{{ rec }}</li>
              </ul>
            </template>
          </el-alert>

          <div class="draft-section">
            <div class="section-title">Analysis focus</div>
            <div class="focus-text">{{ draftPreview.profile.analysis_focus || 'No analysis highlights yet' }}</div>
          </div>

          <div class="draft-section">
            <div class="section-title">Analysis Dimensions</div>
            <div class="draft-items">
              <div v-for="(dim, idx) in draftPreview.profile.analysis_dimensions" :key="`${dim.name}-${idx}`" class="draft-item">
                <div class="draft-item-header">
                  <div class="item-title-group">
                    <span class="item-title">{{ dim.name }}</span>
                    <el-tag size="small" :type="statusTagType(draftPreview.dimension_assessments[idx]?.coverage_status)">
                      {{ draftPreview.dimension_assessments[idx]?.coverage_label || 'To be evaluated' }}
                    </el-tag>
                    <el-tag size="small" effect="plain">{{ dim.importance || 'high' }}</el-tag>
                  </div>
                  <el-button link type="danger" @click="removeDimensionFromDraft(idx)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <div class="item-description">{{ dim.description }}</div>
                <div class="item-meta">
                  <el-tag
                    v-for="(src, sourceIdx) in draftPreview.dimension_assessments[idx]?.matched_sources || []"
                    :key="`${dim.name}-${sourceIdx}`"
                    size="small"
                    :type="sourceTagType(src.type)"
                  >
                    {{ src.type_label }} · {{ src.name }}
                  </el-tag>
                  <span v-if="!(draftPreview.dimension_assessments[idx]?.matched_sources || []).length" class="meta-placeholder">No clear matching source yet</span>
                </div>
                <div class="item-note">{{ draftPreview.dimension_assessments[idx]?.user_note || 'You can continue to chat and ask me to rewrite or delete the dimension.' }}</div>
              </div>
            </div>
          </div>

          <div class="draft-section">
            <div class="section-title">key indicators</div>
            <div class="metric-list">
              <div v-for="(metric, idx) in draftPreview.metric_assessments" :key="`${metric.name}-${idx}`" class="metric-item">
                <div class="metric-main">
                  <span>{{ metric.name }}</span>
                  <el-tag size="small" :type="statusTagType(metric.coverage_status)">{{ metric.coverage_label }}</el-tag>
                </div>
                <el-button link type="danger" @click="removeMetricFromDraft(idx)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
          </div>

          <div class="draft-section">
            <div class="section-title">Comparable companies</div>
            <div class="tag-group">
              <el-tag v-for="company in draftPreview.profile.comparable_companies" :key="company" type="info">{{ company }}</el-tag>
              <span v-if="!draftPreview.profile.comparable_companies.length" class="meta-placeholder">There is currently no comparable company</span>
            </div>
          </div>

          <div class="draft-section">
            <div class="section-title">Suggestions for next steps</div>
            <ul class="summary-list compact">
              <li v-for="(guide, idx) in draftPreview.next_step_guidance" :key="idx">{{ guide }}</li>
            </ul>
          </div>
        </div>

        <el-empty
          v-else
          description="First talk to the assistant on the left side and after generating the first version of the industry draft, the current configuration and data coverage will be displayed in real time."
          :image-size="90"
        />
      </el-card>
    </div>

    <el-card class="saved-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">🏭 Industry configuration saved</div>
            <div class="card-subtitle">List management is retained, adding/editing can still be done manually</div>
          </div>
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon>
            Create manually
          </el-button>
        </div>
      </template>

      <el-table :data="industryProfiles" v-loading="loading" empty-text="There is currently no industry configuration. You can generate and save it through chat above.">
        <el-table-column prop="display_name" label="Industry" min-width="140">
          <template #default="{ row }">
            <span class="industry-name">{{ row.display_name || row.industry }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Analysis Dimensions" min-width="260">
          <template #default="{ row }">
            <el-tag v-for="dim in (row.analysis_dimensions || []).slice(0, 3)" :key="dim.name" size="small" class="table-tag">
              {{ dim.name }}
            </el-tag>
            <el-tag v-if="(row.analysis_dimensions || []).length > 3" size="small" type="info">
              +{{ row.analysis_dimensions.length - 3 }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="key indicators" min-width="220">
          <template #default="{ row }">
            <el-tag v-for="metric in (row.key_metrics || []).slice(0, 3)" :key="metric" size="small" type="success" class="table-tag">
              {{ metric }}
            </el-tag>
            <el-tag v-if="(row.key_metrics || []).length > 3" size="small" type="info">
              +{{ row.key_metrics.length - 3 }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? 'enable' : 'Disable' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="editProfile(row)">
              <el-icon><Edit /></el-icon> Edit
            </el-button>
            <el-button link type="danger" @click="deleteProfile(row)">
              <el-icon><Delete /></el-icon> Delete
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editDialogVisible" :title="editMode === 'create' ? 'Create industry configuration' : 'Edit industry configuration'" width="780px" top="5vh">
      <el-form :model="formData" label-width="100px">
        <el-form-item label="Industry name" required>
          <el-select
            v-model="formData.industry"
            filterable
            placeholder="Search and select industry"
            style="width: 100%"
            :disabled="editMode === 'edit'"
            :loading="industryListLoading"
          >
            <el-option v-for="name in industryList" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="display name">
          <el-input v-model="formData.display_name" placeholder="For example: banking industry (leave blank to use the industry name)" />
        </el-form-item>
        <el-form-item label="Analysis focus">
          <el-input v-model="formData.analysis_focus" type="textarea" :rows="3" placeholder="The key areas of focus when analyzing this industry" />
        </el-form-item>
        <el-form-item label="Enabled status">
          <el-switch v-model="formData.is_active" />
        </el-form-item>

        <el-divider>Analysis Dimensions</el-divider>
        <div v-for="(dim, idx) in formData.analysis_dimensions" :key="idx" class="dimension-row">
          <el-input v-model="dim.name" placeholder="Dimension name" style="width: 160px" />
          <el-input v-model="dim.description" placeholder="Dimension description" style="flex: 1; margin: 0 8px" />
          <el-select v-model="dim.importance" placeholder="importance" style="width: 110px; margin-right: 8px">
            <el-option label="key" value="critical" />
            <el-option label="high" value="high" />
            <el-option label="in" value="medium" />
          </el-select>
          <el-button link type="danger" @click="formData.analysis_dimensions.splice(idx, 1)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <el-button
          type="primary"
          plain
          size="small"
          style="margin-top: 8px"
          @click="formData.analysis_dimensions.push({ name: '', description: '', importance: 'high', data_source: 'fundamentals' })"
        >
          <el-icon><Plus /></el-icon> Add dimension
        </el-button>

        <el-divider>key indicators</el-divider>
        <el-select
          v-model="formData.key_metrics"
          multiple
          filterable
          allow-create
          default-first-option
          :reserve-keyword="false"
          placeholder="Enter the indicator name and press Enter"
          style="width: 100%"
        />

        <el-divider>Comparable companies</el-divider>
        <el-select
          v-model="formData.comparable_companies"
          multiple
          filterable
          allow-create
          default-first-option
          :reserve-keyword="false"
          placeholder="Enter the company name and press Enter"
          style="width: 100%"
        />
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotRound, Delete, Edit, MagicStick, Plus, Promotion, RefreshRight, User } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { analysisProfilesApi, type GeneratePreview, type IndustryProfile } from '@/api/analysisProfiles'

type ElTagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
type ElAlertType = 'success' | 'info' | 'warning' | 'error'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const route = useRoute()
const loading = ref(false)
const generating = ref(false)
const submitting = ref(false)

const industryProfiles = ref<IndustryProfile[]>([])
const industryList = ref<string[]>([])
const industryListLoading = ref(false)

const chatIndustry = ref('')
const chatInput = ref('')
const messages = ref<ChatMessage[]>([])
const messagesContainer = ref<HTMLElement | null>(null)
const draftPreview = ref<GeneratePreview | null>(null)

const editDialogVisible = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editingId = ref<string | null>(null)

const emptyForm = (): IndustryProfile => ({
  industry: '',
  display_name: '',
  analysis_dimensions: [],
  analysis_focus: '',
  key_metrics: [],
  comparable_companies: [],
  is_active: true,
})

const formData = ref<IndustryProfile>(emptyForm())

function cloneDeep<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const statusTagType = (status?: string): ElTagType => {
  if (status === 'directly_usable') return 'success'
  if (status === 'partially_usable') return 'warning'
  if (status === 'external_required') return 'danger'
  return 'info'
}

const sourceTagType = (type?: string): ElTagType => {
  if (type === 'builtin') return 'info'
  if (type === 'mcp') return 'warning'
  if (type === 'skill') return 'success'
  return 'info'
}

const overallBadgeType = computed<ElTagType>(() => {
  const status = draftPreview.value?.coverage_summary?.overall_status
  if (status === 'ready') return 'success'
  if (status === 'review_needed') return 'warning'
  return 'danger'
})

const overallAlertType = computed<ElAlertType>(() => {
  const status = draftPreview.value?.coverage_summary?.overall_status
  if (status === 'ready') return 'success'
  if (status === 'review_needed') return 'warning'
  return 'error'
})

const currentIndustryLabel = computed(() => {
  return chatIndustry.value || draftPreview.value?.profile?.industry || 'Not selected'
})

const countStatuses = (items: Array<{ coverage_status?: string }> = []) => {
  const counts = {
    directly_usable: 0,
    partially_usable: 0,
    external_required: 0,
    review_recommended: 0,
  }
  items.forEach((item) => {
    const key = item?.coverage_status as keyof typeof counts
    if (key && typeof counts[key] === 'number') counts[key] += 1
  })
  return counts
}

const createDefaultCoverageSummary = () => ({
  overall_status: 'review_needed' as const,
  overall_label: 'It is recommended to save it after manual review.',
  dimension_counts: countStatuses(),
  metric_counts: countStatuses(),
  recommendations: [] as string[],
})

const normalizeProfile = (profile?: Partial<IndustryProfile> | null): IndustryProfile => ({
  ...emptyForm(),
  ...cloneDeep(profile || {}),
  analysis_dimensions: Array.isArray(profile?.analysis_dimensions) ? cloneDeep(profile.analysis_dimensions) : [],
  key_metrics: Array.isArray(profile?.key_metrics) ? [...profile.key_metrics] : [],
  comparable_companies: Array.isArray(profile?.comparable_companies) ? [...profile.comparable_companies] : [],
})

const normalizePreview = (preview: any): GeneratePreview => ({
  profile: normalizeProfile(preview?.profile),
  coverage_summary: preview?.coverage_summary || createDefaultCoverageSummary(),
  capability_snapshot: preview?.capability_snapshot || {
    builtin_sources: [],
    enabled_mcp_servers: [],
    active_skills: [],
    manual_import: {
      available: true,
      label: 'Manual import',
      description: 'External data can be supplemented manually',
    },
    counts: {
      builtin_sources: 0,
      enabled_mcp_servers: 0,
      active_skills: 0,
    },
    notes: [],
  },
  dimension_assessments: Array.isArray(preview?.dimension_assessments) ? cloneDeep(preview.dimension_assessments) : [],
  metric_assessments: Array.isArray(preview?.metric_assessments) ? cloneDeep(preview.metric_assessments) : [],
  next_step_guidance: Array.isArray(preview?.next_step_guidance) ? [...preview.next_step_guidance] : [],
})

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const pushMessage = (role: ChatMessage['role'], content: string) => {
  messages.value.push({ role, content })
  scrollToBottom()
}

const buildWelcomeMessage = () => {
  return 'Hello, I will work with you to iteratively generate industry analysis configurations.\n\n You can start by:\n1. Select an industry above and click Generate first draft \n2. Or send a message directly below, e.g. Help me make an Internet industry configuration and delete items without data sources \n\n I will tell you in each round which data systems can support it, which ones require MCP/Skill/external import, and finally ask you whether to save.'
}

const buildAssistantSummary = (preview: GeneratePreview, hadDraft: boolean) => {
  const dimensionCounts = preview.coverage_summary.dimension_counts || countStatuses()
  const metricCounts = preview.coverage_summary.metric_counts || countStatuses()

  return `${hadDraft ? 'I have revised the current draft based on your latest request.' : 'I first generated a first draft for you.'}

Industry:${preview.profile.display_name || preview.profile.industry}
Current status:${preview.coverage_summary.overall_label}
Dimensions ${preview.profile.analysis_dimensions.length} Item: Can be used directly ${dimensionCounts.directly_usable} / Partially available ${dimensionCounts.partially_usable} / external data required ${dimensionCounts.external_required} / Recommend review ${dimensionCounts.review_recommended}
indicator ${preview.profile.key_metrics.length} Item: Can be used directly ${metricCounts.directly_usable} / Partially available ${metricCounts.partially_usable} / external data required ${metricCounts.external_required} / Recommend review ${metricCounts.review_recommended}
System capabilities: built-in data sources ${preview.capability_snapshot.counts.builtin_sources} class,MCP ${preview.capability_snapshot.counts.enabled_mcp_servers} one,Skill ${preview.capability_snapshot.counts.active_skills} .

You can continue to let me:
- Delete items that require external data
- Increase profit, cash flow, capital expenditure and other dimensions
- Maintain operational metrics, but clearly label the need for external sources
- Converged into a more streamlined 5 core dimensions

If this version is already suitable, I can help you save it now.`
}

const rebuildCoverageSummary = () => {
  if (!draftPreview.value) return

  const dimensionCounts = countStatuses(draftPreview.value.dimension_assessments)
  const metricCounts = countStatuses(draftPreview.value.metric_assessments)
  const totalExternal = dimensionCounts.external_required + metricCounts.external_required
  const totalReview = dimensionCounts.review_recommended + metricCounts.review_recommended

  let overall_status: 'ready' | 'review_needed' | 'prune_needed' = 'prune_needed'
  let overall_label = 'It is recommended to crop first and then save'

  if (totalExternal === 0 && totalReview <= 1) {
    overall_status = 'ready'
    overall_label = 'Most of the content has already been implemented'
  } else if (totalExternal <= 2 && totalReview <= 3) {
    overall_status = 'review_needed'
    overall_label = 'It is recommended to save it after manual review.'
  }

  const recommendations: string[] = []
  if (dimensionCounts.directly_usable || metricCounts.directly_usable) {
    recommendations.push('Priority reservation Can be used directly dimensions and indicators, which are most easily supported stably by the current system.')
  }
  if (totalExternal) {
    recommendations.push(`There are still ${totalExternal} Item is identified as external data required , Please confirm the MCP/Skill/manual import plan before saving.`)
  }
  if (totalReview) {
    recommendations.push(`There are still ${totalReview} The item is Recommend review , If the source cannot be confirmed, it is recommended to continue deleting it.`)
  }
  if (!recommendations.length) {
    recommendations.push('The current draft is more suitable as the default industry analysis template.')
  }

  draftPreview.value.coverage_summary = {
    overall_status,
    overall_label,
    dimension_counts: dimensionCounts,
    metric_counts: metricCounts,
    recommendations,
  }
}

const resetConversation = (preserveIndustry = false) => {
  const preserved = preserveIndustry ? chatIndustry.value : ''
  chatIndustry.value = preserved
  chatInput.value = ''
  draftPreview.value = null
  messages.value = [{ role: 'assistant', content: buildWelcomeMessage() }]
  scrollToBottom()
}

const inferIndustryFromText = (text: string) => {
  return industryList.value.find((name) => text.includes(name)) || ''
}

const requestDraft = async (userRequest: string) => {
  const industry = chatIndustry.value.trim()
  if (!industry) {
    ElMessage.warning('Please select your industry first, or clearly mention the industry name in your message')
    return
  }

  const hadDraft = Boolean(draftPreview.value)
  generating.value = true
  try {
    const res = await analysisProfilesApi.generateIndustry(industry, {
      user_request: userRequest,
      existing_profile: draftPreview.value?.profile,
    }) as any

    if (res?.success && res.data) {
      draftPreview.value = normalizePreview(res.data)
      pushMessage('assistant', buildAssistantSummary(draftPreview.value, hadDraft))
    } else {
      ElMessage.error(res?.message || 'Build failed')
      pushMessage('assistant', 'This round of generation failed. You can try again later, or change the request to a more specific one and let me revise it.')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || 'AI Generation failed, please try again later')
    pushMessage('assistant', 'I did not successfully generate the draft this round. Please try again later or be more specific with your request.')
  } finally {
    generating.value = false
  }
}

const startDraftGeneration = async () => {
  if (!chatIndustry.value.trim()) {
    ElMessage.warning('Please select an industry first')
    return
  }

  const starter = `Please first provide ${chatIndustry.value.trim()}] Generate a draft version of the industry analysis configuration, taking into account the feasibility of the current system s built-in data, MCP, Skills and manual import.`
  pushMessage('user', starter)
  await requestDraft(starter)
}

const handleSend = async () => {
  const text = chatInput.value.trim()
  if (!text) return
  chatInput.value = ''

  if (!chatIndustry.value.trim()) {
    const inferred = inferIndustryFromText(text)
    if (inferred) chatIndustry.value = inferred
  }

  pushMessage('user', text)

  if (!chatIndustry.value.trim()) {
    pushMessage('assistant', 'I don t know yet which industry you want to configure. Please select the industry above first, or directly state the industry name in the database in the message.')
    return
  }

  const normalized = text.replace(/[。！？!?.\s]/g, '')
  if (draftPreview.value && ['save', 'Confirm to save', 'save now', 'Just save it'].includes(normalized)) {
    await handleSaveDraft()
    return
  }

  await requestDraft(text)
}

const sendQuickPrompt = async (prompt: string) => {
  if (!draftPreview.value) {
    ElMessage.warning('Please generate a draft version')
    return
  }
  pushMessage('user', prompt)
  await requestDraft(prompt)
}

const removeDimensionFromDraft = (index: number) => {
  if (!draftPreview.value) return
  draftPreview.value.profile.analysis_dimensions.splice(index, 1)
  draftPreview.value.dimension_assessments.splice(index, 1)
  rebuildCoverageSummary()
  ElMessage.success('The dimension has been deleted')
}

const removeMetricFromDraft = (index: number) => {
  if (!draftPreview.value) return
  const metricName = draftPreview.value.metric_assessments[index]?.name
  draftPreview.value.metric_assessments.splice(index, 1)
  if (metricName) {
    draftPreview.value.profile.key_metrics = draftPreview.value.profile.key_metrics.filter((item) => item !== metricName)
  }
  rebuildCoverageSummary()
  ElMessage.success('The indicator has been deleted')
}

const pruneUnsupported = () => {
  if (!draftPreview.value) return

  const removableDimensions = draftPreview.value.dimension_assessments
    .filter((item) => ['external_required', 'review_recommended'].includes(item.coverage_status))
    .map((item) => item.name)

  const removableMetrics = draftPreview.value.metric_assessments
    .filter((item) => ['external_required', 'review_recommended'].includes(item.coverage_status))
    .map((item) => item.name)

  const keepDimensionIndexes = draftPreview.value.dimension_assessments
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => ['directly_usable', 'partially_usable'].includes(item.coverage_status))
    .map(({ index }) => index)

  const nextDimensions = keepDimensionIndexes.map((index) => draftPreview.value!.profile.analysis_dimensions[index])
  const nextDimensionAssessments = keepDimensionIndexes.map((index) => draftPreview.value!.dimension_assessments[index])

  const keepMetricIndexes = draftPreview.value.metric_assessments
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => ['directly_usable', 'partially_usable'].includes(item.coverage_status))
    .map(({ index }) => index)

  const nextMetricAssessments = keepMetricIndexes.map((index) => draftPreview.value!.metric_assessments[index])
  const keptMetricNames = new Set(nextMetricAssessments.map((item) => item.name))

  draftPreview.value.profile.analysis_dimensions = nextDimensions
  draftPreview.value.dimension_assessments = nextDimensionAssessments
  draftPreview.value.metric_assessments = nextMetricAssessments
  draftPreview.value.profile.key_metrics = draftPreview.value.profile.key_metrics.filter((item) => keptMetricNames.has(item))

  rebuildCoverageSummary()

  const removedSummary = [
    removableDimensions.length ? `Delete dimensions:${removableDimensions.join(', ')}` : '',
    removableMetrics.length ? `Delete indicator:${removableMetrics.join(', ')}` : '',
  ].filter(Boolean).join('\n')

  pushMessage('assistant', `${removedSummary || 'There are currently no items that obviously need to be clipped.'}\n\n I have cut out the items that are more difficult to implement first. This version is now closer to an industry template that can be directly saved; if you want to continue to add or adjust, you can continue to tell me.`)
  ElMessage.success('Unsupported items cropped')
}

const showCreateDialog = () => {
  editMode.value = 'create'
  editingId.value = null
  formData.value = { ...emptyForm(), industry: chatIndustry.value || '' }
  editDialogVisible.value = true
}

const openDraftInEditor = () => {
  if (!draftPreview.value) return
  editMode.value = 'create'
  editingId.value = null
  formData.value = normalizeProfile(draftPreview.value.profile)
  editDialogVisible.value = true
}

const editProfile = (row: IndustryProfile) => {
  editMode.value = 'edit'
  editingId.value = row.id || null
  formData.value = normalizeProfile(row)
  editDialogVisible.value = true
}

const handleSaveDraft = async () => {
  if (!draftPreview.value) {
    ElMessage.warning('Please create a draft')
    return
  }

  const payload = normalizeProfile(draftPreview.value.profile)
  if (!payload.industry.trim()) {
    ElMessage.warning('The current draft is missing an industry name and cannot be saved temporarily.')
    return
  }

  const existing = industryProfiles.value.find((item) => item.industry === payload.industry)

  try {
    const confirmMessage = existing
      ? `Industry ${payload.industry}] Configuration already exists. Overwrite it with current chat draft?`
      : `Confirm that the current ${payload.industry}] Draft saved as industry configuration?`

    await ElMessageBox.confirm(confirmMessage, 'Confirm to save', {
      confirmButtonText: existing ? 'Overwrite and save' : 'save',
      cancelButtonText: 'Cancel',
      type: 'warning',
    })

    let res: any
    if (existing?.id) {
      res = await analysisProfilesApi.updateIndustry(existing.id, payload)
    } else {
      try {
        res = await analysisProfilesApi.createIndustry(payload)
      } catch (createErr: any) {
        // 409 = The industry already exists but the local list is out of date. Refresh the list and change it. update
        if (createErr?.response?.status === 409 || createErr?.status === 409) {
          await loadProfiles()
          const freshExisting = industryProfiles.value.find((item) => item.industry === payload.industry)
          if (freshExisting?.id) {
            res = await analysisProfilesApi.updateIndustry(freshExisting.id, payload)
          } else {
            throw new Error('The industry configuration already exists but the ID cannot be obtained. Please refresh the page and try again.')
          }
        } else {
          throw createErr
        }
      }
    }

    if (res?.success) {
      ElMessage.success(existing?.id ? 'Overwritten and saved' : 'Saved successfully')
      pushMessage('assistant', `Okay, the current draft has been put${existing?.id ? 'Overwrite and save' : 'save'}Configured for industry. If you want to continue optimizing later, you can come back and talk to me at any time.`)
      await loadProfiles()
    } else {
      ElMessage.error(res?.message || 'Save failed')
    }
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || 'Save failed')
    }
  }
}

const loadIndustryList = async () => {
  industryListLoading.value = true
  try {
    const res = await analysisProfilesApi.getIndustryList() as any
    if (res?.success) {
      industryList.value = res.data || []
    }
  } catch (error) {
    console.error('Failed to load industry list:', error)
  } finally {
    industryListLoading.value = false
  }
}

const loadProfiles = async () => {
  loading.value = true
  try {
    const res = await analysisProfilesApi.listIndustries() as any
    if (res?.success) {
      industryProfiles.value = res.data || []
    }
  } catch (error) {
    console.error('Failed to load industry configuration:', error)
    ElMessage.error('Failed to load industry configuration')
  } finally {
    loading.value = false
  }
}

const submitForm = async () => {
  if (!formData.value.industry.trim()) {
    ElMessage.warning('Please enter the industry name')
    return
  }

  submitting.value = true
  try {
    const payload = normalizeProfile(formData.value)
    let res: any
    if (editMode.value === 'create') {
      res = await analysisProfilesApi.createIndustry(payload)
    } else if (editingId.value) {
      res = await analysisProfilesApi.updateIndustry(editingId.value, payload)
    }

    if (res?.success) {
      ElMessage.success(editMode.value === 'create' ? 'Created successfully' : 'Update successful')
      editDialogVisible.value = false
      await loadProfiles()
    } else {
      ElMessage.error(res?.message || 'Save failed')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || 'Save failed')
  } finally {
    submitting.value = false
  }
}

const deleteProfile = async (row: IndustryProfile) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete the industry configuration ${row.display_name || row.industry}] ?`,
      'Confirm deletion',
      { confirmButtonText: 'OK', cancelButtonText: 'Cancel', type: 'warning' },
    )

    const res = await analysisProfilesApi.deleteIndustry(row.id!) as any
    if (res?.success) {
      ElMessage.success('Delete successfully')
      await loadProfiles()
    } else {
      ElMessage.error(res?.message || 'Delete failed')
    }
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('Delete failed')
    }
  }
}

onMounted(async () => {
  await Promise.all([loadProfiles(), loadIndustryList()])
  const qIndustry = route.query.industry as string | undefined
  if (qIndustry?.trim()) {
    chatIndustry.value = qIndustry.trim()
  }
  resetConversation()
})
</script>

<style scoped lang="scss">
.analysis-profiles-container {
  padding: 20px;
}

.page-alert {
  margin-bottom: 16px;
}

.alert-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.95fr);
  gap: 16px;
  margin-bottom: 16px;
}

.workspace-card,
.saved-card {
  border-radius: 12px;
}

.chat-card,
.draft-card {
  min-height: 760px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.industry-select {
  flex: 1;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.chat-body {
  display: flex;
  flex-direction: column;
  min-height: 660px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 20px 16px;
  background: linear-gradient(180deg, rgba(64, 158, 255, 0.03), transparent 18%);
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  max-width: 92%;

  &.message-user {
    align-self: flex-end;
    flex-direction: row-reverse;

    .message-avatar {
      background: var(--el-color-primary-light-9);
      color: var(--el-color-primary);
    }

    .message-content {
      background: var(--el-color-primary);
      color: #fff;
    }
  }

  &.message-assistant {
    align-self: flex-start;

    .message-avatar {
      background: var(--el-fill-color-light);
      color: var(--el-text-color-regular);
    }

    .message-content {
      background: var(--el-fill-color-lighter);
      color: var(--el-text-color-primary);
    }
  }
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-content {
  border-radius: 14px;
  padding: 12px 16px;
}

.message-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  font-size: 14px;
}

.assistant-content {
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.02);
}

.thinking-bubble {
  opacity: 0.95;
}

.thinking-content {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.thinking-text {
  color: var(--el-text-color-secondary);
}

.thinking-dots .dot {
  animation: thinking-blink 1.4s infinite;
  display: inline-block;
  width: 0.5em;
}

.thinking-dots .dot:nth-child(1) { animation-delay: 0s; }
.thinking-dots .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes thinking-blink {
  0%, 60%, 100% { opacity: 0.2; }
  30% { opacity: 1; }
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-extra-light);
}

.quick-actions-title {
  display: inline-flex;
  align-items: center;
  margin-right: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.input-area {
  flex-shrink: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);

  .input-row {
    display: flex;
    gap: 12px;
    align-items: flex-end;
  }

  .send-btn {
    flex-shrink: 0;
    height: 72px;
    padding: 0 20px;
  }

  .input-tip {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    color: var(--el-text-color-placeholder);
    line-height: 1.6;
  }

  :deep(.el-textarea__inner) {
    resize: none;
  }
}

.draft-scroll {
  max-height: 690px;
  overflow-y: auto;
  padding-right: 4px;
}

.summary-descriptions,
.summary-alert,
.draft-section {
  margin-bottom: 16px;
}

.summary-list {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}

.summary-list.compact {
  margin-top: 0;
}

.section-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.focus-text {
  padding: 12px;
  border-radius: 10px;
  background: var(--el-fill-color-extra-light);
  color: var(--el-text-color-regular);
  line-height: 1.8;
  white-space: pre-wrap;
}

.draft-items,
.metric-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.draft-item,
.metric-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 12px;
  background: #fff;
}

.draft-item-header,
.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.item-title-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.item-title,
.industry-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.item-description {
  margin-top: 8px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.item-meta,
.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.item-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.meta-placeholder {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.metric-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.saved-card {
  margin-top: 4px;
}

.table-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}

.dimension-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

@media (max-width: 1280px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .chat-card,
  .draft-card {
    min-height: auto;
  }

  .draft-scroll {
    max-height: none;
  }
}

@media (max-width: 768px) {
  .analysis-profiles-container {
    padding: 12px;
  }

  .card-header,
  .session-toolbar,
  .toolbar-actions,
  .header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .message-item {
    max-width: 100%;
  }

  .input-area .input-row {
    flex-direction: column;
  }

  .input-area .send-btn {
    width: 100%;
    height: 40px;
  }

  .dimension-row {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
}
</style>

