<template>
  <div class="analysis-report-tabs">
    <div class="tab-bar" role="tablist">
      <button
        v-for="key in reportKeys"
        :key="key"
        type="button"
        role="tab"
        :aria-selected="selectedKey === key"
        @click="selectedKey = key"
      >
        {{ key }}
      </button>
    </div>
    <article v-if="selectedKey && reports[selectedKey]" class="report-body">
      {{ reports[selectedKey] }}
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ reports: Record<string, string> }>()
const reportKeys = computed(() => Object.keys(props.reports || {}))
const selectedKey = ref<string>(reportKeys.value[0] || '')
</script>

<style scoped>
.analysis-report-tabs {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
