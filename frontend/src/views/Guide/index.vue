<template>
  <div class="guide-page">
    <!-- welcome title -->
    <div class="guide-header">
      <h1 class="guide-title">
        <el-icon><Document /></el-icon>
        Welcome TradingAgents-CN
      </h1>
      <p class="guide-subtitle">
        {{ isJdyunModeRef ? 'Follow the steps below to complete the initial setup and start using AI-assisted stock analysis' : 'Follow the steps below to complete the initial setup and start learning AI-assisted stock analysis technology' }}
      </p>
      <el-button v-if="!loading" text type="primary" @click="loadAllStatus" class="refresh-btn">
        <el-icon><Refresh /></el-icon>
        Refresh progress
      </el-button>
    </div>

    <!-- JD Cloud Edition Guide: 4 steps -->
    <div v-if="isJdyunModeRef" class="steps-container" v-loading="loading" element-loading-text="Checking configuration progress...">
      <el-steps :active="jdyunCurrentStep" direction="vertical" finish-status="success">
        <!-- JD Cloud Version Step 1: Welcome (system is ready) -->
        <el-step title="Welcome" description="Your system has been configured by your administrator">
          <template #description>
            <div class="step-content">
              <div class="jdyun-ready-list">
                <div class="ready-item">
                  <el-icon color="#67c23a"><CircleCheck /></el-icon>
                  <span>Large model:<strong>{{ jdyunStatus.current_model || 'GLM-5.1' }}</strong> (ready)</span>
                </div>
                <div class="ready-item">
                  <el-icon color="#67c23a"><CircleCheck /></el-icon>
                  <span>Data source:<strong>Tushare + AKShare</strong> (ready)</span>
                </div>
                <div class="ready-item">
                  <el-icon color="#67c23a"><CircleCheck /></el-icon>
                  <span>Fully functional and open (no license activation required)</span>
                </div>
              </div>
              <p class="step-tip" style="margin-top: 12px;">
                Start analyzing in just 3 steps: Sync your data → Add a stock watchlist → Complete first study
              </p>
            </div>
          </template>
        </el-step>

        <!-- JD Cloud Version Step 2: Synchronize stock data -->
        <el-step title="Sync stock data" description="Synchronize basic stock data to the system">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.dataSynced" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                Stock data has been synchronized
              </p>
              <template v-else>
                <p>Synchronize basic stock data and obtain the latest stock information:</p>
                <ul class="step-list">
                  <li><strong>Step one:</strong>Synchronize basic data (stock list, basic information)</li>
                  <li><strong>Step two:</strong>Synchronize historical data (K line, market)</li>
                  <li><strong>Step three:</strong>Synchronize financial data (financial reports, indicators)</li>
                  <li>
                    <strong style="color: var(--el-color-warning);">Note:</strong>
                    Analysis is performed when the data is not synchronized, and the results may be inaccurate due to incomplete data.
                  </li>
                </ul>
              </template>
              <el-button type="primary" @click="goToSync">
                <el-icon><Refresh /></el-icon>
                Go to data sync
              </el-button>
            </div>
          </template>
        </el-step>

        <!-- JD Cloud Version Step 3: Search and add stocks to watch list -->
        <el-step title="Search and add stocks to watchlist" description="Search for stocks of interest and add to your watchlist">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.hasFavorites" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                Stock watchlist added
              </p>
              <template v-else>
                <p>Get started with the stock screener:</p>
                <ul class="step-list">
                  <li>in"stock screen"Page search for stock symbol or name</li>
                  <li>View stock details</li>
                  <li>Add stocks of interest to"Stock Watchlist"</li>
                </ul>
              </template>
              <el-button type="primary" @click="goToScreening">
                <el-icon><Search /></el-icon>
                Go to stock screener
              </el-button>
            </div>
          </template>
        </el-step>

        <!-- JD Cloud Version Step 4: Complete the first analysis -->
        <el-step title="Complete your first study" description="AI research on stock watchlists">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.hasAnalysis" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                First research analysis completed
              </p>
              <template v-else>
                <p>Start your first AI stock research:</p>
                <ul class="step-list">
                  <li>in"single stock research"Enter the stock code on the page (eg: 600519)</li>
                  <li>Select research depth (level 1-5, quick to comprehensive)</li>
                  <li>Click"Start researching", Waiting for multi-agent collaboration to complete</li>
                  <li>About 5-8 minutes at low depth, maybe 15-20 minutes at high depth</li>
                </ul>
              </template>
              <el-button type="primary" @click="goToAnalysis">
                <el-icon><TrendCharts /></el-icon>
                Start researching
              </el-button>
            </div>
          </template>
        </el-step>
      </el-steps>

      <!-- Complete boot button -->
      <div v-if="jdyunAllCompleted" class="jdyun-complete-section">
        <el-alert
          title="Boot is complete"
          type="success"
          description="You have completed all the initial setup steps and are ready to use the full functionality of the system."
          :closable="false"
          show-icon
        />
        <div class="complete-actions">
          <el-button @click="goToLearning">
            <el-icon><Reading /></el-icon>
            View Learning Center
          </el-button>
          <el-button type="primary" size="large" @click="completeJdyunGuide">
            Go to dashboard
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- Skip boot: Allow entry to the dashboard even if all steps are not completed to avoid an infinite loop -->
      <div v-else class="jdyun-complete-section">
        <el-alert
          title="You can skip booting at any time"
          type="info"
          description="You can still enter the dashboard to start using it before completing all the steps. You can check back later from the Usage Guide in the sidebar."
          :closable="false"
          show-icon
        />
        <div class="complete-actions">
          <el-button @click="goToLearning">
            <el-icon><Reading /></el-icon>
            View Learning Center
          </el-button>
          <el-button type="primary" size="large" @click="completeJdyunGuide">
            Go to dashboard
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- Standard version boot: 7 steps (the original logic remains unchanged) -->
    <div v-else class="steps-container" v-loading="loading" element-loading-text="Checking configuration progress...">
      <el-steps :active="currentStep" direction="vertical" finish-status="success">
        <!-- Step 1: Get the Big Model API Key -->
        <el-step title="Get the big model API key" description="Select and get an API key for a large language model">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.llmKey" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                Large model API key configured
              </p>
              <template v-else>
              <p>The system supports a variety of mainstream large language models. It is recommended to use domestic models first. You need to choose one of them and obtain an API key:</p>
              <ul class="step-list">
                <li>
                  <strong>Volcano Ark:</strong>Bean bag large model Seed series (recommended for domestic users)<br>
                  <span style="font-size: 13px; color: var(--el-text-color-secondary);">Thanks to Byte Volcano Engine for sponsoring this project! Sign up and get 25 million Tokens</span>
                  <div class="register-link-wrapper">
                    <el-link href="https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN" target="_blank" type="primary" :underline="false" class="register-link">
                      <el-icon><Link /></el-icon>
                      Register and receive 25 million Tokens, go now
                    </el-link>
                  </div>
                </li>
                <li>
                  <strong>DeepSeek: </strong>DeepSeek-V4-Pro, V4-Flash Model (recommended for domestic users)
                  <div class="register-link-wrapper">
                    <el-link href="https://platform.deepseek.com/" target="_blank" type="primary" :underline="false" class="register-link">
                      <el-icon><Link /></el-icon>
                      Register a DeepSeek account now
                    </el-link>
                  </div>
                </li>
                <li><strong>Wisdom spectrum AI:</strong>GLM-5, GLM-5.2 Other models</li>
                <li><strong>OpenAI: </strong>GPT-5, GPT-5.4 Other models</li>
                <li><strong>Claude: </strong>Claude Opus 5, Opus 4.8 Other models</li>
                <li><strong>Others:</strong>Kimi, Xiaomi MiMo, AIHubMix, silicon-based mobile, etc.</li>
                <li><strong>Local model:</strong>Ollama (No API Key required, local deployment)</li>
              </ul>
              <p class="step-tip">💡 Tip: Domestic users are recommended to use Volcano Ark or DeepSeek first for faster access and more stable use.</p>
              </template>
            </div>
          </template>
        </el-step>

        <!-- Step 2: Get the data source API key -->
        <el-step title="Get data source API key" description="Register a Tushare account and get API Token">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.dataKey" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                Data source Token configured
              </p>
              <template v-else>
              <p>System usage <strong>Tushare</strong> As a data source, you need to register an account and obtain an API Token:</p>
              <ul class="step-list">
                <li>Visit Tushare official website to register an account</li>
                <li>Get it in your personal center after logging in API Token</li>
                <li>Save the token, you will need it for subsequent configuration.</li>
              </ul>
              <div class="register-link-wrapper">
                <el-link href="https://tushare.pro/weborder/#/login?reg=tacn" target="_blank" type="primary" :underline="false" class="register-link">
                  <el-icon><Link /></el-icon>
                  Register a Tushare account now
                </el-link>
                <el-link href="https://tushare.pro/user/index" target="_blank" type="info" :underline="false" class="register-link" style="margin-left: 12px;">
                  <el-icon><Link /></el-icon>
                  Go to personal center to get Token
                </el-link>
              </div>
              </template>
            </div>
          </template>
        </el-step>

        <!-- Step 3: Fill in the Token configuration -->
        <el-step title="Fill in the Token configuration" description="Fill in your API key on the settings page">
          <template #description>
            <div class="step-content">
              <p>Complete the following configuration on the settings page:</p>
              <ul class="step-list">
                <li>
                  <strong>Configure the large model API key:</strong>
                  <ol style="margin-top: 8px; padding-left: 24px;">
                    <li>enter"Configuration management" → "Factory management"menu</li>
                    <li>Find the corresponding manufacturer (such as Volcano Ark, DeepSeek, etc.)</li>
                    <li>Click"Edit"button</li>
                    <li>Fill in the API key field with the key obtained in step 1</li>
                    <li>Save configuration</li>
                  </ol>
                </li>
                <li>
                  <strong>Configure data source API key:</strong>
                  <div style="margin-top: 8px; padding-left: 0;">
                    <p style="margin-bottom: 8px; color: var(--el-text-color-regular); font-size: 14px;">
                      <strong>IMPORTANT NOTE:</strong>Tushare The data source requires account points to reach <strong style="color: var(--el-color-warning);">2000 Points or more</strong>to use the full functionality.
                      If there are insufficient points, the system will automatically use the free open source data source (AKShare) as an alternative.
                      <strong style="color: var(--el-color-warning);">Please note:</strong>Due to stability issues, open source data sources<strong>Used only to experience this platform</strong>, Not recommended for formal learning or analysis scenarios.
                    </p>
                    <ol style="margin-top: 8px; padding-left: 24px;">
                      <li>enter"Configuration management" → "Data source configuration"menu</li>
                      <li>Find the Tushare data source and click"Edit"</li>
                      <li>Fill in the Token obtained in step 2 (in <a href="https://tushare.pro/user/index" target="_blank" rel="noopener noreferrer" class="tushare-link">Tushare Personal center</a> Get)</li>
                      <li>Save configuration</li>
                      <li>If the points are less than 2000, the system will automatically use free data sources such as AKShare (for experience only, not recommended for official use)</li>
                    </ol>
                  </div>
                </li>
                <li>After saving the configuration, you can click"test"Button to verify the connection is normal</li>
              </ul>
              <el-button type="primary" @click="goToSettings">
                <el-icon><Setting /></el-icon>
                Go to settings page
              </el-button>
            </div>
          </template>
        </el-step>

        <!-- Step 4: Activate License (the community version does not have this interface and is automatically hidden during runtime) -->
        <el-step v-if="licenseSupported" title="Activate License Authorization" description="Enter the License key to activate the system">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.licenseValid" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                License Already activated, no need to repeat the operation
              </p>
              <template v-else>
                <p>v3.0 The version requires license activation to use full functionality:</p>
                <ul class="step-list">
                  <li>enter"settings" → "personal settings" → "Authorization management"Page</li>
                  <li>Enter the License Key you received</li>
                  <li>Click"activate"Button completes activation</li>
                  <li>All features available upon activation</li>
                </ul>
                <p class="step-tip">💡 Tip: If you do not receive the license key, please contact the administrator to obtain it</p>
              </template>
              <el-button type="primary" @click="goToLicense">
                <el-icon><Key /></el-icon>
                Go to authorization management
              </el-button>
            </div>
          </template>
        </el-step>

        <!-- Step 5: Sync data -->
        <el-step title="Sync stock data" description="Synchronize basic stock data to the system">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.dataSynced" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                Stock data has been synchronized
              </p>
              <template v-else>
              <p>Complete data synchronization and obtain the latest basic stock information:</p>
              <ul class="step-list">
                <li>
                  <strong>Important note:</strong>Current data synchronization function<strong style="color: var(--el-color-warning);">Only supports A-share market</strong>. 
                </li>
                <li>
                  <strong>Multiple data source synchronization steps:</strong>
                  <ol style="margin-top: 8px; padding-left: 24px;">
                    <li>enter"settings" → "Synchronization of multiple data sources"Function</li>
                    <li><strong>Step one:</strong>Synchronize basic data (stock list, basic information, etc.)</li>
                    <li><strong>Step two:</strong>Synchronize historical data (K-line data, historical market conditions, etc.)</li>
                    <li><strong>Step three:</strong>Synchronize financial data (financial report data, financial indicators, etc.)</li>
                    <li>Wait for all sync tasks to complete (may take longer)</li>
                  </ol>
                </li>
                <li>
                  <strong style="color: var(--el-color-danger);">⚠️ IMPORTANT NOTE:</strong>
                  If data synchronization is not completed, stock analysis may<strong>Unable to get complete data</strong>, lead to analysis results<strong>Inaccurate</strong>. 
                  It is recommended to wait for data synchronization to complete before performing analysis.
                </li>
              </ul>
              <el-button type="primary" @click="goToSync">
                <el-icon><Refresh /></el-icon>
                Go to data sync
              </el-button>
              </template>
            </div>
          </template>
        </el-step>

        <!-- Step 6: Search for stocks -->
        <el-step title="Search and add stocks to watchlist" description="Search for stocks of interest and add to your watchlist">
          <template #description>
            <div class="step-content">
              <p>Get started with the stock screener:</p>
              <ul class="step-list">
                <li>in"stock screen"Page search for stock symbol or name</li>
                <li>View stock details</li>
                <li>Add stocks of interest to"Stock Watchlist"</li>
                <li>
                  <strong style="color: var(--el-color-warning);">💡 Tips:</strong>
                  If you use the AKShare (AK) data source, due to data synchronization limitations,<strong>Unable to use category filtering function</strong>. 
                  It is recommended to use the Tushare data source for complete filtering capabilities.
                </li>
              </ul>
              <el-button type="primary" @click="goToScreening">
                <el-icon><Search /></el-icon>
                Go to stock screener
              </el-button>
            </div>
          </template>
        </el-step>

        <!-- Step 7: Complete your first research -->
        <el-step title="Complete your first study" description="AI research on stock watchlists">
          <template #description>
            <div class="step-content">
              <p v-if="stepStatus.hasAnalysis" class="step-completed-tip">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                First research analysis completed
              </p>
              <template v-else>
              <p>Start your first AI stock research:</p>
              <ul class="step-list">
                <li>
                  <strong>Fill in the stock code:</strong>
                  in"single stock research"Enter the stock code on the page (such as: 000001, 600000, etc.)
                </li>
                <li>
                  <strong>Check whether the data is complete:</strong>
                  The system will automatically detect whether the basic data, historical data, and financial data of the stock are complete.
                </li>
                <li>
                  <strong>Select research depth and research team:</strong>
                  <ol style="margin-top: 8px; padding-left: 24px;">
                    <li>Select the research depth level (levels 1-5, from fast to comprehensive)</li>
                    <li>Select a research team (you can choose multiple research modules, such as market, fundamentals, news, etc.)</li>
                  </ol>
                </li>
                <li>
                  <strong>Start researching:</strong>
                  Click"Start researching"button, the system will start the multi-agent collaborative research process
                </li>
                <li>
                  <strong>Wait and see the results:</strong>
                  Wait for the study to complete (about 5-8 minutes for low depth, maybe 15-20 minutes for high depth) and view the detailed research report and study conclusions after the study is completed
                </li>
              </ul>
              <el-button type="primary" @click="goToAnalysis">
                <el-icon><TrendCharts /></el-icon>
                Start researching
              </el-button>
              </template>
            </div>
          </template>
        </el-step>
      </el-steps>
    </div>

    <!-- Prompt message -->
    <el-alert
      title="Tips"
      type="info"
      :closable="false"
      show-icon
      class="info-alert"
    >
      <template #default>
        <p>If you have trouble setting up, you can:</p>
        <ul>
          <li>View <a href="/about" target="_blank">About page</a> Learn more</li>
          <li>visit <a href="/learning" target="_blank">Learning Center</a> View tutorial</li>
          <li>Contact technical support for assistance</li>
        </ul>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Document,
  Setting,
  Refresh,
  Search,
  TrendCharts,
  Link,
  Key,
  CircleCheck,
  Reading,
  ArrowRight
} from '@element-plus/icons-vue'
import { ApiClient } from '@/api/request'
import { isJdyunMode } from '@/utils/config'

const router = useRouter()
const isJdyunModeRef = isJdyunMode()
const currentStep = ref(0)
const loading = ref(true)
// License Whether the step is available (the community version does not have the /api/license/status interface, and this step is automatically hidden when 404 occurs)
const licenseSupported = ref(true)

// JD Cloud version status
const jdyunStatus = ref({
  current_model: ''
})

// Completion status of each step
const stepStatus = ref({
  llmKey: false,        // steps 1: LLM API key
  dataKey: false,       // steps 2: data source Token
  configDone: false,    // steps 3: Fill in the configuration
  dataSynced: false,    // steps 5: Data synchronization
  hasFavorites: false,  // steps 6: Add a stock watchlist
  hasAnalysis: false,   // steps 7: Complete research
  licenseValid: false   // License activate
})

// Check stock watchlist status
const checkFavorites = async () => {
  try {
    const resp = await ApiClient.get('/api/favorites')
    if (resp.success && resp.data) {
      const favorites = Array.isArray(resp.data) ? resp.data : (resp.data.items || resp.data.favorites || [])
      stepStatus.value.hasFavorites = favorites.length > 0
    }
  } catch (e) {
    console.error('Checking stock watchlist failed:', e)
  }
}

// Check JD Cloud version configuration (current model name)
const checkJdyunConfig = async () => {
  try {
    const resp = await ApiClient.get('/api/config/jdyun/status')
    if (resp.success && resp.data) {
      jdyunStatus.value.current_model = resp.data.current_model || resp.data.model || ''
    }
  } catch (e) {
    // Use default value if interface does not exist
    jdyunStatus.value.current_model = 'GLM-5.1'
  }
}

// Current steps of JD Cloud version (based on stepStatus)
const jdyunCurrentStep = computed(() => {
  // 4 Step: Welcome → sync → Stock Watchlist → first analysis
  if (!stepStatus.value.dataSynced) return 1
  if (!stepStatus.value.hasFavorites) return 2
  if (!stepStatus.value.hasAnalysis) return 3
  return 4
})

// Is Jingdong Cloud version fully completed?
const jdyunAllCompleted = computed(() =>
  stepStatus.value.dataSynced &&
  stepStatus.value.hasFavorites &&
  stepStatus.value.hasAnalysis
)

// Complete JD Cloud version guidance
const completeJdyunGuide = () => {
  try {
    localStorage.setItem('jdyun_guide_completed', 'true')
  } catch (e) {
    console.warn('Writing to localStorage failed:', e)
  }
  router.push('/dashboard')
}

const goToLearning = () => {
  router.push('/learning')
}

// Detect LLM API key configuration status
const checkLLMKey = async () => {
  try {
    const resp = await ApiClient.get('/api/config/llm/providers')
    if (resp.success && resp.data) {
      const providers = Array.isArray(resp.data) ? resp.data : (resp.data.providers || [])
      stepStatus.value.llmKey = providers.some((p: any) => p.has_api_key || p.has_api_secret)
    }
  } catch (e) {
    console.error('Checking LLM configuration failed:', e)
  }
}

// Detect data source synchronization status (indirectly determine whether Token is configured)
const checkDataSync = async () => {
  try {
    const resp = await ApiClient.get('/api/sync/stock_basics/status')
    if (resp.success && resp.data) {
      // If there are synchronized records or data volumes > 0, Description Token has been configured and synchronized
      const status = resp.data
      if (status.total_count > 0 || status.status === 'completed') {
        stepStatus.value.dataKey = true
        stepStatus.value.dataSynced = true
      }
    }
  } catch (e) {
    console.error('Checking data sync status failed:', e)
  }
}

// Check whether the analysis task has been completed
const checkAnalysisHistory = async () => {
  try {
    const resp = await ApiClient.get('/api/v2/tasks/list', {
      params: { status: 'completed', limit: 1 }
    })
    if (resp.success && resp.data) {
      stepStatus.value.hasAnalysis = (resp.data.total || 0) > 0
    }
  } catch (e) {
    console.error('Check analysis history failed:', e)
  }
}

// Check License Status
const checkLicense = async () => {
  try {
    // Note: The third parameter is RequestConfig; if it is mistransmitted to the second parameter, it will become URL query.
    // Causes skipErrorHandler to fail and community version 404 pop-up window
    const resp = await ApiClient.get('/api/license/status', undefined, { skipErrorHandler: true })
    if (resp.success && resp.data) {
      stepStatus.value.licenseValid = resp.data.is_valid || resp.data.has_token || false
    }
  } catch (e: any) {
    // 404 = Community Edition (without License activation function), hides the activation steps in the boot
    if (e?.response?.status === 404) {
      licenseSupported.value = false
      console.debug('License The interface is not available (community version), the activation steps have been hidden')
    } else {
      console.error('Failed to check license status:', e)
    }
  }
}

// Calculate current step based on completion status
const updateCurrentStep = () => {
  // After the Community Edition hides the License step, the index of subsequent steps is moved forward one position.
  const hasLicenseStep = licenseSupported.value
  let step = 0
  if (stepStatus.value.llmKey) step = 1
  if (stepStatus.value.dataKey) step = 2
  if (stepStatus.value.llmKey && stepStatus.value.dataKey) step = 3
  if (hasLicenseStep && stepStatus.value.licenseValid) step = 4
  if (stepStatus.value.dataSynced) step = hasLicenseStep ? 5 : 4
  if (stepStatus.value.hasAnalysis) step = hasLicenseStep ? 7 : 6
  currentStep.value = step
}

// Load all states
const loadAllStatus = async () => {
  loading.value = true
  if (isJdyunModeRef) {
    // JD Cloud version: only check synchronization, stock watch list, analysis history
    await Promise.allSettled([
      checkDataSync(),
      checkFavorites(),
      checkAnalysisHistory(),
      checkJdyunConfig()
    ])
  } else {
    // Standard Edition: Check all configurations
    await Promise.allSettled([
      checkLLMKey(),
      checkDataSync(),
      checkAnalysisHistory(),
      checkLicense()
    ])
  }
  updateCurrentStep()
  loading.value = false
}

onMounted(() => {
  loadAllStatus()
})

const goToSettings = () => {
  router.push('/settings/config')
}

const goToSync = () => {
  router.push('/settings/sync')
}

const goToScreening = () => {
  router.push('/screening')
}

const goToAnalysis = () => {
  router.push('/analysis/single')
}

const goToLicense = () => {
  router.push('/settings/license')
}
</script>

<style lang="scss" scoped>
.guide-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 40px 24px;

  .guide-header {
    text-align: center;
    margin-bottom: 48px;

    .refresh-btn {
      margin-top: 12px;
    }

    .guide-title {
      font-size: 36px;
      font-weight: 700;
      color: var(--el-text-color-primary);
      margin: 0 0 16px 0;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;

      .el-icon {
        font-size: 40px;
        color: var(--el-color-primary);
      }
    }

    .guide-subtitle {
      font-size: 18px;
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .steps-container {
    margin-bottom: 48px;

    :deep(.el-steps) {
      .el-step {
        margin-bottom: 40px;
        padding-bottom: 0;
        
        &:last-child {
          margin-bottom: 0;
        }
      }

      .el-step__head {
        margin-right: 24px !important;
        flex-shrink: 0;
        min-width: 40px;
        
        .el-step__icon {
          width: 40px;
          height: 40px;
          font-size: 20px;
          margin-right: 0 !important;
        }
      }

      .el-step__main {
        padding-top: 8px !important;
        flex: 1;
        min-width: 0;
      }

      .el-step__title {
        font-size: 18px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        margin-bottom: 20px !important;
        margin-top: 0 !important;
        margin-left: 0 !important;
        line-height: 1.6;
        padding-left: 0 !important;
        padding-top: 0 !important;
      }

      .el-step__description {
        margin-top: 0 !important;
        padding-left: 0 !important;
        padding-top: 0 !important;
      }
    }

    .step-content {
      padding: 24px;
      margin-top: 12px !important;
      background: var(--el-bg-color-page);
      border-radius: 8px;
      border-left: 4px solid var(--el-color-primary);

      p {
        margin: 0 0 16px 0;
        color: var(--el-text-color-regular);
        font-size: 15px;
        line-height: 1.8;

        &.step-completed-tip {
          display: flex;
          align-items: center;
          gap: 6px;
          color: var(--el-color-success);
          font-weight: 500;
        }

        &.step-tip {
          background: var(--el-color-info-light-9);
          border-left: 3px solid var(--el-color-info);
          padding: 12px 16px;
          border-radius: 4px;
          margin-top: 16px;
          color: var(--el-text-color-primary);
          font-size: 14px;
        }
      }

      .step-list {
        margin: 0 0 20px 0;
        padding-left: 24px;
        color: var(--el-text-color-regular);

        li {
          margin-bottom: 16px;
          line-height: 1.8;

          strong {
            color: var(--el-text-color-primary);
            font-weight: 600;
          }

          ol {
            margin-top: 8px;
            margin-bottom: 0;
            padding-left: 24px;
            color: var(--el-text-color-regular);

            li {
              margin-bottom: 6px;
              line-height: 1.6;
              font-size: 14px;

              &:last-child {
                margin-bottom: 0;
              }
            }
          }

          .tushare-link {
            color: var(--el-color-primary);
            text-decoration: none;
            font-weight: 500;

            &:hover {
              text-decoration: underline;
            }
          }

          .register-link-wrapper {
            margin-top: 8px;
            margin-left: 0;
            margin-bottom: 4px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
          }

          .register-link {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-weight: 500;
            font-size: 14px;
          }

          &:last-child {
            margin-bottom: 0;
          }
        }
      }

      .el-button {
        margin-top: 8px;
      }
    }
  }

  .quick-actions {
    background: var(--el-bg-color);
    border-radius: 12px;
    padding: 32px;
    margin-bottom: 32px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    border: 1px solid var(--el-border-color-lighter);

    h3 {
      margin: 0 0 24px 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    .action-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;

      .el-button {
        flex: 1;
        min-width: 150px;
      }
    }
  }

  .info-alert {
    margin-top: 32px;

    :deep(.el-alert__content) {
      p {
        margin: 0 0 12px 0;
        color: var(--el-text-color-regular);
      }

      ul {
        margin: 0;
        padding-left: 24px;
        color: var(--el-text-color-regular);

        li {
          margin-bottom: 8px;
          line-height: 1.6;

          a {
            color: var(--el-color-primary);
            text-decoration: none;

            &:hover {
              text-decoration: underline;
            }
          }
        }
      }
    }
  }
}

// Responsive design
@media (max-width: 768px) {
  .guide-page {
    padding: 24px 16px;

    .guide-header {
      .guide-title {
        font-size: 28px;
        flex-direction: column;
        gap: 8px;

        .el-icon {
          font-size: 32px;
        }
      }

      .guide-subtitle {
        font-size: 16px;
      }
    }

    .steps-container {
      :deep(.el-steps) {
        .el-step__head {
          .el-step__icon {
            width: 32px;
            height: 32px;
            font-size: 16px;
          }
        }

        .el-step__title {
          font-size: 16px;
        }
      }

      .step-content {
        padding: 16px;

        .step-list {
          padding-left: 20px;
        }
      }
    }

    .quick-actions {
      padding: 24px;

      .action-buttons {
        .el-button {
          min-width: 100%;
        }
      }
    }
  }
}
</style>

// Jingdong cloud version guide style
.jdyun-ready-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  margin-top: 8px;

  .ready-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: var(--el-text-color-regular);

    strong {
      color: var(--el-text-color-primary);
    }
  }
}

.step-completed-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-success);
  font-weight: 500;
}

.jdyun-complete-section {
  margin-top: 32px;
  padding: 24px;
  background: linear-gradient(135deg, rgba(103, 194, 58, 0.05) 0%, rgba(64, 158, 255, 0.05) 100%);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);

  .complete-actions {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-top: 16px;
  }
}
