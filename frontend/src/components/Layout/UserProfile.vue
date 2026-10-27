<template>
  <div class="user-profile" :class="{ collapsed: appStore.sidebarCollapsed }">
    <!-- Student level display -->
    <div v-if="!appStore.sidebarCollapsed" class="license-badge" @click="goToLicense">
      <el-tag
        :type="licenseTagType"
        size="small"
        effect="dark"
        class="license-tag"
      >
        <el-icon v-if="licenseStore.isPro" style="margin-right: 2px;"><Star /></el-icon>
        {{ licenseLabel }}
      </el-tag>
      <span v-if="licenseStore.daysRemaining !== null && licenseStore.daysRemaining > 0" class="expire-hint">
        {{ licenseStore.daysRemaining }}Expires after days
      </span>
    </div>
    <div v-else class="license-badge-mini" @click="goToLicense">
      <el-tooltip :content="licenseLabel" placement="right">
        <el-icon :color="licenseIconColor" :size="18"><Star v-if="licenseStore.isPro" /><UserFilled v-else /></el-icon>
      </el-tooltip>
    </div>

    <!-- User information -->
    <el-dropdown trigger="click" @command="handleCommand">
      <div class="profile-info">
        <el-avatar :size="32" :src="userAvatar">
          <el-icon><User /></el-icon>
        </el-avatar>
        <div v-if="!appStore.sidebarCollapsed" class="user-info">
          <div class="username">{{ userDisplayName }}</div>
          <div class="user-role">{{ userRole }}</div>
        </div>
      </div>

      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="settings">
            <el-icon><Setting /></el-icon>
            settings
          </el-dropdown-item>
          <el-dropdown-item divided command="logout">
            <el-icon><SwitchButton /></el-icon>
            Log out
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useLicenseStore } from '@/stores/license'
import { User, Setting, SwitchButton, Star, UserFilled } from '@element-plus/icons-vue'

// 🔧 Jingdong cloud model
const isJdyunMode = import.meta.env.VITE_JDYUN_MODE === 'true'

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const licenseStore = useLicenseStore()

// User avatar: Give priority to the avatar set by the user, otherwise return undefined and use the default icon of el-avatar.
const userAvatar = computed(() => authStore.user?.avatar || undefined)
const userDisplayName = computed(() => authStore.user?.username || 'Not logged in')
const userRole = computed(() => {
  if (!authStore.user) return 'Not logged in'
  return 'User'
})

// Related to student level
const licenseLabel = computed(() => {
  // 🔧 JD Cloud Mode: Display"Jingdong cloud version"
  if (isJdyunMode) return 'Jingdong cloud version'
  const plan = licenseStore.plan
  if (plan === 'enterprise') return 'lifelong senior student'
  if (plan === 'pro') return 'Senior student'
  if (plan === 'trial') return 'Experience senior students'
  return 'junior student'
})

const licenseTagType = computed(() => {
  // 🔧 JD Cloud mode: use primary style
  if (isJdyunMode) return 'primary'
  const plan = licenseStore.plan
  if (['enterprise', 'pro'].includes(plan)) return 'success'
  if (plan === 'trial') return 'warning'
  return 'info'
})

const licenseIconColor = computed(() => {
  // 🔧 JD Cloud Mode: Use Blue
  if (isJdyunMode) return '#409eff'
  const plan = licenseStore.plan
  if (['enterprise', 'pro'].includes(plan)) return '#67c23a'
  if (plan === 'trial') return '#e6a23c'
  return '#909399'
})

const goToLicense = () => {
  // 🔧 JD Cloud Mode: Do not jump to the authorization page
  if (isJdyunMode) return
  router.push('/settings/license')
}

const handleCommand = async (command: string) => {
  switch (command) {
    case 'settings':
      router.push('/settings')
      break
    case 'logout':
      if (isJdyunMode) {
        // JD Cloud mode: jump to gateway /logout clear jdyun_session cookie
        // After the gateway clears cookies, it will jump to /login with a 302 error. The user needs to log in again next time.
        authStore.clearAuthInfo()
        window.location.href = '/logout'
      } else {
        await authStore.logout()
        ElMessage.success('Logged out')
        router.push('/login')
      }
      break
  }
}
</script>

<style lang="scss" scoped>
.user-profile {
  padding: 12px;

  &.collapsed {
    padding: 8px;
    text-align: center;
  }

  .license-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    margin-bottom: 8px;
    border-radius: 6px;
    background-color: var(--el-fill-color-lighter);
    cursor: pointer;
    transition: background-color 0.3s ease;

    &:hover {
      background-color: var(--el-fill-color-light);
    }

    .license-tag {
      font-size: 12px;
    }

    .expire-hint {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }
  }

  .license-badge-mini {
    display: flex;
    justify-content: center;
    padding: 8px;
    margin-bottom: 8px;
    cursor: pointer;
    border-radius: 6px;
    transition: background-color 0.3s ease;

    &:hover {
      background-color: var(--el-fill-color-lighter);
    }
  }

  .profile-info {
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 8px;
    border-radius: 6px;
    transition: background-color 0.3s ease;

    &:hover {
      background-color: var(--el-fill-color-lighter);
    }

    .user-info {
      flex: 1;
      min-width: 0;

      .username {
        font-size: 14px;
        font-weight: 500;
        color: var(--el-text-color-primary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .user-role {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
      }
    }
  }
}
</style>
