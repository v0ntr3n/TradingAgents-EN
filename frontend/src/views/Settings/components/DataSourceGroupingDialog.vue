<template>
  <el-dialog
    :model-value="visible"
    :title="`Manage data source groupings - ${dataSourceName}`"
    width="600px"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="grouping-content">
      <div class="section">
        <h4>Available market categories</h4>
        <div class="category-list">
          <div
            v-for="category in availableCategories"
            :key="category.id"
            class="category-item"
          >
            <div class="category-info">
              <el-tag :type="category.enabled ? 'success' : 'info'" size="small">
                {{ category.display_name }}
              </el-tag>
              <span class="category-desc">{{ category.description }}</span>
            </div>
            <div class="category-actions">
              <el-input-number
                v-model="categoryPriorities[category.id]"
                :min="0"
                :max="100"
                size="small"
                controls-position="right"
                placeholder="priority"
                style="width: 100px; margin-right: 8px"
              />
              <el-button
                size="small"
                type="primary"
                @click="addToCategory(category.id)"
                :disabled="!category.enabled"
              >
                add
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <el-divider />

      <div class="section">
        <h4>Categories added</h4>
        <div class="assigned-list">
          <div
            v-for="grouping in currentGroupings"
            :key="grouping.market_category_id"
            class="assigned-item"
          >
            <div class="assigned-info">
              <el-tag
                :type="grouping.enabled ? 'success' : 'warning'"
                size="small"
              >
                {{ getCategoryDisplayName(grouping.market_category_id) }}
              </el-tag>
              <span class="priority-info">priority: {{ grouping.priority }}</span>
            </div>
            <div class="assigned-actions">
              <el-input-number
                v-model="grouping.priority"
                :min="0"
                :max="100"
                size="small"
                controls-position="right"
                style="width: 100px; margin-right: 8px"
                @change="updateGroupingPriority(grouping)"
              />
              <el-button
                size="small"
                :type="grouping.enabled ? 'warning' : 'success'"
                @click="toggleGrouping(grouping)"
              >
                {{ grouping.enabled ? 'Disable' : 'enable' }}
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="removeFromCategory(grouping.market_category_id)"
              >
                Remove
              </el-button>
            </div>
          </div>
          
          <div v-if="currentGroupings.length === 0" class="empty-state">
            <el-empty description="This data source has not yet been added to any market categories" :image-size="80" />
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">close</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          Save changes
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  configApi, 
  type MarketCategory, 
  type DataSourceGrouping 
} from '@/api/config'

// Props
interface Props {
  visible: boolean
  dataSourceName: string
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

// Refs
const saving = ref(false)
const categories = ref<MarketCategory[]>([])
const allGroupings = ref<DataSourceGrouping[]>([])
const categoryPriorities = ref<Record<string, number>>({})

// Computed
const currentGroupings = computed(() => {
  return allGroupings.value.filter(g => g.data_source_name === props.dataSourceName)
})

const availableCategories = computed(() => {
  const assignedCategoryIds = currentGroupings.value.map(g => g.market_category_id)
  return categories.value.filter(c => !assignedCategoryIds.includes(c.id))
})

// Get category display name
const getCategoryDisplayName = (categoryId: string) => {
  const category = categories.value.find(c => c.id === categoryId)
  return category?.display_name || categoryId
}

// Load data
const loadData = async () => {
  try {
    const [categoriesData, groupingsData] = await Promise.all([
      configApi.getMarketCategories(),
      configApi.getDataSourceGroupings()
    ])
    
    categories.value = categoriesData.filter(c => c.enabled)
    allGroupings.value = groupingsData
    
    // Initialization priority
    categories.value.forEach(category => {
      categoryPriorities.value[category.id] = 0
    })
  } catch (error) {
    console.error('Failed to load data:', error)
    ElMessage.error('Failed to load data')
  }
}

// Add to category
const addToCategory = async (categoryId: string) => {
  try {
    const priority = categoryPriorities.value[categoryId] || 0
    await configApi.addDataSourceToCategory(props.dataSourceName, categoryId, priority)
    
    // Update local data
    allGroupings.value.push({
      data_source_name: props.dataSourceName,
      market_category_id: categoryId,
      priority: priority,
      enabled: true
    })
    
    ElMessage.success('Added to category successfully')
  } catch (error) {
    console.error('Failed to add to category:', error)
    ElMessage.error('Failed to add to category')
  }
}

// Remove from category
const removeFromCategory = async (categoryId: string) => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to remove this data source from this category?',
      'Confirm removal',
      { type: 'warning' }
    )

    await configApi.removeDataSourceFromCategory(props.dataSourceName, categoryId)
    
    // Update local data
    const index = allGroupings.value.findIndex(
      g => g.data_source_name === props.dataSourceName && g.market_category_id === categoryId
    )
    if (index > -1) {
      allGroupings.value.splice(index, 1)
    }
    
    ElMessage.success('Removed from category successfully')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Removal failed:', error)
      ElMessage.error('Removal failed')
    }
  }
}

// Switch group status
const toggleGrouping = async (grouping: DataSourceGrouping) => {
  try {
    const newEnabled = !grouping.enabled
    await configApi.updateDataSourceGrouping(
      grouping.data_source_name,
      grouping.market_category_id,
      { enabled: newEnabled }
    )
    
    grouping.enabled = newEnabled
    ElMessage.success(`Grouped${newEnabled ? 'enable' : 'Disable'}`)
  } catch (error) {
    console.error('Failed to switch group status:', error)
    ElMessage.error('Failed to switch group status')
  }
}

// Update group priority
const updateGroupingPriority = async (grouping: DataSourceGrouping) => {
  try {
    await configApi.updateDataSourceGrouping(
      grouping.data_source_name,
      grouping.market_category_id,
      { priority: grouping.priority }
    )
  } catch (error) {
    console.error('Update priority failed:', error)
    ElMessage.error('Update priority failed')
  }
}

// Monitor visible changes
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadData()
    }
  }
)

// processing closed
const handleClose = () => {
  emit('update:visible', false)
}

// Process save
const handleSave = () => {
  emit('success')
  handleClose()
}

// life cycle
onMounted(() => {
  if (props.visible) {
    loadData()
  }
})
</script>

<style lang="scss" scoped>
.grouping-content {
  .section {
    margin-bottom: 20px;

    h4 {
      margin: 0 0 12px 0;
      color: #303133;
      font-size: 14px;
    }
  }

  .category-list {
    .category-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px;
      border: 1px solid #ebeef5;
      border-radius: 4px;
      margin-bottom: 8px;

      .category-info {
        flex: 1;
        display: flex;
        align-items: center;
        gap: 8px;

        .category-desc {
          color: #909399;
          font-size: 12px;
        }
      }

      .category-actions {
        display: flex;
        align-items: center;
      }
    }
  }

  .assigned-list {
    .assigned-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px;
      background: #f5f7fa;
      border-radius: 4px;
      margin-bottom: 8px;

      .assigned-info {
        flex: 1;
        display: flex;
        align-items: center;
        gap: 8px;

        .priority-info {
          color: #909399;
          font-size: 12px;
        }
      }

      .assigned-actions {
        display: flex;
        align-items: center;
      }
    }

    .empty-state {
      text-align: center;
      padding: 20px;
    }
  }
}

.dialog-footer {
  text-align: right;
}
</style>
