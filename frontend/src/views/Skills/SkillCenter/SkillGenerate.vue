<template>
  <div class="skill-generate">
    <!-- Create task list (including ongoing/failed/completed) -->
    <el-card class="history-card session-card">
      <template #header>
        <div class="card-header">
          <span>Create task</span>
          <div class="header-right">
            <el-select v-model="sessionStatusFilter" size="small" style="width: 120px" @change="loadSessions">
              <el-option label="All" value="all" />
              <el-option label="In progress" value="in_progress" />
              <el-option label="only failed" value="failed" />
              <el-option label="only completed" value="completed" />
            </el-select>
            <el-button text size="small" @click="loadSessions">Refresh</el-button>
          </div>
        </div>
      </template>
      <el-table :data="sessions" v-if="sessions.length" size="small">
        <el-table-column label="Requirement description" min-width="200">
          <template #default="scope">
            {{ scope.row.spec?.description || scope.row.rounds?.[0]?.user_message || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Status" width="100">
          <template #default="scope">
            <el-tag :type="getSessionTagType(scope.row.status)" size="small">
              {{ getSessionStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Progress" width="120">
          <template #default="scope">
            <el-progress
              v-if="scope.row.status === 'generating'"
              :percentage="Math.round((scope.row.pipeline_progress || 0) * 100)"
              :stroke-width="14"
              :text-inside="true"
              status="warning"
            />
            <span v-else-if="scope.row.pipeline_stage">—</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="Update time" width="170">
          <template #default="scope">
            {{ formatTime(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="140">
          <template #default="scope">
            <el-button
              v-if="scope.row.status === 'failed'"
              size="small"
              type="warning"
              @click="resumeSession(scope.row.session_id)"
            >Repair</el-button>
            <el-button
              v-if="scope.row.status === 'gathering' || scope.row.status === 'confirmed'"
              size="small"
              type="primary"
              @click="resumeSession(scope.row.session_id)"
            >continue</el-button>
            <el-button
              v-if="scope.row.status === 'generating'"
              size="small"
              disabled
            >Generating</el-button>
            <el-button
              v-if="scope.row.status === 'completed'"
              size="small"
              @click="viewSessionSkill(scope.row)"
            >View</el-button>
            <el-button
              size="small"
              text
              type="danger"
              @click="deleteSession(scope.row.session_id)"
            >Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-hint">
        <el-empty description="No tasks created yet" :image-size="60" />
      </div>
    </el-card>

    <!-- Completed Skill List -->
    <el-card class="history-card">
      <template #header>
        <span>AI generated Skill</span>
      </template>
      <el-table :data="recentSkills" v-if="recentSkills.length">
        <el-table-column prop="display_name" label="Name" />
        <el-table-column prop="status" label="Status">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.status)">
              {{ getStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="Generation time" width="170" />
        <el-table-column label="Operation" width="300">
          <template #default="scope">
            <div class="row-actions">
              <el-button size="small" type="primary" @click="openTestDialog(scope.row)">test</el-button>
              <el-button size="small" @click="openEditDialog(scope.row)">Editorial Notes</el-button>
              <el-button size="small" @click="viewSkill(scope.row)">View</el-button>
              <el-button size="small" @click="iterateSkill(scope.row)">iterative optimization</el-button>
              <el-button size="small" text type="danger" @click="deleteSkill(scope.row)">Delete</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-hint">
        <el-empty description="No generation record yet" />
      </div>
    </el-card>

    <el-dialog
      v-model="detailVisible"
      :title="`Skill Details:${detailSkill?.display_name || ''}`"
      width="900px"
      destroy-on-close
      class="skill-detail-dialog"
    >
      <div v-if="detailSkill" class="skill-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Name">{{ detailSkill.display_name }}</el-descriptions-item>
          <el-descriptions-item label="Tool ID">{{ detailSkill.tool_id }}</el-descriptions-item>
          <el-descriptions-item label="Status">
            <el-tag :type="getStatusTagType(detailSkill.status)" size="small">
              {{ getStatusLabel(detailSkill.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Classification">{{ detailSkill.category || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Description" :span="2">{{ detailSkill.description || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Generate rounds">{{ detailSkill.generation_rounds || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Time consuming to generate">
            {{ detailSkill.generation_time ? detailSkill.generation_time + 's' : '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="detailSkill.parameters?.length" class="detail-section">
          <div class="section-title">Parameter list</div>
          <el-table :data="detailSkill.parameters" size="small" border>
            <el-table-column prop="name" label="Parameter name" width="140" />
            <el-table-column prop="type" label="Type" width="100" />
            <el-table-column prop="description" label="Description" />
            <el-table-column prop="required" label="Required" width="60">
              <template #default="scope">
                {{ scope.row.required ? 'Yes' : 'No' }}
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="detail-section">
          <div class="section-title">source code</div>
          <div v-loading="codeLoading" class="code-container">
            <pre v-if="skillCode"><code>{{ skillCode }}</code></pre>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">close</el-button>
        <el-button type="primary" @click="detailSkill && openTestDialog(detailSkill)">test</el-button>
        <el-button @click="detailSkill && openEditDialog(detailSkill)">Editorial Notes</el-button>
        <el-button type="primary" plain @click="iterateSkill(detailSkill)">iterative optimization</el-button>
      </template>
    </el-dialog>

    <!-- Online test dialog -->
    <el-dialog
      v-model="testVisible"
      :title="`Test Skills:${testSkill?.display_name || ''}`"
      width="760px"
      destroy-on-close
      class="skill-test-dialog"
    >
      <div v-if="testSkill" class="test-dialog-body">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="Really run the Skill in the sandbox, modify the parameters directly and test repeatedly."
          style="margin-bottom: 12px;"
        />
        <el-form label-position="top" size="small" class="test-form">
          <el-form-item
            v-for="param in testParamDefs"
            :key="param.name"
            :label="`${param.name}${param.required ? ' *' : ''}（${param.type || 'string'}）${param.description ? ' — ' + param.description : ''}`"
          >
            <el-switch
              v-if="param.type === 'boolean'"
              v-model="testArgs[param.name]"
            />
            <el-input-number
              v-else-if="param.type === 'integer' || param.type === 'float'"
              v-model="testArgs[param.name]"
              :controls="false"
              style="width: 100%"
              :placeholder="param.default !== undefined && param.default !== null ? String(param.default) : 'If not filled in, the function default value will be used.'"
            />
            <el-input
              v-else
              v-model="testArgs[param.name]"
              :placeholder="param.default !== undefined && param.default !== null ? String(param.default) : 'If not filled in, the function default value will be used.'"
            />
          </el-form-item>
          <el-form-item v-if="!testParamDefs.length" label="parameters">
            <span class="form-hint">This Skill has no parameters defined and can be run directly.</span>
          </el-form-item>
        </el-form>

        <div v-if="testResult" class="test-result">
          <el-alert
            :type="testResult.success ? 'success' : 'error'"
            :closable="false"
            show-icon
            :title="testResult.success
              ? `Execution successful (time consuming) ${(testResult.execution_time || 0).toFixed(2)}s) `
              : `Execution failed (time consuming ${(testResult.execution_time || 0).toFixed(2)}s) `"
            :description="testResult.error || ''"
            style="margin-bottom: 8px;"
          />
          <div class="result-section-title">Execution output</div>
          <pre class="result-json">{{ formatJson(testResult.output) }}</pre>
          <el-collapse v-if="testResult.stderr" class="stderr-collapse">
            <el-collapse-item title="Error log (stderr)" name="stderr">
              <pre class="result-stderr">{{ testResult.stderr }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
      <template #footer>
        <el-button
          v-if="testSkill?.test_input && Object.keys(testSkill.test_input).length"
          @click="fillExampleArgs"
        >Fill in the sample parameters</el-button>
        <el-button @click="testVisible = false">close</el-button>
        <el-button type="primary" :loading="testLoading" @click="runTest">Run tests</el-button>
      </template>
    </el-dialog>

    <!-- Edit Description Dialog -->
    <el-dialog
      v-model="editVisible"
      title="Edit skill description"
      width="560px"
      destroy-on-close
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="What is modified here is the display name and function description; if the parameters, code and interface contract need to be changed, please use Iterative Optimization to generate a new version."
        style="margin-bottom: 14px;"
      />
      <el-form label-position="top">
        <el-form-item label="Name" required>
          <el-input v-model="editForm.display_name" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="Function description">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            placeholder="Describe the purpose, input and return content of this Skill"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { skillGenerationApi } from '@/api/skillGeneration'

const router = useRouter()
const recentSkills = ref<any[]>([])
const sessions = ref<any[]>([])
const sessionStatusFilter = ref('in_progress')
const detailVisible = ref(false)
const detailSkill = ref<any>(null)
const skillCode = ref('')
const codeLoading = ref(false)

// Online test
const testVisible = ref(false)
const testLoading = ref(false)
const testSkill = ref<any>(null)
const testArgs = ref<Record<string, any>>({})
const testResult = ref<any>(null)

// Editorial Notes
const editVisible = ref(false)
const editSaving = ref(false)
const editForm = ref<{ tool_id: string; display_name: string; description: string }>({
  tool_id: '',
  display_name: '',
  description: '',
})

// The test form only displays the parameters defined by the Skill
const testParamDefs = computed(() => {
  const params = testSkill.value?.parameters
  return Array.isArray(params) ? params : []
})

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: 'Enabled',
    disabled: 'Disabled',
    draft: 'draft',
    testing: 'Under test',
    archived: 'Archived',
    failed: 'failed'
  }
  return labels[status] || status
}

type ElTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

function getStatusTagType(status: string): ElTagType {
  const types: Record<string, ElTagType> = {
    active: 'success',
    disabled: 'warning',
    draft: 'info',
    testing: 'primary',
    archived: 'info',
    failed: 'danger'
  }
  return types[status] || 'info'
}

function getSessionStatusLabel(status: string) {
  const labels: Record<string, string> = {
    gathering: 'Requirements are being communicated',
    confirmed: 'Specifications confirmed',
    generating: 'Generating',
    completed: 'Completed',
    failed: 'failed'
  }
  return labels[status] || status
}

function getSessionTagType(status: string): ElTagType {
  const types: Record<string, ElTagType> = {
    gathering: 'primary',
    confirmed: 'info',
    generating: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return types[status] || 'info'
}

function formatTime(t: string) {
  if (!t) return '-'
  return t.replace('T', ' ').slice(0, 19)
}

async function viewSkill(skill: any) {
  detailSkill.value = skill
  detailVisible.value = true
  skillCode.value = ''
  try {
    codeLoading.value = true
    const result = await skillGenerationApi.getSkillCode(skill.tool_id)
    skillCode.value = result.code || ''
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Failed to load code')
  } finally {
    codeLoading.value = false
  }
}

function viewSessionSkill(session: any) {
  const toolId = session.pipeline_result?.tool_id
  if (toolId) {
    const skill = recentSkills.value.find(s => s.tool_id === toolId)
    if (skill) {
      viewSkill(skill)
      return
    }
  }
  router.push('/skills/generation/create?sessionId=' + session.session_id)
}

function resumeSession(sessionId: string) {
  router.push('/skills/generation/create?sessionId=' + sessionId)
}

function iterateSkill(skill: any) {
  // Jump to the Skill generation page and bring the existing Skill information for iterative optimization
  const params = new URLSearchParams()
  params.set('toolId', skill.tool_id)
  params.set('displayName', skill.display_name || '')
  params.set('description', skill.description || '')
  params.set('category', skill.category || '')
  params.set('mode', 'iterate')
  detailVisible.value = false
  router.push('/skills/generation/create?' + params.toString())
}

async function deleteSession(sessionId: string) {
  try {
    await ElMessageBox.confirm('Confirm to delete this creation task?', 'Tips', { type: 'warning' })
    await skillGenerationApi.deleteSession(sessionId)
    ElMessage.success('Deleted')
    await loadSessions()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || 'Delete failed')
    }
  }
}

async function deleteSkill(skill: any) {
  try {
    await ElMessageBox.confirm(`Confirm deletion of Skill ${skill.display_name}] ? It cannot be restored after deletion.`, 'Tips', { type: 'warning' })
    await skillGenerationApi.deleteSkill(skill.tool_id)
    ElMessage.success('Deleted')
    await loadRecentSkills()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || 'Delete failed')
    }
  }
}

// ==================== Online test ====================

function buildInitialTestArgs(skill: any): Record<string, any> {
  const args: Record<string, any> = {}
  const example = skill.test_input || {}
  for (const param of skill.parameters || []) {
    const name = param.name
    const exampleVal = example[name]
    if (exampleVal !== undefined && exampleVal !== null && exampleVal !== '') {
      args[name] = exampleVal
    } else if (param.default !== undefined && param.default !== null) {
      args[name] = param.default
    } else if (param.type === 'boolean') {
      args[name] = false
    } else {
      // The key is first left blank, and the input box displays placeholder (if not filled in, the function default value is used)
      args[name] = undefined
    }
  }
  return args
}

function openTestDialog(skill: any) {
  testSkill.value = skill
  testArgs.value = buildInitialTestArgs(skill)
  testResult.value = null
  detailVisible.value = false
  testVisible.value = true
}

function fillExampleArgs() {
  if (testSkill.value) {
    testArgs.value = buildInitialTestArgs(testSkill.value)
  }
}

async function runTest() {
  if (!testSkill.value) return
  // Only submit filled-in parameters; 0/false is a legal input parameter and must be retained
  const args: Record<string, any> = {}
  for (const [key, value] of Object.entries(testArgs.value)) {
    if (value !== null && value !== undefined && value !== '') {
      args[key] = value
    }
  }
  testLoading.value = true
  testResult.value = null
  try {
    testResult.value = await skillGenerationApi.testSkill(testSkill.value.tool_id, args)
  } catch (error: any) {
    testResult.value = {
      success: false,
      output: null,
      stderr: '',
      execution_time: 0,
      error: error?.response?.data?.detail || error?.message || 'Test request failed',
    }
  } finally {
    testLoading.value = false
  }
}

function formatJson(value: any): string {
  if (value === null || value === undefined) return ' (no output)'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

// ==================== Editorial Notes ====================

function openEditDialog(skill: any) {
  editForm.value = {
    tool_id: skill.tool_id,
    display_name: skill.display_name || '',
    description: skill.description || '',
  }
  detailVisible.value = false
  editVisible.value = true
}

async function saveEdit() {
  const displayName = editForm.value.display_name.trim()
  if (!displayName) {
    ElMessage.warning('Name cannot be empty')
    return
  }
  editSaving.value = true
  try {
    await skillGenerationApi.updateSkillInfo(
      editForm.value.tool_id,
      displayName,
      editForm.value.description.trim(),
    )
    ElMessage.success('Description updated')
    editVisible.value = false
    // Synchronize local list and detail cache to avoid displaying old names before re-pulling
    const target = recentSkills.value.find(s => s.tool_id === editForm.value.tool_id)
    if (target) {
      target.display_name = displayName
      target.description = editForm.value.description.trim()
    }
    if (detailSkill.value?.tool_id === editForm.value.tool_id) {
      detailSkill.value.display_name = displayName
      detailSkill.value.description = editForm.value.description.trim()
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Save failed')
  } finally {
    editSaving.value = false
  }
}

async function loadRecentSkills() {
  try {
    const result = await skillGenerationApi.listSkills({ page: 1, page_size: 10 })
    recentSkills.value = result.items || []
  } catch (error) {
    console.error('Load recent skills failed:', error)
  }
}

async function loadSessions() {
  try {
    const result = await skillGenerationApi.listSessions({ page: 1, page_size: 20 })
    let items = result.items || []
    const filter = sessionStatusFilter.value
    if (filter === 'in_progress') {
      items = items.filter(s => ['gathering', 'confirmed', 'generating'].includes(s.status))
    } else if (filter === 'failed') {
      items = items.filter(s => s.status === 'failed')
    } else if (filter === 'completed') {
      items = items.filter(s => s.status === 'completed')
    }
    sessions.value = items
  } catch (error) {
    console.error('Load sessions failed:', error)
  }
}

onMounted(() => {
  loadRecentSkills()
  loadSessions()
})
</script>

<style scoped>
.skill-generate {
  padding: 20px;
}

.history-card {
  max-width: 800px;
  margin-bottom: 16px;
}

.session-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .header-right {
    display: flex;
    gap: 8px;
    align-items: center;
  }
}

.empty-hint {
  padding: 40px;
  text-align: center;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  align-items: center;
}

.form-hint {
  color: #909399;
  font-size: 13px;
}

.test-dialog-body {
  .test-result {
    margin-top: 14px;
  }

  .result-section-title {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    margin: 8px 0 6px;
  }

  .result-json,
  .result-stderr {
    margin: 0;
    padding: 10px;
    background: #f5f7fa;
    border-radius: 4px;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #303133;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 320px;
    overflow: auto;
  }

  .result-stderr {
    background: #fef0f0;
    color: #f56c6c;
  }

  .stderr-collapse {
    margin-top: 8px;
  }
}

.skill-detail {
  .detail-section {
    margin-top: 16px;

    .section-title {
      font-size: 14px;
      font-weight: 600;
      color: #303133;
      margin-bottom: 8px;
    }
  }

  .code-container {
    max-height: 400px;
    overflow: auto;
    background: #f5f7fa;
    border-radius: 4px;
    padding: 12px;

    pre {
      margin: 0;
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 12px;
      line-height: 1.6;
      color: #303133;
      white-space: pre-wrap;
      word-break: break-all;
    }
  }
}
</style>
