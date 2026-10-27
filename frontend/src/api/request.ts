import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import router from '@/router'
import { isTokenValid } from '@/utils/auth'

declare module 'axios' {
  export interface AxiosRequestConfig {
    skipAuth?: boolean
    skipAuthError?: boolean
    skipErrorHandler?: boolean
    showLoading?: boolean
    loadingText?: string
    retryCount?: number
    retryDelay?: number
    _retry?: boolean
    __retryCount?: number
  }
}

// API response interface
export interface ApiResponse<T = any> {
  success: boolean
  data: T
  message: string
  code?: number
  timestamp?: string
  request_id?: string
}

// Request configuration interface
export interface RequestConfig extends AxiosRequestConfig {
  skipAuth?: boolean
  skipAuthError?: boolean  // Skip automatic handling of 401 errors (used for login and other interfaces)
  skipErrorHandler?: boolean
  showLoading?: boolean
  loadingText?: string
  retryCount?: number  // Number of retries
  retryDelay?: number  // Retry delay (milliseconds)
  _retry?: boolean
  __retryCount?: number
}

// Message deduplication: record the most recently displayed error message
const recentMessages = new Map<string, number>()
const MESSAGE_THROTTLE_TIME = 3000 // 3 The same message will not be displayed repeatedly within seconds.

// 401 Error handling flag (to avoid multiple requests triggering login jumps at the same time)
let isHandling401 = false

// Token Refresh solo flight control to avoid concurrent 401 triggering refresh storm
let refreshTokenPromise: Promise<boolean> | null = null

const maskTokenFingerprint = (token?: string | null): string => {
  if (!token) {
    return 'none'
  }

  if (token.length <= 16) {
    return token
  }

  return `${token.substring(0, 8)}...${token.substring(token.length - 8)}`
}

const ensureSingleFlightTokenRefresh = (authStore: any) => {
  if (!refreshTokenPromise) {
    refreshTokenPromise = authStore.refreshAccessToken()
      .finally(() => {
        refreshTokenPromise = null
      })
  }
  return refreshTokenPromise
}

// Show error message (with duplicates removed)
const showErrorMessage = (message: string) => {
  const now = Date.now()
  const lastTime = recentMessages.get(message)

  // If the same message has been displayed within 3 seconds, skip
  if (lastTime && now - lastTime < MESSAGE_THROTTLE_TIME) {
    console.log('⏭️ Skip duplicate messages:', message)
    return
  }

  // Record message display time
  recentMessages.set(message, now)

  // Clean up expired message records (to keep the Map from growing infinitely)
  if (recentMessages.size > 50) {
    const entries = Array.from(recentMessages.entries())
    entries.sort((a, b) => a[1] - b[1])
    // Delete the oldest 25 records
    entries.slice(0, 25).forEach(([key]) => recentMessages.delete(key))
  }

  ElMessage.error(message)
}

// Handling 401 errors (with anti-shake)
const handle401Error = (authStore: any, message: string = 'Login has expired, please log in again') => {
  // Skip if handling 401 error
  if (isHandling401) {
    console.log('⏭️ Processing 401 error, skipping repeated processing')
    return
  }

  isHandling401 = true

  // Clear authentication information and jump to login page
  console.log('🔒 Handle 401 errors: clear authentication information and jump to the login page')
  authStore.clearAuthInfo()
  router.push('/login')
  showErrorMessage(message)

  // 3 Reset flag after seconds
  setTimeout(() => {
    isHandling401 = false
  }, 3000)
}

// Create axios instance
const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '',
    timeout: 600000, // Increase the timeout to 600 seconds (10 minutes, used for long-term operations such as transaction review analysis)
    withCredentials: true,  // 🔥 Important: Allow sending and receiving cookies (for session authentication)
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache',  // Disable client cache
      'Pragma': 'no-cache'
    }
  })

  // request interceptor
  instance.interceptors.request.use(
    async (config: any) => {
      const authStore = useAuthStore()
      const appStore = useAppStore()

      // Add authentication header (always overwrite with the latest Token; support localStorage to avoid losing Token in early requests)
      if (!config.skipAuth) {
        const storedToken = authStore.token || localStorage.getItem('auth-token')
        const shouldTryRefresh = Boolean(
          storedToken
          && !isTokenValid(storedToken)
          && authStore.refreshToken
          && !String(config.url || '').includes('/auth/refresh')
        )

        if (shouldTryRefresh) {
          console.log('🔄 It is detected that the access token has expired before the request is sent. Try to refresh it first.', {
            url: config.url,
            staleTokenFingerprint: maskTokenFingerprint(storedToken),
            refreshTokenFingerprint: maskTokenFingerprint(authStore.refreshToken),
          })
          const refreshed = await ensureSingleFlightTokenRefresh(authStore)
          if (!refreshed) {
            console.warn('⚠️ If the token refresh fails before the request is sent, the original 401 process will continue to be processed.')
          }
        }

        const token = authStore.token || localStorage.getItem('auth-token')
        if (token) {
          config.headers = config.headers || {}
          config.headers.Authorization = `Bearer ${token}`
        }

        // Add App Token header (for license verification)
        const appToken = localStorage.getItem('app-token')
        if (appToken) {
          config.headers = config.headers || {}
          config.headers['X-App-Token'] = appToken
        }
      }

      // Add request ID
      config.headers['X-Request-ID'] = generateRequestId()

      // Add language header
      config.headers['Accept-Language'] = appStore.language

      // show loading status
      if (config.showLoading) {
        appStore.setLoading(true, 0)
      }

      // Endpoint Compatibility Guard: Block/Fix misuse of /api/stocks/quote (missing path parameter {code}) 
      try {
        const rawUrl = String(config.url || '')
        const pathOnly = rawUrl.split('?')[0].replace(/\/+$|^\s+|\s+$/g, '')
        if (pathOnly === '/api/stocks/quote' || pathOnly === '/api/stocks/quote/') {
          const code = (config.params && (config.params.code || (config as any).params?.stock_code)) ?? undefined
          if (code) {
            const codeStr = String(code)
            config.url = `/api/stocks/${codeStr}/quote`
            if (config.params) {
              delete (config.params as any).code
              delete (config.params as any).stock_code
            }
          } else {
            console.error('❌ Misuse of endpoints: /api/stocks/quote missing code')
            return Promise.reject(new Error('Frontend misused endpoint: code is missing, please use instead /api/stocks/{code}/quote'))
          }
        }

        const base = String(config.baseURL || '')
        const urlStr = String(config.url || '')
        const baseHasApi = /\/api\/?$/.test(base)
        const urlStartsWithApi = urlStr.startsWith('/api/') || urlStr === '/api'
        if (baseHasApi && urlStartsWithApi) {
          config.url = urlStr.replace(/^\/api(\/)?/, '/$1')
        }

        // Uniform removal /api/* Slash at the end of the path to avoid FastAPI default 307 redirect
        const finalUrl = String(config.url || '')
        if (finalUrl.startsWith('/api/') && finalUrl.length > 5) {
          config.url = finalUrl.replace(/\/+(\?|$)/, '$1')
        }
      } catch (e) {
        console.warn('Endpoint compatibility check exception', e)
      }

      return config
    },
    (error) => {
      console.error('❌ Request interceptor error:', error)
      return Promise.reject(error)
    }
  )

  // response interceptor
  instance.interceptors.response.use(
    (response: AxiosResponse) => {
      const appStore = useAppStore()
      const authStore = useAuthStore()
      const config = response.config as RequestConfig

      // Hide loading status
      if (config.showLoading) {
        appStore.setLoading(false)
      }

      // Check business status code
      const data = response.data as ApiResponse
      if (data && typeof data === 'object' && 'success' in data) {
        if (!data.success) {
          // Check whether it is an authentication error (processed first, does not rely on skipErrorHandler)
          const code = data.code
          if (code === 401 || code === 40101 || code === 40102 || code === 40103) {
            // If the request is marked to skip authentication error handling (such as a login request), it is not automatically processed
            if (!config.skipAuthError) {
              console.log('🔒 Business error: Authentication failed (HTTP 200)')
              handle401Error(authStore, data.message || 'Login has expired, please log in again')
            }
            return Promise.reject(new Error(data.message || 'Authentication failed'))
          }

          // Other business errors
          if (!config.skipErrorHandler) {
            handleBusinessError(data)
            return Promise.reject(new Error(data.message || 'Request failed'))
          }
        }
      }

      // Return response.data instead of response so the caller can access it directly ApiResponse
      return response.data
    },
    async (error) => {
      const appStore = useAppStore()
      const authStore = useAuthStore()
      const config = error.config as RequestConfig

      // Hide loading status
      if (config?.showLoading) {
        appStore.setLoading(false)
      }

      // Handling HTTP status code errors
      if (error.response) {
        const { status, data } = error.response

        switch (status) {
          case 401:
            // If the refresh request itself fails, do not try to refresh again (to avoid infinite loops)
            if (config?.url?.includes('/auth/refresh')) {
              console.error('❌ Refresh token Request failed')
              if (config?.skipAuthError) {
                ;(error as any).__skipGlobalAuthRedirect = true
                break
              }
              handle401Error(authStore, 'Login has expired, please log in again')
              break
            }

            // When unauthorized, try to refresh the token first, even if skipAuthError=true Refreshing should also not be skipped.
            if (!config?.skipAuth && authStore.refreshToken && !config?._retry) {
              try {
                console.log('🔄 401 Error, try refreshing token...')
                config._retry = true
                const success = await ensureSingleFlightTokenRefresh(authStore)
                if (success) {
                  console.log('✅ Token Refresh successful, retry the original request')
                  // Resend original request
                  return instance.request(config)
                } else {
                  console.log('❌ Token Refresh failed')
                }
              } catch (refreshError) {
                console.error('❌ Token Refresh exception:', refreshError)
              }
            }

            // If the request is marked to skip authentication error handling (such as a partially downgradeable interface), do not automatically logout/jump.
            if (config?.skipAuthError) {
              ;(error as any).__skipGlobalAuthRedirect = true
              break
            }

            // Clear authentication information and jump to login page
            handle401Error(authStore, 'Login has expired, please log in again')
            break

          case 403:
            showErrorMessage('Insufficient permissions to access the resource')
            break

          case 400:
            // Parameter error, display detailed error information
            if (!config?.skipErrorHandler) {
              const message = data?.detail || data?.message || error.message || 'Request parameter error'
              showErrorMessage(message)
            }
            break

          case 404:
            if (!config?.skipErrorHandler) {
              showErrorMessage('The requested resource does not exist')
            }
            break

          case 429:
            showErrorMessage('The request is too frequent, please try again later.')
            break

          case 500:
            // Prioritize display of detailed error information returned by the backend
            if (!config?.skipErrorHandler) {
              const message = data?.detail || data?.message || 'Internal server error, please try again later'
              showErrorMessage(message)
              // Attach detailed error information to the error object for use by the component
              error.message = message
            }
            break

          case 502:
          case 503:
          case 504:
            showErrorMessage('The service is temporarily unavailable, please try again later')
            break

          default:
            if (!config?.skipErrorHandler) {
              const message = data?.detail || data?.message || error.message || 'Network request failed'
              showErrorMessage(message)
            }
        }
      } else if (error.code === 'ECONNABORTED') {
        console.error('🔍 [REQUEST] Request timeout error:', {
          code: error.code,
          message: error.message,
          timeout: config?.timeout,
          url: config?.url
        })

        // Try again
        if (await shouldRetry(config, error)) {
          return retryRequest(instance, config)
        }

        showErrorMessage('Request timed out, please check network connection')
      } else if (error.message === 'Network Error') {
        console.error('🔍 [REQUEST] Network connection error:', {
          message: error.message,
          code: error.code,
          url: config?.url,
          baseURL: config?.baseURL
        })

        // Try again
        if (await shouldRetry(config, error)) {
          return retryRequest(instance, config)
        }

        showErrorMessage('Network connection failed, please check network settings')
      } else if (error.message.includes('Failed to fetch')) {
        console.error('🔍 [REQUEST] Fetch failure error:', {
          message: error.message,
          code: error.code,
          url: config?.url,
          baseURL: config?.baseURL
        })

        // Try again
        if (await shouldRetry(config, error)) {
          return retryRequest(instance, config)
        }

        showErrorMessage('Network request failed, please check server connection')
      } else if (!config?.skipErrorHandler) {
        console.error('🔍 [REQUEST] Other errors:', {
          message: error.message,
          code: error.code,
          name: error.name,
          url: config?.url
        })
        showErrorMessage(error.message || 'unknown error')
      }

      return Promise.reject(error)
    }
  )

  return instance
}

// Handle business errors
const handleBusinessError = (data: ApiResponse) => {
  const { code, message } = data
  const authStore = useAuthStore()

  switch (code) {
    case 401:
    case 40101:  // Unauthorized
    case 40102:  // Token Invalid
    case 40103:  // Token Expired
      console.log('🔒 Business error: Authentication failed')
      handle401Error(authStore, message || 'Login has expired, please log in again')
      break
    case 40001:
      showErrorMessage('Parameter error')
      break
    case 403:
    case 40003:
      showErrorMessage('Insufficient permissions')
      break
    case 40004:
      showErrorMessage('Resource does not exist')
      break
    case 40005:
      showErrorMessage('Operation failed')
      break
    case 50001:
      showErrorMessage('Server error')
      break
    default:
      if (message) {
        showErrorMessage(message)
      }
  }
}

// Generate request ID
const generateRequestId = (): string => {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

// Determine whether you should try again
const shouldRetry = async (config: RequestConfig | undefined, error: any): Promise<boolean> => {
  if (!config) return false

  // Get retry configuration (default retries 2 times)
  let retryCount = 2
  if (config.retryCount !== undefined) {
    retryCount = config.retryCount
  }
  const currentRetry = (config as any).__retryCount || 0

  // If it has been retried the specified number of times, it will not be retried again.
  if (currentRetry >= retryCount) {
    console.log(`🔄 Maximum number of retries reached (${retryCount}), Stop retrying`)
    return false
  }

  // Only retry on network errors and timeout errors
  const shouldRetryError =
    error.code === 'ECONNABORTED' ||
    error.message === 'Network Error' ||
    error.message.includes('Failed to fetch') ||
    (error.response && [502, 503, 504].includes(error.response.status))

  return shouldRetryError
}

// Retry request
const retryRequest = async (instance: AxiosInstance, config: RequestConfig): Promise<any> => {
  const currentRetry = (config as any).__retryCount || 0
  // Use explicit default value processing
  let retryDelay = 1000
  if (config.retryDelay !== undefined) {
    retryDelay = config.retryDelay
  }

  // Increase retry count
  (config as any).__retryCount = currentRetry + 1

  console.log(`🔄 No. ${currentRetry + 1} Retry requests: ${config.url}`)

  // Retry after delay
  await new Promise(resolve => setTimeout(resolve, retryDelay * (currentRetry + 1)))

  return instance.request(config)
}

// Create request instance
const request = createAxiosInstance()

// Test API connection
export const testApiConnection = async (): Promise<boolean> => {
  try {
    await request.get('/api/health', {
      timeout: 5000,
      skipErrorHandler: true
    } as any)

    return true
  } catch (error: any) {
    console.error('❌ API Connection test failed:', error.code || error.message)

    return false
  }
}

// Request method encapsulation
export class ApiClient {
  // GET Request
  static async get<T = any>(
    url: string,
    params?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.get(url, { params, ...config })
  }

  // POST Request
  static async post<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.post(url, data, config)
  }

  // PUT Request
  static async put<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.put(url, data, config)
  }

  // DELETE Request
  static async delete<T = any>(
    url: string,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.delete(url, config)
  }

  // PATCH Request
  static async patch<T = any>(
    url: string,
    data?: any,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.patch(url, data, config)
  }

  // Upload files
  static async upload<T = any>(
    url: string,
    file: File,
    onProgress?: (progress: number) => void,
    config?: RequestConfig
  ): Promise<ApiResponse<T>> {
    const formData = new FormData()
    formData.append('file', file)

    // The response interceptor has already returned response.data, so it is returned directly here
    return await request.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(progress)
        }
      },
      ...config
    })
  }

  // Download file
  static async download(
    url: string,
    filename?: string,
    config?: RequestConfig
  ): Promise<void> {
    // For blob responses, the response interceptor returns the blob data
    const blobData = await request.get(url, {
      responseType: 'blob',
      ...config
    })

    const blob = new Blob([blobData as unknown as BlobPart])
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
}

export default request
export { request }
