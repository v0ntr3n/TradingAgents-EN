import { ref } from 'vue'
import type { ModelCapability } from '@/types/domain'
import { logger } from '@/utils/logger'

export function useConfigManagement() {
  const activeTab = ref<'llm' | 'datasources' | 'database' | 'catalog'>('llm')
  const modelCatalog = ref<ModelCapability[]>([])
  const isLoading = ref(false)

  function selectTab(tab: 'llm' | 'datasources' | 'database' | 'catalog') {
    activeTab.value = tab
    logger.debug('Switched config management tab:', tab)
  }

  return {
    activeTab,
    modelCatalog,
    isLoading,
    selectTab,
  }
}
