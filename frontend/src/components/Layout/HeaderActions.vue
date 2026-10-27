<template>
  <div class="header-actions">
    <!-- theme switching -->
    <el-tooltip content="switch theme" placement="bottom">
      <el-button type="text" @click="toggleTheme" class="action-btn">
        <el-icon>
          <Sunny v-if="appStore.isDarkTheme" />
          <Moon v-else />
        </el-icon>
      </el-button>
    </el-tooltip>

    <!-- Full screen switch -->
    <el-tooltip content="full screen" placement="bottom">
      <el-button type="text" @click="toggleFullscreen" class="action-btn">
        <el-icon><FullScreen /></el-icon>
      </el-button>
    </el-tooltip>

    <!-- Notification -->
    <el-tooltip content="Notification" placement="bottom">
      <el-badge :value="unreadCount" :hidden="unreadCount === 0">
        <el-button type="text" @click="openDrawer" class="action-btn">
          <el-icon><Bell /></el-icon>
        </el-button>
      </el-badge>
    </el-tooltip>

    <!-- help -->
    <el-tooltip content="help" placement="bottom">
      <el-button type="text" @click="showHelp" class="action-btn">
        <el-icon><QuestionFilled /></el-icon>
      </el-button>
    </el-tooltip>

    <!-- Notification drawer (Option B) -->
    <el-drawer v-model="drawerVisible" direction="rtl" size="360px" :with-header="true" title="Message center">
      <div class="notif-toolbar">
        <el-segmented v-model="filter" :options="[{label: 'All', value: 'all'}, {label: 'unread', value: 'unread'}]" size="small" />
        <el-button size="small" text type="primary" @click="onMarkAllRead" :disabled="unreadCount===0">All read</el-button>
      </div>
      <el-scrollbar max-height="calc(100vh - 160px)">
        <el-empty v-if="items.length===0" description="No notification yet" />
        <div v-else class="notif-list">
          <div v-for="n in items" :key="n.id" class="notif-item" :class="{unread: n.status==='unread'}">
            <div class="row">
              <el-tag :type="tagType(n.type)" size="small">{{ typeLabel(n.type) }}</el-tag>
              <span class="time">{{ toLocal(n.created_at) }}</span>
            </div>
            <div class="title" @click="go(n)">{{ n.title }}</div>
            <div class="content" v-if="n.content">{{ n.content }}</div>
            <div class="ops">
              <el-button size="small" text type="primary" @click="go(n)" :disabled="!n.link">View</el-button>
              <el-button size="small" text @click="onMarkRead(n)" v-if="n.status==='unread'">Mark as read</el-button>
            </div>
          </div>
        </div>
      </el-scrollbar>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notifications'
import { useAuthStore } from '@/stores/auth'
import { storeToRefs } from 'pinia'
import {
  Sunny,
  Moon,
  FullScreen,
  Bell,
  QuestionFilled
} from '@element-plus/icons-vue'

const router = useRouter()

const appStore = useAppStore()
const authStore = useAuthStore()
const notifStore = useNotificationStore()
const { unreadCount, items } = storeToRefs(notifStore)
const drawerVisible = ref(false)
const filter = ref<'all' | 'unread'>('all')
let timerCount: any = null
let timerList: any = null

const toggleTheme = () => { appStore.toggleTheme() }
const toggleFullscreen = () => {
  if (document.fullscreenElement) document.exitFullscreen()
  else document.documentElement.requestFullscreen()
}

function openDrawer() {
  drawerVisible.value = true
  notifStore.loadList(filter.value)
}
function onMarkRead(n: any) { notifStore.markRead(n.id) }
function onMarkAllRead() { notifStore.markAllRead() }
function typeLabel(t: string) { return t === 'analysis' ? 'analysis' : t === 'alert' ? 'early warning' : 'system' }
function tagType(t: string) { return t === 'analysis' ? 'success' : t === 'alert' ? 'warning' : 'info' }
function toLocal(iso: string) { try { return new Date(iso).toLocaleString() } catch { return iso } }
function go(n: any) { if (n.link) window.open(n.link, '_blank') }

onMounted(() => {
  notifStore.refreshUnreadCount()
  // 🔥 Establish WebSocket connection (priority), failure will automatically degrade to SSE
  notifStore.connect()

  timerCount = setInterval(() => notifStore.refreshUnreadCount(), 30000)
  watch(drawerVisible, (v) => {
    if (v) {
      notifStore.loadList(filter.value)
      timerList = setInterval(() => notifStore.loadList(filter.value), 60000)
    } else if (timerList) {
      clearInterval(timerList)
      timerList = null
    }
  }, { immediate: true })
  watch(filter, () => { if (drawerVisible.value) notifStore.loadList(filter.value) })

  // token Reconnect on change
  watch(() => authStore.token, (nextToken, previousToken) => {
    if (!nextToken) {
      notifStore.disconnect()
      return
    }
    if (!previousToken || !notifStore.connected) {
      notifStore.connect()
    }
  })
})

onUnmounted(() => {
  if (timerCount) clearInterval(timerCount)
  if (timerList) clearInterval(timerList)
  // 🔥 Disconnect all connections (WebSocket and SSE)
  notifStore.disconnect()
})

function showHelp() {
  router.push('/help')
}
</script>

<style lang="scss" scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;

  .action-btn {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;

    .el-icon { font-size: 18px; }
  }
}

/* Notification drawer style */
.notif-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.notif-list { display: flex; flex-direction: column; gap: 12px; }
.notif-item { padding: 10px 8px; border-radius: 8px; border: 1px solid var(--el-border-color-lighter); }
.notif-item.unread { background: var(--el-fill-color-light); }
.notif-item .row { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.notif-item .title { font-weight: 600; cursor: pointer; margin-bottom: 4px; }
.notif-item .title:hover { text-decoration: underline; }
.notif-item .content { font-size: 12px; color: var(--el-text-color-regular); }
.notif-item .ops { display: flex; gap: 8px; margin-top: 6px; }
</style>
