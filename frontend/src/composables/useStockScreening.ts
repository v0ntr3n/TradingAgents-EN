import { ref, computed } from 'vue'
import type { ScreeningResult } from '@/types/domain'

export function useStockScreening() {
  const results = ref<ScreeningResult[]>([])
  const isScreening = ref(false)
  const queryText = ref('')

  const totalMatches = computed(() => results.value.length)

  function setResults(rows: ScreeningResult[]) {
    results.value = rows
  }

  return {
    results,
    isScreening,
    queryText,
    totalMatches,
    setResults,
  }
}
