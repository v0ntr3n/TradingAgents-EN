/**
 * WebSocket Connection tools
 *
 * Unified encapsulation of WebSocket connections,Process:
 * - Certification: JWT token / Jingdong cloud model(Gateway injection)
 * - Automatically reconnect(exponential backoff)
 * - Heartbeat detection
 * - Automatic JSON parsing of messages
 *
 * Usage:
 *   const ws = createWebSocket('/api/ws/xxx', {
 *     onOpen: () => { ... },
 *     onMessage: (data) => { ... },
 *     onError: (err) => { ... },
 *     onClose: () => { ... },
 *     autoReconnect: true,
 *   })
 *   ws.send({ type: 'ping' })
 *   ws.close()
 */

import { isJdyunMode } from '@/utils/config'

export interface CreateWebSocketOptions {
  /** Connection success callback */
  onOpen?: () => void
  /** Receive message callback(JSON parsed) */
  onMessage?: (data: any) => void
  /** Connection error callback */
  onError?: (error: Event) => void
  /** Connection close callback */
  onClose?: (event: CloseEvent) => void
  /** Whether to automatically reconnect,Default true */
  autoReconnect?: boolean
  /** Maximum number of reconnections,Default 5 */
  maxReconnectAttempts?: number
  /** Initial reconnect delay(milliseconds),Default 1000 */
  initialReconnectDelay?: number
  /** Maximum reconnection delay(milliseconds),Default 30000 */
  maxReconnectDelay?: number
  /** heartbeat interval(milliseconds),Default 30000,Set to 0 to disable */
  heartbeatInterval?: number
  /** Heartbeat message content,Default { type: 'ping' } */
  heartbeatMessage?: any
  /** Custom sub-protocol */
  protocols?: string | string[]
  /** Whether to skip token authentication(public WS) */
  skipAuth?: boolean
}

export interface ManagedWebSocket {
  /** Native WebSocket instance */
  socket: WebSocket | null
  /** Send message(automatic JSON.stringify) */
  send: (data: any) => void
  /** close connection */
  close: (code?: number, reason?: string) => void
  /** Manual reconnect */
  reconnect: () => void
  /** Current number of reconnections */
  reconnectAttempts: number
  /** Is it connected? */
  isConnected: () => boolean
}

export function createWebSocket(
  path: string,
  options: CreateWebSocketOptions = {},
): ManagedWebSocket {
  const {
    onOpen,
    onMessage,
    onError,
    onClose,
    autoReconnect = true,
    maxReconnectAttempts = 5,
    initialReconnectDelay = 1000,
    maxReconnectDelay = 30000,
    heartbeatInterval = 30000,
    heartbeatMessage = { type: 'ping' },
    protocols,
    skipAuth = false,
  } = options

  let socket: WebSocket | null = null
  let reconnectAttempts = 0
  let shouldReconnect = autoReconnect
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  const buildUrl = (): string => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const base = `${wsProtocol}//${host}${path}`

    if (skipAuth) return base

    const token = localStorage.getItem('auth-token') || ''
    // Jingdong cloud model: Not passed on token,Injected by gateway Basic Auth
    if (token && !isJdyunMode()) {
      return `${base}?token=${encodeURIComponent(token)}`
    }
    return base
  }

  const clearHeartbeat = () => {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  const startHeartbeat = () => {
    if (heartbeatInterval <= 0) return
    clearHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        try {
          socket.send(JSON.stringify(heartbeatMessage))
        } catch {
          // ignore
        }
      }
    }, heartbeatInterval)
  }

  const connect = () => {
    const url = buildUrl()

    try {
      socket = protocols ? new WebSocket(url, protocols) : new WebSocket(url)
    } catch (error) {
      console.error('[WS] Failed to create connection:', error)
      onError?.(error as unknown as Event)
      scheduleReconnect()
      return
    }

    socket.onopen = () => {
      reconnectAttempts = 0
      startHeartbeat()
      onOpen?.()
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage?.(data)
      } catch {
        // Non-JSON messages are directly transmitted transparently
        onMessage?.(event.data)
      }
    }

    socket.onerror = (error) => {
      console.error('[WS] Connection error:', error)
      onError?.(error)
    }

    socket.onclose = (event) => {
      clearHeartbeat()
      onClose?.(event)

      if (shouldReconnect && reconnectAttempts < maxReconnectAttempts) {
        scheduleReconnect()
      }
    }
  }

  const scheduleReconnect = () => {
    if (!shouldReconnect || reconnectAttempts >= maxReconnectAttempts) return

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
    }

    const delay = Math.min(
      initialReconnectDelay * Math.pow(2, reconnectAttempts),
      maxReconnectDelay,
    )

    reconnectTimer = setTimeout(() => {
      reconnectAttempts++
      connect()
    }, delay)
  }

  const managed: ManagedWebSocket = {
    get socket() {
      return socket
    },

    send(data: any) {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.warn('[WS] Connection not ready,Message not sent')
        return
      }
      socket.send(typeof data === 'string' ? data : JSON.stringify(data))
    },

    close(code?: number, reason?: string) {
      shouldReconnect = false
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      clearHeartbeat()
      if (socket) {
        socket.close(code, reason)
      }
    },

    reconnect() {
      reconnectAttempts = 0
      shouldReconnect = true
      if (socket) {
        socket.close()
      } else {
        connect()
      }
    },

    get reconnectAttempts() {
      return reconnectAttempts
    },

    isConnected() {
      return socket?.readyState === WebSocket.OPEN
    },
  }

  // initial connection
  connect()

  return managed
}
