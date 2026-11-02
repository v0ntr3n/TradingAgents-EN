<template>
  <div class="analysis-progress-stepper" role="status" aria-live="polite">
    <div class="progress-header">
      <span class="stage-label">{{ status }}</span>
      <span class="progress-pct tabular-nums">{{ progress }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  status: string
  progress: number
}>()
</script>

<style scoped>
.analysis-progress-stepper {
  background: var(--color-surface-elevated);
  color: var(--color-text-primary);
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
}
.progress-header {
  display: flex;
  justify-content: space-between;
}
</style>
