<template>
  <div class="market-category-management">
    <div class="header">
      <h3>Market classification management</h3>
      <el-button type="primary" icon="Plus" @click="showAddDialog">
        Add category
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="categories"
      style="width: 100%"
      row-key="id"
    >
      <el-table-column prop="sort_order" label="sort" width="80" sortable />
      
      <el-table-column prop="id" label="Classification ID" width="120" />
      
      <el-table-column prop="display_name" label="display name" width="120" />
      
      <el-table-column prop="description" label="Description" min-width="200" />
      
      <el-table-column label="Status" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'danger'" size="small">
            {{ row.enabled ? 'enable' : 'Disable' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Number of data sources" width="120">
        <template #default="{ row }">
          <el-tag type="info" size="small">
            {{ getDataSourceCount(row.id) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="creation time" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="Operation" width="200" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            @click="editCategory(row)"
          >
            Edit
          </el-button>
          <el-button
            size="small"
            :type="row.enabled ? 'warning' : 'success'"
            @click="toggleCategory(row)"
          >
            {{ row.enabled ? 'Disable' : 'enable' }}
          </el-button>
          <el-button
            size="small"
            type="danger"
            @click="deleteCategory(row)"
            :disabled="getDataSourceCount(row.id) > 0"
          >
            Delete
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Classification dialog box -->
    <MarketCategoryDialog
      v-model:visible="dialogVisible"
      :category="currentCategory"
      @success="handleSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { configApi, type MarketCategory, type DataSourceGrouping } from '@/api/config'
import MarketCategoryDialog from './MarketCategoryDialog.vue'

// Refs
const loading = ref(false)
const categories = ref<MarketCategory[]>([])
const groupings = ref<DataSourceGrouping[]>([])
const dialogVisible = ref(false)
const currentCategory = ref<MarketCategory | null>(null)

// Computed
const getDataSourceCount = computed(() => {
  return (categoryId: string) => {
    return groupings.value.filter(g => g.market_category_id === categoryId && g.enabled).length
  }
})

// Format date
const formatDate = (dateStr?: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

// Load data
const loadCategories = async () => {
  loading.value = true
  try {
    categories.value = await configApi.getMarketCategories()
    // Sort by sort order
    categories.value.sort((a, b) => a.sort_order - b.sort_order)
  } catch (error) {
    console.error('Failed to load market categories:', error)
    ElMessage.error('Failed to load market categories')
  } finally {
    loading.value = false
  }
}

const loadGroupings = async () => {
  try {
    groupings.value = await configApi.getDataSourceGroupings()
  } catch (error) {
    console.error('Failed to load grouping relationship:', error)
  }
}

// Show add dialog
const showAddDialog = () => {
  currentCategory.value = null
  dialogVisible.value = true
}

// Edit category
const editCategory = (category: MarketCategory) => {
  currentCategory.value = category
  dialogVisible.value = true
}

// Switch classification status
const toggleCategory = async (category: MarketCategory) => {
  try {
    await configApi.updateMarketCategory(category.id, {
      enabled: !category.enabled
    })
    
    category.enabled = !category.enabled
    ElMessage.success(`Classified${category.enabled ? 'enable' : 'Disable'}`)
  } catch (error) {
    console.error('Failed to switch classification status:', error)
    ElMessage.error('Failed to switch classification status')
  }
}

// Delete category
const deleteCategory = async (category: MarketCategory) => {
  const dataSourceCount = getDataSourceCount.value(category.id)
  
  if (dataSourceCount > 0) {
    ElMessage.warning('There are data sources under this category and cannot be deleted.')
    return
  }

  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete the market category? "${category.display_name}" ?`,
      'Confirm deletion',
      { type: 'warning' }
    )

    await configApi.deleteMarketCategory(category.id)
    await loadCategories()
    ElMessage.success('Market category deleted successfully')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete market category:', error)
      ElMessage.error('Failed to delete market category')
    }
  }
}

// Processed successfully
const handleSuccess = () => {
  loadCategories()
}

// life cycle
onMounted(() => {
  loadCategories()
  loadGroupings()
})
</script>

<style lang="scss" scoped>
.market-category-management {
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    h3 {
      margin: 0;
      color: #303133;
    }
  }
}
</style>
