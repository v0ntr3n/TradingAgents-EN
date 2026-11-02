<template>
  <section class="model-catalog-tab">
    <h3>28-LLM Registry Model Catalog</h3>
    <table>
      <thead>
        <tr>
          <th>Model ID</th>
          <th>Provider</th>
          <th>Tier</th>
          <th>Context</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in models" :key="m.model_id">
          <td>{{ m.model_id }}</td>
          <td>{{ m.provider }}</td>
          <td>{{ m.tier }}</td>
          <td class="tabular-nums">{{ m.context_window }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import type { ModelCapability } from '@/types/domain'

defineProps<{ models: ModelCapability[] }>()
</script>

<style scoped>
.model-catalog-tab {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
