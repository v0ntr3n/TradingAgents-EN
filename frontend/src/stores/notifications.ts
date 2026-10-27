import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { notificationsApi, type NotificationItem } from '@/api/notifications'
import { useAuthStore } from '@/stores/auth'
import { isJdyunMode } from '@/utils/config'

type NotificationSocketState = {
  socket: WebSocket | null
  reconnectTimer: ReturnType<typeof setTimeout> | null
  reconnectAttempts: number
  shouldReconnect: boolean
  currentToken: string
  isConnecting: boolean
}

declare global {
  interface Window {
    __TA_NOTIFICATION_SOCKET_STATE__?: NotificationSocketState
  }
}

function getGlobalSocketState(): NotificationSocketState {
  if (!window.__TA_NOTIFICATION_SOCKET_STATE__) {
    window.__TA_NOTIFICATION_SOCKET_STATE__ = {
      socket: null,
      reconnectTimer: null,
      reconnectAttempts: 0,
      shouldReconnect: false,
      currentToken: '',
      isConnecting: false,
    }
  }
  return window.__TA_NOTIFICATION_SOCKET_STATE__
}

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<NotificationItem[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const drawerVisible = ref(false)

  // 🔥 WebSocket connection status
  const ws = ref<WebSocket | null>(null)
  const wsConnected = ref(false)
  const maxReconnectAttempts = 10  // Increase the number of reconnections

  const syncSocketRefs = () => {
    const state = getGlobalSocketState()
    ws.value = state.socket
    wsConnected.value = Boolean(state.socket && state.socket.readyState === WebSocket.OPEN)
  }

  const clearReconnectTimer = () => {
    const state = getGlobalSocketState()
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer)
      state.reconnectTimer = null
    }
  }

  // connection status
  const connected = computed(() => wsConnected.value)

  const hasUnread = computed(() => unreadCount.value > 0)

  async function refreshUnreadCount() {
    try {
      const res = await notificationsApi.getUnreadCount()
      unreadCount.value = res?.data?.count ?? 0
    } catch {
      // noop
    }
  }

  async function loadList(status: 'unread' | 'all' = 'all') {
    loading.value = true
    try {
      const res = await notificationsApi.getList({ status, page: 1, page_size: 20 })
      items.value = res?.data?.items ?? []
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: string) {
    await notificationsApi.markRead(id)
    const idx = items.value.findIndex(x => x.id === id)
    if (idx !== -1) items.value[idx].status = 'read'
    if (unreadCount.value > 0) unreadCount.value -= 1
  }

  async function markAllRead() {
    await notificationsApi.markAllRead()
    items.value = items.value.map(x => ({ ...x, status: 'read' }))
    unreadCount.value = 0
  }

  function addNotification(n: Omit<NotificationItem, 'id' | 'status' | 'created_at'> & { id?: string; created_at?: string; status?: 'unread' | 'read' }) {
    const id = n.id || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const created_at = n.created_at || new Date().toISOString()
    const item: NotificationItem = {
      id,
      title: n.title,
      content: n.content,
      type: n.type,
      status: n.status ?? 'unread',
      created_at,
      link: n.link,
      source: n.source
    }
    items.value.unshift(item)
    if (item.status === 'unread') unreadCount.value += 1
  }

  // 🔥 Connect to WebSocket (preferred)
  function connectWebSocket() {
    try {
      const authStore = useAuthStore()
      const token = authStore.token || localStorage.getItem('auth-token') || ''
      const jdyun = isJdyunMode()

      // JD Cloud mode: You can connect without JWT token, Basic Auth authentication is injected by the gateway
      // Non-JD Cloud mode: required JWT token
      if (!token && !jdyun) {
        console.warn('[WS] Token not found, unable to connect WebSocket')
        disconnectWebSocket()
        return
      }

      const state = getGlobalSocketState()
      state.shouldReconnect = true

      if (state.isConnecting) {
        console.debug('[WS] Already connected, skip repeated connection requests')
        return
      }

      // In JD Cloud mode, when the token is empty, it is marked with a placeholder to ensure that the currentToken is logically consistent.
      const connKey = token || (jdyun ? '__jdyun_basic_auth__' : '')
      if (
        state.socket
        && (state.socket.readyState === WebSocket.OPEN || state.socket.readyState === WebSocket.CONNECTING)
        && state.currentToken === connKey
      ) {
        console.debug('[WS] Reuse existing notification connection')
        syncSocketRefs()
        return
      }

      clearReconnectTimer()

      if (state.socket) {
        try {
          state.socket.close()
        } catch (error) {
          console.debug('[WS] Failed to close old connection:', error)
        } finally {
          state.socket = null
        }
      }

      // WebSocket connection address
      // 🔥 Uniformly use the currently accessed server address (the development environment uses the Vite proxy, and the production environment uses the Nginx proxy)
      // When there is no token in JD Cloud mode, the token parameter is not passed, and the Basic Auth header is authenticated by the gateway.
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const wsUrl = token
        ? `${wsProtocol}//${host}/api/ws/notifications?token=${encodeURIComponent(token)}`
        : `${wsProtocol}//${host}/api/ws/notifications`

      console.log('[WS] Connect to:', wsUrl, jdyun && !token ? '(JD Cloud Basic Auth)' : '')

      const socket = new WebSocket(wsUrl)
      state.socket = socket
      state.currentToken = connKey
      state.isConnecting = true
      syncSocketRefs()

      socket.onopen = () => {
        console.log('[WS] Connection successful')
        state.isConnecting = false
        wsConnected.value = true
        state.reconnectAttempts = 0
        syncSocketRefs()
      }

      socket.onclose = (event) => {
        console.log('[WS] connection closed:', event.code, event.reason)
        state.isConnecting = false
        wsConnected.value = false
        if (state.socket === socket) {
          state.socket = null
        }
        syncSocketRefs()

        // Automatically reconnect
        if (state.shouldReconnect && state.reconnectAttempts < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts), 30000)
          console.log(`[WS] ${delay}ms Reconnect later (try ${state.reconnectAttempts + 1}/${maxReconnectAttempts})`)

          state.reconnectTimer = setTimeout(() => {
            state.reconnectAttempts++
            connectWebSocket()
          }, delay)
        } else {
          if (state.shouldReconnect) {
            console.error('[WS] Reached the maximum number of reconnections and stopped reconnecting.')
          }
        }
      }

      socket.onerror = (error) => {
        console.error('[WS] Connection error:', error)
        state.isConnecting = false
        wsConnected.value = false
      }

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          handleWebSocketMessage(message)
        } catch (error) {
          console.error('[WS] Failed to parse message:', error)
        }
      }
    } catch (error) {
      const state = getGlobalSocketState()
      state.isConnecting = false
      console.error('[WS] Connection failed:', error)
      wsConnected.value = false
    }
  }

  // Handling WebSocket messages
  function handleWebSocketMessage(message: any) {
    console.log('[WS] message received:', message)

    switch (message.type) {
      case 'connected':
        console.log('[WS] Connection confirmation:', message.data)
        break

      case 'notification':
        // Handle notifications
        if (message.data && message.data.title && message.data.type) {
          addNotification({
            id: message.data.id,
            title: message.data.title,
            content: message.data.content,
            type: message.data.type,
            link: message.data.link,
            source: message.data.source,
            created_at: message.data.created_at,
            status: message.data.status || 'unread'
          })
        }
        break

      case 'heartbeat':
        // Heartbeat message, no need to process
        break

      default:
        console.warn('[WS] Unknown message type:', message.type)
    }
  }

  // Disconnect WebSocket
  function disconnectWebSocket() {
    const state = getGlobalSocketState()
    state.shouldReconnect = false
    state.isConnecting = false
    state.currentToken = ''
    clearReconnectTimer()

    if (state.socket) {
      try {
        state.socket.close()
      } catch (error) {
        console.debug('[WS] Close failed on disconnect:', error)
      }
      state.socket = null
    }

    wsConnected.value = false
    state.reconnectAttempts = 0
    syncSocketRefs()
  }

  // 🔥 connect WebSocket
  function connect() {
    console.log('[Notifications] Start connecting...')
    connectWebSocket()
  }

  // 🔥 Disconnect WebSocket
  function disconnect() {
    console.log('[Notifications] Disconnect...')
    disconnectWebSocket()
  }

  function setDrawerVisible(v: boolean) {
    drawerVisible.value = v
  }

  return {
    items,
    unreadCount,
    hasUnread,
    loading,
    drawerVisible,
    connected,
    wsConnected,
    refreshUnreadCount,
    loadList,
    markRead,
    markAllRead,
    addNotification,
    connect,
    disconnect,
    connectWebSocket,
    disconnectWebSocket,
    setDrawerVisible
  }
})
