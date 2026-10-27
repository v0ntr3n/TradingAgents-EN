<template>
  <div class="reviewable-trades-table">
    <el-empty
      v-if="!loading && stocks.length === 0"
      description="There are currently no transactions to review. Please perform buying and selling operations in simulated trading first."
    >
      <el-button type="primary" @click="goToPaperTrading">Go to simulated trading</el-button>
    </el-empty>

    <el-table v-else :data="stocks" v-loading="loading" stripe>
      <el-table-column prop="code" label="Stock code" width="110">
        <template #default="{ row }">
          <el-link type="primary" :href="`/stocks/${row.code}`" class="stock-link">
            {{ row.code }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="Stock name" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" :href="`/stocks/${row.code}`" class="stock-link">
            {{ row.name || '-' }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="market" label="market" width="70" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="getMarketType(row.market)">{{ row.market || 'CN' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="buy_count" label="buy" width="70" align="center" />
      <el-table-column prop="sell_count" label="sell" width="70" align="center" />
      <el-table-column prop="total_pnl" label="Cumulative profit and loss" width="120" align="right">
        <template #default="{ row }">
          <span :class="(row.total_pnl || 0) >= 0 ? 'positive' : 'negative'">
            {{ formatPnl(row.total_pnl) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="Status" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'completed' || row.sell_count >= row.buy_count" type="success" size="small">
            Position closed
          </el-tag>
          <el-tag v-else-if="row.sell_count > 0" type="warning" size="small">
            partial position
          </el-tag>
          <el-tag v-else type="primary" size="small">
            In position
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Operation" width="220" fixed="right">
        <template #default="{ row }">
          <el-button 
            type="primary" 
            link
            size="small" 
            @click="handleStartReview(row.code)"
          >
            Initiate review
          </el-button>
          <el-button 
            type="success" 
            link
            size="small" 
            @click="handleViewReport(row)"
          >
            View report
          </el-button>
          <el-button 
            type="info" 
            link
            size="small" 
            @click="handleViewHistory(row)"
          >
            Review history
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="tips">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          <span>Review tips</span>
        </template>
        <template #default>
          <ul>
            <li>Review can help you review the basis of the transaction and discover problems in execution</li>
            <li>Completed transactions can be reviewed one by one to continuously improve research preparation and execution discipline.</li>
            <li>Stocks in positions can also be reviewed, focusing on reviewing whether the basis for entry at the time was sufficient.</li>
          </ul>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { ReviewableStock } from '@/api/review'

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

defineProps<{
  stocks: ReviewableStock[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'start-review', code: string): void
  (e: 'view-report', stock: ReviewableStock): void
  (e: 'view-history', stock: ReviewableStock): void
}>()

const router = useRouter()

// Processing the click of the initiate review button
const handleStartReview = (code: string) => {
  emit('start-review', code)
}

const handleViewReport = (stock: ReviewableStock) => {
  emit('view-report', stock)
}

const handleViewHistory = (stock: ReviewableStock) => {
  emit('view-history', stock)
}

const formatPnl = (value?: number) => {
  if (value === undefined || value === null) return '-'
  const prefix = value >= 0 ? '+' : ''
  return prefix + value.toFixed(2)
}

const getMarketType = (market?: string): TagType => {
  const map: Record<string, TagType> = {
    CN: 'danger'
  }
  return map[market || 'CN'] || 'info'
}

const goToPaperTrading = () => {
  router.push('/paper')
}
</script>

<style scoped lang="scss">
.reviewable-trades-table {
  .stock-link {
    font-weight: 500;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }

  .positive { color: #f56c6c; }  // Chinese custom: red indicates profit (positive number)
  .negative { color: #67c23a; }  // Chinese custom: green indicates loss (negative number)
  
  .tips {
    margin-top: 20px;
    
    ul {
      margin: 8px 0 0 0;
      padding-left: 20px;
      li {
        margin-bottom: 4px;
        font-size: 13px;
      }
    }
  }
}
</style>

