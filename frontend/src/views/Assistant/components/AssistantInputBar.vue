<template>
  <form class="assistant-input-bar" @submit.prevent="submitQuery">
    <input
      v-model="draft"
      type="text"
      placeholder="Ask about fundamentals, regime weights, or risk factors..."
      aria-label="Research assistant query"
    />
    <button type="submit" :disabled="disabled || !draft.trim()">Send</button>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ (e: 'send', text: string): void }>()
const draft = ref('')

function submitQuery() {
  const text = draft.value.trim()
  if (text) {
    emit('send', text)
    draft.value = ''
  }
}
</script>

<style scoped>
.assistant-input-bar {
  display: flex;
  gap: 0.5rem;
  background: var(--color-surface-secondary);
  padding: 0.75rem;
}
</style>
