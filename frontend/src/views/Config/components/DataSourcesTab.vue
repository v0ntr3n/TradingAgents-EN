<template>
  <section class="data-sources-tab">
    <h3>Market Data Sources</h3>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ defaultSource?: string }>()
</script>

<style scoped>
.data-sources-tab {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
