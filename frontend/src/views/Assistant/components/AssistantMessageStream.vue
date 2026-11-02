<template>
  <div class="assistant-message-stream" role="log" aria-live="polite">
    <div
      v-for="(msg, idx) in messages"
      :key="idx"
      class="message-bubble"
      :data-role="msg.role"
    >
      {{ msg.content }}
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  messages: Array<{ role: string; content: string }>
}>()
</script>

<style scoped>
.assistant-message-stream {
  background: var(--color-surface-primary);
  color: var(--color-text-primary);
}
</style>
