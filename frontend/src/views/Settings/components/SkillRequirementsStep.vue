<template>
  <section class="skill-requirements-step">
    <h3>Step 1: Skill Requirement Specification</h3>
    <textarea
      v-model="localPrompt"
      rows="4"
      placeholder="Describe the quantitative or data tool skill..."
      aria-label="Skill requirement description"
    />
    <button type="button" @click="$emit('next', localPrompt)">Continue</button>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineEmits<{ (e: 'next', requirement: string): void }>()
const localPrompt = ref('')
</script>

<style scoped>
.skill-requirements-step {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
