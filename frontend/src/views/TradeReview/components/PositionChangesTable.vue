<template>
  <div class="position-changes-table">
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="code" label="Stock code" width="100">
        <template #default="{ row }">
          <el-link type="primary" :href="`/stocks/${row.code}`" class="stock-link">
            {{ row.code }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="Stock name" width="120">
        <template #default="{ row }">
          <el-link type="primary" :href="`/stocks/${row.code}`" class="stock-link">
            {{ row.name }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="market" label="market" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="getMarketType(row.market)">{{ row.market }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="current_quantity" label="Position quantity" width="100" align="right" />
      <el-table-column prop="cost_price" label="cost price" width="100" align="right">
        <template #default="{ row }">
          {{ row.cost_price?.toFixed(2) || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="unrealized_pnl" label="floating profit and loss" width="120" align="right">
        <template #default="{ row }">
          <span :class="row.unrealized_pnl >= 0 ? 'positive' : 'negative'">
            {{ formatPnl(row.unrealized_pnl) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="unrealized_pnl_pct" label="Profit and loss ratio" width="100" align="right">
        <template #default="{ row }">
          <span :class="row.unrealized_pnl_pct >= 0 ? 'positive' : 'negative'">
            {{ formatPct(row.unrealized_pnl_pct) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="Operation" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handleStartReview(row)">
            Initiate review
          </el-button>
          <el-button type="success" link size="small" @click="handleViewReport(row)">
            View report
          </el-button>
          <el-button type="info" link size="small" @click="handleViewHistory(row)">
            Review history
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-empty v-if="!loading && items.length === 0" description="No position data yet" />
  </div>
</template>

<script setup lang="ts">
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

interface PositionChangeItem {
  code: string
  name: string
  market: string
  operations: number
  current_quantity: number
  cost_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  last_operation_time: string
}

defineProps<{
  items: PositionChangeItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'start-review', item: PositionChangeItem): void
  (e: 'view-report', item: PositionChangeItem): void
  (e: 'view-history', item: PositionChangeItem): void
}>()

const getMarketType = (market: string): TagType => {
  const map: Record<string, TagType> = {
    CN: 'danger'
  }
  return map[market] || 'info'
}

const formatPnl = (val?: number) => {
  if (val === undefined || val === null) return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + val.toFixed(2)
}

const formatPct = (val?: number) => {
  if (val === undefined || val === null) return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + val.toFixed(2) + '%'
}

const handleStartReview = (item: PositionChangeItem) => {
  emit('start-review', item)
}

const handleViewReport = (item: PositionChangeItem) => {
  emit('view-report', item)
}

const handleViewHistory = (item: PositionChangeItem) => {
  emit('view-history', item)
}
</script>

<style scoped lang="scss">
.position-changes-table {
  .positive { color: #f56c6c; }  // Chinese custom: red indicates profit (positive number)
  .negative { color: #67c23a; }  // Chinese custom: green indicates loss (negative number)

  .stock-link {
    font-weight: 500;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}
</style>

