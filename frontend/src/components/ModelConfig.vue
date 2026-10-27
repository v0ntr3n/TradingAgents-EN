<template>
  <div class="model-config-component">
    <!-- AI Model configuration -->
    <div class="config-section">
      <h4 class="config-title">🤖 AI Model configuration</h4>
      <div class="model-config">
        <div class="model-item">
          <div class="model-label">
            <span>Quickly analyze models</span>
            <el-tooltip content="Used for market analysis, news analysis, fundamental analysis, etc." placement="top">
              <el-icon class="help-icon"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
          <el-select v-model="localQuickModel" size="small" style="width: 100%" filterable @change="onQuickModelChange">
            <el-option
              v-for="model in availableModels"
              :key="`quick-${model.provider}/${model.model_name}`"
              :label="getModelOptionLabel(model)"
              :value="encodeModelSelection(model)"
            >
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <span style="flex: 1;">{{ model.model_display_name || model.model_name }}</span>
                <div style="display: flex; align-items: center; gap: 4px;">
                  <!-- Ability Level Badge -->
                  <el-tag
                    v-if="model.capability_level"
                    :type="getCapabilityTagType(model.capability_level)"
                    size="small"
                    effect="plain"
                  >
                    {{ getCapabilityText(model.capability_level) }}
                  </el-tag>
                  <!-- role tag -->
                  <el-tag
                    v-if="isQuickAnalysisRole(model.suitable_roles)"
                    type="success"
                    size="small"
                    effect="plain"
                  >
                    ⚡fast
                  </el-tag>
                  <span style="font-size: 12px; color: #909399;">{{ model.provider }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>

        <div class="model-item">
          <div class="model-label">
            <span>Deep decision-making model</span>
            <el-tooltip content="Used for comprehensive decision-making by research integrators and final assessment by risk assessors" placement="top">
              <el-icon class="help-icon"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
          <el-select v-model="localDeepModel" size="small" style="width: 100%" filterable @change="onDeepModelChange">
            <el-option
              v-for="model in availableModels"
              :key="`deep-${model.provider}/${model.model_name}`"
              :label="getModelOptionLabel(model)"
              :value="encodeModelSelection(model)"
            >
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <span style="flex: 1;">{{ model.model_display_name || model.model_name }}</span>
                <div style="display: flex; align-items: center; gap: 4px;">
                  <!-- Ability Level Badge -->
                  <el-tag
                    v-if="model.capability_level"
                    :type="getCapabilityTagType(model.capability_level)"
                    size="small"
                    effect="plain"
                  >
                    {{ getCapabilityText(model.capability_level) }}
                  </el-tag>
                  <!-- role tag -->
                  <el-tag
                    v-if="isDeepAnalysisRole(model.suitable_roles)"
                    type="warning"
                    size="small"
                    effect="plain"
                  >
                    🧠Depth
                  </el-tag>
                  <span style="font-size: 12px; color: #909399;">{{ model.provider }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>
      </div>

      <!-- 🆕 Model recommendation tips -->
      <el-alert
        v-if="modelRecommendation"
        :title="modelRecommendation.title"
        :type="modelRecommendation.type"
        :closable="false"
        style="margin-top: 12px;"
      >
        <template #default>
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
            <div style="font-size: 13px; line-height: 1.8; flex: 1; white-space: pre-line;">
              {{ modelRecommendation.message }}
            </div>
            <el-button
              v-if="modelRecommendation.quickModel && modelRecommendation.deepModel"
              type="primary"
              size="small"
              @click="applyRecommendedModels"
              style="flex-shrink: 0;"
            >
              Application recommendations
            </el-button>
          </div>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { recommendModels } from '@/api/modelCapabilities'
import {
  encodeModelSelection,
  findModelBySelection,
  getModelOptionLabel,
  parseModelSelection,
  resolveModelSelection,
} from '@/utils/modelSelection'

// Props
interface Props {
  quickAnalysisModel: string
  deepAnalysisModel: string
  availableModels: any[]
  analysisDepth: string | number  // Supports strings (such as"Standard") or number (such as 3)
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'update:quickAnalysisModel': [value: string]
  'update:deepAnalysisModel': [value: string]
}>()

// Local state
const localQuickModel = ref(props.quickAnalysisModel)
const localDeepModel = ref(props.deepAnalysisModel)

// Model recommendation tips
const modelRecommendation = ref<{
  title: string
  message: string
  type: 'success' | 'warning' | 'info' | 'error'
  quickModel?: string
  deepModel?: string
} | null>(null)

// Watch props changes
watch(() => props.quickAnalysisModel, (newVal) => {
  localQuickModel.value = resolveModelSelection(newVal, props.availableModels)
})

watch(() => props.deepAnalysisModel, (newVal) => {
  localDeepModel.value = resolveModelSelection(newVal, props.availableModels)
})

// Emit changes
const onQuickModelChange = (value: string) => {
  emit('update:quickAnalysisModel', value)
}

const onDeepModelChange = (value: string) => {
  emit('update:deepAnalysisModel', value)
}

/**
 * Get ability level text
 */
const getCapabilityText = (level: number): string => {
  const texts: Record<number, string> = {
    1: '⚡Basics',
    2: '📊Standard',
    3: '🎯Advanced',
    4: '🔥Professional',
    5: '👑flagship'
  }
  return texts[level] || '📊Standard'
}

/**
 * Get ability level label type
 */
const getCapabilityTagType = (level: number): 'success' | 'info' | 'warning' | 'danger' => {
  if (level >= 4) return 'danger'
  if (level >= 3) return 'warning'
  if (level >= 2) return 'success'
  return 'info'
}

/**
 * Determine whether it is suitable for rapid analysis
 */
const isQuickAnalysisRole = (roles: string[] | undefined): boolean => {
  if (!roles || !Array.isArray(roles)) return false
  return roles.includes('quick_analysis') || roles.includes('both')
}

/**
 * Determine whether it is suitable for in-depth analysis
 */
const isDeepAnalysisRole = (roles: string[] | undefined): boolean => {
  if (!roles || !Array.isArray(roles)) return false
  return roles.includes('deep_analysis') || roles.includes('both')
}

/**
 * Check model suitability and provide recommendations
 */
const checkModelSuitability = async () => {
  // Convert analysis depth to standard format
  let depthName: string
  if (typeof props.analysisDepth === 'number') {
    const depthNames: Record<number, string> = {
      1: 'fast',
      2: 'Basics',
      3: 'Standard',
      4: 'Depth',
      5: 'Comprehensive'
    }
    depthName = depthNames[props.analysisDepth] || 'Standard'
  } else {
    depthName = props.analysisDepth
  }

  try {
    // Get recommended models
    const recommendRes = await recommendModels(depthName)
    const responseData = recommendRes?.data?.data

    if (responseData) {
      const quickModel = responseData.quick_model || 'unknown'
      const deepModel = responseData.deep_model || 'unknown'
      const quickSelection = resolveModelSelection(
        quickModel,
        props.availableModels,
        parseModelSelection(localQuickModel.value).provider
      )
      const deepSelection = resolveModelSelection(
        deepModel,
        props.availableModels,
        parseModelSelection(localDeepModel.value).provider
      )

      // Get the display name of the model
      const quickModelInfo = findModelBySelection(props.availableModels, quickSelection)
      const deepModelInfo = findModelBySelection(props.availableModels, deepSelection)

      const quickDisplayName = quickModelInfo?.model_display_name || quickModel
      const deepDisplayName = deepModelInfo?.model_display_name || deepModel

      // Get recommendation reasons
      const reason = responseData.reason || ''

      // Build recommended instructions
      const depthDescriptions: Record<string, string> = {
        'fast': 'Browse quickly to get basic information',
        'Basics': 'Basic analysis to understand the main indicators',
        'Standard': 'Standard analysis to fully evaluate stocks',
        'Depth': 'Conduct in-depth research and explore investment opportunities',
        'Comprehensive': 'Comprehensive analysis and formation of systematic research conclusions'
      }

      const message = `${depthDescriptions[depthName] || 'standard analysis'}\n\n Recommended model configuration:\n• Quick model:${quickDisplayName}\n• Deep model:${deepDisplayName}\n\n${reason}`

      modelRecommendation.value = {
        title: '💡 Model recommendation',
        message,
        type: 'info',
        quickModel: quickSelection,
        deepModel: deepSelection
      }
    } else {
      // If there is no recommended data, show a general description
      const generalDescriptions: Record<string, string> = {
        'fast': 'Quick analysis: Just use the basic model, focusing on speed and cost',
        'Basics': 'Basic analysis: use the basic level for fast models and the standard level for deep models.',
        'Standard': 'Standard analysis: Use basic level for fast models, and use standard level or above for deep models.',
        'Depth': 'Depth analysis: Use standard level for fast models, and use advanced level or higher for deep models, which require reasoning capabilities.',
        'Comprehensive': 'Comprehensive analysis: use standard level for fast models, professional level or above for deep models, strong reasoning ability'
      }

      modelRecommendation.value = {
        title: '💡 Model recommendation',
        message: generalDescriptions[depthName] || generalDescriptions['Standard'],
        type: 'info'
      }
    }
  } catch (error) {
    console.error('Failed to obtain model recommendations:', error)
  }
}

/**
 * Apply the recommended model configuration
 */
const applyRecommendedModels = () => {
  if (modelRecommendation.value?.quickModel && modelRecommendation.value?.deepModel) {
    localQuickModel.value = modelRecommendation.value.quickModel
    localDeepModel.value = modelRecommendation.value.deepModel
    
    emit('update:quickAnalysisModel', modelRecommendation.value.quickModel)
    emit('update:deepAnalysisModel', modelRecommendation.value.deepModel)

    // Clear recommendations
    modelRecommendation.value = null

    ElMessage.success('Recommended model configuration applied')
  }
}

// Monitor and analyze depth changes
watch(() => props.analysisDepth, () => {
  checkModelSuitability()
})

// Listen for model selection changes
watch([localQuickModel, localDeepModel], () => {
  checkModelSuitability()
})

// initialization
onMounted(() => {
  localQuickModel.value = resolveModelSelection(props.quickAnalysisModel, props.availableModels)
  localDeepModel.value = resolveModelSelection(props.deepAnalysisModel, props.availableModels)
  checkModelSuitability()
})
</script>

<style lang="scss" scoped>
.model-config-component {
  .config-section {
    margin-bottom: 24px;

    &:last-child {
      margin-bottom: 0;
    }

    .config-title {
      font-size: 14px;
      font-weight: 600;
      color: #1a202c;
      margin: 0 0 12px 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .model-config {
      .model-item {
        margin-bottom: 16px;

        &:last-child {
          margin-bottom: 0;
        }

        .model-label {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
          font-size: 13px;
          color: #374151;

          .help-icon {
            color: #9ca3af;
            cursor: help;
          }
        }
      }
    }
  }
}
</style>

