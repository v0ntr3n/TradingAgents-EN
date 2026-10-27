<template>
  <div class="embedded-nanobot-page">
    <div class="page-header">
      <div>
        <h1>Embedded Nanobot Debug page</h1>
        <p>This page directly calls the nanobot runtime embedded in the project to verify the database model configuration, session keys, tool calls and returned content.</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadStatus" :loading="loadingStatus">refresh status</el-button>
        <el-button @click="clearMessages" plain>Clear local records</el-button>
      </div>
    </div>

    <div class="page-grid">
      <el-card class="config-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>Run configuration</span>
          </div>
        </template>

        <div class="status-block">
          <el-tag :type="statusInfo?.enabled ? 'success' : 'danger'">{{ statusInfo?.enabled ? 'Enabled' : 'Not available' }}</el-tag>
          <div class="status-line" v-if="statusInfo?.user_id">User:{{ statusInfo.user_id }}</div>
          <div class="status-line" v-if="statusInfo?.workspace">Workspace:{{ statusInfo.workspace }}</div>
        </div>

        <el-form label-position="top">
          <el-form-item label="session key">
            <div class="session-key-row">
              <el-input v-model="form.sessionKey" placeholder="For example:embedded:user:debug" />
              <el-button plain :disabled="streaming || sending" @click="createNewSession">New session</el-button>
            </div>
          </el-form-item>
          <el-form-item label="Model name">
            <el-input v-model="form.model" placeholder="Leave blank to use database default configuration" />
          </el-form-item>
          <el-form-item label="channel">
            <el-input v-model="form.channel" placeholder="api" />
          </el-form-item>
          <el-form-item label="Chat ID">
            <el-input v-model="form.chatId" placeholder="Leave blank to inherit the session key" />
          </el-form-item>
          <el-form-item label="Skill list">
            <el-input
              v-model="form.skillNamesText"
              type="textarea"
              :rows="3"
              resize="none"
              placeholder="One skill name per line; if left blank, it will not be explicitly enabled. skill"
            />
          </el-form-item>
        </el-form>

        <div class="history-block">
          <div class="card-header">
            <span>database session</span>
            <el-button size="small" text @click="loadThreads" :loading="loadingThreads">Refresh</el-button>
          </div>
          <div class="thread-filter-grid">
            <el-select v-model="selectedThreadScope" size="small" placeholder="active session" @change="loadThreads">
              <el-option label="active session" value="active" />
              <el-option label="Archived conversation" value="archived" />
            </el-select>
            <el-input v-model="threadSearchText" size="small" clearable placeholder="Search titles, abstracts, recent issues" />
            <el-select v-model="selectedThreadAgentFilter" size="small" placeholder="All Agent">
              <el-option label="All Agent" value="all" />
              <el-option
                v-for="option in nanobotThreadAgentOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select v-model="selectedThreadTimeFilter" size="small" placeholder="all time">
              <el-option label="all time" value="all" />
              <el-option label="last 24 hours" value="24h" />
              <el-option label="last 7 days" value="7d" />
              <el-option label="Last 30 days" value="30d" />
            </el-select>
          </div>
          <el-empty v-if="!loadingThreads && !threadItems.length" :description="selectedThreadScope === 'archived' ? 'No archived conversations yet' : 'No database session yet'" :image-size="56" />
          <div v-else class="thread-list">
            <div v-if="loadingThreads" class="status-line">Loading database session...</div>
            <div v-else-if="!filteredThreadItems.length" class="status-line">{{ selectedThreadScope === 'archived' ? 'There are no archived conversations matching the filter criteria' : 'No sessions matching filter criteria' }}</div>
            <div
              v-for="thread in filteredThreadItems"
              :key="thread.thread_id"
              :class="['thread-item', { active: selectedThreadId === thread.thread_id }]"
            >
              <button
                type="button"
                class="thread-main"
                @click="loadThreadMessages(thread.thread_id)"
              >
                <div class="thread-title-row">
                  <strong>{{ thread.title || 'Nanobot session' }}</strong>
                  <el-tag size="small" effect="plain">{{ thread.message_count }}</el-tag>
                </div>
                <div class="thread-desc">{{ thread.last_user_message || thread.summary || 'No abstract yet' }}</div>
                <div class="thread-meta-row">
                  <div class="thread-meta">{{ formatThreadMeta(thread) }}</div>
                  <div class="thread-meta-badges">
                    <el-tag v-if="thread.archived" size="small" type="info" effect="plain">Archived</el-tag>
                    <div v-if="thread.thread_context?.spec_name" class="thread-agent">{{ thread.thread_context.spec_name }}</div>
                  </div>
                </div>
              </button>
              <el-button
                v-if="thread.archived"
                type="primary"
                link
                class="thread-delete-btn"
                @click.stop="handleRestoreThread(thread)"
              >restore</el-button>
              <el-button
                v-else
                type="danger"
                link
                class="thread-delete-btn"
                @click.stop="handleDeleteThread(thread)"
              >Archive</el-button>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="chat-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>Dialog debugging</span>
            <div class="header-tags">
              <el-tag v-if="streaming" type="success" effect="plain">Executing</el-tag>
              <el-tag v-if="lastUsageText" type="info" effect="plain">{{ lastUsageText }}</el-tag>
            </div>
          </div>
        </template>

        <div class="message-list" v-if="messages.length">
          <div
            v-for="(item, index) in messages"
            :key="`${item.role}-${index}`"
            :class="['message-item', item.role]"
          >
            <div class="message-role">{{ item.role === 'user' ? 'you' : 'Nanobot' }}</div>
            <div class="message-content">{{ item.content }}</div>
            <div class="message-meta" v-if="item.toolsUsed?.length || item.stopReason">
              <span v-if="item.stopReason">Ending reason:{{ item.stopReason }}</span>
              <span v-if="item.toolsUsed?.length">Tools:{{ item.toolsUsed.join(', ') }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="No message sent yet" :image-size="80" />

        <div v-if="currentProgressHint" class="streaming-hint">{{ currentProgressHint }}</div>

        <div class="composer">
          <el-input
            v-model="draftMessage"
            type="textarea"
            :rows="4"
            resize="vertical"
            placeholder="For example: List the top-level directories of the current workspace and describe how you plan to explore the project."
            @keydown.enter.ctrl.prevent="handleSend"
          />
          <div class="composer-actions">
            <div class="composer-hint">Ctrl + Enter send</div>
            <el-button type="primary" :loading="sending" :disabled="!draftMessage.trim()" @click="handleSend">send</el-button>
          </div>
        </div>
      </el-card>
    </div>

    <div class="result-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>real-time execution trace</span>
          </div>
        </template>
        <el-empty v-if="!traceEvents.length" description="No execution track yet" :image-size="60" />
        <div v-else class="trace-list">
          <div v-for="(item, index) in traceEvents" :key="`${item.kind}-${index}`" class="trace-item">
            <div class="trace-kind">{{ item.kind }}</div>
            <div class="trace-message">{{ item.message }}</div>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>Last tool event</span>
          </div>
        </template>
        <el-empty v-if="!lastToolEventsText" description="No tool events yet" :image-size="60" />
        <pre v-else class="json-block">{{ lastToolEventsText }}</pre>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>most recent usage</span>
          </div>
        </template>
        <el-empty v-if="!lastUsageJson" description="None yet usage" :image-size="60" />
        <pre v-else class="json-block">{{ lastUsageJson }}</pre>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import embeddedNanobotApi, {
  type EmbeddedNanobotChatResponse,
  type EmbeddedNanobotMessageItem,
  type EmbeddedNanobotStreamCallbacks,
  type EmbeddedNanobotStatusResponse,
  type EmbeddedNanobotThreadItem,
} from '@/api/embeddedNanobot'

type DebugMessage = {
  role: 'user' | 'assistant'
  content: string
  toolsUsed?: string[]
  stopReason?: string
}

type TraceItem = {
  kind: string
  message: string
}

const TOOL_STATUS_LABELS: Record<string, string> = {
  started: 'start',
  ok: 'Complete',
  completed: 'Complete',
  error: 'failed',
}

const loadingStatus = ref(false)
const sending = ref(false)
const streaming = ref(false)
const statusInfo = ref<EmbeddedNanobotStatusResponse | null>(null)
const messages = ref<DebugMessage[]>([])
const lastResponse = ref<EmbeddedNanobotChatResponse | null>(null)
const draftMessage = ref('')
const currentProgressHint = ref('')
const traceEvents = ref<TraceItem[]>([])
const threadItems = ref<EmbeddedNanobotThreadItem[]>([])
const loadingThreads = ref(false)
const selectedThreadId = ref('')
const selectedThreadScope = ref('active')
const threadSearchText = ref('')
const selectedThreadAgentFilter = ref('all')
const selectedThreadTimeFilter = ref('all')
let activeStreamController: AbortController | null = null

const form = ref({
  sessionKey: 'embedded:user:debug',
  model: '',
  channel: 'api',
  chatId: '',
  skillNamesText: '',
})

const sanitizeSessionSegment = (value?: string) => {
  return String(value || 'debug')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'debug'
}

const generateSessionKey = () => {
  const userSegment = sanitizeSessionSegment(statusInfo.value?.user_id)
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)
  const randomSuffix = Math.random().toString(36).slice(2, 8)
  return `embedded:user:${userSegment}:${timestamp}:${randomSuffix}`
}

const parseSkillNames = () => {
  return form.value.skillNamesText
    .split(/\r?\n/)
    .map(item => item.trim())
    .filter(Boolean)
}

const stringifyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value || '')
  }
}

const lastToolEventsText = computed(() => {
  const toolEvents = lastResponse.value?.tool_events
  if (!toolEvents?.length) return ''
  return stringifyJson(toolEvents)
})

const lastUsageJson = computed(() => {
  const usage = lastResponse.value?.usage
  if (!usage || !Object.keys(usage).length) return ''
  return stringifyJson(usage)
})

const lastUsageText = computed(() => {
  const usage = lastResponse.value?.usage || {}
  const parts = [
    typeof usage.prompt_tokens === 'number' ? `prompt ${usage.prompt_tokens}` : '',
    typeof usage.completion_tokens === 'number' ? `completion ${usage.completion_tokens}` : '',
    typeof usage.total_tokens === 'number' ? `total ${usage.total_tokens}` : '',
  ].filter(Boolean)
  return parts.join(' | ')
})

const nanobotThreadAgentOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const item of threadItems.value) {
    const specId = String(item.thread_context?.spec_id || '').trim()
    const specName = String(item.thread_context?.spec_name || '').trim()
    if (!specId || seen.has(specId)) continue
    seen.set(specId, specName || specId)
  }
  return Array.from(seen.entries()).map(([value, label]) => ({ value, label }))
})

const filteredThreadItems = computed(() => {
  const keyword = String(threadSearchText.value || '').trim().toLowerCase()
  const now = Date.now()
  const windowMap: Record<string, number> = {
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
  }
  return threadItems.value.filter(item => {
    if (selectedThreadAgentFilter.value !== 'all') {
      if (String(item.thread_context?.spec_id || '').trim() !== selectedThreadAgentFilter.value) {
        return false
      }
    }

    if (selectedThreadTimeFilter.value !== 'all') {
      const timestamp = Date.parse(String(item.updated_at || item.created_at || ''))
      const range = windowMap[selectedThreadTimeFilter.value]
      if (!Number.isFinite(timestamp) || !range || now - timestamp > range) {
        return false
      }
    }

    if (!keyword) return true
    const haystack = [
      item.title,
      item.last_user_message,
      item.summary,
      item.thread_context?.spec_name,
    ].join(' ').toLowerCase()
    return haystack.includes(keyword)
  })
})

const mapThreadMessages = (items: EmbeddedNanobotMessageItem[]): DebugMessage[] => {
  return items.map(item => ({
    role: item.role === 'user' ? 'user' : 'assistant',
    content: String(item.content || ''),
    toolsUsed: item.tools_used || [],
    stopReason: item.stop_reason,
  }))
}

const loadStatus = async () => {
  loadingStatus.value = true
  try {
    statusInfo.value = await embeddedNanobotApi.getStatus()
  } catch (error: any) {
    ElMessage.error(error?.message || 'Failed to read embedded nanobot status')
  } finally {
    loadingStatus.value = false
  }
}

const loadThreads = async () => {
  loadingThreads.value = true
  try {
    const result = await embeddedNanobotApi.listThreads(20, selectedThreadScope.value === 'archived')
    threadItems.value = result.items || []
  } catch (error: any) {
    threadItems.value = []
    ElMessage.error(error?.message || 'Failed to read database session')
  } finally {
    loadingThreads.value = false
  }
}

const formatThreadMeta = (thread: EmbeddedNanobotThreadItem) => {
  const raw = String(thread.updated_at || thread.created_at || '').trim()
  if (!raw) return 'unknown time'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString('zh-CN', { hour12: false })
}

const loadThreadMessages = async (threadId: string, silent = false) => {
  try {
    const result = await embeddedNanobotApi.getThreadMessages(threadId)
    selectedThreadId.value = threadId
    form.value.sessionKey = result.thread?.session_key || threadId
    form.value.chatId = result.thread?.thread_id || threadId
    messages.value = mapThreadMessages(result.messages || [])
    const assistantMessages = (result.messages || []).filter(item => item.role === 'assistant')
    const latestAssistant = assistantMessages[assistantMessages.length - 1]
    lastResponse.value = latestAssistant ? {
      content: latestAssistant.content,
      session_key: result.thread?.session_key || threadId,
      thread_id: result.thread?.thread_id || threadId,
      stop_reason: latestAssistant.stop_reason,
      tools_used: latestAssistant.tools_used || [],
      usage: latestAssistant.usage || {},
      tool_events: latestAssistant.tool_events || [],
    } : null
    currentProgressHint.value = ''
  } catch (error: any) {
    if (!silent) {
      ElMessage.error(error?.message || 'Failed to load session messages')
    }
  }
}

const handleDeleteThread = async (thread: EmbeddedNanobotThreadItem) => {
  try {
    await ElMessageBox.confirm(`Archive conversation${thread.title || thread.thread_id}] Afterwards, it will be hidden from the active list, but historical messages will still remain. Continue?`, 'Archive session', {
      type: 'warning',
      confirmButtonText: 'Archive',
      cancelButtonText: 'Cancel',
      confirmButtonClass: 'el-button--danger',
    })
    await embeddedNanobotApi.deleteThread(thread.thread_id)
    if (selectedThreadId.value === thread.thread_id) {
      selectedThreadId.value = ''
      form.value.sessionKey = generateSessionKey()
      form.value.chatId = ''
      clearMessages()
    }
    await loadThreads()
    ElMessage.success('Conversation archived')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close' || error?.action === 'cancel' || error?.action === 'close') return
    ElMessage.error(error?.message || 'Archive session failed')
  }
}

const handleRestoreThread = async (thread: EmbeddedNanobotThreadItem) => {
  try {
    await embeddedNanobotApi.restoreThread(thread.thread_id)
    await loadThreads()
    ElMessage.success('Session restored to active list')
  } catch (error: any) {
    ElMessage.error(error?.message || 'Failed to restore session')
  }
}

const clearMessages = () => {
  messages.value = []
  lastResponse.value = null
  currentProgressHint.value = ''
  traceEvents.value = []
}

const createNewSession = () => {
  if (streaming.value || sending.value) return
  form.value.sessionKey = generateSessionKey()
  form.value.chatId = ''
  selectedThreadId.value = ''
  clearMessages()
  ElMessage.success('Switched to new debugging session')
}

const pushTrace = (kind: string, message: string) => {
  if (!message) return
  traceEvents.value.push({ kind, message })
}

const handleSend = async () => {
  if (sending.value || streaming.value) return
  const message = draftMessage.value.trim()
  if (!message) return

  sending.value = true
  streaming.value = true
  currentProgressHint.value = 'Sending request'
  messages.value.push({ role: 'user', content: message })
  messages.value.push({ role: 'assistant', content: '' })
  const assistantIndex = messages.value.length - 1
  try {
    traceEvents.value = []
    const payload = {
      message,
      session_key: form.value.sessionKey.trim() || undefined,
      model: form.value.model.trim() || undefined,
      channel: form.value.channel.trim() || 'api',
      chat_id: form.value.chatId.trim() || undefined,
      skill_names: parseSkillNames(),
    }
    await new Promise<void>((resolve, reject) => {
      const callbacks: EmbeddedNanobotStreamCallbacks = {
        onStarted(data) {
          currentProgressHint.value = data.message || 'Nanobot Processing of request has started'
          pushTrace('started', currentProgressHint.value)
        },
        onProgress(data) {
          const msg = data.message || 'Executing'
          currentProgressHint.value = msg
          pushTrace('progress', msg)
        },
        onToken(content) {
          messages.value[assistantIndex].content += content
        },
        onToolEvent(event) {
          const toolName = event.name || 'unknown'
          const status = event.status || 'ok'
          const detail = event.detail ? `：${event.detail}` : ''
          const statusLabel = TOOL_STATUS_LABELS[status] || status
          currentProgressHint.value = status === 'started'
            ? `Executing tool ${toolName}`
            : `Tools ${toolName}${statusLabel === 'Complete' ? ' Completed' : ` ${statusLabel}`}`
          pushTrace('tool', `${toolName}（${statusLabel}）${detail}`)
        },
        onStepEvent(event) {
          const stepTitle = event.title || event.step || 'steps'
          const status = event.status || 'started'
          const detail = event.detail ? `：${event.detail}` : ''
          const statusLabel = TOOL_STATUS_LABELS[status] || (status === 'completed' ? 'Complete' : status)
          currentProgressHint.value = status === 'started'
            ? (event.detail || `Executing ${stepTitle}`)
            : (event.detail || `${stepTitle} Completed`)
          pushTrace('step', `${stepTitle}（${statusLabel}）${detail}`)
        },
        onDone(data) {
          lastResponse.value = data
          messages.value[assistantIndex].content = data.content || messages.value[assistantIndex].content
          messages.value[assistantIndex].toolsUsed = data.tools_used || []
          messages.value[assistantIndex].stopReason = data.stop_reason
          currentProgressHint.value = 'This round of replies has been returned; if the background log is still being updated, it is usually due to finishing actions such as session archiving.'
          pushTrace('done', 'Nanobot This round of reply has been completed; there may still be non-blocking closing logs in the background.')
          resolve()
        },
        onError(messageText) {
          messages.value[assistantIndex].content = `Request failed:${messageText || 'unknown error'}`
          currentProgressHint.value = ''
          reject(new Error(messageText || 'unknown error'))
        },
      }
      activeStreamController?.abort()
      activeStreamController = embeddedNanobotApi.chatStream(payload, callbacks)
    })
    draftMessage.value = ''
    await loadThreads()
    if (lastResponse.value?.thread_id) {
      await loadThreadMessages(lastResponse.value.thread_id, true)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || 'Embedded Nanobot Request failed')
  } finally {
    activeStreamController = null
    streaming.value = false
    sending.value = false
  }
}

onMounted(() => {
  loadStatus()
  loadThreads()
})
</script>

<style scoped lang="scss">
.embedded-nanobot-page {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;

  .page-header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;

    h1 {
      margin: 0 0 8px;
      font-size: 28px;
    }

    p {
      margin: 0;
      color: var(--el-text-color-secondary);
      max-width: 760px;
      line-height: 1.6;
    }
  }

  .header-actions {
    display: flex;
    gap: 12px;
  }

  .page-grid,
  .result-grid {
    display: grid;
    grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
    gap: 20px;
  }

  .result-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .header-tags {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-block {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .history-block {
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--el-border-color-lighter);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .thread-filter-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }

  .status-line {
    color: var(--el-text-color-secondary);
    word-break: break-all;
  }

  .thread-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: 320px;
    overflow: auto;
  }

  .thread-item {
    border: 1px solid var(--el-border-color-light);
    border-radius: 12px;
    background: #fff;
    display: flex;
    gap: 8px;
    align-items: stretch;

    &.active {
      border-color: #9fd5c8;
      background: linear-gradient(135deg, #f0fdf9 0%, #ffffff 100%);
    }
  }

  .thread-main {
    flex: 1;
    border: 0;
    background: transparent;
    padding: 12px;
    text-align: left;
    cursor: pointer;
  }

  .thread-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    color: var(--el-text-color-primary);
  }

  .thread-desc {
    margin-top: 8px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--el-text-color-secondary);
  }

  .thread-meta {
    font-size: 11px;
    color: #94a3b8;
  }

  .thread-meta-row {
    margin-top: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .thread-meta-badges {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .thread-agent {
    font-size: 11px;
    line-height: 1.4;
    color: #0f766e;
    background: #ecfeff;
    border: 1px solid #a5f3fc;
    border-radius: 999px;
    padding: 2px 8px;
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .thread-delete-btn {
    align-self: center;
    padding-right: 12px;
  }

  .session-key-row {
    display: flex;
    gap: 12px;
    align-items: center;

    :deep(.el-input) {
      flex: 1;
    }
  }

  .chat-card {
    min-height: 560px;

    :deep(.el-card__body) {
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-height: 500px;
    }
  }

  .message-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 520px;
    overflow: auto;
    padding-right: 4px;
  }

  .message-item {
    border-radius: 16px;
    padding: 14px 16px;
    border: 1px solid var(--el-border-color-light);
    background: #fff;

    &.user {
      background: linear-gradient(135deg, #eef7ff 0%, #f7fbff 100%);
      border-color: #cfe4ff;
    }

    &.assistant {
      background: linear-gradient(135deg, #fffaf0 0%, #fff 100%);
      border-color: #f2dfb1;
    }
  }

  .message-role {
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-secondary);
    margin-bottom: 8px;
  }

  .message-content {
    white-space: pre-wrap;
    line-height: 1.7;
    word-break: break-word;
  }

  .message-meta {
    margin-top: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .composer {
    border-top: 1px solid var(--el-border-color-lighter);
    padding-top: 12px;
  }

  .streaming-hint {
    margin-top: 4px;
    padding: 10px 12px;
    border-radius: 12px;
    background: #f0f9ff;
    color: #075985;
    font-size: 13px;
  }

  .composer-actions {
    margin-top: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .composer-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .json-block {
    margin: 0;
    padding: 14px;
    border-radius: 12px;
    background: #0f172a;
    color: #dbeafe;
    overflow: auto;
    max-height: 420px;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 12px;
    line-height: 1.6;
  }

  .trace-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: 420px;
    overflow: auto;
  }

  .trace-item {
    border: 1px solid var(--el-border-color-light);
    border-radius: 12px;
    padding: 12px 14px;
    background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
  }

  .trace-kind {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 6px;
  }

  .trace-message {
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-text-color-primary);
    white-space: pre-wrap;
    word-break: break-word;
  }

  @media (max-width: 1100px) {
    .page-grid,
    .result-grid {
      grid-template-columns: 1fr;
    }

    .page-header {
      flex-direction: column;
    }

    .session-key-row {
      flex-direction: column;
      align-items: stretch;
    }

    .thread-filter-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>