<template>
  <section class="llm-providers-tab">
    <h3>LLM Providers</h3>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ activeProvider?: string }>()
</script>

<style scoped>
.llm-providers-tab {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
