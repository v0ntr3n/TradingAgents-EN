<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="Review cycle" required>
        <el-radio-group v-model="form.period_type" @change="handlePeriodTypeChange">
          <el-radio value="week">Weekly</el-radio>
          <el-radio value="month">monthly</el-radio>
          <el-radio value="quarter">quarter</el-radio>
          <el-radio value="year">annual</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="time range" required>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="to"
          start-placeholder="start date"
          end-placeholder="end date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
          :shortcuts="dateShortcuts"
        />
      </el-form-item>

      <el-form-item>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            {{ alertText }}
          </template>
        </el-alert>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!dateRange" @click="submit">
        Start review
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { reviewApi, type PeriodType } from '@/api/review'

const props = withDefaults(defineProps<{
  modelValue: boolean
  source?: 'paper' | 'position'  // data source: paper(simulated trading) or position(Position operation)
}>(), {
  source: 'paper'
})
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success', reviewId: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const dialogTitle = computed(() => {
  return props.source === 'position' ? 'Initiate a periodic review (position operation)' : 'Initiate periodic review (simulated trading)'
})

const alertText = computed(() => {
  return props.source === 'position'
    ? 'The periodic review will analyze all position operations within the selected time period and generate a comprehensive assessment report'
    : 'The periodic review will analyze all simulated transactions within the selected time period and generate a comprehensive evaluation report'
})

const form = ref<{ period_type: PeriodType }>({
  period_type: 'month'
})

const dateRange = ref<[string, string] | null>(null)
const submitting = ref(false)

// Date shortcut options
const dateShortcuts = [
  {
    text: 'last week',
    value: () => {
      const end = new Date()
      const start = new Date()
      const day = end.getDay() || 7
      end.setDate(end.getDate() - day)
      start.setDate(end.getDate() - 6)
      return [start, end]
    }
  },
  {
    text: 'this month',
    value: () => {
      const end = new Date()
      const start = new Date(end.getFullYear(), end.getMonth(), 1)
      return [start, end]
    }
  },
  {
    text: 'last month',
    value: () => {
      const end = new Date()
      end.setDate(0) // last day of last month
      const start = new Date(end.getFullYear(), end.getMonth(), 1)
      return [start, end]
    }
  },
  {
    text: 'this quarter',
    value: () => {
      const end = new Date()
      const quarter = Math.floor(end.getMonth() / 3)
      const start = new Date(end.getFullYear(), quarter * 3, 1)
      return [start, end]
    }
  },
  {
    text: 'this year',
    value: () => {
      const end = new Date()
      const start = new Date(end.getFullYear(), 0, 1)
      return [start, end]
    }
  }
]

// Update date range based on period type
const updateDateRange = (type: PeriodType) => {
  const now = new Date()
  let start: Date, end: Date
  
  switch (type) {
    case 'week':
      end = new Date()
      start = new Date()
      start.setDate(end.getDate() - 7)
      break
    case 'month':
      end = new Date()
      start = new Date(now.getFullYear(), now.getMonth(), 1)
      break
    case 'quarter': {
      end = new Date()
      const quarter = Math.floor(now.getMonth() / 3)
      start = new Date(now.getFullYear(), quarter * 3, 1)
      break
    }
    case 'year':
      end = new Date()
      start = new Date(now.getFullYear(), 0, 1)
      break
  }
  
  const formatDate = (d: Date) => d.toISOString().split('T')[0]
  dateRange.value = [formatDate(start), formatDate(end)]
}

const handlePeriodTypeChange = (type: string | number | boolean | undefined) => {
  if (typeof type !== 'string') {
    return
  }
  updateDateRange(type as PeriodType)
}

const submit = async () => {
  if (!dateRange.value || dateRange.value.length !== 2) {
    ElMessage.warning('Please select a time range')
    return
  }

  try {
    submitting.value = true
    const res = await reviewApi.createPeriodicReview({
      period_type: form.value.period_type,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
      source: props.source
    })

    if (res.success && res.data?.review_id) {
      ElMessage.success('Phased review completed')
      emit('success', res.data.review_id)
    } else {
      ElMessage.error(res.message || 'Review failed')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Review failed')
  } finally {
    submitting.value = false
  }
}

// Initialize date range
watch(visible, (val) => {
  if (val) {
    updateDateRange(form.value.period_type)
  }
})
</script>

