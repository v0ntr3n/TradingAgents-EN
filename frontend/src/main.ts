import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import zhCn from 'element-plus/es/locale/lang/zh-cn'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

import App from './App.vue'
import router from './router'
import { setupGlobalComponents } from './components'
import { setupDeliverableDownloadInterceptor } from './utils/deliverableDownload'
import { useAuthStore } from './stores/auth'
import { useAppStore } from './stores/app'
import './styles/index.scss'
import './styles/dark-theme.scss'

// Create application instance
const app = createApp(App)

// Register Element Plus Icon
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// Use plugins
const pinia = createPinia()
app.use(pinia)
app.use(router)
// Set global Chinese locale (Element Plus)
dayjs.locale('zh-cn')
app.use(ElementPlus, {
  size: 'default',
  zIndex: 3000,
  locale: zhCn,
  // Configure message prompts
  message: {
    max: 3, // Display up to 3 messages simultaneously
    grouping: true, // Enable message grouping, messages with the same content will not be displayed repeatedly
    duration: 3000, // The default display time is 3 seconds
  },
})

// Register global components
setupGlobalComponents(app)

// Intelligent assistant deliverable download interception (the browser navigation of the download link in the historical message does not have JWT, and the global delegation is changed) fetch+blob) 
setupDeliverableDownloadInterceptor()

// Global error handling
app.config.errorHandler = (err, _vm, info) => {
  console.error('global error:', err, info)

  // Check if it is an authentication error
  if (err && typeof err === 'object') {
    const error = err as any
    // Check the error message or status code
    if (
      !error.__skipGlobalAuthRedirect && (
        error.message?.includes('Authentication failed') ||
        error.message?.includes('Login has expired') ||
        error.message?.includes('Token') ||
        error.response?.status === 401 ||
        error.code === 401
      )
    ) {
      console.log('🔒 Global error handling: Authentication error detected, jump to login page')
      const authStore = useAuthStore()
      authStore.clearAuthInfo()
      router.push('/login')
    }
  }

  // Error monitoring services can be integrated here
}

// Global warning handling
app.config.warnHandler = (msg, _vm, trace) => {
  console.warn('global warning:', msg, trace)
}

// Initialize authentication status
const initApp = async () => {
  try {
    const authStore = useAuthStore()
    const appStore = useAppStore()

    console.log('🔄 Initialize application state...')

    // Apply theme
    appStore.applyTheme()
    console.log('🎨 Theme has been applied:', appStore.theme)

    // Set up network status monitoring
    window.addEventListener('online', () => {
      console.log('🌐 Network is connected')
      appStore.setOnlineStatus(true)
      appStore.checkApiConnection()
    })

    window.addEventListener('offline', () => {
      console.log('📱 The network is disconnected')
      appStore.setOnlineStatus(false)
      appStore.setApiConnected(false)
    })

    // Check API connection status
    console.log('🔍 Check API connection status...')
    const apiConnected = await appStore.checkApiConnection()

    if (apiConnected) {
      await appStore.fetchApiVersion()
    }

    if (apiConnected) {
      console.log('✅ API The connection is normal, check the authentication status...')
      // Check locally stored authentication information (set a short timeout)
      const checkPromise = authStore.checkAuthStatus()
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Authentication check timeout')), 5000) // 5 seconds timeout
      })

      await Promise.race([checkPromise, timeoutPromise])
      console.log('✅ Authentication status initialization completed')

      // If the user is logged in, start the token automatic refresh timer
      if (authStore.isAuthenticated) {
        const { setupTokenRefreshTimer } = await import('./utils/auth')
        setupTokenRefreshTimer()
      }
    } else {
      console.log('⚠️ API Connection failed, authentication check skipped')
    }
  } catch (error: unknown) {
    console.warn('⚠️ App initialization failed, but the app will continue to launch:', error)
    // If it is a network error, it will not affect application startup.
    if ((error as any)?.code === 'ECONNABORTED' || (error as any)?.message?.includes('timeout')) {
      console.log('📱 Offline mode: App will launch without backend connection')
    }
  } finally {
    // Mount the application regardless of authentication status
    app.mount('#app')
    console.log('🚀 Application is mounted')
  }
}

// Start application
initApp()

// Debugging information in development environment
if (import.meta.env.DEV) {
  console.log('🚀 TradingAgents-CN v3.0.0 Front-end application started')
  console.log('📊 current environment:', import.meta.env.MODE)
  console.log('🔗 API address:', import.meta.env.VITE_API_BASE_URL || '/api')
}
