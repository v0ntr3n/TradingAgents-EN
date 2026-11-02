<template>
  <header class="stock-quote-header">
    <div>
      <h2>{{ name }} ({{ symbol }})</h2>
    </div>
    <div class="quote-metrics tabular-nums">
      <span class="latest-price">{{ price.toFixed(2) }}</span>
      <span :class="pctChg >= 0 ? 'price-up' : 'price-down'">
        {{ pctChg >= 0 ? '+' : '' }}{{ pctChg.toFixed(2) }}%
      </span>
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  symbol: string
  name: string
  price: number
  pctChg: number
}>()
</script>

<style scoped>
.stock-quote-header {
  display: flex;
  justify-content: space-between;
  background: var(--color-surface-secondary);
  padding: 1rem;
}
.price-up {
  color: var(--color-up);
}
.price-down {
  color: var(--color-down);
}
</style>
