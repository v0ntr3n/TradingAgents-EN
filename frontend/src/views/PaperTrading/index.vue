<template>
  <div class="paper-trading">
    <div class="header">
      <div class="title">
        <el-icon style="margin-right:8px"><CreditCard /></el-icon>
        <span>simulated trading</span>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" text size="small" @click="refreshAll">Refresh</el-button>
        <el-button type="primary" :icon="Plus" @click="openOrderDialog">Place a market order</el-button>
        <el-button type="success" plain :icon="Setting" @click="() => openInitializeDialog()">Initialize account</el-button>
        <el-button type="danger" plain :icon="Delete" @click="confirmReset">Reset account</el-button>
      </div>
    </div>

    <!-- Risk warning banner -->
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    >
      <template #title>
        <div style="font-weight: 600; font-size: 14px;">⚠️ Simulated trading risk warning</div>
      </template>
      <div style="font-size: 13px; line-height: 1.8;">
        <p style="margin: 0 0 8px 0;">
          <strong>1. Simulation properties:</strong>This function is a simulated trading tool that uses virtual funds and does not involve real fund transactions. It is only for learning and practice and does not constitute any investment advice.
        </p>
        <p style="margin: 0 0 8px 0;">
          <strong>2. Data latency:</strong>The market data used in simulated trading may be delayed and different from the actual market conditions. The transaction price and timing are for reference only.
        </p>
        <p style="margin: 0 0 8px 0;">
          <strong>3. Real offer difference:</strong>There are significant differences between the simulated trading environment and real trading, including but not limited to: slippage, liquidity, transaction costs, psychological pressure and other factors. Simulated profits do not mean that real trading can be profitable.
        </p>
        <p style="margin: 0;">
          <strong>4. Investment risks:</strong>Stock investments involve market risks that may result in loss of principal. Please do not use simulated trading results as the basis for real investment decisions. Please fully evaluate your own risk tolerance and consult a professional investment advisor before real trading.
        </p>
      </div>
    </el-alert>

    <el-row :gutter="16" class="body">
      <el-col :span="8">
        <el-card shadow="hover" class="account-card">
          <template #header><div class="card-hd">Account information</div></template>
          <div v-if="account">
            <el-tabs v-model="activeMarketTab" type="border-card">
              <!-- A stock account -->
              <el-tab-pane label="🇨🇳 A shares" name="CN">
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="available funds">¥{{ fmtAmount(account.cash?.CNY ?? (typeof account.cash === 'number' ? account.cash : 0)) }}</el-descriptions-item>
                  <el-descriptions-item label="Position market value">¥{{ fmtAmount(account.positions_value?.CNY ?? (typeof account.positions_value === 'number' ? account.positions_value : 0)) }}</el-descriptions-item>
                  <el-descriptions-item label="total assets">¥{{ fmtAmount(account.equity?.CNY ?? (typeof account.equity === 'number' ? account.equity : 0)) }}</el-descriptions-item>
                  <el-descriptions-item label="Realized profit and loss">
                    <span :style="{ color: (account.realized_pnl?.CNY ?? (typeof account.realized_pnl === 'number' ? account.realized_pnl : 0)) >= 0 ? '#67C23A' : '#F56C6C' }">
                      ¥{{ fmtAmount(account.realized_pnl?.CNY ?? (typeof account.realized_pnl === 'number' ? account.realized_pnl : 0)) }}
                    </span>
                  </el-descriptions-item>
                </el-descriptions>
              </el-tab-pane>
            </el-tabs>

            <div style="margin-top: 12px; text-align: center; color: #909399; font-size: 12px">
              Update time: {{ formatDateTime(account.updated_at) }}
            </div>
          </div>
          <el-empty v-else description="No account data yet" />
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="hover" class="positions-card">
          <template #header>
            <div class="card-hd">
              Position
              <span style="margin-left: 8px; font-size: 12px; color: #909399; font-weight: normal">
                ({{ filteredPositions.length }} a)
              </span>
            </div>
          </template>
          <el-table :data="filteredPositions" size="small" v-loading="loading.positions">
            <el-table-column label="code" width="100">
              <template #default="{ row }">
                <el-link type="primary" @click="viewStockDetail(row.code)">{{ row.code }}</el-link>
              </template>
            </el-table-column>
            <el-table-column label="Name" width="100">
              <template #default="{ row }">{{ row.name || '-' }}</template>
            </el-table-column>
            <el-table-column label="market" width="70">
              <template #default>
                <el-tag type="success" size="small">🇨🇳 A shares</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Quantity" width="80">
              <template #default="{ row }">
                {{ row.quantity }}
                <span v-if="row.available_qty !== undefined && row.available_qty < row.quantity" style="color: #909399; font-size: 11px">
                  (Available{{ row.available_qty }})
                </span>
              </template>
            </el-table-column>
            <el-table-column label="average price" width="100">
              <template #default="{ row }">{{ getCurrencySymbol(row.currency) }}{{ fmtPrice(row.avg_cost) }}</template>
            </el-table-column>
            <el-table-column label="latest price" width="100">
              <template #default="{ row }">{{ getCurrencySymbol(row.currency) }}{{ fmtPrice(row.last_price) }}</template>
            </el-table-column>
            <el-table-column label="floating profit" width="120">
              <template #default="{ row }">
                <span :style="{ color: (Number(row.last_price || 0) - Number(row.avg_cost || 0)) >= 0 ? '#67C23A' : '#F56C6C' }">
                  {{ getCurrencySymbol(row.currency) }}{{ fmtAmount((Number(row.last_price || 0) - Number(row.avg_cost || 0)) * Number(row.quantity || 0)) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="200">
              <template #default="{ row }">
                <el-button size="small" type="primary" link @click="viewStockDetail(row.code)">Details</el-button>
                <el-button size="small" type="success" link @click="goAnalysisWithCode(row.code)">analysis</el-button>
                <el-button size="small" type="danger" link @click="sellPosition(row)">sell</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="hover" class="orders-card" style="margin-top:16px">
          <template #header>
            <div class="card-hd">
              Order record
              <span style="margin-left: 8px; font-size: 12px; color: #909399; font-weight: normal">
                ({{ filteredOrders.length }} Article)
              </span>
            </div>
          </template>
          <el-table :data="filteredOrders" size="small" v-loading="loading.orders">
            <el-table-column label="time" width="160">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="direction" width="80">
              <template #default="{ row }">
                <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                  {{ row.side === 'buy' ? 'buy' : 'sell' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="code" width="100">
              <template #default="{ row }">
                <el-link type="primary" @click="viewStockDetail(row.code)">{{ row.code }}</el-link>
              </template>
            </el-table-column>
            <el-table-column label="Name" width="100">
              <template #default="{ row }">{{ row.name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="price" label="Transaction price" width="100">
              <template #default="{ row }">{{ fmtPrice(row.price) }}</template>
            </el-table-column>
            <el-table-column prop="quantity" label="Quantity" width="100" />
            <el-table-column label="Status" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'filled' ? 'success' : 'info'" size="small">
                  {{ row.status === 'filled' ? 'Transaction completed' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <!-- Related research reports -->
            <el-table-column label="correlation analysis" width="120">
              <template #default="{ row }">
                <el-button v-if="row.analysis_id" size="small" type="primary" link @click="viewReport(row.analysis_id)">
                  View report
                </el-button>
                <span v-else style="color: #909399;">-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="orderDialog" title="Place a market order" width="480px">
      <!-- Research contextual prompts -->
      <div v-if="(order as any).analysis_id" class="analysis-context" style="margin-bottom:12px">
        <el-alert :closable="false" type="info" show-icon>
          <template #title>
            From the research report:<span style="font-family:monospace">{{ (order as any).analysis_id }}</span>
            <el-button link size="small" type="primary" style="margin-left:8px" @click="viewReport((order as any).analysis_id)">View report</el-button>
          </template>
          <div v-if="analysisLoading" style="color:#666">Loading research summary…</div>
          <div v-else-if="analysisContext">
            <div style="font-size:12px;color:#666">
              <span>Target:{{ analysisContext.stock_symbol || '-' }}</span>
              <span style="margin-left:8px">Research summary:{{ analysisContext.summary || analysisContext.recommendation || '-' }}</span>
            </div>
          </div>
        </el-alert>
      </div>

      <el-form label-width="90px">
        <el-form-item label="direction">
          <el-radio-group v-model="order.side">
            <el-radio-button label="buy">buy</el-radio-button>
            <el-radio-button label="sell">sell</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="code">
          <el-input v-model="order.code" placeholder="A shares: 600519" @input="detectMarket" />
        </el-form-item>
        <el-form-item label="market" v-if="detectedMarket">
          <el-tag v-if="detectedMarket === 'ETF'" type="success">📈 ETF fund (CNY)</el-tag>
          <el-tag v-else type="success">🇨🇳 A stock market (CNY)</el-tag>
          <div style="margin-top: 8px; font-size: 12px; color: #909399">
            <span v-if="detectedMarket === 'ETF'">💡 On-exchange ETFs are simulated according to A-share rules.T+1, Buy today and sell tomorrow</span>
            <span v-else>💡 A shares T+1, Buy today and sell tomorrow</span>
          </div>
        </el-form-item>
        <el-form-item label="Quantity">
          <el-input-number v-model="order.qty" :min="1" />
        </el-form-item>
        <el-form-item label="price">
          <el-checkbox v-model="useCustomPrice" style="margin-right: 8px">Specify price</el-checkbox>
          <el-input-number
            v-if="useCustomPrice"
            v-model="order.price"
            :min="0.01"
            :precision="2"
            :step="0.01"
            style="width: 150px"
            placeholder="Enter price"
          />
          <span v-if="useCustomPrice && priceRange" style="margin-left: 8px; font-size: 12px; color: #909399">
            (Today s range: {{ priceRange.low?.toFixed(2) || '-' }} - {{ priceRange.high?.toFixed(2) || '-' }})
          </span>
          <span v-else-if="!useCustomPrice && currentPrice" style="margin-left: 8px; font-size: 12px; color: #909399">
            Use real-time prices: {{ currentPrice.toFixed(2) }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="orderDialog=false">Cancel</el-button>
        <el-button type="primary" @click="submitOrder">Submit</el-button>
      </template>
    </el-dialog>

    <!-- Initialize account dialog -->
    <el-dialog v-model="initializeDialog" title="Initialize account" width="500px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
        <template #title>
          <div style="font-size: 13px;">
            💡 Tip: Initializing your account will set up your initial funds for simulated trading. If the account already exists, all positions and orders will be cleared and reset to the specified amount.
          </div>
        </template>
      </el-alert>
      
      <el-form :model="initialCash" label-width="120px">
        <el-form-item label="🇨🇳 A initial capital (CNY)">
          <el-input-number
            v-model="initialCash.CNY"
            :min="0"
            :precision="2"
            :step="10000"
            style="width: 100%"
            placeholder="Please enter the initial capital of A shares"
          >
            <template #prefix>¥</template>
          </el-input-number>
          <div style="font-size: 12px; color: #909399; margin-top: 4px;">
            Default: ¥1,000,000.00
          </div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="initializeDialog = false">Cancel</el-button>
        <el-button type="primary" @click="handleInitialize" :loading="initializing">
          Confirm initialization
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CreditCard, Refresh, Plus, Delete, Setting } from '@element-plus/icons-vue'
import { paperApi } from '@/api/paper'
import { analysisApi } from '@/api/analysis'
import { stocksApi } from '@/api/stocks'
import { formatDateTime } from '@/utils/datetime'
import { getMarketByStockCode, normalizeMarketForAnalysis } from '@/utils/market'

// Routing and initialization
const route = useRoute()
const router = useRouter()

// data
const account = ref<any | null>(null)
const positions = ref<any[]>([])
const orders = ref<any[]>([])
const loading = ref({ account: false, positions: false, orders: false })

const orderDialog = ref(false)
const order = ref({ side: 'buy', code: '', qty: 100, price: undefined as number | undefined })
const detectedMarket = ref<string>('')

// Initialize account dialog
const initializeDialog = ref(false)
const initializing = ref(false)
const initialCash = ref<{ CNY: number }>({
  CNY: 1000000
})
const activeMarketTab = ref<string>('CN')
const useCustomPrice = ref(false)
const currentPrice = ref<number | null>(null)
const priceRange = ref<{ high: number; low: number } | null>(null)

// Calculated property: filtering positions based on current market tab
const filteredPositions = computed(() => {
  if (!positions.value || positions.value.length === 0) return []
  return positions.value.filter(pos => {
    const market = pos.market || 'CN'
    return market === activeMarketTab.value
  })
})

// Calculated property: filter orders based on current market tab
const filteredOrders = computed(() => {
  if (!orders.value || orders.value.length === 0) return []
  return orders.value.filter(ord => {
    const market = ord.market || 'CN'
    return market === activeMarketTab.value
  })
})

// Analyze context
const analysisContext = ref<any | null>(null)
const analysisLoading = ref(false)

// method
function fmtPrice(n: number | null | undefined) {
  if (n == null || Number.isNaN(n as any)) return '-'
  return Number(n).toFixed(2)
}
function fmtAmount(n: number | null | undefined) {
  // 🔥 Fix: Handle NaN and non-numeric values
  if (n == null || Number.isNaN(n as any) || typeof n !== 'number') return '0.00'
  return Number(n).toFixed(2)
}

// Get currency symbol
function getCurrencySymbol(_currency: string | undefined) {
  return '¥'
}

// Get price information (current price and price range)
async function fetchPriceInfo() {
  if (!order.value.code || !detectedMarket.value) {
    currentPrice.value = null
    priceRange.value = null
    return
  }

  try {
    const res = await paperApi.getQuote(order.value.code, detectedMarket.value)
    if (res.success && res.data) {
      currentPrice.value = res.data.current_price || null
      if (res.data.high && res.data.low) {
        priceRange.value = {
          high: res.data.high,
          low: res.data.low
        }
      } else {
        priceRange.value = null
      }
    }
  } catch (e: any) {
    console.warn('Failed to obtain price information:', e)
    currentPrice.value = null
    priceRange.value = null
  }
}

// Detect market type
function detectMarket() {
  const code = order.value.code.trim().toUpperCase()
  if (!code) {
    detectedMarket.value = ''
    currentPrice.value = null
    priceRange.value = null
    return
  }

  // A Share: 6 digits
  if (/^\d{6}$/.test(code)) {
    detectedMarket.value = getMarketByStockCode(code) === 'ETF' ? 'ETF' : 'CN'
    fetchPriceInfo()
    return
  }

  // Default A shares
  detectedMarket.value = 'CN'
  fetchPriceInfo()
}

async function fetchAccount() {
  try {
    loading.value.account = true
    const res = await paperApi.getAccount()
    if (res.success) {
      account.value = res.data.account
      // Optional: It can also be filled in from the positions brought back by the account interface.
      // positions.value = res.data.positions || positions.value
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to obtain account')
  } finally {
    loading.value.account = false
  }
}

async function fetchPositions() {
  try {
    loading.value.positions = true
    const res = await paperApi.getPositions()
    if (res.success) {
      positions.value = res.data.items || []
      // Get stock names in batches
      await fetchStockNames(positions.value)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to obtain position')
  } finally {
    loading.value.positions = false
  }
}

async function fetchOrders() {
  try {
    loading.value.orders = true
    const res = await paperApi.getOrders(50)
    if (res.success) {
      orders.value = res.data.items || []
      // Get stock names in batches
      await fetchStockNames(orders.value)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to get order')
  } finally {
    loading.value.orders = false
  }
}

// Get stock names in batches
async function fetchStockNames(items: any[]) {
  if (!items || items.length === 0) return

  // Get all unique tickers
  const codes = [...new Set(items.map(item => item.code).filter(Boolean))]

  // Get the names of all stocks in parallel
  await Promise.all(
    codes.map(async (code) => {
      try {
        const res = await stocksApi.getQuote(code)
        if (res.success && res.data && res.data.name) {
          // Update all projects containing this code
          items.forEach(item => {
            if (item.code === code) {
              item.name = res.data.name
            }
          })
        }
      } catch (error) {
        console.warn(`Get stocks ${code} name failed:`, error)
      }
    })
  )
}

function openOrderDialog() {
  orderDialog.value = true
  // Reset price related status
  useCustomPrice.value = false
  order.value.price = undefined
  currentPrice.value = null
  priceRange.value = null
  // If you already have a code, get pricing information
  if (order.value.code && detectedMarket.value) {
    fetchPriceInfo()
  }
}

async function submitOrder() {
  try {
    const payload: any = { 
      side: order.value.side as 'buy' | 'sell', 
      code: order.value.code, 
      quantity: Number(order.value.qty),
      market: detectedMarket.value || undefined
    }
    
    // 🔥 If price is specified, add to payload
    if (useCustomPrice.value && order.value.price !== undefined && order.value.price !== null) {
      payload.price = Number(order.value.price)
      console.log('[Place an order] Use specified price:', payload.price)
    } else {
      console.log('[Place an order] Use real-time prices (no price specified)')
    }
    
    if ((order.value as any).analysis_id) payload.analysis_id = (order.value as any).analysis_id
    
    const res = await paperApi.placeOrder(payload)
    if (res.success) {
      ElMessage.success('Order placed successfully')
      orderDialog.value = false
      // Reset order form
      order.value = { side: 'buy', code: '', qty: 100, price: undefined }
      useCustomPrice.value = false
      currentPrice.value = null
      priceRange.value = null
      await refreshAll()
    } else {
      ElMessage.error(res.message || 'Order failed')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'Order failed')
  }
}

// Open the Initialize Account dialog box
function openInitializeDialog(isReset: boolean = false) {
  // If the account already exists and it is not a reset operation, the current amount is displayed as the default value
  if (account.value && !isReset) {
    const cash = account.value.cash
    if (typeof cash === 'object' && cash !== null) {
      initialCash.value = {
        CNY: cash.CNY || 1000000
      }
    } else if (typeof cash === 'number') {
      // Compatible with older formats
      initialCash.value = {
        CNY: cash
      }
    }
  } else {
    // Reset operation or new account, use default values
    initialCash.value = {
      CNY: 1000000
    }
  }
  initializeDialog.value = true
}

// Handle initialization account
async function handleInitialize() {
  try {
    // Verification amount
    if (initialCash.value.CNY < 0) {
      ElMessage.error('The initial amount cannot be negative')
      return
    }
    
    // Check if the amount>0
    if (initialCash.value.CNY <= 0) {
      ElMessage.warning('The initial amount must be greater than 0')
      return
    }
    
    initializing.value = true
    const res = await paperApi.initializeAccount({
      initial_cash: {
        CNY: initialCash.value.CNY
      }
    })
    
    if (res.success) {
      ElMessage.success('Account has been initialized')
      initializeDialog.value = false
      await refreshAll()
    } else {
      ElMessage.error(res.message || 'Initialization failed')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to initialize account')
  } finally {
    initializing.value = false
  }
}

async function confirmReset() {
  try {
    // Ask about using a custom amount
    await ElMessageBox.confirm(
      'Resetting the account will clear all orders and positions.\n\n Use a custom initial amount?',
      'Reset account',
      {
        confirmButtonText: 'Use custom amount',
        cancelButtonText: 'Use default amount',
        distinguishCancelAndClose: true,
        type: 'warning'
      }
    )
    // User selected"Use custom amount", Open initialization dialog (reset mode)
    openInitializeDialog(true)
  } catch (e: any) {
    // User selected"Use default amount"or close the dialog
    if (e === 'cancel') {
      // User selected"Use default amount", Continue the reset process
      try {
        await ElMessageBox.confirm('All orders and positions will be cleared, and the account will be reset to the default initial cash. Are you sure to reset?', 'Confirm reset', { type: 'warning' })
        const res = await paperApi.resetAccount()
        if (res.success) {
          ElMessage.success('Account has been reset')
          await refreshAll()
        }
      } catch (resetError: any) {
        if (resetError !== 'cancel') {
          ElMessage.error(resetError.message || 'Reset failed')
        }
      }
    }
    // if e === 'close', The user closes the dialog box without taking any action
  }
}

async function refreshAll() {
  await Promise.all([fetchAccount(), fetchPositions(), fetchOrders()])
}

// View report details (jump to report details page)
function viewReport(analysisId: string) {
  if (!analysisId) return
  // Jump to report details page
  router.push({ name: 'ReportDetail', params: { id: analysisId } })
}

// Jump to analysis page (with ticker and market)
function goAnalysisWithCode(stockCode: string) {
  if (!stockCode) return
  // Determine the market based on stock code
  const market = getMarketByCode(stockCode)
  router.push({ name: 'SingleAnalysis', query: { stock: stockCode, market } })
}

// Determine the market based on stock code
function getMarketByCode(code: string): string {
  if (!code) return 'A shares'
  return getMarketByStockCode(code)
}

// View stock details (jump to stock details page)
function viewStockDetail(stockCode: string) {
  if (!stockCode) return
  // Jump to stock details page
  router.push({ name: 'StockDetail', params: { code: stockCode } })
}

// Sell position
async function sellPosition(position: any) {
  if (!position || !position.code) return

  try {
    // Confirm sell
    await ElMessageBox.confirm(
      `Confirm sell ${position.name || position.code}? \n\n Current positions:${position.quantity} shares\n Average price:${fmtPrice(position.avg_cost)}\n Latest price:${fmtPrice(position.last_price)}`,
      'sell confirmation',
      {
        confirmButtonText: 'Confirm sell',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    // Submit sell order
    const payload = {
      side: 'sell' as const,
      code: position.code,
      quantity: position.quantity,
      market: getMarketByStockCode(position.code) === 'ETF' ? 'ETF' : position.market
    }

    const res = await paperApi.placeOrder(payload)
    if (res.success) {
      ElMessage.success('Sold successfully')
      await refreshAll()
    } else {
      ElMessage.error(res.message || 'Selling failed')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Selling failed:', error)
      ElMessage.error(error?.message || 'Selling failed')
    }
  }
}

async function fetchAnalysisContext(analysisId: string) {
  try {
    analysisLoading.value = true
    analysisContext.value = null
    const res = await analysisApi.getResult(analysisId)
    analysisContext.value = res as any
  } catch (e) {
    // Ignore errors, just for display
  } finally {
    analysisLoading.value = false
  }
}

onMounted(() => {
  let hasPrefill = false
  const qCode = String(route.query.code || '').trim()
  if (qCode) {
    order.value.code = qCode
    hasPrefill = true
  }
  const qMarket = String(route.query.market || '').trim()
  if (qMarket) {
    const normalizedMarket = normalizeMarketForAnalysis(qMarket)
    if (normalizedMarket === 'ETF') {
      detectedMarket.value = 'ETF'
    } else {
      detectedMarket.value = 'CN'
    }
    hasPrefill = true
  }
  const qSide = String(route.query.side || '').trim().toLowerCase()
  if (qSide === 'buy' || qSide === 'sell') {
    order.value.side = qSide as 'buy' | 'sell'
    hasPrefill = true
  }
  const qQty = Number(route.query.qty || route.query.quantity || 0)
  if (!Number.isNaN(qQty) && qQty > 0) {
    order.value.qty = Math.round(qQty)
    hasPrefill = true
  }
  // Optional: Bring analysis when placing orders later ID
  const qAnalysisId = String(route.query.analysis_id || '').trim()
  if (qAnalysisId) {
    // Temporarily stored locally and attached when waiting for order submission
    ;(order as any).analysis_id = qAnalysisId
    fetchAnalysisContext(qAnalysisId)
    hasPrefill = true
  }
  if (hasPrefill) {
    orderDialog.value = true
    if (!detectedMarket.value && qCode) {
      detectMarket()
    } else if (qCode && detectedMarket.value) {
      fetchPriceInfo()
    }
  }
  refreshAll()
})
</script>

<style scoped>
.paper-trading { padding: 16px; }
.header { display:flex; align-items:center; justify-content:space-between; margin-bottom: 12px; }
.title { display:flex; align-items:center; font-weight: 600; font-size: 16px; }
.card-hd { font-weight: 600; }
</style>