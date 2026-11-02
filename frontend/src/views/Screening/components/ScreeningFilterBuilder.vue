<template>
  <section class="screening-filter-builder">
    <input
      v-model="nlQuery"
      type="text"
      placeholder="e.g. PE < 25 and ROE > 15"
      aria-label="Natural language screening query"
    />
    <button type="button" @click="$emit('apply', nlQuery)">Apply Filter</button>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineEmits<{ (e: 'apply', query: string): void }>()
const nlQuery = ref('')
</script>

<style scoped>
.screening-filter-builder {
  background: var(--color-surface-secondary);
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
}
</style>
