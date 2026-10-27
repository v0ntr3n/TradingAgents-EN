<template>
  <el-card class="account-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span>Capital account</span>
        <div class="actions">
          <el-button type="primary" size="small" @click="openDepositDialog()">
            <el-icon><Plus /></el-icon> Deposit
          </el-button>
          <el-button size="small" @click="openWithdrawDialog()">
            <el-icon><Minus /></el-icon> Withdraw funds
          </el-button>
          <el-button size="small" @click="showSettingsDialog = true">
            <el-icon><Setting /></el-icon>
          </el-button>
        </div>
      </div>
    </template>

    <!-- uninitialized state -->
    <div v-if="!hasInitialized" class="init-prompt">
      <el-empty description="Initial funds have not been set yet">
        <el-button type="primary" @click="showInitDialog = true">Set up initial funding</el-button>
      </el-empty>
    </div>

    <!-- Account Summary - Tab display by currency -->
    <div v-else class="summary-content">
      <el-tabs v-model="activeCurrency" type="border-card" class="currency-tabs">
        <!-- A shares (CNY) -->
        <el-tab-pane label="🇨🇳 A shares (CNY)" name="CNY">
          <CurrencyAccount
            :summary="summary"
            currency="CNY"
            symbol="¥"
            @deposit="() => openDepositDialog('CNY')"
            @withdraw="() => openWithdrawDialog('CNY')"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Initialization dialog -->
    <el-dialog v-model="showInitDialog" title="Set up initial funding" width="500px">
      <el-form :model="initForm" label-width="120px">
        <el-form-item label="A shares (CNY)">
          <el-input-number v-model="initForm.CNY" :min="0" :max="100000000" :step="10000" :precision="0" style="width: 100%" placeholder="Optional" />
        </el-form-item>
        <el-alert type="info" :closable="false" style="margin-bottom: 16px">
          <template #default>
            You can set the initial funds of multiple currencies at the same time. At least one currency needs to be set.
          </template>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="showInitDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleInitialize">OK</el-button>
      </template>
    </el-dialog>

    <!-- Deposit dialog box -->
    <el-dialog v-model="showDepositDialog" :title="`Deposit - ${getCurrencyLabel(transactionForm.currency)}`" width="400px">
      <el-form :model="transactionForm" label-width="80px">
        <el-form-item label="market">
          <el-radio-group v-model="transactionForm.currency">
            <el-radio-button value="CNY">🇨🇳 A shares</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Amount">
          <el-input-number v-model="transactionForm.amount" :min="100" :max="100000000" :step="1000" :precision="2" style="width: 100%" />
          <span class="currency-hint">{{ getCurrencySymbol(transactionForm.currency) }}</span>
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="transactionForm.description" placeholder="Optional" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDepositDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleDeposit">OK</el-button>
      </template>
    </el-dialog>

    <!-- Withdrawal dialog box -->
    <el-dialog v-model="showWithdrawDialog" :title="`Withdraw funds - ${getCurrencyLabel(transactionForm.currency)}`" width="400px">
      <el-form :model="transactionForm" label-width="80px">
        <el-form-item label="market">
          <el-radio-group v-model="transactionForm.currency">
            <el-radio-button value="CNY">🇨🇳 A shares</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Amount">
          <el-input-number
            v-model="transactionForm.amount"
            :min="100"
            :max="getMaxWithdraw(transactionForm.currency)"
            :step="1000"
            :precision="2"
            style="width: 100%"
          />
          <span class="currency-hint">{{ getCurrencySymbol(transactionForm.currency) }}</span>
        </el-form-item>
        <el-form-item label="Available">
          <span class="available-cash">{{ getCurrencySymbol(transactionForm.currency) }}{{ formatMoney(summary?.cash?.[transactionForm.currency] || 0) }}</span>
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="transactionForm.description" placeholder="Optional" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showWithdrawDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleWithdraw">OK</el-button>
      </template>
    </el-dialog>

    <!-- settings dialog -->
    <el-dialog v-model="showSettingsDialog" title="Account settings" width="450px">
      <el-form :model="settingsForm" label-width="140px">
        <el-form-item label="Maximum position of a single stock">
          <el-input-number v-model="settingsForm.max_position_pct" :min="5" :max="100" :step="5" />
          <span class="unit">%</span>
        </el-form-item>
        <el-form-item label="maximum loss tolerance">
          <el-input-number v-model="settingsForm.max_loss_pct" :min="1" :max="50" :step="1" />
          <span class="unit">%</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSettingsDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleUpdateSettings">save</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, Minus, Setting } from '@element-plus/icons-vue'
import { portfolioApi, type AccountSummary } from '@/api/portfolio'
import { ElMessage } from 'element-plus'
import CurrencyAccount from './CurrencyAccount.vue'

const emit = defineEmits<{
  (e: 'updated'): void
}>()

const loading = ref(false)
const submitting = ref(false)
const summary = ref<AccountSummary | null>(null)
const activeCurrency = ref<'CNY'>('CNY')

// dialog state
const showInitDialog = ref(false)
const showDepositDialog = ref(false)
const showWithdrawDialog = ref(false)
const showSettingsDialog = ref(false)

// form data
const initForm = ref({ CNY: 0 })
const transactionForm = ref({ amount: 10000, currency: 'CNY' as string, description: '' })
const settingsForm = ref({ max_position_pct: 30, max_loss_pct: 10 })

// Has it been initialized?
const hasInitialized = computed(() => {
  const cny = (summary.value?.initial_capital?.CNY || 0) + (summary.value?.total_deposit?.CNY || 0)
  return cny > 0
})

// Format amount
const formatMoney = (val: number) => {
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Currency Related Methods
const getCurrencySymbol = (currency: string) => {
  const map: Record<string, string> = { CNY: '¥' }
  return map[currency] || '¥'
}

const getCurrencyLabel = (currency: string) => {
  const map: Record<string, string> = { CNY: 'A shares (CNY)' }
  return map[currency] || currency
}

const getMaxWithdraw = (currency: string) => {
  return summary.value?.cash?.[currency as keyof typeof summary.value.cash] || 0
}

// Open the deposit dialog
const openDepositDialog = (currency?: string) => {
  transactionForm.value = { amount: 10000, currency: currency || activeCurrency.value || 'CNY', description: '' }
  showDepositDialog.value = true
}

// Open the withdrawal dialog box
const openWithdrawDialog = (currency?: string) => {
  transactionForm.value = { amount: 10000, currency: currency || activeCurrency.value || 'CNY', description: '' }
  showWithdrawDialog.value = true
}

// Load data
const loadData = async () => {
  loading.value = true
  try {
    const res = await portfolioApi.getAccountSummary()
    if (res.success && res.data) {
      summary.value = res.data
      // Update settings form
      settingsForm.value = {
        max_position_pct: res.data.settings?.max_position_pct || 30,
        max_loss_pct: res.data.settings?.max_loss_pct || 10
      }
    }
  } catch (e) {
    console.error('Failed to load account summary', e)
  } finally {
    loading.value = false
  }
}

// Initialize account
const handleInitialize = async () => {
  const amount = initForm.value.CNY
  if (amount <= 0) {
    ElMessage.warning('Please enter valid initial funds')
    return
  }

  submitting.value = true
  try {
    const res = await portfolioApi.initializeAccount(amount, 'CNY')
    if (!res.success) {
      ElMessage.error(`CNY Initial fund setup failed: ${res.message}`)
      return
    }

    ElMessage.success('Initial funds set up successfully')
    showInitDialog.value = false
    initForm.value = { CNY: 0 }
    await loadData()
    emit('updated')
  } catch (e: any) {
    ElMessage.error(e.message || 'Setup failed')
  } finally {
    submitting.value = false
  }
}

// Deposit
const handleDeposit = async () => {
  submitting.value = true
  try {
    const res = await portfolioApi.deposit(transactionForm.value.amount, transactionForm.value.currency, transactionForm.value.description)
    if (res.success) {
      ElMessage.success(res.message || 'Deposit successful')
      showDepositDialog.value = false
      transactionForm.value = { amount: 10000, currency: 'CNY', description: '' }
      await loadData()
      emit('updated')
    } else {
      ElMessage.error(res.message || 'Deposit failed')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Deposit failed')
  } finally {
    submitting.value = false
  }
}

// Withdraw funds
const handleWithdraw = async () => {
  submitting.value = true
  try {
    const res = await portfolioApi.withdraw(transactionForm.value.amount, transactionForm.value.currency, transactionForm.value.description)
    if (res.success) {
      ElMessage.success(res.message || 'Withdraw successfully')
      showWithdrawDialog.value = false
      transactionForm.value = { amount: 10000, currency: 'CNY', description: '' }
      await loadData()
      emit('updated')
    } else {
      ElMessage.error(res.message || 'Withdrawal failed')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Withdrawal failed')
  } finally {
    submitting.value = false
  }
}

// Update settings
const handleUpdateSettings = async () => {
  submitting.value = true
  try {
    const res = await portfolioApi.updateAccountSettings(settingsForm.value)
    if (res.success) {
      ElMessage.success('Settings saved')
      showSettingsDialog.value = false
      await loadData()
    } else {
      ElMessage.error(res.message || 'Save failed')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'Save failed')
  } finally {
    submitting.value = false
  }
}

// Expose methods to parent component
defineExpose({ loadData })

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.account-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: flex;
  gap: 8px;
}

.init-prompt {
  padding: 20px 0;
}

.summary-content {
  padding: 8px 0;
}

.stat-item {
  text-align: center;
}

.stat-item .label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-item .value {
  font-size: 18px;
  font-weight: bold;
  color: #303133;
}

.stat-item .value.profit {
  color: #f56c6c; /* Red indicates profit (Chinese stock market norm) */
}

.stat-item .value.loss {
  color: #67c23a; /* Green indicates loss (Chinese stock market norm) */
}

.stat-item .pct {
  font-size: 12px;
  font-weight: normal;
}

.detail-row {
  font-size: 13px;
}

.detail-label {
  color: #909399;
}

.detail-value {
  color: #606266;
  margin-left: 4px;
}

.unit {
  margin-left: 8px;
  color: #909399;
}

.currency-tabs {
  margin-top: 8px;
}

.currency-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.currency-hint {
  margin-left: 8px;
  color: #909399;
  font-weight: bold;
}

.available-cash {
  color: #67c23a;
  font-weight: bold;
}
</style>
