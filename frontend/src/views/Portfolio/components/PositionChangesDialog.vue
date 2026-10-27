<template>
  <el-dialog
    v-model="visible"
    title="📋 Position change record"
    width="900px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- Filter criteria -->
    <div class="filter-bar">
      <el-select v-model="filters.market" placeholder="market" clearable size="small" style="width: 100px">
        <el-option label="All" value="" />
        <el-option label="A shares" value="CN" />
      </el-select>
      <el-select v-model="filters.change_type" placeholder="Change type" clearable size="small" style="width: 120px">
        <el-option label="All" value="" />
        <el-option label="buy" value="buy" />
        <el-option label="Add to position" value="add" />
        <el-option label="Reduce positions" value="reduce" />
        <el-option label="sell" value="sell" />
        <el-option label="adjust" value="adjust" />
      </el-select>
      <el-input v-model="filters.code" placeholder="Stock code" clearable size="small" style="width: 120px" />
      <el-button type="primary" size="small" @click="loadData">Query</el-button>
      <el-button size="small" @click="resetFilters">Reset filter</el-button>
      <el-button
        v-if="filters.code"
        type="danger"
        size="small"
        plain
        @click="confirmResetPosition"
      >
        reset {{ filters.code }} Position
      </el-button>
    </div>

    <!-- Change record form -->
    <el-table :data="changes" v-loading="loading" stripe size="small" max-height="500">
      <el-table-column prop="created_at" label="time" width="160">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="code" label="code" width="90" />
      <el-table-column prop="name" label="Name" width="100" />
      <el-table-column prop="market" label="market" width="70">
        <template #default="{ row }">
          <el-tag :type="getMarketTagType(row.market, row.code)" size="small">{{ getMarketName(row.market, row.code) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="change_type" label="Type" width="80">
        <template #default="{ row }">
          <el-tag :type="getChangeTypeTag(row.change_type)" size="small">{{ getChangeTypeName(row.change_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Quantity change" width="120">
        <template #default="{ row }">
          <span :class="row.quantity_change >= 0 ? 'text-success' : 'text-danger'">
            {{ row.quantity_change >= 0 ? '+' : '' }}{{ row.quantity_change }}
          </span>
          <div class="sub-text">{{ row.quantity_before }} → {{ row.quantity_after }}</div>
        </template>
      </el-table-column>
      <el-table-column label="cost price" width="120">
        <template #default="{ row }">
          {{ getCurrencySymbol(row.currency) }}{{ row.cost_price_after.toFixed(2) }}
          <div class="sub-text" v-if="row.cost_price_before !== row.cost_price_after">
            {{ row.cost_price_before.toFixed(2) }} → {{ row.cost_price_after.toFixed(2) }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Funding changes" width="120">
        <template #default="{ row }">
          <span :class="row.cash_change >= 0 ? 'text-success' : 'text-danger'">
            {{ row.cash_change >= 0 ? '+' : '' }}{{ getCurrencySymbol(row.currency) }}{{ Math.abs(row.cash_change).toFixed(2) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="Description" min-width="120" show-overflow-tooltip />
      <el-table-column label="Operation" width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="['buy','add','reduce','sell'].includes(row.change_type)"
            type="primary"
            link
            size="small"
            @click="openEdit(row as PositionChange)"
          >
            Edit
          </el-button>
          <el-button
            v-if="['buy','add','reduce','sell','adjust'].includes(row.change_type)"
            type="danger"
            link
            size="small"
            @click="confirmDelete(row as PositionChange)"
          >
            Delete
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Single record editing dialog box -->
    <el-dialog
      v-model="editVisible"
      :title="`Edit${getChangeTypeName(editForm.change_type)}record`"
      width="420px"
      append-to-body
      @close="resetEditForm"
    >
      <p class="edit-tip">Used to correct entry errors (quantity, unit price). After modification, subsequent records and positions will be automatically recalculated.</p>
      <el-form label-width="100px">
        <el-form-item label="stocks">
          {{ editForm.code }} {{ editForm.name }}
        </el-form-item>
        <el-form-item label="Type">
          <el-tag :type="getChangeTypeTag(editForm.change_type)" size="small">
            {{ getChangeTypeName(editForm.change_type) }}
          </el-tag>
        </el-form-item>
        <el-form-item :label="editForm.change_type === 'buy' || editForm.change_type === 'add' ? 'Buy quantity' : 'Sell quantity'" required>
          <el-input-number
            v-model="editForm.quantity"
            :min="1"
            :precision="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="editForm.change_type === 'buy' || editForm.change_type === 'add' ? 'Buying price' : 'Selling price'" required>
          <el-input-number
            v-model="editForm.price"
            :min="0.01"
            :precision="2"
            :step="0.01"
            controls-position="right"
            style="width: 100%"
          />
          <span class="unit-hint">{{ getCurrencySymbol(editForm.currency) }}/shares</span>
        </el-form-item>
        <el-form-item label="trading hours">
          <el-date-picker
            v-model="editForm.trade_time"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="Optional"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="submitEdit">
          OK
        </el-button>
      </template>
    </el-dialog>

    <!-- Pagination -->
    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadData"
        @current-change="loadData"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { portfolioApi, type PositionChange, type PositionChangeType } from '@/api/portfolio'
import { getMarketByStockCode } from '@/utils/market'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue', 'refresh'])

const visible = ref(props.modelValue)
const loading = ref(false)
const changes = ref<PositionChange[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(50)

const editVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref<{
  id: string
  code: string
  name: string
  currency: string
  change_type: string
  quantity: number
  price: number
  trade_time?: string
}>({
  id: '',
  code: '',
  name: '',
  currency: 'CNY',
  change_type: '',
  quantity: 0,
  price: 0
})

const filters = ref({
  market: '',
  change_type: '' as PositionChangeType | '',
  code: ''
})

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) loadData()
})

watch(visible, (val) => emit('update:modelValue', val))

const loadData = async () => {
  loading.value = true
  try {
    const res = await portfolioApi.getPositionChanges({
      market: filters.value.market || undefined,
      change_type: filters.value.change_type || undefined,
      code: filters.value.code || undefined,
      limit: pageSize.value,
      skip: (currentPage.value - 1) * pageSize.value
    })
    changes.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || 'Loading failed')
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.value = { market: '', change_type: '', code: '' }
  currentPage.value = 1
  loadData()
}

function getEditQuantity(row: PositionChange): number {
  return row.change_type === 'buy' || row.change_type === 'add'
    ? row.quantity_change
    : Math.abs(row.quantity_change)
}

function getEditPrice(row: PositionChange): number {
  if (row.change_type === 'buy' || row.change_type === 'add') {
    if (row.quantity_change > 0 && row.cost_value_before !== undefined && row.cost_value_after !== undefined) {
      return (row.cost_value_after - row.cost_value_before) / row.quantity_change
    }
    return row.cost_price_after
  }
  return row.trade_price ?? 0
}

const openEdit = (row: PositionChange) => {
  editForm.value = {
    id: row.id,
    code: row.code,
    name: row.name,
    currency: row.currency,
    change_type: row.change_type,
    quantity: getEditQuantity(row),
    price: getEditPrice(row),
    trade_time: row.trade_time ? String(row.trade_time).slice(0, 10) : undefined
  }
  editVisible.value = true
}

const resetEditForm = () => {
  editForm.value = { id: '', code: '', name: '', currency: 'CNY', change_type: '', quantity: 0, price: 0 }
}

const confirmDelete = async (row: PositionChange) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete this article${getChangeTypeName(row.change_type)}Record? Subsequent records will be automatically recalculated after deletion.`,
      'Confirm deletion',
      { type: 'warning' }
    )
    await portfolioApi.deletePositionChange(row.id)
    ElMessage.success('Delete successfully')
    loadData()
    emit('refresh')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || 'Delete failed')
  }
}

const confirmResetPosition = async () => {
  const code = filters.value.code
  if (!code) return
  const market = filters.value.market || 'CN'
  try {
    await ElMessageBox.confirm(
      `Confirm reset ${code} of the entire position? All change records and positions of the stock will be deleted, and this operation cannot be restored.`,
      'Confirm reset',
      { type: 'warning' }
    )
    const res = await portfolioApi.resetPosition(code, market)
    ElMessage.success(`Reset successful, deleted ${res.data?.deleted_changes ?? 0} records`)
    filters.value.code = ''
    loadData()
    emit('refresh')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || 'Reset failed')
  }
}

const submitEdit = async () => {
  const { id, quantity, price, trade_time } = editForm.value
  if (!quantity || quantity <= 0) {
    ElMessage.warning('Please enter a valid quantity')
    return
  }
  if (!price || price <= 0) {
    ElMessage.warning('Please enter a valid unit price')
    return
  }
  editSubmitting.value = true
  try {
    await portfolioApi.updatePositionChange(id, { quantity, price, trade_time })
    ElMessage.success('Record correction successful')
    editVisible.value = false
    loadData()
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e.message || 'Correction failed')
  } finally {
    editSubmitting.value = false
  }
}

const handleClose = () => emit('update:modelValue', false)

const formatDateTime = (dt: string) => {
  if (!dt) return '-'
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const getMarketName = (m: string, code?: string) => {
  if (m === 'CN' && code && getMarketByStockCode(code) === 'ETF') return 'ETF'
  return ({ CN: 'A shares' }[m] || m)
}
const getMarketTagType = (m: string, code?: string) => {
  if (m === 'CN' && code && getMarketByStockCode(code) === 'ETF') return 'success'
  return ({ CN: 'danger' }[m] || 'info') as any
}
const getCurrencySymbol = (c: string) => ({ CNY: '¥' }[c] || c)
const getChangeTypeName = (t: string) => ({ buy: 'buy', add: 'Add to position', reduce: 'Reduce positions', sell: 'sell', adjust: 'adjust' }[t] || t)
const getChangeTypeTag = (t: string) => ({ buy: 'success', add: 'primary', reduce: 'warning', sell: 'danger', adjust: 'info' }[t] || 'info') as any
</script>

<style scoped>
.filter-bar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.pagination-bar { margin-top: 16px; display: flex; justify-content: flex-end; }
.text-success { color: #f56c6c; } /* Red indicates success/profit (Chinese stock market norm) */
.text-danger { color: #67c23a; } /* Green indicates danger/loss (Chinese stock market norm) */
.sub-text { font-size: 11px; color: #909399; }
.edit-tip { font-size: 12px; color: #909399; margin-bottom: 16px; }
.unit-hint { margin-left: 8px; font-size: 12px; color: #909399; }
</style>

