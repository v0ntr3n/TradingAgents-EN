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

import { isJdyunMode } from '@/utils/config'

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
