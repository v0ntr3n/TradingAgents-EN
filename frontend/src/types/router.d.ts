import 'vue-router'

// Augment Vue Router's RouteMeta to include app-specific fields
declare module 'vue-router' {
  interface RouteMeta {
    // Page title
    title?: string
    // Whether certification is required
    requiresAuth?: boolean
    // Menu icon name (same as Element Plus icon name)
    icon?: string
    // Whether to hide in the menu
    hideInMenu?: boolean
    // Page switching animation name (used for <transition name="...">) 
    transition?: string
  }
}