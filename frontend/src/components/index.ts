import type { App } from 'vue'
import MarketSelector from './Global/MarketSelector.vue'
import MultiMarketStockSearch from './Global/MultiMarketStockSearch.vue'

// Global component registration
export function setupGlobalComponents(app: App) {
  // Register multi-market related components
  app.component('MarketSelector', MarketSelector)
  app.component('MultiMarketStockSearch', MultiMarketStockSearch)
}

export default setupGlobalComponents
