<template>
  <div v-if="growthPanelEnabled" class="growth-panel">
    <el-collapse v-model="activeCollapse" class="growth-collapse">
      <el-collapse-item name="growth">
        <template #title>
          <div class="collapse-title">
            <el-icon><Collection /></el-icon>
            <span>{{ title }}</span>
            <el-tag type="info" size="small" class="collapse-tag">memory {{ growthSummary.memory_items_count }}</el-tag>
            <el-tag type="warning" size="small" class="collapse-tag">Suggestions {{ growthSummary.suggestions_count }}</el-tag>
          </div>
        </template>

        <div class="growth-panel-body">
          <div class="growth-toolbar">
            <el-button v-if="taskId" size="small" @click.stop="refreshGrowthContext" :loading="growthLoading">
              Refresh extraction items
            </el-button>
          </div>

          <el-skeleton :loading="growthLoading" animated :rows="4">
            <template #default>
              <template v-if="taskId">
                <el-tabs class="growth-tabs">
            <el-tab-pane :label="`Growing memory (${growthMemories.length})`" name="memories">
              <div v-if="growthMemories.length" class="growth-list">
                <div v-for="item in growthMemories" :key="item.memory_id" class="growth-item">
                  <div class="growth-item-header">
                    <div class="growth-item-title-row">
                      <h4>{{ item.title }}</h4>
                      <div class="growth-item-tags">
                        <el-tag size="small" :type="memoryStatusTagType(item.status)">
                          {{ GrowthMemoryStatusNames[item.status] || item.status }}
                        </el-tag>
                        <el-tag size="small" effect="plain">
                          {{ GrowthMemoryScopeNames[item.scope] || item.scope }}
                        </el-tag>
                        <el-tag size="small" effect="plain">Confidence {{ formatConfidence(item.confidence) }}</el-tag>
                      </div>
                    </div>
                    <div v-if="item.status === GrowthMemoryStatus.PENDING" class="growth-actions">
                      <el-button size="small" type="primary" @click="handleApproveMemory(item.memory_id)">approve</el-button>
                      <el-button size="small" @click="handleRejectMemory(item.memory_id)">reject</el-button>
                    </div>
                  </div>
                  <p v-if="item.summary" class="growth-summary-text">{{ item.summary }}</p>
                  <div v-if="getFormattedMemoryContent(item).highlights.length" class="growth-highlights">
                    <div
                      v-for="highlight in getFormattedMemoryContent(item).highlights"
                      :key="`${item.memory_id}-${highlight.label}`"
                      class="growth-highlight-row"
                    >
                      <span class="growth-meta-label">{{ highlight.label }}：</span>
                      <span class="growth-highlight-value">{{ highlight.value }}</span>
                    </div>
                  </div>
                  <el-collapse>
                    <el-collapse-item title="View full content" :name="item.memory_id">
                      <div class="growth-content markdown-body" v-html="renderMarkdown(getFormattedMemoryContent(item).displayText)"></div>
                    </el-collapse-item>
                  </el-collapse>
                  <div v-if="item.evidence_refs?.length" class="growth-evidence">
                    <span class="growth-meta-label">Source of evidence:</span>
                    <el-tag v-for="ref in item.evidence_refs" :key="`${ref.type}-${ref.id}`" size="small" effect="plain">
                      {{ ref.label || ref.type }}: {{ ref.id }}
                    </el-tag>
                  </div>
                </div>
              </div>
              <el-empty v-else description="There is no growth memory for the current task" />
            </el-tab-pane>

            <el-tab-pane :label="`Growth advice (${growthSuggestions.length})`" name="suggestions">
              <div v-if="growthSuggestions.length" class="growth-list">
                <div v-for="item in growthSuggestions" :key="item.suggestion_id" class="growth-item suggestion-item">
                  <div class="growth-item-header">
                    <div class="growth-item-title-row">
                      <h4>{{ item.title }}</h4>
                      <div class="growth-item-tags">
                        <el-tag size="small" :type="suggestionStatusTagType(item.status)">
                          {{ GrowthSuggestionStatusNames[item.status] || item.status }}
                        </el-tag>
                        <el-tag size="small" effect="plain">{{ getSuggestionTypeLabel(item.suggestion_type) }}</el-tag>
                        <el-tag size="small" effect="plain">Confidence {{ formatConfidence(item.confidence) }}</el-tag>
                      </div>
                    </div>
                    <div v-if="item.status === GrowthSuggestionStatus.PENDING" class="growth-actions">
                      <el-button size="small" type="primary" @click="handleAcceptSuggestion(item.suggestion_id)">accept</el-button>
                      <el-button size="small" @click="handleDismissSuggestion(item.suggestion_id)">ignore</el-button>
                    </div>
                    <div v-else-if="item.activation_result?.session_id" class="growth-actions">
                      <el-button size="small" type="success" plain @click="openWorkflowOptimization(item)">
                        Open an optimization session
                      </el-button>
                    </div>
                  </div>
                  <p class="growth-summary-text">{{ item.summary }}</p>
                  <div v-if="getFormattedSuggestionAction(item).highlights.length" class="growth-highlights">
                    <div
                      v-for="highlight in getFormattedSuggestionAction(item).highlights"
                      :key="`${item.suggestion_id}-${highlight.label}`"
                      class="growth-highlight-row"
                    >
                      <span class="growth-meta-label">{{ highlight.label }}：</span>
                      <span class="growth-highlight-value">{{ highlight.value }}</span>
                    </div>
                  </div>
                  <el-collapse v-if="item.suggested_action">
                    <el-collapse-item title="View suggested actions" :name="item.suggestion_id">
                      <pre class="json-content">{{ getFormattedSuggestionAction(item).displayText }}</pre>
                    </el-collapse-item>
                  </el-collapse>
                  <div v-if="item.source_refs?.length" class="growth-evidence">
                    <span class="growth-meta-label">Source:</span>
                    <el-tag v-for="ref in item.source_refs" :key="`${ref.type}-${ref.id}`" size="small" effect="plain">
                      {{ ref.label || ref.type }}: {{ ref.id }}
                    </el-tag>
                  </div>
                </div>
              </div>
              <el-empty v-else description="There are no growth suggestions for the current task" />
            </el-tab-pane>
          </el-tabs>
              </template>
              <el-empty v-else description="The current page has no associated tasks and cannot load the growth context." />
            </template>
          </el-skeleton>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection } from '@element-plus/icons-vue'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'

// marked The configuration has been @/utils/markdown Unified management
const renderMarkdown = (content: string): string => {
  if (!content?.trim()) return ''
  try {
    return safeMarkdown(content)
  } catch {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}
import {
  getTaskGrowthContext,
  approveGrowthMemory,
  rejectGrowthMemory,
  acceptGrowthSuggestion,
  dismissGrowthSuggestion,
  GrowthMemoryStatus,
  GrowthSuggestionStatus,
  GrowthMemoryStatusNames,
  GrowthSuggestionStatusNames,
  GrowthMemoryScopeNames,
  type TaskGrowthContextPayload,
  type GrowthMemoryItem,
  type GrowthSuggestion
} from '@/api/workflowGrowth'

type GrowthHighlight = {
  label: string
  value: string
}

type FormattedGrowthContent = {
  highlights: GrowthHighlight[]
  displayText: string
}

type FormattedSuggestionAction = {
  highlights: GrowthHighlight[]
  displayText: string
}

const props = withDefaults(defineProps<{
  taskId?: string | null
  title?: string
  initialContext?: TaskGrowthContextPayload | null
  closeOnNavigate?: boolean
}>(), {
  title: 'Experience refinement',
  initialContext: null,
  closeOnNavigate: false
})

const emit = defineEmits<{
  (e: 'navigated'): void
  (e: 'updated', context: TaskGrowthContextPayload | null): void
}>()

const router = useRouter()
const growthPanelEnabled = false
const activeCollapse = ref<string[]>([])  // default fold(empty array = No expansion items)
const growthLoading = ref(false)
const growthContext = ref<TaskGrowthContextPayload | null>(props.initialContext)

const growthMemories = computed<GrowthMemoryItem[]>(() => growthContext.value?.memory_items || [])
const growthSuggestions = computed<GrowthSuggestion[]>(() => growthContext.value?.suggestions || [])
const growthSummary = computed(() => ({
  memory_items_count: growthContext.value?.summary?.memory_items_count || 0,
  suggestions_count: growthContext.value?.summary?.suggestions_count || 0
}))

const FIELD_LABELS: Record<string, string> = {
  action: 'Operation tendency',
  analysis_view: 'Analysis conclusion',
  confidence: 'Confidence',
  risk_level: 'risk level',
  risk_score: 'risk score',
  target_price: 'target price',
  price_analysis_range: 'price range',
  stop_loss_price: 'Stop loss level',
  take_profit_price: 'Take profit level',
  reasoning: 'core rationale',
  conclusion: 'Conclusion',
  summary: 'Summary'
}

const SUGGESTION_TYPE_LABELS: Record<string, string> = {
  memory_promotion: 'Memory improvement suggestions',
  research_asset_promotion: 'Research asset accumulation',
  workflow_optimization: 'Workflow optimization',
  watch_rule_suggestion: 'Follow-up rules'
}

const ACTION_TARGET_LABELS: Record<string, string> = {
  object_tracking: 'object tracking',
  workflow_generation: 'Workflow optimization',
  research_asset: 'research assets'
}

const ACTION_MODE_LABELS: Record<string, string> = {
  follow_up_focus: 'Establish tracking focus',
  follow_up_field: 'Supplemental field tracking',
  start_session: 'Start an optimization session',
  promote_growth_asset: 'Precipitated into research assets'
}

const safeParseJson = (value: string): Record<string, any> | null => {
  if (!value) return null
  // Try it directly JSON.parse
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  } catch {
    // ignore
  }
  // Try converting Python-style single quotes to double quotes
  try {
    // Convert outer single-quote key-value pairs to double quotes (simple heuristic)
    const fixed = value
      .replace(/'/g, '"')                     // All single quotes→double quotes
      .replace(/None/g, 'null')               // Python None→null
      .replace(/True/g, 'true')               // Python True→true
      .replace(/False/g, 'false')             // Python False→false
    const parsed = JSON.parse(fixed)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

/**
 * Extract available JSON objects from the content string.
 * Support:
 *  - Standard JSON
 *  - markdown ```json ... ``` Code blocks (can be nested within outer dictionary values)
 *  - Python repr Dictionary of formats (single quotes)
 *  - Outer layer {'key': '```json\n{...}```'} Nested structure
 */
const extractJsonLikeObject = (content: string): Record<string, any> | null => {
  if (!content) return null

  // 1. Try to extract from the markdown code block (there may be multiple, take the deepest one that contains the complete JSON)
  const fencedRegex = /```(?:json)?\s*([\s\S]*?)```/gi
  let fencedMatch: RegExpExecArray | null
  while ((fencedMatch = fencedRegex.exec(content)) !== null) {
    const inner = fencedMatch[1].trim()
    const parsed = safeParseJson(inner)
    if (parsed) return parsed
  }

  // 2. Try to extract {...} interval
  const firstBrace = content.indexOf('{')
  const lastBrace = content.lastIndexOf('}')
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    const slice = content.slice(firstBrace, lastBrace + 1).trim()
    const parsed = safeParseJson(slice)
    if (parsed) {
      // If the parsing result has only one key and its value is a string containing JSON, recursively extract
      const keys = Object.keys(parsed)
      if (keys.length === 1 && typeof parsed[keys[0]] === 'string') {
        const inner = extractJsonLikeObject(parsed[keys[0]])
        if (inner) return inner
      }
      return parsed
    }
  }

  return null
}

const formatMetricValue = (key: string, value: unknown): string => {
  if (value === undefined || value === null || value === '') return '-'
  if (key === 'confidence' && typeof value === 'number') return `${Math.round(value * 100)}%`
  if (key === 'risk_score' && typeof value === 'number') return value.toFixed(2)
  if (key === 'price_analysis_range' && Array.isArray(value)) return value.join(' - ')
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

/**
 * Clean the original content text, removing code block tags, Python dict wrappers, etc. to make it readable.
 */
const cleanGrowthText = (content: string): string => {
  if (!content) return ''

  let text = content

  // Remove outer layer Python dict wrapper: {'some_key': '...'}
  const outerDictMatch = text.match(/^\s*\{['"]\w+['"]\s*:\s*['"]([\s\S]*)['"]\s*\}\s*$/)
  if (outerDictMatch) {
    text = outerDictMatch[1]
  }

  // Remove markdown code block tags
  text = text.replace(/```json\s*/gi, '').replace(/```/g, '')

  // Remove escaped newlines
  text = text.replace(/\\n/g, '\n').replace(/\\t/g, '  ')

  // Try formatting the inline JSON
  const braceStart = text.indexOf('{')
  const braceEnd = text.lastIndexOf('}')
  if (braceStart >= 0 && braceEnd > braceStart) {
    const jsonSlice = text.slice(braceStart, braceEnd + 1)
    const parsed = safeParseJson(jsonSlice)
    if (parsed) {
      return Object.entries(parsed)
        .map(([k, v]) => `${FIELD_LABELS[k] || k}：${formatMetricValue(k, v)}`)
        .join('\n\n')
    }
  }

  // final cleanup
  text = text.replace(/\r/g, '').trim()
  return text
}

const getFormattedMemoryContent = (item: GrowthMemoryItem): FormattedGrowthContent => {
  const parsedPayload = extractJsonLikeObject(item.content)
  const sourceField = String(item.structured_payload?.source_field || '')
  const relevantKeys = [
    'action',
    'analysis_view',
    'risk_level',
    'risk_score',
    'confidence',
    'price_analysis_range',
    'target_price',
    'reasoning',
    'summary',
    'conclusion'
  ]

  const highlights: GrowthHighlight[] = []
  if (parsedPayload) {
    relevantKeys.forEach((key) => {
      const value = parsedPayload[key]
      if (value !== undefined && value !== null && value !== '') {
        highlights.push({
          label: FIELD_LABELS[key] || key,
          value: formatMetricValue(key, value)
        })
      }
    })
  }

  if (!highlights.length && sourceField && item.summary) {
    highlights.push({
      label: 'Refined results',
      value: item.summary
    })
  }

  const displayText = parsedPayload
    ? Object.entries(parsedPayload)
        .map(([key, value]) => `${FIELD_LABELS[key] || key}：${formatMetricValue(key, value)}`)
        .join('\n\n')
    : cleanGrowthText(item.content)

  return {
    highlights,
    displayText: displayText || item.summary || 'No content yet'
  }
}

const getFormattedSuggestionAction = (item: GrowthSuggestion): FormattedSuggestionAction => {
  const action = item.suggested_action || {}
  const payload = action.payload && typeof action.payload === 'object' ? action.payload : {}
  const target = String(action.target || '')
  const mode = String(action.mode || '')
  const highlights: GrowthHighlight[] = []

  if (target) {
    highlights.push({ label: 'target', value: ACTION_TARGET_LABELS[target] || target })
  }
  if (mode) {
    highlights.push({ label: 'action', value: ACTION_MODE_LABELS[mode] || mode })
  }

  if (target === 'object_tracking') {
    if (payload.symbol) highlights.push({ label: 'tracking target', value: String(payload.symbol) })
    if (Array.isArray(payload.focus_points) && payload.focus_points.length) {
      highlights.push({ label: 'Keep track of key points', value: payload.focus_points.join('; ') })
    }
    if (payload.source_field) highlights.push({ label: 'Source field', value: String(payload.source_field) })
    if (payload.focus_summary) highlights.push({ label: 'Tracking instructions', value: String(payload.focus_summary) })
    if (payload.decision_action) highlights.push({ label: 'Relevant decision-making', value: String(payload.decision_action) })
    if (payload.agent_name) highlights.push({ label: 'source agent', value: String(payload.agent_name) })
  }

  if (target === 'workflow_generation') {
    if (payload.workflow_id) highlights.push({ label: 'Workflow', value: String(payload.workflow_id) })
    if (payload.description) highlights.push({ label: 'Optimization instructions', value: String(payload.description) })
    if (payload.source_field) highlights.push({ label: 'Focus on fields', value: String(payload.source_field) })
  }

  if (target === 'research_asset') {
    if (payload.object_key) highlights.push({ label: 'Precipitation object', value: String(payload.object_key) })
    if (payload.source_field) highlights.push({ label: 'Source field', value: String(payload.source_field) })
    if (payload.workflow_id) highlights.push({ label: 'Associated workflows', value: String(payload.workflow_id) })
    if (payload.agent_name) highlights.push({ label: 'source agent', value: String(payload.agent_name) })
  }

  const displayText = highlights.length
    ? highlights.map((entry) => `${entry.label}：${entry.value}`).join('\n\n')
    : JSON.stringify(action, null, 2)

  return {
    highlights,
    displayText: displayText || 'No suggested actions yet'
  }
}

const refreshGrowthContext = async () => {
  if (!growthPanelEnabled) {
    growthContext.value = null
    emit('updated', growthContext.value)
    return
  }

  if (!props.taskId) {
    growthContext.value = props.initialContext
    return
  }

  growthLoading.value = true
  try {
    const res = await getTaskGrowthContext(props.taskId)
    growthContext.value = (res as any)?.data?.data || (res as any)?.data || null
    emit('updated', growthContext.value)
  } catch (error: any) {
    if ((error?.message || '').includes('404')) {
      growthContext.value = props.initialContext
      emit('updated', growthContext.value)
      return
    }
    console.error('[TaskGrowthPanel] Failed to get growth context:', error)
    ElMessage.error(error?.message || 'Failed to get growth context')
  } finally {
    growthLoading.value = false
  }
}

const handleApproveMemory = async (memoryId: string) => {
  try {
    await approveGrowthMemory(memoryId)
    ElMessage.success('Approved for growing memory')
    await refreshGrowthContext()
  } catch (error: any) {
    ElMessage.error(error?.message || 'Failed to approve growing memory')
  }
}

const handleRejectMemory = async (memoryId: string) => {
  try {
    await rejectGrowthMemory(memoryId)
    ElMessage.success('Rejected growth memory')
    await refreshGrowthContext()
  } catch (error: any) {
    ElMessage.error(error?.message || 'Refuse to grow memory failure')
  }
}

const handleAcceptSuggestion = async (suggestionId: string) => {
  try {
    const res = await acceptGrowthSuggestion(suggestionId)
    const acceptedSuggestion = (res as any)?.data?.data || (res as any)?.data || null
    ElMessage.success('Growth suggestions accepted')
    await refreshGrowthContext()

    if (acceptedSuggestion?.activation_result?.session_id) {
      openWorkflowOptimization(acceptedSuggestion)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || 'Failure to accept growth advice')
  }
}

const handleDismissSuggestion = async (suggestionId: string) => {
  try {
    await dismissGrowthSuggestion(suggestionId)
    ElMessage.success('Growth suggestions ignored')
    await refreshGrowthContext()
  } catch (error: any) {
    ElMessage.error(error?.message || 'Ignoring Growth Advice Failure')
  }
}

const formatConfidence = (value?: number) => {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '-'
  return `${Math.round(Number(value) * 100)}%`
}

const memoryStatusTagType = (status: string) => {
  if (status === GrowthMemoryStatus.APPROVED) return 'success'
  if (status === GrowthMemoryStatus.REJECTED) return 'danger'
  if (status === GrowthMemoryStatus.PENDING) return 'warning'
  return 'info'
}

const suggestionStatusTagType = (status: string) => {
  if (status === GrowthSuggestionStatus.ACCEPTED) return 'success'
  if (status === GrowthSuggestionStatus.DISMISSED) return 'info'
  if (status === GrowthSuggestionStatus.PENDING) return 'warning'
  return 'info'
}

const getSuggestionTypeLabel = (suggestionType?: string) => {
  if (!suggestionType) return 'Growth advice'
  return SUGGESTION_TYPE_LABELS[suggestionType] || suggestionType
}

const openWorkflowOptimization = (suggestion: GrowthSuggestion) => {
  const sessionId = suggestion.activation_result?.session_id
  if (!sessionId) {
    ElMessage.warning('There are no optimization sessions open for the current recommendation')
    return
  }

  router.push({
    name: 'WorkflowGenerationCreate',
    query: { session_id: sessionId }
  })

  if (props.closeOnNavigate) {
    emit('navigated')
  }
}

watch(
  () => props.initialContext,
  (value) => {
    if (value) {
      growthContext.value = value
    }
  },
  { immediate: true }
)

watch(
  () => props.taskId,
  () => {
    void refreshGrowthContext()
  },
  { immediate: true }
)
</script>

<style scoped lang="scss">
.growth-panel {
  .growth-collapse {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    overflow: hidden;

    :deep(.el-collapse-item__header) {
      padding: 12px 16px;
      font-size: 16px;
      font-weight: 600;
      height: auto;
      line-height: 1.5;
      background: #fafafa;
      border-bottom: none;
    }

    :deep(.el-collapse-item__wrap) {
      border-top: 1px solid #e5e7eb;
    }

    :deep(.el-collapse-item__content) {
      padding: 0;
    }
  }

  .collapse-title {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .collapse-tag {
    margin-left: 4px;
  }

  .growth-panel-body {
    padding: 16px;
  }

  .growth-toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 12px;
  }

  .growth-tabs {
    :deep(.el-tabs__content) {
      overflow: visible;
    }
  }

  .growth-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .growth-highlights {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 12px 0;
    padding: 12px 14px;
    border-radius: 8px;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
  }

  .growth-highlight-row {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    line-height: 1.6;
  }

  .growth-highlight-value {
    flex: 1;
    color: #374151;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .growth-item {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 16px;
    background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  }

  .growth-item-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }

  .growth-item-title-row {
    display: flex;
    flex-direction: column;
    gap: 8px;

    h4 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: #1f2937;
    }
  }

  .growth-item-tags,
  .growth-actions,
  .growth-evidence {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .growth-summary-text {
    margin: 0 0 10px;
    color: #4b5563;
    line-height: 1.7;
  }

  .growth-content {
    line-height: 1.7;
    color: #374151;
    font-size: 14px;

    :deep(h1), :deep(h2), :deep(h3), :deep(h4) {
      margin: 12px 0 8px;
      font-weight: 600;
      color: #1f2937;
    }
    :deep(h2) { font-size: 16px; }
    :deep(h3) { font-size: 15px; }
    :deep(h4) { font-size: 14px; }

    :deep(p) {
      margin: 6px 0;
    }

    :deep(ul), :deep(ol) {
      padding-left: 20px;
      margin: 6px 0;
    }

    :deep(table) {
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0;
      font-size: 13px;

      th, td {
        border: 1px solid #e5e7eb;
        padding: 6px 10px;
        text-align: left;
      }
      th {
        background: #f9fafb;
        font-weight: 600;
      }
    }

    :deep(code) {
      background: #f3f4f6;
      padding: 2px 5px;
      border-radius: 3px;
      font-size: 13px;
    }

    :deep(pre) {
      background: #f3f4f6;
      padding: 12px;
      border-radius: 6px;
      overflow-x: auto;
      margin: 8px 0;

      code {
        background: none;
        padding: 0;
      }
    }

    :deep(blockquote) {
      border-left: 3px solid #d1d5db;
      padding-left: 12px;
      margin: 8px 0;
      color: #6b7280;
    }
  }

  .growth-meta-label {
    color: #6b7280;
    font-size: 13px;
    line-height: 24px;
  }

  .json-content {
    background-color: #f5f7fa;
    padding: 12px;
    border-radius: 4px;
    font-size: 12px;
    line-height: 1.6;
    overflow-x: auto;
    max-height: 320px;
    overflow-y: auto;
    margin: 0;
  }
}
</style>