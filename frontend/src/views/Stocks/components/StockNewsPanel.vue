<template>
  <section class="stock-news-panel">
    <h3>Disclosed News &amp; Announcements</h3>
    <ul>
      <li v-for="(item, idx) in headlines" :key="idx">{{ item }}</li>
    </ul>
  </section>
</template>

<script setup lang="ts">
defineProps<{ headlines: string[] }>()
</script>

<style scoped>
.stock-news-panel {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
