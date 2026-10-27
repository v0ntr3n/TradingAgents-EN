<template>
  <el-dialog v-model="visible" :title="`${position?.code} - ${position?.name} Position operation`" width="600px">
    <el-form v-if="position" :model="form" label-width="100px">
      <!-- Operation type selection -->
      <el-form-item label="Operation type">
        <el-radio-group v-model="form.operation_type">
          <el-radio value="add">Increase positions</el-radio>
          <el-radio value="reduce">Reduce positions</el-radio>
          <el-radio value="dividend">dividend</el-radio>
          <el-radio value="split">stock split</el-radio>
          <el-radio value="merge">partnership</el-radio>
          <el-radio value="adjust">Adjust cost price</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- Increase/reduce positions -->
      <template v-if="form.operation_type === 'add' || form.operation_type === 'reduce'">
        <el-form-item label="Quantity">
          <el-input-number v-model="form.quantity" :min="1" :max="1000000" :step="1" />
        </el-form-item>
        <el-form-item label="price">
          <el-input-number v-model="form.price" :min="0.01" :max="100000" :step="0.01" :precision="2" />
        </el-form-item>
        <el-form-item label="Date">
          <el-date-picker v-model="form.date" type="date" />
        </el-form-item>
      </template>

      <!-- dividend -->
      <template v-if="form.operation_type === 'dividend'">
        <el-form-item label="Dividend amount">
          <el-input-number v-model="form.dividend_amount" :min="0" :step="0.01" :precision="2" />
        </el-form-item>
        <el-form-item label="Dividend date">
          <el-date-picker v-model="form.date" type="date" />
        </el-form-item>
      </template>

      <!-- Stock split/share merger -->
      <template v-if="form.operation_type === 'split' || form.operation_type === 'merge'">
        <el-form-item label="Proportion">
          <el-input v-model="form.ratio" placeholder="For example: 2:1 or 1:2" />
        </el-form-item>
        <el-form-item label="Operation date">
          <el-date-picker v-model="form.date" type="date" />
        </el-form-item>
      </template>

      <!-- Adjust cost price -->
      <template v-if="form.operation_type === 'adjust'">
        <el-form-item label="Current cost price">
          <span class="text-gray-500">{{ position?.cost_price?.toFixed(2) }}</span>
        </el-form-item>
        <el-form-item label="new cost price">
          <el-input-number v-model="form.new_cost_price" :min="0.01" :max="100000" :step="0.01" :precision="2" />
        </el-form-item>
        <el-form-item label="Operation date">
          <el-date-picker v-model="form.date" type="date" />
        </el-form-item>
      </template>

      <el-form-item label="Remarks">
        <el-input v-model="form.notes" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">OK</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { PositionItem } from '@/api/portfolio'

interface AggregatedPosition extends PositionItem {
  position_count: number
  positions: PositionItem[]
}

const props = defineProps<{
  modelValue: boolean
  position: AggregatedPosition | null
  operationType?: 'add' | 'reduce' | 'dividend' | 'split' | 'merge' | 'adjust' | 'other'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'refresh'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const submitting = ref(false)
const form = ref({
  operation_type: 'add',
  quantity: 0,
  price: 0,
  dividend_amount: 0,
  ratio: '',
  new_cost_price: 0,
  date: new Date(),
  notes: ''
})

// Reset form
watch(() => visible.value, (val) => {
  if (val) {
    // Initialize the operation type according to operationType
    const typeMap: Record<string, string> = {
      'add': 'add',
      'reduce': 'reduce',
      'dividend': 'dividend',
      'split': 'split',
      'merge': 'merge',
      'adjust': 'adjust',
      'other': 'dividend'
    }
    const initialType = typeMap[props.operationType || 'add'] || 'add'

    form.value = {
      operation_type: initialType,
      quantity: 0,
      price: 0,
      dividend_amount: 0,
      ratio: '',
      new_cost_price: props.position?.cost_price || 0,
      date: new Date(),
      notes: ''
    }
  }
})

const handleSubmit = async () => {
  submitting.value = true
  try {
    const { portfolioApi } = await import('@/api/portfolio')

    if (!props.position) {
      ElMessage.error('Position information does not exist')
      return
    }

    const code = props.position.code
    const market = props.position.market

    // Build operation request
    const operationData: any = {
      operation_type: form.value.operation_type,
      code,
      market,
      notes: form.value.notes || undefined,
      operation_date: form.value.date ? new Date(form.value.date).toISOString() : undefined
    }

    // Add different parameters based on operation type
    if (form.value.operation_type === 'add' || form.value.operation_type === 'reduce') {
      if (!form.value.quantity || form.value.quantity <= 0) {
        ElMessage.error('Please enter a valid quantity')
        return
      }
      if (!form.value.price || form.value.price <= 0) {
        ElMessage.error('Please enter a valid price')
        return
      }
      operationData.quantity = form.value.quantity
      operationData.price = form.value.price
    } else if (form.value.operation_type === 'dividend') {
      if (!form.value.dividend_amount || form.value.dividend_amount <= 0) {
        ElMessage.error('Please enter a valid dividend amount')
        return
      }
      operationData.dividend_amount = form.value.dividend_amount
    } else if (form.value.operation_type === 'split' || form.value.operation_type === 'merge') {
      if (!form.value.ratio || !form.value.ratio.includes(':')) {
        ElMessage.error('Please enter a valid ratio, such as 2:1')
        return
      }
      operationData.ratio = form.value.ratio
    } else if (form.value.operation_type === 'adjust') {
      if (!form.value.new_cost_price || form.value.new_cost_price <= 0) {
        ElMessage.error('Please enter a valid new cost price')
        return
      }
      operationData.new_cost_price = form.value.new_cost_price
    }

    // Call unified position operation API
    const result = await portfolioApi.operatePosition(operationData)
    const operationResult = result.data ?? result

    // Display different success messages based on operation type
    if (form.value.operation_type === 'reduce' && operationResult.profit !== undefined) {
      const profitText = operationResult.profit >= 0 ? `Profit ${operationResult.profit.toFixed(2)}` : `Loss ${Math.abs(operationResult.profit).toFixed(2)}`
      ElMessage.success(`${operationResult.message}, ${profitText}Yuan (${operationResult.profit_pct?.toFixed(2)}%)`)
    } else {
      ElMessage.success(operationResult.message || 'Operation successful')
    }

    visible.value = false
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e.message || 'Operation failed')
  } finally {
    submitting.value = false
  }
}
</script>
