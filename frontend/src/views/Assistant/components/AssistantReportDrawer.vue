<template>
  <aside v-if="open" class="assistant-report-drawer" aria-label="Attached Research Reports">
    <header>
      <h4>Attached Research Reports</h4>
      <button type="button" @click="$emit('close')">Close</button>
    </header>
    <slot />
  </aside>
</template>

<script setup lang="ts">
defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.assistant-report-drawer {
  background: var(--color-surface-elevated);
  border-left: 1px solid var(--color-border-subtle);
}
</style>
