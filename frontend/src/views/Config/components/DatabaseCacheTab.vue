<template>
  <section class="database-cache-tab">
    <h3>Database &amp; Redis Cache</h3>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ mongoConnected?: boolean; redisConnected?: boolean }>()
</script>

<style scoped>
.database-cache-tab {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
