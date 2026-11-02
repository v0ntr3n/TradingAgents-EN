<template>
  <section class="skill-code-preview-step">
    <h3>Step 2: Generated Skill Code &amp; Schema</h3>
    <pre><code>{{ code }}</code></pre>
  </section>
</template>

<script setup lang="ts">
defineProps<{ code: string }>()
</script>

<style scoped>
.skill-code-preview-step {
  background: var(--color-surface-secondary);
  color: var(--color-text-primary);
}
</style>
