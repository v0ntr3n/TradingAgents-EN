<template>
  <div class="basic-layout">
    <!-- sidebar -->
    <aside
      class="sidebar"
      :class="{ collapsed: appStore.sidebarCollapsed }"
      :style="{ width: appStore.actualSidebarWidth + 'px' }"
    >
      <div class="sidebar-header">
        <div class="logo">
          <img src="/favicon.ico" alt="TradingAgents-CN" />
          <span v-show="!appStore.sidebarCollapsed" class="logo-text">
            TradingAgents-CN
          </span>
        </div>
      </div>
      
      <nav class="sidebar-nav">
        <SidebarMenu />
      </nav>
      
      <div class="sidebar-footer">
        <UserProfile />
      </div>
    </aside>

    <!-- Click on the mask: When the mobile terminal is expanded, click on the blank space to collapse the sidebar. -->
    <div
      v-if="isMobile && !appStore.sidebarCollapsed"
      class="sidebar-overlay"
      @click="appStore.setSidebarCollapsed(true)"
    ></div>

    <!-- Main content area -->
    <div class="main-container" :style="{ marginLeft: appStore.actualSidebarWidth + 'px' }" @click="handleMainClick">
      <!-- Authorization status reminder bar -->
      <LicenseAlert />

      <!-- top navigation bar -->
      <header class="header">
        <div class="header-left">
          <el-button
            type="text"
            @click.stop="appStore.toggleSidebar()"
            class="sidebar-toggle"
          >
            <el-icon><Expand v-if="appStore.sidebarCollapsed" /><Fold v-else /></el-icon>
          </el-button>
          
          <Breadcrumb />
        </div>
        
        <div class="header-right">
          <HeaderActions />
        </div>
      </header>

      <!-- Page content -->
      <main class="main-content">
        <div class="content-wrapper" :class="{ 'content-wrapper--full': isFullWidthRoute }">
          <router-view v-slot="{ Component, route }">
            <transition
              :name="route.meta.transition || 'fade'"
              mode="out-in"
              appear
            >
              <keep-alive :include="keepAliveComponents">
                <component :is="Component" :key="route.fullPath" />
              </keep-alive>
            </transition>
          </router-view>
        </div>
      </main>

      <!-- footer -->
      <footer v-if="!hideFooterRoute" class="footer">
        <AppFooter />
      </footer>
    </div>

    <!-- back to top -->
    <el-backtop :right="40" :bottom="40" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useWindowSize } from '@vueuse/core'
import { useAppStore } from '@/stores/app'
import SidebarMenu from '@/components/Layout/SidebarMenu.vue'
import UserProfile from '@/components/Layout/UserProfile.vue'
import Breadcrumb from '@/components/Layout/Breadcrumb.vue'
import HeaderActions from '@/components/Layout/HeaderActions.vue'
import AppFooter from '@/components/Layout/AppFooter.vue'
import LicenseAlert from '@/components/Layout/LicenseAlert.vue'
import { Expand, Fold } from '@element-plus/icons-vue'

const appStore = useAppStore()
const route = useRoute()
const { width } = useWindowSize()

// Components that need to be cached
const keepAliveComponents = computed(() => [
  'Dashboard',
  'StockScreening',
  'AnalysisHistory',
  'QueueManagement'
])

const isFullWidthRoute = computed(() => {
  return route.path.startsWith('/assistant') || route.path.startsWith('/workflow/agent-studio')
})

const hideFooterRoute = computed(() => {
  return route.path.startsWith('/workflow/agent-studio')
})

// Mobile terminal judgment
const isMobile = computed(() => width.value < 768)

// When clicking on the main content, if the mobile terminal and the sidebar are expanded, they will be collapsed.
const handleMainClick = () => {
  if (isMobile.value && !appStore.sidebarCollapsed) {
    appStore.setSidebarCollapsed(true)
  }
}

// Listen for window size changes: automatically collapse the sidebar on small screens
watch(width, (newWidth) => {
  if (newWidth < 768 && !appStore.sidebarCollapsed) {
    appStore.setSidebarCollapsed(true)
  }
})

// When the route changes, the mobile terminal closes the sidebar
watch(() => route.fullPath, () => {
  if (isMobile.value) {
    appStore.setSidebarCollapsed(true)
  }
})
</script>

<style lang="scss" scoped>
.basic-layout {
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 950; // below sidebar(1000), above content area
}

.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  background-color: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  transition: width 0.3s ease;
  z-index: 1000;
  display: flex;
  flex-direction: column;

  &.collapsed {
    width: 64px !important;
  }

  .sidebar-header {
    height: 60px;
    display: flex;
    align-items: center;
    padding: 0 16px;
    border-bottom: 1px solid var(--el-border-color-lighter);

    .logo {
      display: flex;
      align-items: center;
      gap: 12px;

      img {
        width: 32px;
        height: 32px;
      }

      .logo-text {
        font-size: 18px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        white-space: nowrap;
      }
    }
  }

  .sidebar-nav {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .sidebar-footer {
    border-top: 1px solid var(--el-border-color-lighter);
    padding: 8px;
  }
}

.main-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: margin-left 0.3s ease;
}

.header {
  height: 60px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 999;

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;

    .sidebar-toggle {
      padding: 8px;
      
      .el-icon {
        font-size: 18px;
      }
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }
}

.main-content {
  flex: 1;
  padding: 24px;
  // min-height removed to allow flex container to handle height naturally and avoid overflow with variable footer height
  
  .content-wrapper {
    max-width: 1400px;
    margin: 0 auto;

    &.content-wrapper--full {
      max-width: none;
      width: 100%;
    }
  }
}

.footer {
  height: auto;
  min-height: 60px;
  background-color: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px 0;
}

// Responsive design
@media (max-width: 768px) {
  .sidebar {
    transform: translateX(-100%);
    
    &:not(.collapsed) {
      transform: translateX(0);
    }
  }

  .main-container {
    margin-left: 0 !important;
  }

  .main-content {
    padding: 16px;
  }

  .header {
    padding: 0 16px;
  }
}

// Route transition animation
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease;
}

.slide-left-enter-from {
  transform: translateX(30px);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(-30px);
  opacity: 0;
}
</style>

