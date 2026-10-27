<template>
  <div class="floating-chat-container">
    <!-- floating button -->
    <div
      v-if="!visible"
      class="chat-fab"
      @click="openChat"
      title="Use the Q&A Assistant"
    >
      <el-icon class="fab-icon"><ChatDotRound /></el-icon>
      <span class="fab-label">Use Q&A</span>
    </div>

    <!-- chat drawer -->
    <el-drawer
      v-model="visible"
      title="Use the Q&A Assistant"
      direction="rtl"
      size="440px"
      :with-header="true"
      :append-to-body="true"
      class="usage-helper-drawer"
      :before-close="handleClose"
    >
      <div class="chat-body">
        <!-- top description -->
        <div class="chat-intro">
          <div class="chat-intro-text">
            <el-icon color="var(--el-color-primary)"><InfoFilled /></el-icon>
            <span>Ask me any questions about using the system, and I can check your true status before answering.</span>
          </div>
          <el-tooltip content="Rebuild user manual vector index (manual remedy when semantic retrieval is unavailable, no need to restart the backend)" placement="top">
            <el-button
              text
              size="small"
              type="primary"
              :loading="rebuildingIndex"
              @click="rebuildManualIndex"
            >
              <el-icon><RefreshRight /></el-icon>
              Rebuild manual index
            </el-button>
          </el-tooltip>
        </div>

        <!-- Message list -->
        <div class="messages" ref="messagesRef">
          <div
            v-for="(msg, i) in messages"
            :key="i"
            :class="['message', msg.role]"
          >
            <div class="bubble">
              <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
            </div>
            <div v-if="msg.tools_used?.length" class="tools-used">
              <el-tag
                v-for="t in msg.tools_used"
                :key="t"
                size="small"
                type="info"
                effect="plain"
              >
                <el-icon><Tools /></el-icon>
                {{ t }}
              </el-tag>
            </div>
          </div>

          <!-- Tool call progress prompt -->
          <div v-if="toolInProgress" class="message assistant">
            <div class="bubble tool-progress">
              <el-icon class="loading-icon"><Loading /></el-icon>
              <span>{{ toolInProgress }}</span>
            </div>
          </div>

          <!-- Taking up space in thinking -->
          <div v-if="loading && !streamingMessage && !toolInProgress" class="message assistant">
            <div class="bubble">
              <el-icon class="loading-icon"><Loading /></el-icon>
              <span>thinking...</span>
            </div>
          </div>
        </div>

        <!-- quick questions -->
        <div v-if="messages.length === 0 && !loading" class="quick-questions">
          <div class="quick-title">💡 you can ask me:</div>
          <div class="quick-buttons">
            <el-button
              v-for="q in quickQuestions"
              :key="q"
              size="small"
              round
              @click="sendMessage(q)"
            >
              {{ q }}
            </el-button>
          </div>
        </div>

        <!-- input area -->
        <div class="input-area">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="Ask any questions about using the system,Ctrl+Enter send..."
            :disabled="loading"
            @keydown.ctrl.enter="sendMessage()"
            @keydown.meta.enter="sendMessage()"
          />
          <div class="input-actions">
            <el-button
              text
              size="small"
              @click="clearMessages"
              :disabled="loading || messages.length === 0"
            >
              <el-icon><Delete /></el-icon>
              Clear
            </el-button>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!inputText.trim()"
              @click="sendMessage()"
            >
              {{ loading ? 'Sending' : 'send' }}
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Loading,
  InfoFilled,
  Tools,
  Delete,
  RefreshRight,
} from '@element-plus/icons-vue'
import { assistantApi } from '@/api/assistant'
import { renderMarkdown } from '@/utils/markdown'
import { isJdyunMode } from '@/utils/config'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tools_used?: string[]
}

const visible = ref(false)
const inputText = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const rebuildingIndex = ref(false)
const streamingMessage = ref('')
const toolInProgress = ref('')
const messagesRef = ref<HTMLElement>()
const route = useRoute()
const conversationId = ref<string | undefined>(undefined)
let abortController: AbortController | null = null

/** Rebuilding the user manual vector index: Manual remediation when the Embedding Key is not configured at startup causing semantic retrieval to be unavailable */
const rebuildManualIndex = async () => {
  if (rebuildingIndex.value) return
  rebuildingIndex.value = true
  try {
    const res = await assistantApi.rebuildUserManualIndex()
    ElMessage.success(
      `User manual index has been rebuilt:${res.sections_count ?? 0} slices (${res.manuals_count ?? 0} manual)`
    )
  } catch (e: any) {
    ElMessage.error(
      e?.response?.data?.detail || e?.message || 'User Manual Index rebuild failed, please check Embedding configuration'
    )
  } finally {
    rebuildingIndex.value = false
  }
}

// Collection of recent browser errors
const recentErrors: string[] = []
const MAX_ERRORS = 3

const quickQuestions = [
  'Why is today s task 0?',
  'How to join the watchlist?',
  'License How to activate?',
  'Where can I read research reports??',
  'How to configure scheduled analysis?',
  'What version am I in now??',
]

// collect window.onerror
const errorHandler = (event: ErrorEvent) => {
  const msg = event.message || 'Unknown error'
  const filename = event.filename || ''
  const lineNo = event.lineno || 0
  recentErrors.push(`${msg} (${filename.split('/').pop()}:${lineNo})`)
  if (recentErrors.length > MAX_ERRORS) recentErrors.shift()
}

// collect uncaught Promise rejection
const rejectionHandler = (event: PromiseRejectionEvent) => {
  const reason = event.reason
  const msg = typeof reason === 'string' ? reason : (reason?.message || JSON.stringify(reason))
  recentErrors.push(`Promise rejection: ${msg}`.slice(0, 200))
  if (recentErrors.length > MAX_ERRORS) recentErrors.shift()
}

onMounted(() => {
  window.addEventListener('error', errorHandler)
  window.addEventListener('unhandledrejection', rejectionHandler)
})

onUnmounted(() => {
  window.removeEventListener('error', errorHandler)
  window.removeEventListener('unhandledrejection', rejectionHandler)
  abortController?.abort()
})

const openChat = () => {
  visible.value = true
  nextTick(() => {
    scrollToBottom()
  })
}

const handleClose = (done: () => void) => {
  if (loading.value) {
    ElMessage.warning('The conversation is in progress, please wait.')
    return
  }
  done()
}

const clearMessages = () => {
  if (loading.value) return
  messages.value = []
  conversationId.value = undefined
  streamingMessage.value = ''
  toolInProgress.value = ''
}

const collectUserContext = () => {
  return {
    current_route: route.path,
    is_jdyun_mode: isJdyunMode(),
    guide_completed: localStorage.getItem('jdyun_guide_completed') === 'true',
    recent_console_errors: [...recentErrors],
  }
}

const sendMessage = async (text?: string) => {
  const content = (text || inputText.value).trim()
  if (!content || loading.value) return

  // Cancel the last outstanding request
  if (abortController) {
    abortController.abort()
    abortController = null
  }

  messages.value.push({ role: 'user', content })
  inputText.value = ''
  loading.value = true
  streamingMessage.value = ''
  toolInProgress.value = ''

  const userContext = collectUserContext()

  abortController = assistantApi.chatStream(
    content,
    conversationId.value,
    undefined, // model: Let the backend choose
    undefined, // model_config_id
    {
      onToken: (token: string) => {
        if (!streamingMessage.value) {
          // When the first token arrives, create a new assistant message
          messages.value.push({ role: 'assistant', content: '' })
          toolInProgress.value = ''
        }
        streamingMessage.value += token
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg && lastMsg.role === 'assistant') {
          lastMsg.content = streamingMessage.value
        }
        nextTick(() => scrollToBottom())
      },
      onToolEvent: (event: any) => {
        const eventType = event?.event
        if (eventType === 'tool_started') {
          const toolName = event?.tool || event?.tool_name || 'Tools'
          toolInProgress.value = `Calling tool: ${toolName}...`
        } else if (eventType === 'tool_completed') {
          toolInProgress.value = ''
        } else if (eventType === 'tool_round_started') {
          toolInProgress.value = `Tool call No. ${event?.round || '?'} wheel...`
        } else if (eventType === 'llm_thinking') {
          toolInProgress.value = event?.message || 'thinking…'
        }
      },
      onDone: (data: any) => {
        if (data.conversation_id) {
          conversationId.value = data.conversation_id
        }
        // Update the tool call record for the last assistant message
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg && lastMsg.role === 'assistant' && data.tools_used?.length) {
          lastMsg.tools_used = data.tools_used
        }
        // If you don t receive any token (you may go directly to the tool path), use the done reply to find out.
        if (!streamingMessage.value && data.reply) {
          messages.value.push({ role: 'assistant', content: data.reply, tools_used: data.tools_used })
        }
        loading.value = false
        streamingMessage.value = ''
        toolInProgress.value = ''
        abortController = null
        nextTick(() => scrollToBottom())
      },
      onError: (msg: string) => {
        loading.value = false
        streamingMessage.value = ''
        toolInProgress.value = ''
        abortController = null
        // If a partial reply has been generated during the streaming process, add an error message; otherwise, add a separate error message
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content) {
          lastMsg.content += `\n\n❌ **Error**: ${msg}`
        } else {
          messages.value.push({ role: 'assistant', content: `❌ **Error**: ${msg}\n\n Please try again later or refresh the page and try again.` })
        }
        nextTick(() => scrollToBottom())
      },
    },
    {
      assistant_role: 'usage_helper',
      user_context: userContext,
    },
  )
}

const scrollToBottom = () => {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// Scroll to bottom when drawer is open
watch(visible, (v) => {
  if (v) {
    nextTick(() => scrollToBottom())
  }
})
</script>

<style lang="scss" scoped>
.floating-chat-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 2000;
  pointer-events: none;
}

.chat-fab {
  pointer-events: auto;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(64, 158, 255, 0.45);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;

  &:hover {
    transform: translateY(-3px) scale(1.05);
    box-shadow: 0 10px 28px rgba(64, 158, 255, 0.6);
  }

  &:active {
    transform: translateY(-1px) scale(1.02);
  }

  .fab-icon {
    font-size: 22px;
  }

  .fab-label {
    font-size: 10px;
    margin-top: 2px;
    letter-spacing: 0.5px;
  }
}

.chat-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0 12px 12px;
  overflow: hidden;
}

.chat-intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 10px 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}

.chat-intro-text {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 4px 4px 12px 0;
  min-height: 200px;

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: var(--el-border-color);
    border-radius: 3px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
}

.message {
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;

  &.user {
    align-items: flex-end;

    .bubble {
      background: var(--el-color-primary);
      color: #fff;
      border-bottom-right-radius: 4px;
    }
  }

  &.assistant {
    align-items: flex-start;

    .bubble {
      background: var(--el-fill-color-light);
      color: var(--el-text-color-primary);
      border-bottom-left-radius: 4px;
    }
  }
}

.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  word-break: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.bubble-content {
  :deep(p) {
    margin: 0 0 8px 0;
    &:last-child {
      margin-bottom: 0;
    }
  }
  :deep(ul),
  :deep(ol) {
    margin: 6px 0;
    padding-left: 20px;
  }
  :deep(li) {
    margin: 2px 0;
  }
  :deep(code) {
    background: rgba(0, 0, 0, 0.08);
    padding: 1px 4px;
    border-radius: 3px;
    font-family: Consolas, Monaco, monospace;
    font-size: 13px;
  }
  :deep(pre) {
    background: rgba(0, 0, 0, 0.08);
    padding: 8px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 6px 0;
  }
  :deep(strong) {
    font-weight: 600;
  }
}

.tools-used {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.tool-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-style: italic;
}

.loading-icon {
  animation: rotate 1.4s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.quick-questions {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.quick-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.quick-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.input-area {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 10px;

  :deep(.el-textarea__inner) {
    border-radius: 8px;
    font-size: 14px;
    line-height: 1.5;
    resize: none;
  }
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  gap: 8px;
}
</style>

<style lang="scss">
/* Jingdong cloud version floating window drawer global style (non-scoped, adjust el-drawer internal style) */
.usage-helper-drawer {
  pointer-events: auto;

  .el-drawer__header {
    margin-bottom: 0;
    padding: 16px 20px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
  .el-drawer__body {
    padding: 0;
  }
}
</style>
