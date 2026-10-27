<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? 'Edit market category' : 'Add market category'"
    width="500px"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
      label-position="left"
    >
      <el-form-item label="Classification ID" prop="id">
        <el-input
          v-model="formData.id"
          placeholder="Please enter the category ID (English)"
          :disabled="isEdit"
        />
        <div class="form-help">Used for system internal identification, it is recommended to use English</div>
      </el-form-item>

      <el-form-item label="Category name" prop="name">
        <el-input
          v-model="formData.name"
          placeholder="Please enter the category name"
          :disabled="isEdit"
        />
        <div class="form-help">System internal name, usually the same as the ID</div>
      </el-form-item>

      <el-form-item label="display name" prop="display_name">
        <el-input
          v-model="formData.display_name"
          placeholder="Please enter a display name"
        />
        <div class="form-help">User interface display name</div>
      </el-form-item>

      <el-form-item label="sort order" prop="sort_order">
        <el-input-number
          v-model="formData.sort_order"
          :min="1"
          :max="100"
          controls-position="right"
          style="width: 200px"
        />
        <div class="form-help">The smaller the number, the higher the order is.</div>
      </el-form-item>

      <el-form-item label="Enabled status">
        <el-switch v-model="formData.enabled" />
      </el-form-item>

      <el-form-item label="Description" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="Please enter a category description"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">Cancel</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          {{ isEdit ? 'update' : 'Create' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { configApi, type MarketCategory } from '@/api/config'

// Props
interface Props {
  visible: boolean
  category?: MarketCategory | null
}

const props = withDefaults(defineProps<Props>(), {
  category: null
})

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

// Refs
const formRef = ref<FormInstance>()
const loading = ref(false)

// Computed
const isEdit = computed(() => !!props.category)

// form data
const defaultFormData = {
  id: '',
  name: '',
  display_name: '',
  description: '',
  enabled: true,
  sort_order: 1
}

const formData = ref({ ...defaultFormData })

// form validation rules
const rules: FormRules = {
  id: [
    { required: true, message: 'Please enter the category ID', trigger: 'blur' },
    { pattern: /^[a-z_]+$/, message: 'Category IDs can only contain lowercase letters and underscores', trigger: 'blur' }
  ],
  name: [{ required: true, message: 'Please enter the category name', trigger: 'blur' }],
  display_name: [{ required: true, message: 'Please enter a display name', trigger: 'blur' }],
  sort_order: [{ required: true, message: 'Please enter the sort order', trigger: 'blur' }]
}

// Monitor classification changes
watch(
  () => props.category,
  (category) => {
    if (category) {
      formData.value = { ...defaultFormData, ...category, description: category.description || '' }
    } else {
      formData.value = { ...defaultFormData }
    }
  },
  { immediate: true }
)

// Monitor visible changes
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      if (props.category) {
        formData.value = { ...defaultFormData, ...props.category, description: props.category.description || '' }
      } else {
        formData.value = { ...defaultFormData }
      }
    }
  }
)

// processing closed
const handleClose = () => {
  emit('update:visible', false)
}

// Handle submission
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    loading.value = true

    if (isEdit.value) {
      // Update category
      await configApi.updateMarketCategory(formData.value.id, formData.value)
      ElMessage.success('Market classification updated successfully')
    } else {
      // Create categories
      await configApi.addMarketCategory(formData.value)
      ElMessage.success('Market classification created successfully')
    }

    emit('success')
    handleClose()
  } catch (error) {
    console.error('Failed to save market category:', error)
    ElMessage.error('Failed to save market category')
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.form-help {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}

.dialog-footer {
  text-align: right;
}
</style>
