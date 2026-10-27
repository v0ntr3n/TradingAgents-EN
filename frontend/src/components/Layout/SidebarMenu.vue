<template>
  <el-menu
    :default-active="activeMenu"
    :collapse="appStore.sidebarCollapsed"
    :unique-opened="true"
    router
    class="sidebar-menu"
  >
    <el-menu-item index="/dashboard">
      <el-icon><Odometer /></el-icon>
      <template #title>Dashboard</template>
    </el-menu-item>

    <el-menu-item index="/guide">
      <el-icon><Document /></el-icon>
      <template #title>User Guide</template>
    </el-menu-item>

    <el-menu-item index="/learning">
      <el-icon><Reading /></el-icon>
      <template #title>Learning Center</template>
    </el-menu-item>

    <el-menu-item index="/analysis/single">
      <el-icon><TrendCharts /></el-icon>
      <template #title>single stock research</template>
    </el-menu-item>

    <!-- Pro: Batch analysis (when the community version is released, the entire navigation.pro.ts file is replaced with an empty configuration, and the menu is automatically hidden) -->
    <el-menu-item v-for="item in proTopLevelItems" :key="item.path" :index="item.path">
      <el-icon><DataAnalysis /></el-icon>
      <template #title>
        {{ item.label }}
        <el-tag v-if="item.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
      </template>
    </el-menu-item>

    <el-menu-item index="/analysis/general">
      <el-icon><Search /></el-icon>
      <template #title>general studies</template>
    </el-menu-item>

    <el-menu-item index="/assistant">
      <el-icon><ChatDotRound /></el-icon>
      <template #title>Smart Assistant</template>
    </el-menu-item>

    <el-menu-item index="/memory">
      <el-icon><Coin /></el-icon>
      <template #title>AI memory</template>
    </el-menu-item>

    <!-- Skill Center (free and open starting from v3.6.0) -->
    <el-menu-item index="/skills">
      <el-icon><MagicStick /></el-icon>
      <template #title>Skill Center</template>
    </el-menu-item>

    <el-menu-item index="/reports">
      <el-icon><Document /></el-icon>
      <template #title>research report</template>
    </el-menu-item>

    <!-- Pro: Analysis flow submenu (automatically hidden when the community version is released, see navigation.pro.ts) -->
    <el-sub-menu :index="proWorkflowMenu.path">
      <template #title>
        <el-icon><SetUp /></el-icon>
        <span>{{ proWorkflowMenu.label }}</span>
        <el-tag v-if="proWorkflowMenu.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
      </template>
      <el-menu-item v-for="child in proWorkflowMenu.children" :key="child.path" :index="child.path">
        {{ child.label }}
        <el-tag v-if="child.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
        <el-tag v-else-if="child.badge" :type="child.badge.type" size="small" style="margin-left: 4px; transform: scale(0.85);">{{ child.badge.text }}</el-tag>
      </el-menu-item>
    </el-sub-menu>

    <el-menu-item index="/tasks/unified">
      <el-icon><List /></el-icon>
      <template #title>mission center</template>
    </el-menu-item>

    <el-menu-item index="/screening">
      <el-icon><Search /></el-icon>
      <template #title>stock screen</template>
    </el-menu-item>

    <el-menu-item index="/favorites">
      <el-icon><Star /></el-icon>
      <template #title>Stock Watchlist</template>
    </el-menu-item>

    <el-menu-item index="/paper">
      <el-icon><CreditCard /></el-icon>
      <template #title>simulated trading</template>
    </el-menu-item>

    <el-menu-item index="/portfolio">
      <el-icon><PieChart /></el-icon>
      <template #title>Position research</template>
    </el-menu-item>

    <el-menu-item index="/review">
      <el-icon><DocumentChecked /></el-icon>
      <template #title>Operation review</template>
    </el-menu-item>

    <!-- Pro: Trading plan (automatically hidden when the community version is released, see navigation.pro.ts) -->
    <el-menu-item v-for="item in proTradingSystemMenuItems" :key="item.path" :index="item.path">
      <el-icon><Tickets /></el-icon>
      <template #title>
        {{ item.label }}
        <el-tag v-if="item.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
      </template>
    </el-menu-item>

    <el-sub-menu index="/settings">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>settings</span>
      </template>

      <!-- personal settings -->
      <el-sub-menu index="/settings-personal">
        <template #title>personal settings</template>
        <el-menu-item index="/settings">General settings</el-menu-item>
        <el-menu-item index="/settings?tab=appearance">Appearance settings</el-menu-item>
        <el-menu-item index="/settings?tab=analysis">Analyze preferences</el-menu-item>
        <el-menu-item index="/settings?tab=notifications">Notification settings</el-menu-item>
        <el-menu-item index="/settings?tab=security">Security settings</el-menu-item>
        <el-menu-item index="/settings?tab=assistant">Assistant settings</el-menu-item>

        <!-- Pro: Personal settings items (automatically hidden when the community version is released, see navigation.pro.ts) -->
        <el-menu-item v-for="item in proPersonalSettingsItems" :key="item.path" :index="item.path">
          {{ item.label }}
          <el-tag v-if="item.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
        </el-menu-item>
        <el-menu-item v-if="!isJdyunMode() && proLicenseMenuItem" :index="proLicenseMenuItem.path">
          {{ proLicenseMenuItem.label }}
          <el-icon style="margin-left: 4px;"><Key /></el-icon>
        </el-menu-item>
      </el-sub-menu>

      <!-- System configuration -->
      <el-sub-menu index="/settings-config">
        <template #title>System configuration</template>
        <!-- JD Cloud mode: Display JD Cloud configuration status page (read-only), hide configuration management -->
        <el-menu-item v-if="isJdyunMode()" index="/settings/jdyun-config">System configuration</el-menu-item>
        <!-- Non-JD Cloud mode: display complete configuration management -->
        <el-menu-item v-else index="/settings/config">Configuration management</el-menu-item>
        <el-menu-item index="/settings/cache">Cache management</el-menu-item>
      </el-sub-menu>

      <!-- Analysis configuration -->
      <el-sub-menu index="/settings-analysis">
        <template #title>Analysis configuration</template>
        <!-- Pro: Analysis configuration items (automatically hidden when the community version is released, see navigation.pro.ts) -->
        <el-menu-item v-for="item in proAnalysisSettingsItems" :key="item.path" :index="item.path">
          {{ item.label }}
          <el-tag v-if="item.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
        </el-menu-item>
        <el-menu-item index="/settings/analysis-profiles">
          Industry/Stock Allocation
          <el-tag type="info" size="small" style="margin-left: 4px; transform: scale(0.85);">Smart</el-tag>
        </el-menu-item>
      </el-sub-menu>

      <!-- System management -->
      <el-sub-menu index="/settings-admin">
        <template #title>System management</template>
        <el-menu-item index="/settings/database">Database management</el-menu-item>
        <el-menu-item index="/settings/logs">Operation log</el-menu-item>
        <el-menu-item index="/settings/system-logs">System log</el-menu-item>
        <el-menu-item index="/settings/sync">Synchronization of multiple data sources</el-menu-item>
        <el-menu-item index="/settings/capability-index">Tool capability index</el-menu-item>
        <el-menu-item index="/settings/scheduler">scheduled tasks</el-menu-item>
        <!-- Pro: System management items (automatically hidden when the community version is released, see navigation.pro.ts) -->
        <el-menu-item v-for="item in proAdminSettingsItems" :key="item.path" :index="item.path">
          {{ item.label }}
          <el-tag v-if="item.advanced" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
        </el-menu-item>
        <el-menu-item index="/settings/data-import">
          Data import management
          <el-tag v-if="isAdvancedMenuItem('/settings/data-import')" type="success" size="small" style="margin-left: 4px; transform: scale(0.85);">Advanced</el-tag>
        </el-menu-item>
        <el-menu-item index="/settings/usage">usage statistics</el-menu-item>
        <el-menu-item index="/settings/update">System update</el-menu-item>
      </el-sub-menu>
    </el-sub-menu>

    <el-menu-item index="/about">
      <el-icon><InfoFilled /></el-icon>
      <template #title>About</template>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { isJdyunMode } from '@/utils/config'
// Pro Exclusive menu items (v3.6.0 community version open source separation M1): centrally configured in navigation.pro.ts,
// When the community version is released, the entire file is replaced with an empty configuration, and the Pro menu items are automatically not rendered.
import {
  proTopLevelItems,
  proTradingSystemMenuItems,
  proWorkflowMenu,
  proPersonalSettingsItems,
  proLicenseMenuItem,
  proAnalysisSettingsItems,
  proAdminSettingsItems
} from '@/config/navigation.pro'
import {
  Odometer,
  Reading,
  TrendCharts,
  DataAnalysis,
  Document,
  Search,
  Star,
  List,
  SetUp,
  Setting,
  InfoFilled,
  CreditCard,
  PieChart,
  DocumentChecked,
  Key,
  Tickets,
  ChatDotRound,
  Coin,
  MagicStick,
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()

const advancedMenuItems = new Set([
  '/settings/data-import'
])

const isAdvancedMenuItem = (index: string) => {
  // All modes are displayed uniformly"Advanced"Tag, the function is also available in JD Cloud mode (no charge, no authentication)
  return advancedMenuItems.has(index)
}

const activeMenu = computed(() => {
  if (route.path.startsWith('/workflow/agent-studio')) return '/workflow/agent-workshop'
  if (route.path.startsWith('/workflow/agent-workshop/')) return '/workflow/agent-workshop'
  return route.path
})
</script>

<style lang="scss" scoped>
.sidebar-menu {
  border: none;
  height: 100%;

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 48px;
    line-height: 48px;
  }

  :deep(.el-menu-item.is-active) {
    background-color: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
  }
}
</style>
