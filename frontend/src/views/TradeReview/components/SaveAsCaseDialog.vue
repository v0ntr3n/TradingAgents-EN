<template>
  <el-dialog
    v-model="visible"
    title="Save to case library"
    width="500px"
    @close="handleClose"
  >
    <el-form :model="form" label-width="80px">
      <el-form-item label="Stock code">
        <el-input v-model="stockCode" disabled />
      </el-form-item>
      
      <el-form-item label="label">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          placeholder="Select or create a label (optional)"
          style="width: 100%"
        >
          <el-option
            v-for="tag in availableTags"
            :key="tag"
            :label="tag"
            :value="tag"
          />
        </el-select>
        <div style="margin-top: 8px; font-size: 12px; color: #909399;">
          Tip: You can enter a new label and press Enter to create it
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        save
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { reviewApi } from '@/api/review'

const props = defineProps<{
  modelValue: boolean
  reviewId: string
  stockCode?: string
  source?: 'paper' | 'position' | 'real'  // data source: paper(simulated trading) or position(Position operation)
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const form = ref({
  tags: [] as string[]
})

const submitting = ref(false)

// Common tags (can be obtained from the backend)
const availableTags = ref([
  'Success Stories',
  'Failure case',
  'Stop loss in time',
  'Taking profit too early',
  'Chasing the rise and killing the fall',
  'Going against the trend',
  'Position management',
  'Emotional trading',
  'Strong discipline',
  'Needs improvement'
])

const stockCode = computed(() => props.stockCode || '')

const handleClose = () => {
  form.value.tags = []
}

const submit = async () => {
  try {
    submitting.value = true
    const res = await reviewApi.saveAsCase({
      review_id: props.reviewId,
      tags: form.value.tags,
      source: props.source  // Pass data source parameters
    })
    
    if (res.success) {
      ElMessage.success('Saved to case library')
      emit('success')
      visible.value = false
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Save failed')
  } finally {
    submitting.value = false
  }
}

// The listening dialog box opens and the form is reset.
watch(visible, (val) => {
  if (val) {
    form.value.tags = []
  }
})
</script>

<style scoped lang="scss">
// Styles can be added as needed
</style>

