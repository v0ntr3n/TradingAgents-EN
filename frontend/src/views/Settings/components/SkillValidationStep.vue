<template>
  <section class="skill-validation-step">
    <h3>Step 3: Real-Data Dry-Run Validation</h3>
    <div class="validation-status">
      Status: <strong>{{ passed ? 'PASSED' : 'PENDING' }}</strong>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{ passed: boolean }>()
</script>

<style scoped>
.skill-validation-step {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
