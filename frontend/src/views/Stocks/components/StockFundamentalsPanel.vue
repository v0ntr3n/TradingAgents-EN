<template>
  <section class="stock-fundamentals-panel">
    <h3>Point-in-Time Fundamental Ratios</h3>
    <div class="ratios-grid tabular-nums">
      <div>P/E (TTM): {{ peTtm ?? '-' }}</div>
      <div>P/B (MRQ): {{ pbMrq ?? '-' }}</div>
      <div>ROE (TTM): {{ roeTtm ?? '-' }}%</div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  peTtm?: number | null
  pbMrq?: number | null
  roeTtm?: number | null
}>()
</script>

<style scoped>
.stock-fundamentals-panel {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
