<template>
  <el-dialog
    v-model="visible"
    title="Initiate transaction review"
    width="600px"
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="Stock code" required>
        <el-input
          v-model="form.code"
          placeholder="Please enter stock code"
          :disabled="!!presetCode"
          @blur="loadTrades"
        />
        <div v-if="presetCode" class="preset-hint">
          Stocks selected from the reviewable trade list
        </div>
      </el-form-item>
      
      <el-form-item label="transaction history" v-if="trades.length > 0">
        <el-table :data="trades" size="small" max-height="250" @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="side" label="direction" width="60">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? 'buy' : 'sell' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
          <el-table-column prop="price" label="price" width="80" align="right">
            <template #default="{ row }">{{ row.price?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="pnl" label="Profit and loss" width="80" align="right">
            <template #default="{ row }">
              <span v-if="row.pnl !== 0" :class="row.pnl >= 0 ? 'positive' : 'negative'">
                {{ row.pnl?.toFixed(2) }}
              </span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="timestamp" label="time" min-width="120">
            <template #default="{ row }">{{ formatDateTime(row.timestamp) }}</template>
          </el-table-column>
        </el-table>
        
        <div class="summary" v-if="tradeSummary">
          <span>buy: {{ tradeSummary.total_buy_quantity }}shares</span>
          <span>sell: {{ tradeSummary.total_sell_quantity }}shares</span>
          <span :class="tradeSummary.total_pnl >= 0 ? 'positive' : 'negative'">
            Profit and loss: {{ tradeSummary.total_pnl?.toFixed(2) }}
          </span>
        </div>
      </el-form-item>
      
      <el-form-item label="Review type">
        <el-radio-group v-model="form.review_type">
          <el-radio value="complete_trade">Complete transaction review</el-radio>
          <el-radio value="single_trade">Single transaction review</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button 
        type="primary" 
        :loading="submitting" 
        :disabled="isSubmitDisabled" 
        @click="submit"
      >
        Start review
      </el-button>
      <!-- debugging information -->
      <div v-if="isSubmitDisabled" style="font-size: 12px; color: #909399; margin-top: 8px; padding: 8px; background: #f5f7fa; border-radius: 4px;">
        <div>debugging information:</div>
        <div>• selectedTradeIds.length = {{ selectedTradeIds.length }}</div>
        <div>• trades.length = {{ trades.length }}</div>
        <div>• form.code = {{ form.code || '(empty)' }}</div>
        <div>• presetCode = {{ presetCode || '(None)' }}</div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { reviewApi, type TradeRecord, type ReviewType } from '@/api/review'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps<{
  modelValue: boolean
  presetCode?: string  // Default stock symbol
  source?: 'paper' | 'real'  // data source: paper(simulated trading) or real(User positions)
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success', reviewId: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// Default code (Use in template)
const presetCode = computed(() => props.presetCode)

const form = ref<{ code: string; review_type: ReviewType }>({
  code: '',
  review_type: 'complete_trade'
})

const trades = ref<TradeRecord[]>([])
const tradeSummary = ref<any>(null)
const selectedTradeIds = ref<string[]>([])
const submitting = ref(false)

// Computed property: whether the button is available
const isSubmitDisabled = computed(() => {
  const disabled = selectedTradeIds.value.length === 0
  console.log('[NewReviewDialog] Button status check', {
    selectedTradeIdsCount: selectedTradeIds.value.length,
    tradesCount: trades.value.length,
    code: form.value.code,
    disabled
  })
  return disabled
})

// Monitor changes in preset codes, automatically set and load transaction records
watch(() => props.presetCode, (newCode) => {
  if (newCode && visible.value) {
    form.value.code = newCode
    loadTrades()
  }
}, { immediate: true })

// The monitoring dialog box opens, and if there is a preset code, it will be automatically loaded.
watch(visible, (isVisible) => {
  if (isVisible && props.presetCode) {
    form.value.code = props.presetCode
    loadTrades()
  } else if (!isVisible) {
    // reset on shutdown
    form.value.code = ''
    trades.value = []
    tradeSummary.value = null
    selectedTradeIds.value = []
  }
})

onMounted(() => {
  console.log('[NewReviewDialog] Component is mounted', {
    modelValue: props.modelValue,
    presetCode: props.presetCode,
    source: props.source
  })
})

const loadTrades = async () => {
  console.log('[NewReviewDialog] loadTrades start', { code: form.value.code })
  
  if (!form.value.code) {
    console.log('[NewReviewDialog] The stock code is empty and the transaction record is cleared.')
    trades.value = []
    tradeSummary.value = null
    selectedTradeIds.value = []
    return
  }
  
  try {
    console.log('[NewReviewDialog] Call API to get transaction records', { code: form.value.code })
    const res = await reviewApi.getTradesByCode(form.value.code)
    console.log('[NewReviewDialog] API response', res)
    
    if (res.success) {
      trades.value = res.data?.trades || []
      tradeSummary.value = res.data?.summary || null
      // Select all by default
      selectedTradeIds.value = trades.value.map(t => t.trade_id)
      console.log('[NewReviewDialog] Transaction record loaded successfully', {
        tradesCount: trades.value.length,
        selectedTradeIdsCount: selectedTradeIds.value.length,
        selectedTradeIds: selectedTradeIds.value
      })
    } else {
      console.error('[NewReviewDialog] API Return failure', res)
      ElMessage.error(res.message || 'Failed to load transaction records')
    }
  } catch (e: any) {
    console.error('[NewReviewDialog] Exception loading transaction records', e)
    ElMessage.error(e.message || 'Failed to load transaction records')
  }
}

const handleSelectionChange = (selected: TradeRecord[]) => {
  selectedTradeIds.value = selected.map(t => t.trade_id)
}

const submit = async () => {
  console.log('[NewReviewDialog] Submit a review request', {
    selectedTradeIds: selectedTradeIds.value,
    selectedTradeIdsCount: selectedTradeIds.value.length,
    review_type: form.value.review_type,
    code: form.value.code,
    trades: trades.value
  })
  
  if (selectedTradeIds.value.length === 0) {
    console.warn('[NewReviewDialog] No transaction records selected')
    ElMessage.warning('Please select the transaction record to be reviewed')
    return
  }
  
  try {
    submitting.value = true
    const source = props.source || 'paper'  // Use simulated trading by default
    const requestData = {
      trade_ids: selectedTradeIds.value,
      review_type: form.value.review_type,
      code: form.value.code,
      source: source  // Pass data source parameters
    }
    console.log('[NewReviewDialog] Call to create a review API', requestData)
    
    const res = await reviewApi.createTradeReview(requestData)
    console.log('[NewReviewDialog] Create review API response', res)
    
    if (res.success && res.data?.review_id) {
      ElMessage.success('Review completed')
      emit('success', res.data.review_id)
    } else {
      console.error('[NewReviewDialog] Failed to create a replica', res)
      ElMessage.error(res.message || 'Review failed')
    }
  } catch (e: any) {
    console.error('[NewReviewDialog] Create review exception', e)
    ElMessage.error(e.message || 'Review failed')
  } finally {
    submitting.value = false
  }
}

// Processing when dialog box is shown/hidden
watch(visible, async (val) => {
  console.log('[NewReviewDialog] Dialog state changes', { visible: val, presetCode: props.presetCode })
  
  if (val) {
    // When opening the dialog box, if there is a preset code, it will be automatically loaded.
    if (props.presetCode) {
      console.log('[NewReviewDialog] Use default code', props.presetCode)
      form.value.code = props.presetCode
      await loadTrades()
    } else {
      console.log('[NewReviewDialog] No preset codes, need to be entered manually')
      // reset state
      form.value = { code: '', review_type: 'complete_trade' }
      trades.value = []
      tradeSummary.value = null
      selectedTradeIds.value = []
    }
  } else {
    // Reset form when closing dialog box
    console.log('[NewReviewDialog] Close the dialog box and reset the form')
    form.value = { code: '', review_type: 'complete_trade' }
    trades.value = []
    tradeSummary.value = null
    selectedTradeIds.value = []
  }
})
</script>

<style scoped lang="scss">
.preset-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.summary {
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
  span { margin-right: 16px; }
}
.positive { color: #f56c6c; }  // Chinese custom: red indicates profit (positive number)
.negative { color: #67c23a; }  // Chinese custom: green indicates loss (negative number)
</style>

