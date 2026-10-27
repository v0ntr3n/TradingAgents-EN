import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { isJdyunMode } from '@/utils/config'
// Pro-exclusive routes (v3.6.0 Community Edition open-source separation M1): centralized in pro.routes.ts,
// replaced with empty exports in Community Edition releases without modifying this file
import { proWorkflowRoutes, proTradingSystemRoutes, proAnalysisChildren, proSettingsChildren, proLearningChildren } from './pro.routes'

// Configure NProgress
NProgress.configure({
  showSpinner: false,
  minimum: 0.2,
  easing: 'ease',
  speed: 500
})

// Route configuration
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  // Legacy doc link compatibility: redirect /paper/<name>.md to Learning Center article route
  {
    path: '/paper/:name.md',
    name: 'PaperMdRedirect',
    redirect: (to) => `/learning/article/${to.params.name as string}`,
    meta: { title: 'Document Redirect', hideInMenu: true, requiresAuth: false }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Dashboard',
      icon: 'Dashboard',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'DashboardHome',
        component: () => import('@/views/Dashboard/index.vue'),
        meta: {
          title: 'Dashboard',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/help',
    name: 'Help',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'User Manual',
      icon: 'QuestionFilled',
      requiresAuth: true,
      hideInMenu: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'HelpHome',
        component: () => import('@/views/Help/index.vue'),
        meta: {
          title: 'User Manual',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/guide',
    name: 'Guide',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'User Guide',
      icon: 'Document',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'GuideHome',
        component: () => import('@/views/Guide/index.vue'),
        meta: {
          title: 'User Guide',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/analysis',
    name: 'Analysis',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/analysis/single',
    children: [
      {
        path: 'single',
        name: 'SingleAnalysis',
        component: () => import('@/views/Analysis/SingleAnalysis.vue')
      },
      // Batch analysis (Pro) → pro.routes.ts
      ...proAnalysisChildren,
      {
        path: 'general',
        name: 'GeneralAnalysis',
        component: () => import('@/views/Analysis/GeneralAnalysis.vue')
      },

    ]
  },
  {
    path: '/screening',
    name: 'StockScreening',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Stock Screener',
      icon: 'Search',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'StockScreeningHome',
        component: () => import('@/views/Screening/index.vue'),
        meta: {
          title: 'Stock Screener',
          requiresAuth: true
        }
      }
    ]
  },

  {
    path: '/favorites',
    name: 'Favorites',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Watchlist',
      icon: 'Star',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'FavoritesHome',
        component: () => import('@/views/Favorites/index.vue'),
        meta: {
          title: 'Watchlist',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/learning',
    name: 'Learning',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Learning Center',
      icon: 'Reading',
      requiresAuth: false,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'LearningHome',
        component: () => import('@/views/Learning/index.vue'),
        meta: {
          title: 'Learning Center',
          requiresAuth: false
        }
      },
      {
        path: ':category',
        name: 'LearningCategory',
        component: () => import('@/views/Learning/Category.vue'),
        meta: {
          title: 'Learning Category',
          requiresAuth: false
        }
      },
      {
        path: 'article/:id',
        name: 'LearningArticle',
        component: () => import('@/views/Learning/Article.vue'),
        meta: {
          title: 'Article Detail',
          requiresAuth: false
        }
      },
      {
        path: 'advanced',
        name: 'AdvancedCourses',
        component: () => import('@/views/Learning/Advanced.vue'),
        meta: {
          title: 'From Retail to Systematic Trader: AI-Powered Evolvable Investing',
          requiresAuth: false
        }
      },
      // Advanced course sample reports (Pro, paid course samples) → pro.routes.ts
      ...proLearningChildren,
      {
        path: 'advanced/:category/:lesson',
        name: 'AdvancedLesson',
        component: () => import('@/views/Learning/AdvancedLesson.vue'),
        meta: {
          title: 'From Retail to Systematic Trader: AI-Powered Evolvable Investing',
          requiresAuth: false
        }
      }
    ]
  },
  {
    path: '/stocks',
    name: 'Stocks',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Stock Detail',
      icon: 'TrendCharts',
      requiresAuth: true,
      hideInMenu: true,
      transition: 'fade'
    },
    children: [
      {
        path: ':code',
        name: 'StockDetail',
        component: () => import('@/views/Stocks/Detail.vue'),
        meta: {
          title: 'Stock Detail',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'fade'
        }
      }
    ]
  },


  {
    path: '/tasks',
    name: 'TaskCenter',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/tasks/unified',
    meta: {
      title: 'Task Center',
      icon: 'List',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: 'unified',
        name: 'UnifiedTaskCenter',
        component: () => import('@/views/Tasks/UnifiedTaskCenter.vue'),
        meta: { title: 'Task Center', requiresAuth: true }
      }
    ]
  },
  // Retain legacy route with redirect (in case of direct links)
  {
    path: '/tasks/old',
    name: 'TaskCenterHome',
    redirect: '/tasks/unified',
    meta: { title: 'Task Center (Legacy)', requiresAuth: true }
  },
  { path: '/queue', redirect: '/tasks/unified' },
  { path: '/analysis/history', redirect: '/tasks/unified' },
  {
    path: '/assistant',
    name: 'Assistant',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'AI Assistant',
      icon: 'ChatDotRound',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'AssistantHome',
        component: () => import('@/views/Assistant/index.vue'),
        meta: {
          title: 'AI Assistant',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/debug/embedded-nanobot',
    name: 'EmbeddedNanobotDebug',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Assistant Debug',
      hideInMenu: true,
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'EmbeddedNanobotDebugHome',
        component: () => import('@/views/Debug/EmbeddedNanobot.vue'),
        meta: {
          title: 'Assistant Debug',
          hideInMenu: true,
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/memory',
    name: 'Memory',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Object Memory',
      icon: 'Coin',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'MemoryHome',
        component: () => import('@/views/Memory/index.vue'),
        meta: {
          title: 'Stock Object Memory',
          requiresAuth: true
        }
      }
    ]
  },
  {
    // Skill Center (free and open-source since v3.6.0 in Community Edition)
    path: '/skills',
    name: 'SkillCenter',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Skill Center',
      icon: 'MagicStick',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'SkillCenterHome',
        component: () => import('@/views/Skills/SkillCenter.vue'),
        meta: {
          title: 'Skill Center',
          requiresAuth: true
        }
      },
      {
        path: 'generation/create',
        name: 'SkillGenerationCreate',
        component: () => import('@/views/Skills/SkillGenerationCreate.vue'),
        meta: {
          title: 'Create Skill',
          requiresAuth: true,
          hideInMenu: true
        }
      }
    ]
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Analysis Reports',
      icon: 'Document',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'ReportsHome',
        component: () => import('@/views/Reports/index.vue'),
        meta: {
          title: 'Analysis Reports',
          requiresAuth: true
        }
      },
      {
        path: 'view/:id',
        name: 'ReportDetail',
        component: () => import('@/views/Reports/ReportDetail.vue'),
        meta: {
          title: 'Report Detail',
          requiresAuth: true
        }
      },
      {
        path: 'token',
        name: 'TokenStatistics',
        component: () => import('@/views/Reports/TokenStatistics.vue'),
        meta: {
          title: 'Token Statistics',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Settings',
      icon: 'Setting',
      requiresAuth: true,
      transition: 'slide-left'
    },
    children: [
      {
        path: '',
        name: 'SettingsHome',
        component: () => import('@/views/Settings/index.vue'),
        meta: {
          title: 'Settings',
          requiresAuth: true
        }
      },
      {
        path: 'config',
        name: 'ConfigManagement',
        component: () => import('@/views/Settings/ConfigManagement.vue'),
        meta: {
          title: 'Configuration Management',
          requiresAuth: true
        }
      },
      {
        path: 'database',
        name: 'DatabaseManagement',
        component: () => import('@/views/System/DatabaseManagement.vue'),
        meta: {
          title: 'Database Management',
          requiresAuth: true
        }
      },
      {
        path: 'logs',
        name: 'OperationLogs',
        component: () => import('@/views/System/OperationLogs.vue'),
        meta: {
          title: 'Operation Logs',
          requiresAuth: true
        }
      },
      {
        path: 'system-logs',
        name: 'LogManagement',
        component: () => import('@/views/System/LogManagement.vue'),
        meta: {
          title: 'System Logs',
          requiresAuth: true
        }
      },
      {
        path: 'sync',
        name: 'MultiSourceSync',
        component: () => import('@/views/System/MultiSourceSync.vue'),
        meta: {
          title: 'Multi-Source Sync',
          requiresAuth: true
        }
      },
      {
        path: 'capability-index',
        name: 'CapabilityIndex',
        component: () => import('@/views/Settings/index.vue'),
        meta: {
          title: 'Tool Capability Index',
          requiresAuth: true
        }
      },
      {
        path: 'cache',
        name: 'CacheManagement',
        component: () => import('@/views/Settings/CacheManagement.vue'),
        meta: {
          title: 'Cache Management',
          requiresAuth: true
        }
      },
      {
        path: 'usage',
        name: 'UsageStatistics',
        component: () => import('@/views/Settings/UsageStatistics.vue'),
        meta: {
          title: 'Usage Statistics',
          requiresAuth: true
        }
      },
        {
        path: 'scheduler',
        name: 'SchedulerManagement',
        component: () => import('@/views/System/SchedulerManagement.vue'),
        meta: {
            title: 'Scheduled Tasks',
            requiresAuth: true
        }
      },
        // Social media message management (Pro data persistence) → pro.routes.ts
        {
          path: 'data-import',
          name: 'DataImport',
          component: () => import('@/views/System/DataImport.vue'),
          meta: {
            title: 'Data Import Management',
            requiresAuth: true
          }
        },
        {
          path: 'update',
          name: 'UpdateManagement',
          component: () => import('@/views/System/UpdateManagement.vue'),
          meta: {
            title: 'System Update',
            requiresAuth: true
          }
        },
      // Pro child routes (Templates/Prompts/Push/Groups/Scheduled Analysis/License/Social Media Messages/Data API Guide) → pro.routes.ts
      ...proSettingsChildren,
      {
        path: 'analysis-profiles',
        name: 'AnalysisProfiles',
        component: () => import('@/views/Settings/AnalysisProfiles.vue'),
        meta: { title: 'Sector/Stock Profiles', requiresAuth: true }
      },
      {
        path: 'jdyun-config',
        name: 'JdyunConfig',
        component: () => import('@/views/Settings/JdyunConfig.vue'),
        meta: { title: 'System Configuration', requiresAuth: true }
      }
    ]
  },

  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Auth/Login.vue'),
    meta: {
      title: 'Login',
      hideInMenu: true,
      transition: 'fade'
    }
  },

  {
    path: '/about',
    name: 'About',
    component: () => import('@/views/About/index.vue'),
    meta: {
      title: 'About',
      icon: 'InfoFilled',
      requiresAuth: false, // About page does not require authentication
      transition: 'fade'
    }
  },
  {
    path: '/paper',
    name: 'PaperTrading',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Paper Trading',
      icon: 'CreditCard',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'PaperTradingHome',
        component: () => import('@/views/PaperTrading/index.vue'),
        meta: {
          title: 'Paper Trading',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/portfolio',
    name: 'Portfolio',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Portfolio Analysis',
      icon: 'PieChart',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'PortfolioHome',
        component: () => import('@/views/Portfolio/index.vue'),
        meta: {
          title: 'Portfolio Analysis',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/review',
    name: 'TradeReview',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'Trade Review',
      icon: 'TrendCharts',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'TradeReviewHome',
        component: () => import('@/views/TradeReview/index.vue'),
        meta: {
          title: 'Trade Review',
          requiresAuth: true
        }
      }
    ]
  },
  // Analysis Workflow module (Pro) → pro.routes.ts
  ...proWorkflowRoutes,
  // Trading Plan (Pro, trading_plan_check paid feature) → pro.routes.ts
  ...proTradingSystemRoutes,

  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/Error/404.vue'),
    meta: {
      title: 'Page Not Found',
      hideInMenu: true,
      requiresAuth: true
    }
  }
]

// Create router instance
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

// Global before guard
router.beforeEach(async (to, _from, next) => {
  // Start progress bar
  NProgress.start()

  const authStore = useAuthStore()
  const appStore = useAppStore()

  // Wait for auth initialization to complete to avoid race conditions during navigation
  if (!authStore.authInitialized) {
    try {
      await authStore.checkAuthStatus()
    } catch {
      // Continue with standard check logic if initialization fails
    }
  }

  // Set page title
  const title = to.meta.title as string
  if (title) {
    document.title = `${title} - TradingAgents-CN`
  }

  console.log('🚦 Route guard check:', {
    path: to.fullPath,
    name: to.name,
    requiresAuth: to.meta.requiresAuth,
    requiresPro: to.meta.requiresPro,
    isAuthenticated: authStore.isAuthenticated,
    hasToken: !!authStore.token
  })

  // Check if Pro license permission is required
  if (to.meta.requiresPro) {
    try {
      const { useLicenseStore } = await import('@/stores/license')
      const licenseStore = useLicenseStore()
      
      // Verify license first if status is not loaded
      if (!licenseStore.licenseInfo) {
        await licenseStore.verifyLicense()
      }
      
      if (!licenseStore.isPro) {
        ElMessage.warning('This feature requires Pro membership. Please activate your license first.')
        NProgress.done()
        next('/settings/license')
        return
      }
    } catch (error) {
      console.error('Failed to check license permission:', error)
      // Allow access if check fails (may not be configured in dev environment)
    }
  }

  // Check if authentication is required
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    console.log('🔒 Authentication required but user is not logged in:', {
      path: to.fullPath,
      requiresAuth: to.meta.requiresAuth,
      isAuthenticated: authStore.isAuthenticated,
      token: authStore.token ? 'present' : 'absent'
    })
    // Save original path for redirect after login
    authStore.setRedirectPath(to.fullPath)
    next('/login')
    return
  }



  // Redirect to dashboard if already authenticated and visiting login page
  if (authStore.isAuthenticated && to.name === 'Login') {
    next('/dashboard')
    return
  }

  // JD Cloud edition first-login onboarding: redirect to /guide when visiting dashboard before completing guide
  if (authStore.isAuthenticated && isJdyunMode()) {
    const guideCompleted = (() => {
      try {
        return localStorage.getItem('jdyun_guide_completed') === 'true'
      } catch {
        return false
      }
    })()

    // Do not intercept if user actively clicked "View Guide" or is already on /guide
    const goingToGuide = to.path === '/guide'

    if (!guideCompleted && to.path === '/dashboard' && !goingToGuide) {
      next('/guide?mode=jdyun')
      return
    }
  }

  // PRO feature route check
  const proRoutes = [
    '/settings/email',
    '/settings/channel-configs',
    '/settings/watchlist-groups',
    '/settings/scheduled-analysis',
    '/settings/templates',  // 🔥 Prompt templates require Pro permission
    '/workflow'  // Analysis workflow requires Pro permission
  ]

  // Check if current route is a PRO route
  const isProRoute = proRoutes.some(route => to.path.startsWith(route))
  if (isProRoute && authStore.isAuthenticated) {
    // Lazy-import license store to avoid circular dependency
    const { useLicenseStore } = await import('@/stores/license')
    const licenseStore = useLicenseStore()

    // Ensure license status has been verified
    if (!licenseStore.licenseInfo) {
      await licenseStore.verifyLicense()
    }

    // If not Pro, show warning and redirect to license management page
    if (!licenseStore.isPro) {
      ElMessage.warning('This feature is exclusive to Pro members. Please upgrade your membership first.')
      next('/settings/license')
      return
    }
  }

  // Update current route info
  appStore.setCurrentRoute(to)

  next()
})

// Global after hook
router.afterEach((_to, _from) => {
  // Finish progress bar
  NProgress.done()

  // Post-navigation handling
  nextTick(() => {
    // Page analytics or tracking logic can be added here
  })
})

// Router error handler
router.onError((error) => {
  console.error('Router error:', error)
  NProgress.done()
  ElMessage.error('Failed to load page, please try again')
})

export default router

// Export routes configuration for external use
export { routes }
