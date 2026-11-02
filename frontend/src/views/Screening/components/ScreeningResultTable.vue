<template>
  <table class="screening-result-table">
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Name</th>
        <th>Close</th>
        <th>Chg%</th>
        <th>P/E</th>
        <th>ROE%</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.symbol">
        <td>{{ row.symbol }}</td>
        <td>{{ row.name }}</td>
        <td class="tabular-nums">{{ row.close.toFixed(2) }}</td>
        <td
          class="tabular-nums"
          :class="row.pct_chg >= 0 ? 'price-up' : 'price-down'"
        >
          {{ row.pct_chg.toFixed(2) }}%
        </td>
        <td class="tabular-nums">{{ row.pe_ttm ?? '-' }}</td>
        <td class="tabular-nums">{{ row.roe_ttm ?? '-' }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
import type { ScreeningResult } from '@/types/domain'

defineProps<{ rows: ScreeningResult[] }>()
</script>

<style scoped>
.price-up {
  color: var(--color-up);
}
.price-down {
  color: var(--color-down);
}
</style>
