<template>
  <div class="case-library-table">
    <el-empty v-if="!loading && items.length === 0" description="There are no cases yet. The review results will be added to the case library for future review." />
    
    <el-table v-else :data="items" v-loading="loading" stripe>
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
      <el-table-column prop="realized_pnl" label="Realize profit and loss" width="120" align="right">
        <template #default="{ row }">
          <span :class="row.realized_pnl >= 0 ? 'positive' : 'negative'">
            {{ formatPnl(row.realized_pnl) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="tags" label="label" min-width="150">
        <template #default="{ row }">
          <el-tag 
            v-for="tag in (row.tags || [])" 
            :key="tag" 
            size="small" 
            type="info"
            style="margin-right: 4px"
          >
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="creation time" width="160">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="Operation" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="$emit('view', row.review_id)">
            View details
          </el-button>
          <el-popconfirm title="Are you sure you want to remove it from the case library?" @confirm="$emit('delete', row.review_id)">
            <template #reference>
              <el-button link type="danger" size="small">Remove</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    
    <div class="pagination" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewListItem } from '@/api/review'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps<{
  items: ReviewListItem[]
  loading: boolean
  total: number
  page: number
  pageSize: number
}>()

const emit = defineEmits<{
  (e: 'view', reviewId: string): void
  (e: 'delete', reviewId: string): void
  (e: 'page-change', page: number): void
}>()

const currentPage = computed({
  get: () => props.page,
  set: (val) => emit('page-change', val)
})

const formatPnl = (value: number) => {
  if (value === undefined || value === null) return '-'
  const prefix = value >= 0 ? '+' : ''
  return prefix + value.toFixed(2)
}

const handlePageChange = (page: number) => {
  emit('page-change', page)
}
</script>

<style scoped lang="scss">
.case-library-table {
  .stock-link {
    font-weight: 500;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
  
  .positive { color: #f56c6c; }  // Chinese custom: red indicates profit (positive number)
  .negative { color: #67c23a; }  // Chinese custom: green indicates loss (negative number)
  
  .pagination {
    margin-top: 16px;
    display: flex;
    justify-content: flex-end;
  }
}
</style>

