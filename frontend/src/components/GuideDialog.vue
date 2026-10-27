<template>
  <el-dialog
    v-model="visible"
    title="Welcome TradingAgents-CN"
    width="600px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="!isFirstTime"
  >
    <div class="guide-dialog-content">
      <div class="welcome-header">
        <el-icon class="welcome-icon"><Document /></el-icon>
        <h3>Welcome TradingAgents-CN</h3>
        <p class="welcome-subtitle">Follow the steps below to complete the initial setup and start using the AI-assisted stock analysis technology learning platform</p>
      </div>

      <div class="steps-summary">
        <el-steps direction="vertical" :active="5" finish-status="success" size="small">
          <el-step title="get API Token" description="Get API keys for large models and data sources" />
          <el-step title="Fill in the Token configuration" description="Fill in your API key on the settings page" />
          <el-step title="Sync stock data" description="Synchronize basic stock data to the system" />
          <el-step title="Search and add stocks to watchlist" description="Search for stocks of interest and add to stock watchlist" />
          <el-step title="Complete first analysis" description="Conduct AI analysis on the stocks you follow" />
        </el-steps>
      </div>

      <div class="quick-actions">
        <el-button type="primary" @click="goToGuide" style="width: 100%">
          <el-icon><Document /></el-icon>
          View full user guide
        </el-button>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-checkbox v-model="dontShowAgain" v-if="isFirstTime">
          Don t show this again
        </el-checkbox>
        <div class="footer-buttons">
          <el-button v-if="isFirstTime" @click="handleSkip">Talk to you later</el-button>
          <el-button type="primary" @click="handleConfirm">
            {{ isFirstTime ? 'Get started' : 'Got it' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Document } from '@element-plus/icons-vue'
import { isJdyunMode } from '@/utils/config'

const props = defineProps<{
  modelValue: boolean
  isFirstTime?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'confirm'): void
  (e: 'skip'): void
}>()

const router = useRouter()
const dontShowAgain = ref(false)

// JD Cloud version does not display pop-up windows (the first login will jump directly to /guide from the routing guard)
const visible = computed({
  get: () => !isJdyunMode() && props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const goToGuide = () => {
  router.push('/guide')
  handleConfirm()
}

const handleConfirm = () => {
  if (dontShowAgain.value && props.isFirstTime) {
    // Save to localStorage and never display again
    localStorage.setItem('guide_dialog_shown', 'true')
  }
  emit('confirm')
  visible.value = false
}

const handleSkip = () => {
  emit('skip')
  visible.value = false
}
</script>

<style lang="scss" scoped>
.guide-dialog-content {
  .welcome-header {
    text-align: center;
    margin-bottom: 32px;

    .welcome-icon {
      font-size: 48px;
      color: var(--el-color-primary);
      margin-bottom: 16px;
    }

    h3 {
      margin: 0 0 8px 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    .welcome-subtitle {
      margin: 0;
      color: var(--el-text-color-regular);
      font-size: 14px;
    }
  }

  .steps-summary {
    margin-bottom: 24px;
    padding: 20px;
    background: var(--el-bg-color-page);
    border-radius: 8px;

    :deep(.el-steps) {
      .el-step__title {
        font-size: 14px;
        font-weight: 500;
      }

      .el-step__description {
        font-size: 12px;
        color: var(--el-text-color-regular);
      }
    }
  }

  .quick-actions {
    margin-top: 24px;
  }
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .footer-buttons {
    display: flex;
    gap: 12px;
  }
}
</style>
