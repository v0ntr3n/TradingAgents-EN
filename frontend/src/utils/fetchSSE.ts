import { isJdyunMode } from '@/utils/config'

// ============================================================================
// Module: fetchSSE.ts
// ============================================================================

/**
 * SSE Streaming request tool
 *
 * Unified packaging fetch + ReadableStream SSE streaming requests,Process:
 * - Authentication header automatic injection(JWT / App Token / Jingdong cloud model)
 * - 401 Unified processing
 * - idle timeout
 * - SSE Event analysis(event: / data: Format)
 * - AbortController management
 *
 * Usage:
 *   const controller = fetchSSE('/api/xxx/stream', {
 *     method: 'POST',
 *     body: { ... },
 *     onEvent: (eventType, data) => { ... },
 *     onDone: (data) => { ... },
 *     onError: (msg) => { ... },
 *   })
 *   // Cancel: controller.abort()
 */



export interface SSEOptions {
  method?: 'GET' | 'POST'
  body?: any
  /** idle timeout(milliseconds),Default 90 seconds */
  idleTimeout?: number
  /** Callback when SSE event is received */
  onEvent?: (eventType: string, data: any) => void
  /** Callback when the done event is received or the stream ends normally */
  onDone?: (data?: any) => void
  /** callback on error(HTTP Error/Timeout/Network Error) */
  onError?: (message: string) => void
  /** Callback when the user actively cancels */
  onAbort?: () => void
  /** Custom request header */
  headers?: Record<string, string>
  /** Whether to skip the authentication header(public interface) */
  skipAuth?: boolean
}

/**
 * Make an SSE streaming request
 * @returns AbortController, call .abort() Cancellable request
 */
export function fetchSSE(path: string, options: SSEOptions = {}): AbortController {
  const controller = new AbortController()
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const {
    method = 'POST',
    body,
    idleTimeout = 90_000,
    onEvent,
    onDone,
    onError,
    onAbort,
    headers: customHeaders,
    skipAuth = false,
  } = options

  // Assemble request headers
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...customHeaders,
  }

  if (!skipAuth) {
    const token = localStorage.getItem('auth-token') || ''
    const appToken = localStorage.getItem('app-token') || ''
    // Jingdong cloud model: No manual addition Authorization,Injected by gateway Basic Auth
    if (token && !isJdyunMode()) {
      headers['Authorization'] = `Bearer ${token}`
    }
    if (appToken) {
      headers['X-App-Token'] = appToken
    }
  }

  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let receivedTerminalEvent = false

  const resetIdle = () => {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      onError?.('Connection timeout: The server has not responded for a long time, please try again.')
      controller.abort()
    }, idleTimeout)
  }

  const clearIdle = () => {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  // Parse a single SSE event block
  const parseEventBlock = (part: string): { eventType: string; data: any } | null => {
    if (!part.trim() || part.startsWith(': ')) return null

    let eventType = ''
    const dataLines: string[] = []

    for (const rawLine of part.split('\n')) {
      const line = rawLine.replace(/\r$/, '')
      if (line.startsWith('event: ')) {
        eventType = line.slice(7)
      } else if (line.startsWith('data: ')) {
        dataLines.push(line.slice(6))
      }
    }

    const eventData = dataLines.join('\n')
    if (!eventData) return null

    try {
      return { eventType, data: JSON.parse(eventData) }
    } catch {
      return null
    }
  }

  fetch(`${baseUrl}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        if (response.status === 401) {
          onError?.('Login has expired, please log in again')
        } else {
          onError?.(`HTTP ${response.status}: ${response.statusText}`)
        }
        return
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      resetIdle()

      try {
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            buffer += decoder.decode()
            break
          }

          resetIdle()
          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const part of parts) {
            const parsed = parseEventBlock(part)
            if (!parsed) continue

            const { eventType, data } = parsed

            if (eventType === 'done') {
              receivedTerminalEvent = true
              clearIdle()
              onDone?.(data)
            } else if (eventType === 'error') {
              receivedTerminalEvent = true
              clearIdle()
              onError?.(data.message || 'unknown error')
            } else {
              onEvent?.(eventType, data)
            }
          }
        }

        // Process the remaining contents of buffer
        if (buffer.trim()) {
          const parsed = parseEventBlock(buffer)
          if (parsed) {
            const { eventType, data } = parsed
            if (eventType === 'done') {
              receivedTerminalEvent = true
              onDone?.(data)
            } else if (eventType === 'error') {
              receivedTerminalEvent = true
              onError?.(data.message || 'unknown error')
            } else {
              onEvent?.(eventType, data)
            }
          }
        }

        // The stream ended normally but did not receive the done event
        if (!receivedTerminalEvent && !controller.signal.aborted) {
          onDone?.()
        }
      } finally {
        clearIdle()
        reader.releaseLock()
      }
    })
    .catch((err) => {
      clearIdle()
      if (err.name === 'AbortError') {
        onAbort?.()
      } else {
        onError?.(err.message || 'The network request failed, please check the network connection and try again.')
      }
    })

  return controller
}

// ============================================================================
// Module: createWebSocket.ts
// ============================================================================

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
