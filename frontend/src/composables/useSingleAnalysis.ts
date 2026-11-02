import { ref, computed } from 'vue'
import type { AnalysisTask } from '@/types/domain'
import { logger } from '@/utils/logger'

export function useSingleAnalysis() {
  const currentTask = ref<AnalysisTask | null>(null)
  const isSubmitting = ref(false)
  const errorMessage = ref<string | null>(null)

  const isRunning = computed(() =>
    currentTask.value?.status === 'pending' || currentTask.value?.status === 'running'
  )

  function setTask(task: AnalysisTask | null) {
    currentTask.value = task
    logger.debug('Updated single analysis task', task?.task_id)
  }

  function clearTask() {
    currentTask.value = null
    errorMessage.value = null
  }

  return {
    currentTask,
    isSubmitting,
    errorMessage,
    isRunning,
    setTask,
    clearTask,
  }
}
