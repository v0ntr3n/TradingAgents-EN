<template>
  <div class="general-analysis">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <h1 class="page-title">
            <el-icon class="title-icon"><Document /></el-icon>
            General Research Analysis
          </h1>

          <!-- Risk warning -->
          <div class="risk-disclaimer">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
            >
              <template #title>
                <span style="font-size: 14px;">
                  <strong>⚠️ IMPORTANT NOTE:</strong>All conclusions of this analysis are used to learn and verify AI securities analysis technology and are not intended to be used as real trading guidance.
                </span>
              </template>
            </el-alert>
          </div>

          <p class="page-description">
            Flexible research workbench based on common processes, supporting customized analysis goals and parameters
          </p>
        </div>
      </div>
    </div>

    <!-- Main content area (tab switching) -->
    <el-tabs v-model="activeTab" class="main-tabs">
      <el-tab-pane label="new analysis" name="new">
        <!-- Process selection + dynamic form -->
        <div class="analysis-container">
          <el-card class="main-form-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <h3>Analysis configuration</h3>
                <el-tag type="info" size="small">Required information</el-tag>
              </div>
            </template>

            <!-- Process selection -->
            <el-form label-width="100px" class="analysis-form">
              <div class="form-section">
                <h4 class="section-title">📋 Analysis process</h4>
                <el-form-item label="Process selection">
                  <el-select
                    v-model="selectedWorkflowId"
                    placeholder="Please select a general analysis process"
                    size="large"
                    style="width: 100%"
                    :loading="loadingWorkflows"
                  >
                    <el-option
                      v-for="workflow in workflows"
                      :key="workflow.id"
                      :label="`${workflow.name} v${workflow.version}`"
                      :value="workflow.id"
                    >
                      <span>{{ workflow.name }}</span>
                      <span style="color: #909399; font-size: 12px; margin-left: 8px;">
                        v{{ workflow.version }}
                      </span>
                      <el-tag
                        v-if="workflow.is_default"
                        type="warning"
                        size="small"
                        effect="plain"
                        style="margin-left: 8px;"
                      >
                        Default
                      </el-tag>
                    </el-option>
                  </el-select>
                  <div v-if="selectedWorkflow" class="workflow-description">
                    <el-icon><InfoFilled /></el-icon>
                    <span>{{ selectedWorkflow.description || 'No process description yet' }}</span>
                  </div>
                  <el-empty
                    v-else-if="!loadingWorkflows && workflows.length === 0"
                    description="No general analysis process is available yet"
                    :image-size="60"
                  />
                </el-form-item>
              </div>
            </el-form>

            <!-- Dynamic form (shown only when process is selected) -->
            <template v-if="selectedWorkflowId && selectedWorkflow">
              <el-divider content-position="left">Execution parameters</el-divider>
              <el-form :model="formValues" label-position="top" class="analysis-form">
                <!-- Loading -->
                <el-empty v-if="loadingSelectedWorkflow" description="Load parameter configuration..." :image-size="60"></el-empty>
                <!-- Dynamic form: generated from selectedWorkflowFull.input_config.fields -->
                <template v-else-if="inputFields.length > 0">
                  <template v-for="group in groupedFields" :key="group.name">
                    <div v-if="group.name" class="field-group-title">{{ group.name }}</div>
                    <el-form-item
                      v-for="field in group.fields"
                      :key="field.name"
                      :label="field.label || field.name"
                      :required="field.required"
                    >
                      <!-- string: single line of text -->
                      <el-input
                        v-if="field.type === 'string'"
                        v-model="formValues[field.name]"
                        :placeholder="field.placeholder || ''"
                      />

                      <!-- textarea: multiline text -->
                      <el-input
                        v-else-if="field.type === 'textarea'"
                        v-model="formValues[field.name]"
                        type="textarea"
                        :rows="4"
                        :placeholder="field.placeholder || ''"
                        maxlength="500"
                        show-word-limit
                      />

                      <!-- number: numbers -->
                      <el-input-number
                        v-else-if="field.type === 'number'"
                        v-model="formValues[field.name]"
                        :min="field.min ?? undefined"
                        :max="field.max ?? undefined"
                        style="width: 100%"
                      />

                      <!-- boolean: switch -->
                      <el-switch
                        v-else-if="field.type === 'boolean'"
                        v-model="formValues[field.name]"
                      />

                      <!-- date: date selection -->
                      <el-date-picker
                        v-else-if="field.type === 'date'"
                        v-model="formValues[field.name]"
                        type="date"
                        placeholder="Select date"
                        style="width: 100%"
                        value-format="YYYY-MM-DD"
                      />

                      <!-- select: Drop down radio selection -->
                      <el-select
                        v-else-if="field.type === 'select'"
                        v-model="formValues[field.name]"
                        :placeholder="field.placeholder || 'Please select'"
                        style="width: 100%"
                        :loading="modelsLoading"
                      >
                        <!-- Special handling of model fields: dynamically populate options from enabledModels -->
                        <template v-if="field.name === 'quick_analysis_model' || field.name === 'deep_analysis_model'">
                          <el-option
                            v-for="model in enabledModels"
                            :key="model.model_name"
                            :label="model.model_name"
                            :value="model.model_name"
                          />
                        </template>
                        <!-- Normal options -->
                        <template v-else>
                          <el-option
                            v-for="(opt, idx) in (field.options || [])"
                            :key="idx"
                            :label="field.option_labels?.[idx] || String(opt)"
                            :value="opt"
                          />
                        </template>
                      </el-select>

                      <!-- multiselect: Drop-down multiple selection -->
                      <el-select
                        v-else-if="field.type === 'multiselect'"
                        v-model="formValues[field.name]"
                        multiple
                        :placeholder="field.placeholder || 'Please select'"
                        style="width: 100%"
                      >
                        <el-option
                          v-for="(opt, idx) in (field.options || [])"
                          :key="idx"
                          :label="field.option_labels?.[idx] || String(opt)"
                          :value="opt"
                        />
                      </el-select>

                      <!-- Parameter description -->
                      <div v-if="field.description" class="field-description">{{ field.description }}</div>
                    </el-form-item>
                  </template>
                </template>

                <!-- No input parameter prompt -->
                <el-empty
                  v-else
                  description="This process requires no input parameters"
                  :image-size="60"
                />

                <el-form-item>
                  <el-button
                    type="primary"
                    size="large"
                    :loading="executing"
                    :disabled="!selectedWorkflowId"
                    @click="handleExecute"
                    class="submit-btn"
                  >
                    <el-icon><TrendCharts /></el-icon>
                    Start analysis
                  </el-button>
                </el-form-item>
              </el-form>
            </template>
          </el-card>

          <!-- Execution status display -->
          <el-card v-if="taskStatus !== 'idle'" class="status-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <h3>Execution status</h3>
                <el-tag :type="statusTagType" size="small">{{ statusTagText }}</el-tag>
              </div>
            </template>

            <div class="status-content">
              <div class="status-info">
                <div class="info-item">
                  <span class="info-label">Task ID</span>
                  <span class="info-value">
                    <el-text class="task-id-text" truncated>{{ taskId || '—' }}</el-text>
                    <el-button
                      v-if="taskId"
                      type="primary"
                      link
                      size="small"
                      @click="copyTaskId"
                    >
                      <el-icon><CopyDocument /></el-icon>
                      Copy
                    </el-button>
                  </span>
                </div>

                <div class="info-item">
                  <span class="info-label">Analyze goals</span>
                  <span class="info-value">{{ formValues.analysis_target || formValues.ticker || '—' }}</span>
                </div>

                <div class="info-item">
                  <span class="info-label">start time</span>
                  <span class="info-value">{{ startedAt || '—' }}</span>
                </div>

                <div v-if="taskStatus === 'running'" class="info-item">
                  <span class="info-label">elapsed time</span>
                  <span class="info-value">{{ elapsedText }}</span>
                </div>
              </div>

              <!-- progress bar -->
              <div v-if="taskStatus === 'running'" class="progress-section">
                <el-progress
                  :percentage="progressPercent"
                  :stroke-width="10"
                  :status="progressStatus"
                  :indeterminate="progressPercent === 0"
                />
                <div v-if="currentStep" class="current-step">
                  <el-icon class="rotating-icon"><Loading /></el-icon>
                  <span>{{ currentStep }}</span>
                </div>
              </div>

              <!-- error message -->
              <el-alert
                v-if="taskStatus === 'failed' && errorMessage"
                type="error"
                :closable="false"
                show-icon
                :title="errorMessage"
                style="margin-top: 12px;"
              />

              <!-- Completion prompt -->
              <el-alert
                v-if="taskStatus === 'completed'"
                type="success"
                :closable="false"
                show-icon
                title="Analysis task completed"
                style="margin-top: 12px;"
              >
                <template #default>
                  <div>Click above"View results"button to go to the task center to view the complete analysis report.</div>
                </template>
              </el-alert>

              <!-- Results link -->
              <div v-if="taskStatus === 'completed'" class="result-link-section">
                <el-button
                  type="primary"
                  size="large"
                  @click="viewResult"
                  class="submit-btn"
                >
                  <el-icon><Document /></el-icon>
                  View results
                </el-button>
                <el-button
                  size="large"
                  @click="resetAnalysis"
                  class="submit-btn"
                >
                  <el-icon><Refresh /></el-icon>
                  Reanalyze
                </el-button>
              </div>

              <!-- failed link -->
              <div v-if="taskStatus === 'failed'" class="result-link-section">
                <el-button
                  type="danger"
                  size="large"
                  @click="resetAnalysis"
                  class="submit-btn"
                >
                  <el-icon><Refresh /></el-icon>
                  Reanalyze
                </el-button>
              </div>
            </div>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Historical results tab page (retain original logic) -->
      <el-tab-pane label="historical results" name="history">
        <div class="history-container">
          <!-- filter bar -->
          <el-card shadow="never" class="filter-card">
            <el-form :inline="true" :model="historyFilters" size="default">
              <el-form-item label="process">
                <el-select
                  v-model="historyFilters.workflow_id"
                  placeholder="All processes"
                  clearable
                  style="width: 200px"
                >
                  <el-option
                    v-for="wf in workflows"
                    :key="wf.id"
                    :label="`${wf.name} v${wf.version}`"
                    :value="wf.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="time range">
                <el-date-picker
                  v-model="historyDateRange"
                  type="daterange"
                  range-separator="to"
                  start-placeholder="start date"
                  end-placeholder="end date"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  style="width: 260px"
                />
              </el-form-item>

              <el-form-item label="Keywords">
                <el-input
                  v-model="historyFilters.keyword"
                  placeholder="Search analytics goals"
                  clearable
                  style="width: 200px"
                  @keyup.enter="loadHistory"
                />
              </el-form-item>

              <el-form-item label="Status">
                <el-select
                  v-model="historyFilters.status"
                  placeholder="All status"
                  clearable
                  style="width: 120px"
                >
                  <el-option label="Completed" value="completed" />
                  <el-option label="In progress" value="processing" />
                  <el-option label="failed" value="failed" />
                  <el-option label="Waiting" value="pending" />
                </el-select>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="loadHistory" :loading="historyLoading">
                  <el-icon><Search /></el-icon>
                  Query
                </el-button>
                <el-button @click="resetHistoryFilters">
                  <el-icon><Refresh /></el-icon>
                  reset
                </el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- Historical results table -->
          <el-card shadow="never" class="history-table-card">
            <el-table
              :data="historyList"
              v-loading="historyLoading"
              stripe
              style="width: 100%"
            >
              <template #empty>
                <el-empty description="There is no history yet. After performing a new analysis, you can view the results here." />
              </template>

              <el-table-column label="Analyze goals" min-width="220">
                <template #default="{ row }">
                  <el-link
                    type="primary"
                    @click="showHistoryDetail(row)"
                    style="font-weight: 500;"
                  >
                    {{ row.analysis_target || '—' }}
                  </el-link>
                </template>
              </el-table-column>

              <el-table-column label="process" min-width="160">
                <template #default="{ row }">
                  {{ getWorkflowName(row.workflow_id) }}
                </template>
              </el-table-column>

              <el-table-column label="Status" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="getHistoryStatusColor(row.status)" size="small">
                    {{ getHistoryStatusName(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="Progress" width="120">
                <template #default="{ row }">
                  <el-progress
                    v-if="row.status === 'processing'"
                    :percentage="row.progress || 0"
                    :stroke-width="6"
                  />
                  <span v-else-if="row.status === 'completed'" style="color: #67c23a">100%</span>
                  <span v-else style="color: #909399">—</span>
                </template>
              </el-table-column>

              <el-table-column label="creation time" width="170">
                <template #default="{ row }">
                  {{ formatHistoryTime(row.created_at) }}
                </template>
              </el-table-column>

              <el-table-column label="Time consuming" width="100" align="center">
                <template #default="{ row }">
                  <span v-if="row.execution_time > 0">{{ formatDuration(row.execution_time) }}</span>
                  <span v-else style="color: #909399">—</span>
                </template>
              </el-table-column>

              <el-table-column label="Operation" width="120" fixed="right" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="showHistoryDetail(row)">
                    <el-icon><View /></el-icon>
                    View details
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <!-- Pagination -->
            <div class="pagination-wrapper" v-if="historyTotal > 0">
              <el-pagination
                v-model:current-page="historyCurrentPage"
                v-model:page-size="historyPageSize"
                :total="historyTotal"
                :page-sizes="[10, 20, 50]"
                layout="total, sizes, prev, pager, next"
                @size-change="loadHistory"
                @current-change="loadHistory"
              />
            </div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Historical result details dialog box (retain original logic) -->
    <el-dialog
      v-model="detailDialogVisible"
      title="Analysis result details"
      width="90%"
      top="3vh"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-loading="detailLoading" class="detail-container">
        <template v-if="detailData">
          <!-- Basic information -->
          <el-card shadow="never" class="detail-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><InfoFilled /></el-icon>
                <span>Basic information</span>
              </div>
            </template>
            <el-descriptions :column="3" border>
              <el-descriptions-item label="Analyze goals" :span="2">
                <strong>{{ detailData.task_params?.symbol || detailData.task_params?.analysis_target || detailData.task_params?.ticker || '—' }}</strong>
              </el-descriptions-item>
              <el-descriptions-item label="Status">
                <el-tag :type="getHistoryStatusColor(detailData.status)">
                  {{ getHistoryStatusName(detailData.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="process">
                {{ getWorkflowName(detailData.workflow_id) }}
              </el-descriptions-item>
              <el-descriptions-item label="creation time">
                {{ formatHistoryTime(detailData.created_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="Time consuming">
                {{ detailData.execution_time > 0 ? formatDuration(detailData.execution_time) : '—' }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- error message -->
          <el-card v-if="detailData.error_message" shadow="never" class="detail-section error-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><Warning /></el-icon>
                <span>error message</span>
              </div>
            </template>
            <el-alert :title="detailData.error_message" type="error" :closable="false" show-icon />
          </el-card>

          <!-- Analysis summary -->
          <el-card v-if="detailData.result" shadow="never" class="detail-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><Document /></el-icon>
                <span>Analysis summary</span>
              </div>
            </template>
            <div class="summary-content">
              <div class="summary-item" v-if="detailData.result.summary">
                <div class="summary-label">Summary:</div>
                <div class="summary-value">{{ detailData.result.summary }}</div>
              </div>
              <div class="summary-item" v-if="detailData.result.recommendation">
                <div class="summary-label">Suggestions:</div>
                <div class="summary-value">{{ detailData.result.recommendation }}</div>
              </div>
              <div class="summary-item" v-if="detailData.result.risk_level">
                <div class="summary-label">Risk level:</div>
                <div class="summary-value">
                  <el-tag size="small">{{ detailData.result.risk_level }}</el-tag>
                </div>
              </div>
            </div>
          </el-card>

          <!-- Complete workflow output -->
          <el-card v-if="detailData.result?.report_manifest?.length" shadow="never" class="detail-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><DataAnalysis /></el-icon>
                <span>Complete workflow output</span>
              </div>
            </template>
            <el-collapse v-model="activeReportNames" class="report-collapse">
              <el-collapse-item
                v-for="item in sortedReportManifest"
                :key="item.field"
                :name="item.field"
              >
                <template #title>
                  <div class="report-title">
                    <span class="report-icon">{{ item.icon || '📄' }}</span>
                    <span class="report-name">{{ item.display_name || item.field }}</span>
                    <el-tag
                      v-if="item.is_primary"
                      type="warning"
                      size="small"
                      effect="plain"
                      style="margin-left: 8px;"
                    >
                      main report
                    </el-tag>
                    <el-tag
                      v-if="!item.has_content"
                      type="info"
                      size="small"
                      effect="plain"
                      style="margin-left: 8px;"
                    >
                      No content
                    </el-tag>
                  </div>
                </template>
                <div class="report-content">
                  <template v-if="getReportContent(item.field)">
                    <div class="markdown-content" v-html="renderMarkdown(getReportContent(item.field))"></div>
                  </template>
                  <el-text v-else type="info">This report has no content yet</el-text>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <!-- Research conclusion information -->
          <el-card v-if="detailData.result?.decision" shadow="never" class="detail-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><Tickets /></el-icon>
                <span>Research conclusion information</span>
              </div>
            </template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="research conclusion tendency">
                <el-tag :type="getDecisionColor(detailData.result.decision.action)">
                  {{ detailData.result.decision.action || '—' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Confidence">
                {{ formatPercent(detailData.result.decision.confidence) }}
              </el-descriptions-item>
              <el-descriptions-item label="risk score" :span="2">
                {{ detailData.result.decision.risk_score ?? '—' }}
              </el-descriptions-item>
              <el-descriptions-item
                v-if="detailData.result.decision.reasoning"
                label="Research basis"
                :span="2"
              >
                {{ detailData.result.decision.reasoning }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- raw data -->
          <el-card shadow="never" class="detail-section">
            <template #header>
              <div class="detail-card-header">
                <el-icon><Document /></el-icon>
                <span>Raw data (JSON)</span>
              </div>
            </template>
            <el-collapse>
              <el-collapse-item title="Expand to view complete JSON" name="raw">
                <pre class="json-content">{{ JSON.stringify(detailData, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </el-card>
        </template>
        <el-empty v-else-if="!detailLoading" description="No data yet" />
      </div>

      <template #footer>
        <el-button @click="detailDialogVisible = false">close</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Document,
  TrendCharts,
  InfoFilled,
  Loading,
  Refresh,
  CopyDocument,
  Search,
  View,
  Warning,
  DataAnalysis,
  Tickets,
} from '@element-plus/icons-vue'
import { workflowApi, type WorkflowSummary, type WorkflowDefinition, type InputFieldConfig } from '@/api/workflow'
import { analysisApi } from '@/api/analysis'
import { configApi, type LLMConfig } from '@/api/config'
import {
  getGeneralTaskList,
  getTaskDetail,
  GeneralTaskStatusNames,
  GeneralTaskStatusColors,
  type GeneralTaskListItem,
  type GeneralTaskListParams,
} from '@/api/unifiedTasks'
import { useAuthStore } from '@/stores/auth'
import { isJdyunMode, JDYUN_CHAT_MODELS, loadJdyunChatModels } from '@/utils/config'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'

const router = useRouter()

// ==================== Tab switching ====================
const activeTab = ref<'new' | 'history'>('new')

// Process selection
const workflows = ref<WorkflowSummary[]>([])
const selectedWorkflowId = ref('')
const loadingWorkflows = ref(false)

// Complete data of the selected process (including input_config)
const selectedWorkflowFull = ref<WorkflowDefinition | null>(null)
const loadingSelectedWorkflow = ref(false)

// Model list (only for select type model field dynamic filling option)
const modelsLoading = ref(false)
const allModels = ref<LLMConfig[]>([])
const enabledModels = computed(() => allModels.value.filter(m => m.enabled))

// Dynamic form values:formValues[field.name] = value
const formValues = ref<Record<string, any>>({})

// List of input parameter fields (read from workflow.input_config.fields)
const selectedWorkflow = computed(() => {
  return workflows.value.find(w => w.id === selectedWorkflowId.value)
})
const inputFields = computed<InputFieldConfig[]>(() => {
  return selectedWorkflowFull.value?.input_config?.fields || []
})

// Organize fields into groups
const groupedFields = computed(() => {
  const fields = [...inputFields.value].sort((a, b) => (a.order || 0) - (b.order || 0))
  const groups: Array<{ name: string; fields: InputFieldConfig[] }> = []
  const groupMap = new Map<string, InputFieldConfig[]>()

  for (const f of fields) {
    const g = f.group || ''
    if (!groupMap.has(g)) groupMap.set(g, [])
    groupMap.get(g)!.push(f)
  }

  for (const [name, fields] of groupMap) {
    groups.push({ name, fields })
  }
  return groups
})

// Execution status
const executing = ref(false)
const taskId = ref('')
const taskStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
const errorMessage = ref('')
const progressPercent = ref(0)
const currentStep = ref('')
const startedAt = ref('')
const elapsedSeconds = ref(0)

let pollTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null

// status label
const statusTagType = computed<'info' | 'warning' | 'success' | 'danger'>(() => {
  switch (taskStatus.value) {
    case 'running': return 'warning'
    case 'completed': return 'success'
    case 'failed': return 'danger'
    default: return 'info'
  }
})

const statusTagText = computed(() => {
  switch (taskStatus.value) {
    case 'running': return 'Running'
    case 'completed': return 'Completed'
    case 'failed': return 'Execution failed'
    default: return 'Waiting'
  }
})

// progress bar status
const progressStatus = computed<'' | 'success' | 'exception'>(() => {
  if (taskStatus.value === 'completed') return 'success'
  if (taskStatus.value === 'failed') return 'exception'
  return ''
})

// Elapsed time formatting
const elapsedText = computed(() => {
  const s = elapsedSeconds.value
  if (s < 60) return `${s} seconds`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return `${m} points ${rest} seconds`
})

// ==================== initialization ====================

// Load model configuration
const loadModels = async () => {
  modelsLoading.value = true
  try {
    // 🔥 Jingdong Cloud mode: first load the list of available models from the backend, overwriting the default value
    await loadJdyunChatModels()

    const response = await configApi.getLLMConfigs()
    let models = Array.isArray(response) ? response : []

    // 🔧 JD Cloud mode: only retain the 4 preset models
    if (isJdyunMode()) {
      const jdyunModelSet = new Set<string>(JDYUN_CHAT_MODELS)
      models = models.filter((m: any) => jdyunModelSet.has(m.model_name))
      if (models.length === 0) {
        models = JDYUN_CHAT_MODELS.map(name => ({
          model_name: name,
          model_display_name: name,
          provider: 'jdyun',
          enabled: true
        })) as any
      }
    }
    allModels.value = models
  } catch (error) {
    console.error('Failed to load model configuration:', error)
    // Jingdong cloud model tells the story
    if (isJdyunMode()) {
      allModels.value = JDYUN_CHAT_MODELS.map(name => ({
        model_name: name,
        model_display_name: name,
        provider: 'jdyun',
        enabled: true
      })) as any
    }
  } finally {
    modelsLoading.value = false
  }
}

// Load process list
const loadWorkflows = async () => {
  loadingWorkflows.value = true
  try {
    const data = await workflowApi.listAll()
    const list = Array.isArray(data) ? data : []
    workflows.value = list.filter((w: WorkflowSummary) => w.workflow_type === 'general')

    // Automatically select default process
    const defaultWf = workflows.value.find(w => w.is_default)
    if (defaultWf) {
      selectedWorkflowId.value = defaultWf.id
    } else if (workflows.value.length > 0) {
      selectedWorkflowId.value = workflows.value[0].id
    }
  } catch (e) {
    console.error('Loading process failed', e)
    ElMessage.error('Failed to load process list')
  } finally {
    loadingWorkflows.value = false
  }
}

// Initialize form default values
const initFormValues = async () => {
  const values: Record<string, any> = {}
  // Jingdong Cloud mode: preset model whitelist, used to verify the default model
  const jdyunModelSet = isJdyunMode() ? new Set<string>(JDYUN_CHAT_MODELS) : null
  for (const field of inputFields.value) {
    let defaultVal = field.default
    // Special handling of model fields: loading default model from system configuration
    if (field.name === 'quick_analysis_model' && !defaultVal) {
      try {
        const defaultModels = await configApi.getDefaultModels()
        defaultVal = defaultModels.quick_analysis_model || ''
      } catch { defaultVal = '' }
      // 🔧 JD Cloud Mode: Fall back to the first preset model when the default model is not in the whitelist
      if (isJdyunMode() && defaultVal && jdyunModelSet && !jdyunModelSet.has(defaultVal)) {
        defaultVal = JDYUN_CHAT_MODELS[0]
      }
    } else if (field.name === 'deep_analysis_model' && !defaultVal) {
      try {
        const defaultModels = await configApi.getDefaultModels()
        defaultVal = defaultModels.deep_analysis_model || ''
      } catch { defaultVal = '' }
      // 🔧 JD Cloud Mode: Fall back to the first preset model when the default model is not in the whitelist
      if (isJdyunMode() && defaultVal && jdyunModelSet && !jdyunModelSet.has(defaultVal)) {
        defaultVal = JDYUN_CHAT_MODELS[0]
      }
    } else if (field.name === 'research_depth' && !defaultVal) {
      try {
        const authStore = useAuthStore()
        const userPrefs = authStore.user?.preferences
        if (userPrefs?.default_depth) {
          defaultVal = convertDepthToText(Number(userPrefs.default_depth))
        }
      } catch { /* ignore */ }
    }

    if (defaultVal === null || defaultVal === undefined) {
      switch (field.type) {
        case 'boolean': defaultVal = false; break
        case 'number': defaultVal = undefined; break
        case 'multiselect': defaultVal = []; break
        case 'date':
          if (field.name === 'analysis_date') {
            defaultVal = new Date().toISOString().slice(0, 10)
          } else {
            defaultVal = ''
          }
          break
        default: defaultVal = ''
      }
    }
    values[field.name] = defaultVal
  }
  formValues.value = values
}

// Depth value conversion
const convertDepthToText = (depth: number) => {
  switch (depth) {
    case 1: return 'fast'
    case 2: return 'Basics'
    case 3: return 'Standard'
    case 4: return 'Depth'
    case 5: return 'Comprehensive'
    default: return 'Standard'
  }
}

// Load complete workflow data when process changes are selected
watch(selectedWorkflowId, async (newVal) => {
  if (!newVal) {
    selectedWorkflowFull.value = null
    formValues.value = {}
    return
  }

  loadingSelectedWorkflow.value = true
  try {
    selectedWorkflowFull.value = await workflowApi.get(newVal)
    await initFormValues()
  } catch (e) {
    console.error('Failed to load process details:', e)
    ElMessage.error('Failed to load process details')
  } finally {
    loadingSelectedWorkflow.value = false
  }
})

// ==================== Perform analysis ====================

// Copy task ID
const copyTaskId = async () => {
  if (!taskId.value) return
  try {
    await navigator.clipboard.writeText(taskId.value)
    ElMessage.success('Task ID copied')
  } catch {
    ElMessage.warning('Copy failed, please manually select text to copy')
  }
}

// Perform analysis
const handleExecute = async () => {
  if (!selectedWorkflowId.value) {
    ElMessage.warning('Please select the analysis process first')
    return
  }

  // Validate required fields
  for (const field of inputFields.value) {
    if (field.required) {
      const val = formValues.value[field.name]
      const empty = val === null || val === undefined || val === '' ||
        (Array.isArray(val) && val.length === 0)
      if (empty) {
        ElMessage.warning(`Please fill in${field.label || field.name}`)
        return
      }
    }
  }

  executing.value = true
  taskStatus.value = 'running'
  errorMessage.value = ''
  progressPercent.value = 0
  currentStep.value = 'Initializing analysis engine...'
  startedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
  elapsedSeconds.value = 0

  // Start timing
  startElapsedTimer()

  try {
    // Construct request parameters
    const params: Record<string, any> = {}
    for (const field of inputFields.value) {
      const val = formValues.value[field.name]
      if (val !== null && val !== undefined && val !== '') {
        params[field.name] = val
      }
    }

    // If there is no ticker field but there is analysis_target, reuse it as ticker (the workflow engine needs ticker for parameter mapping)
    if (!params.ticker) {
      if (params.analysis_target) {
        params.ticker = params.analysis_target
      }
    }

    // All parameters merged into custom_params
    const customParams: Record<string, any> = { ...params }
    delete customParams.ticker
    params.custom_params = customParams

    const result = await workflowApi.execute(selectedWorkflowId.value, params)

    if (result.success && result.task_id) {
      taskId.value = result.task_id
      ElMessage.success('Analysis task has been created')
      startPolling()
    } else {
      throw new Error(result.error || result.message || 'Task not obtained ID')
    }
  } catch (e: any) {
    taskStatus.value = 'failed'
    errorMessage.value = e?.message || 'Execution failed'
    ElMessage.error(errorMessage.value)
    stopElapsedTimer()
  } finally {
    executing.value = false
  }
}

// Start polling task status
const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!taskId.value) return
    try {
      const response = await analysisApi.getTaskStatus(taskId.value)
      const status = response.data
      if (!status) return

      if (typeof status.progress === 'number') {
        progressPercent.value = Math.min(100, Math.max(0, Math.round(status.progress)))
      }
      if (status.current_step_name || status.current_step) {
        currentStep.value = status.current_step_name || status.current_step
      } else if (status.message) {
        currentStep.value = status.message
      }

      const st = status.status
      if (st === 'completed' || st === 'success') {
        taskStatus.value = 'completed'
        progressPercent.value = 100
        stopPolling()
        stopElapsedTimer()
        ElMessage.success('Analysis completed')
      } else if (st === 'failed' || st === 'error') {
        taskStatus.value = 'failed'
        errorMessage.value = status.error || status.error_message || 'Task execution failed'
        stopPolling()
        stopElapsedTimer()
        ElMessage.error('Analysis failed')
      }
    } catch (e) {
      console.error('Failed to query task status', e)
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startElapsedTimer = () => {
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value += 1
  }, 1000)
}

const stopElapsedTimer = () => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

const resetAnalysis = () => {
  stopPolling()
  stopElapsedTimer()
  taskStatus.value = 'idle'
  taskId.value = ''
  errorMessage.value = ''
  progressPercent.value = 0
  currentStep.value = ''
  startedAt.value = ''
  elapsedSeconds.value = 0
}

const viewResult = () => {
  if (!taskId.value) return
  router.push({ path: '/tasks/unified', query: { task_id: taskId.value } })
}

// ==================== Historical results management ====================

const historyList = ref<GeneralTaskListItem[]>([])
const historyLoading = ref(false)
const historyTotal = ref(0)
const historyCurrentPage = ref(1)
const historyPageSize = ref(20)
const historyDateRange = ref<[string, string] | null>(null)

const historyFilters = ref<GeneralTaskListParams>({
  workflow_id: undefined,
  keyword: '',
  status: undefined,
})

const detailDialogVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<any>(null)
const activeReportNames = ref<string[]>([])

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const params: GeneralTaskListParams = {
      limit: historyPageSize.value,
      skip: (historyCurrentPage.value - 1) * historyPageSize.value,
    }
    if (historyFilters.value.workflow_id) {
      params.workflow_id = historyFilters.value.workflow_id
    }
    if (historyFilters.value.keyword?.trim()) {
      params.keyword = historyFilters.value.keyword.trim()
    }
    if (historyFilters.value.status) {
      params.status = historyFilters.value.status
    }
    if (historyDateRange.value && historyDateRange.value.length === 2) {
      params.date_start = historyDateRange.value[0]
      params.date_end = historyDateRange.value[1]
    }

    const res = await getGeneralTaskList(params) as any
    const data = res?.data?.data || res?.data || {}
    historyList.value = data.tasks || []
    historyTotal.value = data.total || 0
  } catch (e: any) {
    console.error('Failed to load historical results', e)
    ElMessage.error(e?.message || 'Failed to load historical results')
  } finally {
    historyLoading.value = false
  }
}

const resetHistoryFilters = () => {
  historyFilters.value = {
    workflow_id: undefined,
    keyword: '',
    status: undefined,
  }
  historyDateRange.value = null
  historyCurrentPage.value = 1
  loadHistory()
}

const showHistoryDetail = async (item: GeneralTaskListItem) => {
  detailLoading.value = true
  detailDialogVisible.value = true
  activeReportNames.value = []
  try {
    const data = await getTaskDetail(item.task_id)
    detailData.value = (data as any)?.data || data
  } catch (e: any) {
    console.error('Failed to load details', e)
    ElMessage.error(e?.message || 'Failed to load details')
  } finally {
    detailLoading.value = false
  }
}

const getWorkflowName = (workflowId: string) => {
  const wf = workflows.value.find(w => w.id === workflowId)
  return wf ? `${wf.name} v${wf.version}` : workflowId
}

const getHistoryStatusColor = (status: string) => {
  return GeneralTaskStatusColors[status as keyof typeof GeneralTaskStatusColors] || 'info'
}

const getHistoryStatusName = (status: string) => {
  return GeneralTaskStatusNames[status as keyof typeof GeneralTaskStatusNames] || status
}

const formatHistoryTime = (time: string | number) => {
  if (!time) return '—'
  const d = new Date(time)
  return d.toLocaleString('zh-CN', { hour12: false })
}

const formatDuration = (seconds: number) => {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

const formatPercent = (value: number | null | undefined) => {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}

const sortedReportManifest = computed(() => {
  if (!detailData.value?.result?.report_manifest) return []
  return [...detailData.value.result.report_manifest].sort((a: any, b: any) => {
    if (a.is_primary && !b.is_primary) return -1
    if (!a.is_primary && b.is_primary) return 1
    return (a.order || 0) - (b.order || 0)
  })
})

const getReportContent = (field: string) => {
  if (!detailData.value?.result?.[field]) return ''
  const content = detailData.value.result[field]
  if (typeof content === 'string') return content
  if (typeof content === 'object') return JSON.stringify(content, null, 2)
  return String(content)
}

const renderMarkdown = (text: string) => {
  try {
    return safeMarkdown(text)
  } catch {
    return text
  }
}

const getDecisionColor = (action: string) => {
  if (!action) return 'info'
  const a = action.toLowerCase()
  // New Compliance Terminology"Optimistic/cautious/neutral"Priority matching (semantics are research conclusion tendencies, not transaction instructions)
  if (a.includes('optimistic')) return 'success'   // Green: Positive tendencies
  if (a.includes('Prudence')) return 'warning'   // Yellow: need to be cautious
  if (a.includes('Neutral')) return 'info'      // Gray: no obvious tendency
  // old market view terminology"Bullish/Putish" + Old trading instructions"Buy/Sell" (Compatible with existing data)
  if (a.includes('buy') || a.includes('Go long') || a.includes('buy') || a.includes('bullish')) return 'success'
  if (a.includes('sell') || a.includes('short') || a.includes('sell') || a.includes('Bearish')) return 'danger'
  return 'info'
}

// ==================== life cycle ====================

onMounted(async () => {
  await Promise.all([
    loadModels(),
    loadWorkflows(),
  ])
  if (activeTab.value === 'history') {
    await loadHistory()
  }
})

onUnmounted(() => {
  stopPolling()
  stopElapsedTimer()
})
</script>

<style scoped>
.general-analysis {
  padding: 20px;
  max-width: 1600px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.header-content {
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  border-radius: 8px;
}

.title-section {
  margin-bottom: 16px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #303133;
}

.page-description {
  margin: 12px 0 0 0;
  color: #606266;
  font-size: 14px;
}

.risk-disclaimer {
  margin-top: 12px;
}

.main-tabs {
  margin-top: 0;
}

.analysis-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.main-form-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.form-section {
  margin-bottom: 12px;
}

.section-title {
  font-size: 14px;
  color: #909399;
  margin: 0 0 8px 0;
}

.workflow-description {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
  margin-top: 6px;
}

.field-group-title {
  font-size: 13px;
  color: #909399;
  margin-top: 12px;
  margin-bottom: 8px;
  padding-left: 4px;
  border-left: 3px solid #409eff;
}

.field-description {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.submit-btn {
  width: 100%;
}

.status-card {
  border-radius: 8px;
}

.status-content {
  padding: 4px 0;
}

.status-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  font-size: 13px;
  color: #909399;
  min-width: 70px;
}

.info-value {
  font-size: 13px;
  color: #303133;
}

.task-id-text {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.progress-section {
  margin-top: 16px;
}

.current-step {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}

.rotating-icon {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.result-link-section {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

/* historical results */
.history-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card,
.history-table-card {
  border-radius: 8px;
}

.pagination-wrapper {
  padding: 16px 0 4px 0;
  display: flex;
  justify-content: flex-end;
}

.detail-container {
  padding: 4px 0;
}

.detail-section {
  margin-bottom: 16px;
  border-radius: 6px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.summary-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-item {
  display: flex;
  gap: 8px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
  min-width: 70px;
}

.summary-value {
  font-size: 13px;
  color: #303133;
  flex: 1;
}

.report-collapse {
  margin-top: 4px;
}

.report-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.report-icon {
  font-size: 16px;
}

.report-name {
  font-size: 14px;
  color: #303133;
}

.report-content {
  padding: 4px 0;
}

.markdown-content {
  line-height: 1.6;
  color: #303133;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  color: #303133;
  margin: 12px 0 8px 0;
}

.markdown-content :deep(p) {
  margin: 8px 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
}

.error-section {
  border-color: #fef0f0;
}

.json-content {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  overflow-x: auto;
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
}
</style>
