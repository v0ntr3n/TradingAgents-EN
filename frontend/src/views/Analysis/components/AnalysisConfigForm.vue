<template>
  <section class="analysis-config-form" aria-label="Single Stock Analysis Configuration">
    <div class="field-row">
      <label for="symbol-input">Stock Symbol</label>
      <input
        id="symbol-input"
        v-model="localSymbol"
        type="text"
        placeholder="e.g. 600519.SH or AAPL"
      />
    </div>
    <button type="button" :disabled="disabled || !localSymbol" @click="emitSubmit">
      Run CARE-Agents Analysis
    </button>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ (e: 'submit', symbol: string): void }>()
const localSymbol = ref('')

function emitSubmit() {
  if (localSymbol.value.trim()) {
    emit('submit', localSymbol.value.trim())
  }
}
</script>

<style scoped>
.analysis-config-form {
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border-subtle);
  padding: 1rem;
  border-radius: 0.5rem;
}
</style>
