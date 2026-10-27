import { defineStore } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'
import { useStorage } from '@vueuse/core'
import { APP_CONFIG } from '@/config/app'

export interface AppState {
  // Application base status
  loading: boolean
  loadingProgress: number
  theme: 'light' | 'dark' | 'auto'
  language: 'zh-CN' | 'en-US'

  // network status
  isOnline: boolean
  apiConnected: boolean
  lastApiCheck: number

  // layout status
  sidebarCollapsed: boolean
  sidebarWidth: number

  // Current routing information
  currentRoute: RouteLocationNormalized | null

  // User preferences
  preferences: {
    defaultMarket: 'A shares'
    defaultDepth: '1' | '2' | '3' | '4' | '5'  // 1-5 level analysis depth
    autoRefresh: boolean
    refreshInterval: number
    showWelcome: boolean
  }

  // System information
  version: string
  fullVersion: string
  buildTime: string
  apiVersion: string
}

const defaultPreferences: AppState['preferences'] = {
  defaultMarket: 'A shares',
  defaultDepth: '3',
  autoRefresh: true,
  refreshInterval: 30,
  showWelcome: true
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    loading: false,
    loadingProgress: 0,
    theme: (useStorage('app-theme', 'auto').value || 'auto') as 'light' | 'dark' | 'auto',
    language: (useStorage('app-language', 'zh-CN').value || 'zh-CN') as 'zh-CN' | 'en-US',

    isOnline: navigator.onLine,
    apiConnected: false,
    lastApiCheck: 0,

    sidebarCollapsed: useStorage('sidebar-collapsed', false).value || false,
    sidebarWidth: useStorage('sidebar-width', 240).value || 240,

    currentRoute: null,

    preferences: useStorage<AppState['preferences']>('user-preferences', defaultPreferences).value || defaultPreferences,

    version: APP_CONFIG.version,
    fullVersion: APP_CONFIG.fullVersion,
    buildTime: new Date().toISOString(),
    apiVersion: ''
  }),

  getters: {
    // Whether it is a dark theme
    isDarkTheme(): boolean {
      if (this.theme === 'auto') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches
      }
      return this.theme === 'dark'
    },
    
    // Sidebar actual width
    actualSidebarWidth(): number {
      return this.sidebarCollapsed ? 64 : this.sidebarWidth
    },
    
    // Current page title
    currentPageTitle(): string {
      return this.currentRoute?.meta?.title as string || 'TradingAgents-CN'
    },
    
    // Application information
    appInfo(): Record<string, any> {
      return {
        version: this.version,
        fullVersion: this.fullVersion,
        buildTime: this.buildTime,
        apiVersion: this.apiVersion,
        theme: this.theme,
        language: this.language
      }
    }
  },

  actions: {
    // Set loading status
    setLoading(loading: boolean, progress = 0) {
      this.loading = loading
      this.loadingProgress = progress
    },
    
    // Set loading progress
    setLoadingProgress(progress: number) {
      this.loadingProgress = Math.max(0, Math.min(100, progress))
    },
    
    // switch theme
    toggleTheme() {
      const themes: Array<'light' | 'dark' | 'auto'> = ['light', 'dark', 'auto']
      const currentIndex = themes.indexOf(this.theme)
      this.theme = themes[(currentIndex + 1) % themes.length]
      this.applyTheme()
    },
    
    // Set theme
    setTheme(theme: 'light' | 'dark' | 'auto') {
      this.theme = theme
      this.applyTheme()
      // Sync to localStorage
      localStorage.setItem('app-theme', theme)
    },
    
    // Apply theme
    applyTheme() {
      const isDark = this.isDarkTheme
      document.documentElement.classList.toggle('dark', isDark)
      
      // Update meta tag
      const themeColorMeta = document.querySelector('meta[name="theme-color"]')
      if (themeColorMeta) {
        themeColorMeta.setAttribute('content', isDark ? '#1f2937' : '#409EFF')
      }
    },
    
    // switch language
    setLanguage(language: 'zh-CN' | 'en-US') {
      this.language = language
      document.documentElement.lang = language
      // Sync to localStorage
      localStorage.setItem('app-language', language)
    },
    
    // Toggle sidebar
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
    },
    
    // Set sidebar status
    setSidebarCollapsed(collapsed: boolean) {
      this.sidebarCollapsed = collapsed
      // Sync to localStorage
      localStorage.setItem('sidebar-collapsed', String(collapsed))
    },

    // Set sidebar width
    setSidebarWidth(width: number) {
      this.sidebarWidth = Math.max(200, Math.min(400, width))
      // Sync to localStorage
      localStorage.setItem('sidebar-width', String(this.sidebarWidth))
    },
    
    // Set current route
    setCurrentRoute(route: RouteLocationNormalized) {
      this.currentRoute = route
    },
    
    // Update user preferences
    updatePreferences(preferences: Partial<AppState['preferences']>) {
      this.preferences = { ...this.preferences, ...preferences }
      // Sync to localStorage
      localStorage.setItem('user-preferences', JSON.stringify(this.preferences))
    },
    
    // Reset preferences
    resetPreferences() {
      this.preferences = {
        defaultMarket: 'A shares',
        defaultDepth: '3',
        autoRefresh: true,
        refreshInterval: 30,
        showWelcome: true
      }
    },
    
    // Set network status
    setOnlineStatus(isOnline: boolean) {
      this.isOnline = isOnline
    },

    // Set API connection status
    setApiConnected(connected: boolean) {
      this.apiConnected = connected
      this.lastApiCheck = Date.now()
    },

    // Check API connection status
    async checkApiConnection() {
      try {
        // Use AbortController to implement timeouts
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 seconds timeout

        const response = await fetch('/api/health', {
          method: 'GET',
          signal: controller.signal
        })

        clearTimeout(timeoutId)
        const connected = response.ok
        this.setApiConnected(connected)
        return connected
      } catch (error: unknown) {
        if ((error as any)?.name === 'AbortError') {
          console.warn('API Connection check timeout')
        } else {
          console.warn('API Connection check failed:', error)
        }
        this.setApiConnected(false)
        return false
      }
    },

    // Get API version information
    async fetchApiVersion() {
      try {
        // Use AbortController to implement timeouts
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 seconds timeout

        const response = await fetch('/api/health', {
          signal: controller.signal
        })

        clearTimeout(timeoutId)

        if (response.ok) {
          const data = await response.json()
          this.apiVersion = data.version || 'unknown'
          this.setApiConnected(true)
        } else {
          this.setApiConnected(false)
        }
      } catch (error: unknown) {
        if ((error as any)?.name === 'AbortError') {
          console.warn('Timeout getting API version')
        } else {
          console.warn('Failed to get API version:', error)
        }
        this.apiVersion = 'unknown'
        this.setApiConnected(false)
      }
    },

    // Reset app state
    resetAppState() {
      this.loading = false
      this.loadingProgress = 0
      this.currentRoute = null
    }
  }
})
