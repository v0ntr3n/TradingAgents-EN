import { defineStore } from 'pinia'
import { useStorage } from '@vueuse/core'
import { authApi } from '@/api/auth'
import type { User, LoginForm, RegisterForm, UserUpdatePayload } from '@/types/auth'
import { useAppStore } from './app'
import { isJdyunMode } from '@/utils/config'
import { ElMessage } from 'element-plus'

export interface AuthState {
  // Certification status
  isAuthenticated: boolean
  token: string | null
  refreshToken: string | null
  
  // User information
  user: User | null
  
  // Permission information
  permissions: string[]
  roles: string[]
  
  // Login status
  loginLoading: boolean

  // redirect path
  redirectPath: string

  // Authentication initialization status
  authInitialized: boolean
  authInitPromise: Promise<void> | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => {
    const token = useStorage('auth-token', null).value || null
    const refreshToken = useStorage('refresh-token', null).value || null

    // Verify token format
    const isValidToken = (token: string | null): boolean => {
      if (!token || typeof token !== 'string') return false
      // Check whether it is a mock token (a test token that may be set during development)
      if (token === 'mock-token' || token.startsWith('mock-')) {
        console.warn('⚠️ Mock token detected and will be cleared:', token)
        return false
      }
      // JWT token There should be 3 parts, separated by .
      return token.split('.').length === 3
    }

    const validToken = isValidToken(token) ? token : null
    const validRefreshToken = isValidToken(refreshToken) ? refreshToken : null

    // If the token is invalid, clear related data
    if (!validToken || !validRefreshToken) {
      console.log('🧹 Clear invalid authentication information')
      localStorage.removeItem('auth-token')
      localStorage.removeItem('refresh-token')
      localStorage.removeItem('user-info')
    }

    return {
      isAuthenticated: !!validToken,
      token: validToken,
      refreshToken: validRefreshToken,

      user: validToken ? (useStorage('user-info', null).value || null) : null,

      permissions: [],
      roles: [],

      loginLoading: false,
      redirectPath: '/',

      authInitialized: false,
      authInitPromise: null
    }
  },

  getters: {
    // User avatar: Give priority to the avatar set by the user, otherwise return undefined and use the default icon.
    userAvatar(): string | undefined {
      return this.user?.avatar || undefined
    },
    
    // User display name
    userDisplayName(): string {
      return this.user?.username || this.user?.email || 'unknown user'
    },
    
    // Is it an administrator?
    isAdmin(): boolean {
      return this.roles.includes('admin')
    },
    
    // Check permissions
    hasPermission(): (permission: string) => boolean {
      return (permission: string) => {
        return this.permissions.includes(permission) || this.isAdmin
      }
    },
    
    // Check roles
    hasRole(): (role: string) => boolean {
      return (role: string) => {
        return this.roles.includes(role)
      }
    },
    
    // User statistics
    userStats(): Record<string, number> {
      return {
        totalAnalyses: this.user?.total_analyses || 0,
        successfulAnalyses: this.user?.successful_analyses || 0,
        failedAnalyses: this.user?.failed_analyses || 0,
        dailyQuota: this.user?.daily_quota || 1000,
        concurrentLimit: this.user?.concurrent_limit || 3
      }
    }
  },

  actions: {
    maskTokenFingerprint(token?: string | null) {
      if (!token) {
        return 'none'
      }

      if (token.length <= 16) {
        return token
      }

      return `${token.substring(0, 8)}...${token.substring(token.length - 8)}`
    },

    // Set authentication information
    setAuthInfo(token: string, refreshToken?: string, user?: User) {
      this.token = token
      this.isAuthenticated = true

      if (refreshToken) {
        this.refreshToken = refreshToken
      }

      if (user) {
        this.user = user
      }

      // Manually save to localStorage (ensure persistence)
      localStorage.setItem('auth-token', token)
      if (refreshToken) {
        localStorage.setItem('refresh-token', refreshToken)
      }
      if (user) {
        localStorage.setItem('user-info', JSON.stringify(user))
      }

      // Set API request headers
      this.setAuthHeader(token)

      console.log('✅ Certification information has been saved')
    },
    
    // Clear authentication information
    clearAuthInfo() {
      this.token = null
      this.refreshToken = null
      this.user = null
      this.isAuthenticated = false
      this.permissions = []
      this.roles = []

      // Clear API request headers
      this.setAuthHeader(null)

      // Clear local storage
      localStorage.removeItem('auth-token')
      localStorage.removeItem('refresh-token')
      localStorage.removeItem('user-info')
    },

    // Jump to login page
    redirectToLogin() {
      // Avoid use in non-browser environments router
      if (typeof window !== 'undefined') {
        // Use window.location to jump to avoid router dependency issues
        const currentPath = window.location.pathname
        if (currentPath !== '/login') {
          console.log('🔄 Jump to login page...')
          window.location.href = '/login'
        }
      }
    },
    
    // Set API request headers
    setAuthHeader(_token: string | null) {
      // Here the Authorization header will be set in the API module
      // The specific implementation is in api/request.ts
    },
    
    // Login
    async login(loginForm: LoginForm) {
      // Prevent duplicate login requests
      if (this.loginLoading) {
        console.log('⏭️ Login request in progress, skip repeated calls')
        return false
      }

      try {
        this.loginLoading = true

        const response = await authApi.login(loginForm)

        if (response.success) {
          const { access_token, refresh_token, user } = response.data

          // Set authentication information
          this.setAuthInfo(access_token, refresh_token, user)

          // The open source version admin user has all permissions
          this.permissions = ['*']
          this.roles = ['admin']

          // Sync user preferences to appStore
          this.syncUserPreferencesToAppStore()

          // Start token automatic refresh timer
          const { setupTokenRefreshTimer } = await import('@/utils/auth')
          setupTokenRefreshTimer()

          // The success message is not displayed here, it is displayed by the caller
          return true
        } else {
          // Error messages are not displayed here, displayed by the caller
          return false
        }
      } catch (error: any) {
        console.error('Login failed:', error)
        // Error messages are not displayed here, displayed by the caller
        return false
      } finally {
        this.loginLoading = false
      }
    },
    
    // Register
    async register(registerForm: RegisterForm) {
      try {
        const response = await authApi.register(registerForm)
        
        if (response.success) {
          ElMessage.success('Registration successful, please log in')
          return true
        } else {
          ElMessage.error(response.message || 'Registration failed')
          return false
        }
      } catch (error: any) {
        console.error('Registration failed:', error)
        ElMessage.error(error.message || 'Registration failed, please try again')
        return false
      }
    },
    
    // Log out
    async logout() {
      try {
        // call logout API
        await authApi.logout()
      } catch (error) {
        console.error('Logout API call failed:', error)
      } finally {
        // Regardless of whether the API call is successful or not, local authentication information is cleared
        this.clearAuthInfo()
        console.log('✅ The user has logged out and the authentication information has been cleared')

        // Jump to login page
        this.redirectToLogin()
      }
    },
    
    // Refresh Token
    async refreshAccessToken() {
      try {
        console.log('🔄 Start refreshing Token...')

        if (!this.refreshToken) {
          console.warn('❌ Unable to refresh without refresh token')
          throw new Error('No refresh token')
        }

        // Verify refresh token format
        if (this.refreshToken.split('.').length !== 3) {
          console.error('❌ Refresh token Invalid format')
          throw new Error('Refresh token Invalid format')
        }

        const response = await authApi.refreshToken(this.refreshToken)

        if (response.success) {
          const { access_token, refresh_token } = response.data
          console.log('✅ Token Refresh successful')
          this.setAuthInfo(access_token, refresh_token)
          return true
        } else {
          console.error('❌ Token Refresh failed:', response.message)
          throw new Error(response.message || 'Token Refresh failed')
        }
      } catch (error: any) {
        console.error('❌ Token Refresh exception:', error.message)

        // If it is a network error or server error, do not clear the authentication information immediately
        if (error.code === 'NETWORK_ERROR' || error.response?.status >= 500) {
          console.warn('⚠️ Network or server error, authentication information retained')
          return false
        }

        // For other errors (such as 401), clear authentication information
        console.log('🧹 Clear authentication information and jump to login')
        this.clearAuthInfo()
        this.redirectToLogin()

        return false
      }
    },
    
    // Get user information
    async fetchUserInfo() {
      try {
        console.log('📡 Obtaining user information...')
        const response = await authApi.getUserInfo()

        if (response.success) {
          this.user = response.data
          console.log('✅ User information obtained successfully:', this.user?.username)

          // Sync user preferences to appStore
          this.syncUserPreferencesToAppStore()

          return true
        } else {
          console.warn('⚠️ Failed to obtain user information:', response.message)
          throw new Error(response.message || 'Failed to obtain user information')
        }
      } catch (error) {
        console.error('❌ Failed to obtain user information:', error)
        // Rethrow the error and let the upper layer handle it
        throw error
      }
    },
    
    // The open source version does not require permission checking, admin has all permissions
    async fetchUserPermissions() {
      this.permissions = ['*']
      this.roles = ['admin']
      return true
    },
    
    // Update user information
    async updateUserInfo(userInfo: UserUpdatePayload) {
      try {
        const response = await authApi.updateUserInfo(userInfo)

        if (response.success) {
          this.user = { ...this.user!, ...response.data }

          // Sync user preferences to appStore
          this.syncUserPreferencesToAppStore()

          ElMessage.success('User information updated successfully')
          return true
        } else {
          ElMessage.error(response.message || 'Update failed')
          return false
        }
      } catch (error: any) {
        console.error('Failed to update user information:', error)
        ElMessage.error(error.message || 'Update failed, please try again')
        return false
      }
    },
    
    // Sync user preferences to appStore
    syncUserPreferencesToAppStore() {
      if (!this.user?.preferences) return

      const appStore = useAppStore()
      const prefs = this.user!.preferences

      // Sync theme settings
      if (prefs.ui_theme) {
        appStore.setTheme(prefs.ui_theme as 'light' | 'dark' | 'auto')
      }

      // Sync sidebar width
      if (prefs.sidebar_width) {
        appStore.setSidebarWidth(prefs.sidebar_width)
      }

      // Sync language settings
      if (prefs.language) {
        appStore.setLanguage(prefs.language as 'zh-CN' | 'en-US')
      }

      // Synchronize analysis preferences
      if (prefs.default_market || prefs.default_depth || prefs.auto_refresh !== undefined || prefs.refresh_interval) {
        appStore.updatePreferences({
          defaultMarket: prefs.default_market as any,
          defaultDepth: prefs.default_depth as any,
          autoRefresh: prefs.auto_refresh,
          refreshInterval: prefs.refresh_interval
        })
      }

      console.log('✅ User preferences synced to appStore')
    },

    // Change password
    async changePassword(oldPassword: string, newPassword: string) {
      try {
        const response = await authApi.changePassword({
          old_password: oldPassword,
          new_password: newPassword,
          confirm_password: newPassword
        })

        if (response.success) {
          ElMessage.success('Password changed successfully')
          return true
        } else {
          ElMessage.error(response.message || 'Password change failed')
          return false
        }
      } catch (error: any) {
        console.error('Failed to change password:', error)
        ElMessage.error(error.message || 'Failed to change password, please try again')
        return false
      }
    },
    
    // Set redirect path
    setRedirectPath(path: string) {
      this.redirectPath = path
    },
    
    // Get and clear redirect paths
    getAndClearRedirectPath(): string {
      const path = this.redirectPath || '/dashboard'
      this.redirectPath = '/dashboard'
      return path
    },
    
    // Check authentication status (with singleton Promise to prevent concurrent initialization)
    async checkAuthStatus() {
      // If initialization has been completed, return directly
      if (this.authInitialized) {
        return
      }

      // If initializing, reuse the same Promise
      if (this.authInitPromise) {
        return this.authInitPromise
      }

      // Start initialization and cache Promise
      this.authInitPromise = this._doCheckAuthStatus().finally(() => {
        this.authInitialized = true
      })

      return this.authInitPromise
    },

    // Actual authentication status checking logic
    async _doCheckAuthStatus() {
      if (this.token) {
        try {
          console.log('🔍 Check token validity...')
          // Verify whether the token is valid
          const valid = await this.fetchUserInfo()
          if (valid) {
            this.isAuthenticated = true
            await this.fetchUserPermissions()
            console.log('✅ Authentication status verified successfully')
          } else {
            // Token Invalid, try refreshing
            console.log('🔄 Token Invalid, try refreshing...')
            await this.refreshAccessToken()
          }
        } catch (error: unknown) {
          console.error('❌ Checking authentication status failed:', error)
          // If it is a network error or timeout, the authentication information will not be cleared, but will be marked as unauthenticated.
          if ((error as any)?.code === 'ECONNABORTED' || (error as any)?.message?.includes('timeout')) {
            console.warn('⚠️ The network times out, and the authentication information is retained but marked as unauthenticated.')
            this.isAuthenticated = false
          } else {
            // If there are other errors, the authentication information will be cleared.
            this.clearAuthInfo()
            this.redirectToLogin()
          }
        }
      } else {
        console.log('📝 Without token, skip JWT authentication check')
        // In JD Cloud mode, try to call /api/auth/me through Basic Auth (carrying cookies) to complete automatic password-free login.
        if (isJdyunMode()) {
          try {
            console.log('☁️  JD Cloud Mode: Try Basic Auth password-free authentication')
            const ok = await this.fetchUserInfo()
            if (ok) {
              this.isAuthenticated = true
              await this.fetchUserPermissions()
              console.log('✅ JD Cloud Basic Auth password-free authentication successful:', this.user?.username)
            }
          } catch (e: any) {
            console.log('⚠️  JD Cloud Basic Auth not logged in (normal):', e?.message || e)
          }
        }
      }
    }
  }
})
