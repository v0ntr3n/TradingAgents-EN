<template>
  <section class="stock-kline-panel" aria-label="Price K-Line Chart">
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ symbol: string; period?: string }>()
</script>

<style scoped>
.stock-kline-panel {
  background: var(--color-surface-primary);
  padding: 1rem;
}
</style>
