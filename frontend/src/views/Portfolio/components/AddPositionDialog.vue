<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="isEdit ? 'Edit positions' : 'Add position'"
    width="500px"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="Stock code" prop="code">
        <el-input v-model="form.code" placeholder="Such as: 600519, 510300, AAPL" :disabled="isEdit" />
      </el-form-item>
      <el-form-item label="Stock name" prop="name">
        <el-input 
          v-model="form.name" 
          placeholder="Optional, automatically obtained"
          :disabled="loadingStockName"
        >
          <template #suffix>
            <el-icon v-if="loadingStockName" class="is-loading">
              <Loading />
            </el-icon>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="market" prop="market">
        <el-select v-model="form.market" style="width: 100%">
          <el-option label="A shares" value="CN" />
          <el-option label="ETF" value="ETF" />
        </el-select>
        <div v-if="form.market === 'ETF'" style="font-size: 12px; color: #909399; margin-top: 4px;">
          ETF The position will be stored and priced according to the A-share account (CNY), but the front-end will retain the ETF semantics.
        </div>
      </el-form-item>
      <el-form-item label="Position quantity" prop="quantity">
        <el-input-number v-model="form.quantity" :min="1" :step="100" style="width: 100%" />
      </el-form-item>
      <el-form-item label="cost price" prop="cost_price">
        <el-input-number v-model="form.cost_price" :min="0.01" :precision="2" :step="0.1" style="width: 100%" />
      </el-form-item>
      <el-form-item label="Purchase date" prop="buy_date" required>
        <el-date-picker v-model="form.buy_date" type="date" placeholder="Required, used to verify cost price" style="width: 100%" />
      </el-form-item>
      <el-form-item label="Remarks" prop="notes">
        <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="Optional" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="$emit('update:visible', false)">Cancel</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        {{ isEdit ? 'save' : 'add' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { portfolioApi, type PositionItem, type PositionCreatePayload } from '@/api/portfolio'
import { stocksApi } from '@/api/stocks'
import { getMarketByStockCode } from '@/utils/market'
import { formatLocalDate } from '@/utils/datetime'

const props = defineProps<{
  visible: boolean
  editData?: PositionItem | null
  initialData?: {
    code?: string
    name?: string
    market?: string
    cost_price?: number
  } | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const loadingStockName = ref(false)
let fetchStockNameTimer: ReturnType<typeof setTimeout> | null = null
// 🔥 Record the stock code corresponding to the last time the name was automatically obtained, which is used to determine whether the name needs to be updated.
const lastFetchedCode = ref<string>('')

const isEdit = computed(() => !!props.editData)

const normalizeUiMarket = (market?: string, code?: string) => {
  if (market === 'CN' && code && getMarketByStockCode(code) === 'ETF') return 'ETF'
  return market || 'CN'
}

const normalizeSubmitMarket = (market?: string) => market === 'ETF' ? 'CN' : (market || 'CN')

const form = ref<PositionCreatePayload & { buy_date?: Date | string }>({
  code: '',
  name: '',
  market: 'CN',
  quantity: 100,
  cost_price: 10,
  buy_date: undefined,
  notes: ''
})

// The purchase date is required when adding (used to verify the cost price), and is optional when editing.
const rules = computed<FormRules>(() => ({
  code: [{ required: true, message: 'Please enter stock code', trigger: 'blur' }],
  quantity: [{ required: true, message: 'Please enter the position quantity', trigger: 'blur' }],
  cost_price: [{ required: true, message: 'Please enter cost price', trigger: 'blur' }],
  buy_date: isEdit.value ? [] : [{ required: true, message: 'Please select the purchase date to verify that the cost price is correct', trigger: 'change' }]
}))

// 🔥 Automatically obtain stock names
const fetchStockName = async (code: string) => {
  if (!code || code.trim().length === 0) {
    return
  }
  
  // Not automatically obtained in edit mode
  if (isEdit.value) {
    return
  }
  
  // 🔥 Fix issue 1: For the A-share market, only query when the code length is 6 digits
  const trimmedCode = code.trim()
  if ((form.value.market === 'CN' || form.value.market === 'ETF') && trimmedCode.length !== 6) {
    // A The stock/ETF code must be 6 digits. If the entire code is not entered, the query will not be performed.
    return
  }
  
  // 🔥 Fix issue 3: If the code is changed and the name is obtained automatically, the query should be re-queried
  const currentName = form.value.name?.trim() || ''
  const isCodeChanged = trimmedCode !== lastFetchedCode.value
  
  // If the code changes and the name is automatically obtained (judged by lastFetchedCode), re-query is allowed
  // If the name is entered manually by the user (lastFetchedCode is empty or does not match the current code), it is not automatically overwritten.
  if (currentName.length > 0 && currentName !== 'Optional, automatically obtained' && !isCodeChanged) {
    // The name is not empty and the code has not changed, indicating that it was entered manually by the user and is not automatically overwritten.
    return
  }
  
  // Clear previous timer
  if (fetchStockNameTimer) {
    clearTimeout(fetchStockNameTimer)
    fetchStockNameTimer = null
  }
  
  // Anti-shake: executed after 500ms
  fetchStockNameTimer = setTimeout(async () => {
    try {
      loadingStockName.value = true
      const res = await stocksApi.getQuote(trimmedCode)
      
      if (res.success && res.data) {
        const stockName = res.data.name
        if (stockName) {
          form.value.name = stockName
          // 🔥 Record the stock code of this query, used to determine whether the name is automatically obtained.
          lastFetchedCode.value = trimmedCode
          // If market information is obtained, the market will also be automatically updated.
          if (res.data.market) {
            const marketMap: Record<string, string> = {
              'A shares': 'CN',
              'ETF': 'ETF'
            }
            const marketCode = marketMap[res.data.market] || form.value.market
            if (marketCode !== form.value.market) {
              form.value.market = marketCode
            }
          }
        }
      }
    } catch (error: any) {
      // Fail silently, no error message is displayed (because the stock name is optional)
      console.debug('Failed to automatically obtain stock name:', error)
    } finally {
      loadingStockName.value = false
    }
  }, 500)
}

// Monitor stock code changes
watch(() => form.value.code, (newCode, oldCode) => {
  const trimmedNewCode = newCode?.trim() || ''
  const trimmedOldCode = oldCode?.trim() || ''
  
  // 🔥 Fix problem 2: Ensure that every code change can trigger the query (if the conditions are met)
  // Clear the previous timer to ensure that new input can trigger new queries
  if (fetchStockNameTimer) {
    clearTimeout(fetchStockNameTimer)
    fetchStockNameTimer = null
  }
  
  if (trimmedNewCode.length > 0) {
    // Only query when the code changes (avoid querying the same code repeatedly)
    if (trimmedNewCode !== trimmedOldCode) {
      // 🔥 Fix problem 3: If the code is changed and the name is obtained automatically, clear the name first
      // Determine whether the name is obtained automatically: If lastFetchedCode is equal to the old code, it means the name is obtained automatically
      if (lastFetchedCode.value === trimmedOldCode && form.value.name && form.value.name.trim().length > 0) {
        // The name is obtained automatically. If the code changes, clear the name to query again.
        form.value.name = ''
        lastFetchedCode.value = ''
      }
      fetchStockName(newCode)
    }
  } else {
    // When the code is cleared, the name and record are also cleared
    form.value.name = ''
    lastFetchedCode.value = ''
  }
})

watch(() => props.visible, (val) => {
  if (val && props.editData) {
    form.value = {
      code: props.editData.code,
      name: props.editData.name || '',
      market: normalizeUiMarket(props.editData.market, props.editData.code),
      quantity: props.editData.quantity,
      cost_price: props.editData.cost_price,
      buy_date: props.editData.buy_date || undefined,
      notes: props.editData.notes || ''
    }
    // In edit mode, reset the automatic acquisition record
    lastFetchedCode.value = ''
  } else if (val) {
    const init = props.initialData
    form.value = {
      code: init?.code || '',
      name: init?.name || '',
      market: init?.market || 'CN',
      quantity: 100,
      cost_price: init?.cost_price ?? 10,
      buy_date: undefined,
      notes: ''
    }
    // If there is a pre-filled code, it will be recorded as automatically obtained to avoid being cleared by watch.
    if (init?.code) {
      lastFetchedCode.value = init.code
    } else {
      lastFetchedCode.value = ''
    }
    // Clear timers and records
    if (fetchStockNameTimer) {
      clearTimeout(fetchStockNameTimer)
      fetchStockNameTimer = null
    }
    loadingStockName.value = false
  }
})

const handleSubmit = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    submitting.value = true
    
    const payload: PositionCreatePayload = {
      code: form.value.code,
      name: form.value.name || undefined,
      market: normalizeSubmitMarket(form.value.market),
      quantity: form.value.quantity,
      cost_price: form.value.cost_price,
      buy_date: form.value.buy_date ? formatLocalDate(form.value.buy_date) : undefined,
      notes: form.value.notes || undefined
    }
    
    if (isEdit.value && props.editData) {
      await portfolioApi.updatePosition(props.editData.id, {
        name: payload.name,
        quantity: payload.quantity,
        cost_price: payload.cost_price,
        buy_date: payload.buy_date,
        notes: payload.notes
      })
      ElMessage.success('Update successful')
    } else {
      await portfolioApi.addPosition(payload)
      ElMessage.success('Added successfully')
    }
    
    emit('success')
  } catch (e: any) {
    // The error has been shown in the API interceptor and will not be repeated here
    // Only log for debugging
    console.error('Failed to add/update position:', e)
  } finally {
    submitting.value = false
  }
}
</script>

