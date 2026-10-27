/**
 * Authentication tool function
 * Unified processing of authentication-related logic
 */

import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { ElMessage } from 'element-plus'

/**
 * Check if it is an authentication error
 */
export const isAuthError = (error: any): boolean => {
  if (!error) return false

  // Check HTTP status codes
  if (error.response?.status === 401) {
    return true
  }

  // Check business error codes
  const code = error.code || error.response?.data?.code
  if (code === 401 || code === 40101 || code === 40102 || code === 40103) {
    return true
  }

  // Check the error message
  const message = error.message || error.response?.data?.message || ''
  const authKeywords = [
    'Authentication failed',
    'Login has expired',
    'Unauthorized',
    'unauthorized',
    'token',
    'Token',
    'TOKEN',
    'Please log in again'
  ]

  return authKeywords.some(keyword => message.includes(keyword))
}

/**
 * Handle authentication errors
 * Clear authentication information and jump to login page
 */
export const handleAuthError = (error?: any, showMessage = true): void => {
  console.log('🔒 Handle authentication errors:', error)

  const authStore = useAuthStore()

  // Clear authentication information
  authStore.clearAuthInfo()

  // Show error message
  if (showMessage) {
    const message = error?.message || error?.response?.data?.message || 'Login has expired, please log in again'
    ElMessage.error(message)
  }

  // Jump to login page
  const currentPath = router.currentRoute.value.fullPath
  if (currentPath !== '/login') {
    // Save the current path and jump back after logging in
    authStore.setRedirectPath(currentPath)
    router.push('/login')
  }
}

/**
 * Check if the token is valid
 */
export const isTokenValid = (token: string | null): boolean => {
  if (!token || typeof token !== 'string') {
    return false
  }

  // Check if it is mock token
  if (token === 'mock-token' || token.startsWith('mock-')) {
    console.warn('⚠️ detected mock token')
    return false
  }

  // JWT token There should be 3 parts separated by .
  const parts = token.split('.')
  if (parts.length !== 3) {
    console.warn('⚠️ Token Invalid format')
    return false
  }

  // try to parse token payload
  try {
    const payload = JSON.parse(atob(parts[1]))
    
    // Check if expired
    if (payload.exp) {
      const now = Math.floor(Date.now() / 1000)
      if (payload.exp < now) {
        console.warn('⚠️ Token Expired')
        return false
      }
    }

    return true
  } catch (error) {
    console.warn('⚠️ Token Parsing failed:', error)
    return false
  }
}

/**
 * Extract user information from token
 */
export const parseToken = (token: string): any => {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      return null
    }

    const payload = JSON.parse(atob(parts[1]))
    return payload
  } catch (error) {
    console.error('❌ Token Parsing failed:', error)
    return null
  }
}

/**
 * Get the remaining validity time of the token (seconds)
 */
export const getTokenRemainingTime = (token: string): number => {
  const payload = parseToken(token)
  if (!payload || !payload.exp) {
    return 0
  }

  const now = Math.floor(Date.now() / 1000)
  const remaining = payload.exp - now

  return Math.max(0, remaining)
}

/**
 * Check if the token is about to expire (default 5 minutes)
 */
export const isTokenExpiringSoon = (token: string, thresholdSeconds = 300): boolean => {
  const remaining = getTokenRemainingTime(token)
  return remaining > 0 && remaining < thresholdSeconds
}

/**
 * Automatically refresh token (if it is about to expire)
 */
export const autoRefreshToken = async (): Promise<boolean> => {
  const authStore = useAuthStore()

  if (!authStore.token) {
    return false
  }

  // Check if the token is about to expire
  if (isTokenExpiringSoon(authStore.token)) {
    console.log('🔄 Token About to expire, automatically refresh...')
    try {
      const success = await authStore.refreshAccessToken()
      if (success) {
        console.log('✅ Token Automatic refresh successful')
        return true
      } else {
        console.log('❌ Token Auto refresh failed')
        return false
      }
    } catch (error) {
      console.error('❌ Token Auto refresh exception:', error)
      return false
    }
  }

  return true
}

/**
 * Set scheduled refresh token
 */
export const setupTokenRefreshTimer = (): void => {
  // Check every minute
  setInterval(() => {
    autoRefreshToken()
  }, 60000)

  console.log('✅ Token Auto-refresh timer started')
}

