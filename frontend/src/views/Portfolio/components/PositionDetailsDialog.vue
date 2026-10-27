<template>
  <el-dialog v-model="visible" :title="`${position?.code} - ${position?.name} Position details`" width="800px">
    <div v-if="position" class="position-details">
      <!-- Aggregated information -->
      <el-card class="summary-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>Aggregated information</span>
            <div class="action-buttons">
              <el-button type="primary" size="small" @click="handleAddOperation">Increase positions</el-button>
              <el-button type="warning" size="small" @click="handleReduceOperation">Reduce positions</el-button>
              <el-button type="info" size="small" @click="handleOtherOperation">Other operations</el-button>
            </div>
          </div>
        </template>
        <el-row :gutter="20">
          <el-col :span="6">
            <div class="summary-item">
              <div class="label">total quantity</div>
              <div class="value">{{ position.quantity }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <div class="label">average cost price</div>
              <div class="value">{{ position.cost_price?.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <div class="label">total cost</div>
              <div class="value">{{ formatNumber(position.quantity * position.cost_price) }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <div class="label">Number of positions opened</div>
              <div class="value">{{ position.position_count }}</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- Detailed table -->
      <el-table :data="position.positions" stripe style="margin-top: 16px">
        <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
        <el-table-column prop="cost_price" label="cost price" width="100" align="right">
          <template #default="{ row }">{{ row.cost_price?.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="cost amount" width="120" align="right">
          <template #default="{ row }">{{ formatNumber(row.quantity * row.cost_price) }}</template>
        </el-table-column>
        <el-table-column prop="current_price" label="Current price" width="80" align="right">
          <template #default="{ row }">{{ row.current_price?.toFixed(2) || '-' }}</template>
        </el-table-column>
        <el-table-column label="Profit and loss" width="100" align="right">
          <template #default="{ row }">
            <span :class="pnlClass(row.unrealized_pnl)">{{ formatPnl(row.unrealized_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="buy_date" label="Opening date" width="110">
          <template #default="{ row }">{{ formatDate(row.buy_date) }}</template>
        </el-table-column>
        <el-table-column label="Operation" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleEdit(row)">Edit</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { portfolioApi, type PositionItem } from '@/api/portfolio'

interface AggregatedPosition extends PositionItem {
  position_count: number
  positions: PositionItem[]
}

const props = defineProps<{
  modelValue: boolean
  position: AggregatedPosition | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'edit', position: PositionItem): void
  (e: 'refresh'): void
  (e: 'operation', data: { type: string; position: AggregatedPosition }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const formatNumber = (val: number) => {
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatPnl = (val?: number) => {
  if (!val) return '-'
  const sign = val > 0 ? '+' : ''
  return sign + formatNumber(val)
}

const pnlClass = (val?: number) => {
  if (!val) return ''
  if (val > 0) return 'profit'
  if (val < 0) return 'loss'
  return ''
}

const formatDate = (date?: string) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

// Edit a single position
const handleEdit = (row: PositionItem) => {
  visible.value = false
  emit('edit', row)
}

// Delete a single position
const handleDelete = async (row: PositionItem) => {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete this position record? (Quantity: ${row.quantity}, cost price: ${row.cost_price?.toFixed(2)}) `,
      'Confirm deletion',
      { type: 'warning' }
    )
    await portfolioApi.deletePosition(row.id)
    ElMessage.success('Delete successfully')
    emit('refresh')
    // If there is only one record left, close the dialog box
    if (props.position && props.position.positions.length <= 1) {
      visible.value = false
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || 'Delete failed')
    }
  }
}

// Increase position operation
const handleAddOperation = () => {
  if (props.position) {
    emit('operation', { type: 'add', position: props.position })
  }
}

// Position reduction operation
const handleReduceOperation = () => {
  if (props.position) {
    emit('operation', { type: 'reduce', position: props.position })
  }
}

// Other operations (dividends, stock splits, etc.)
const handleOtherOperation = () => {
  if (props.position) {
    emit('operation', { type: 'other', position: props.position })
  }
}
</script>

<style scoped>
.position-details {
  padding: 0;
}

.summary-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.summary-item {
  text-align: center;
}

.summary-item .label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-item .value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.profit {
  color: #F56C6C; /* Red indicates profit (Chinese stock market norm) */
}

.loss {
  color: #67C23A; /* Green indicates loss (Chinese stock market norm) */
}
</style>

