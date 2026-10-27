<template>
  <div class="settings">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Setting /></el-icon>
        {{ pageTitle }}
      </h1>
      <p class="page-description">
        {{ pageDescription }}
      </p>
    </div>

    <el-row :gutter="24">
      <!-- Left: Settings menu -->
      <el-col :span="6">
        <el-card class="settings-menu" shadow="never">
          <el-menu
            :default-active="activeTab"
            @select="handleMenuSelect"
            class="settings-nav"
          >
            <!-- Personal settings menu -->
            <template v-if="currentSection === 'personal'">
              <el-menu-item index="general">
                <el-icon><User /></el-icon>
                <span>General settings</span>
              </el-menu-item>
              <el-menu-item index="appearance">
                <el-icon><Brush /></el-icon>
                <span>Appearance settings</span>
              </el-menu-item>
              <el-menu-item index="analysis">
                <el-icon><TrendCharts /></el-icon>
                <span>Analyze preferences</span>
              </el-menu-item>
              <el-menu-item index="notifications">
                <el-icon><Bell /></el-icon>
                <span>Notification settings</span>
              </el-menu-item>
              <el-menu-item index="security">
                <el-icon><Lock /></el-icon>
                <span>Security settings</span>
              </el-menu-item>
              <el-menu-item index="assistant">
                <el-icon><ChatDotRound /></el-icon>
                <span>Assistant settings</span>
              </el-menu-item>
              <el-menu-item index="commission">
                <el-icon><Coin /></el-icon>
                <span>Transaction rate</span>
              </el-menu-item>

            </template>

            <!-- System configuration menu -->
            <template v-else-if="currentSection === 'config'">
              <!-- JD Cloud Mode: Display system configuration (read-only status page)+ Data source configuration -->
              <template v-if="isJdyunMode()">
                <el-menu-item index="jdyun-config">
                  <el-icon><Tools /></el-icon>
                  <span>System configuration</span>
                </el-menu-item>
                <el-menu-item index="datasource-config">
                  <el-icon><DataBoard /></el-icon>
                  <span>Data source configuration</span>
                </el-menu-item>
              </template>
              <!-- Non-JD Cloud mode: display complete configuration management -->
              <el-menu-item v-else index="config">
                <el-icon><Tools /></el-icon>
                <span>Configuration management</span>
              </el-menu-item>
              <el-menu-item index="usage">
                <el-icon><DataAnalysis /></el-icon>
                <span>usage statistics</span>
              </el-menu-item>
              <el-menu-item index="cache">
                <el-icon><Coin /></el-icon>
                <span>Cache management</span>
              </el-menu-item>
            </template>

            <!-- System management menu -->
            <template v-else-if="currentSection === 'admin'">
              <el-menu-item index="database">
                <el-icon><Monitor /></el-icon>
                <span>Database management</span>
              </el-menu-item>
              <el-menu-item index="logs">
                <el-icon><Document /></el-icon>
                <span>Operation log</span>
              </el-menu-item>
              <el-menu-item index="sync">
                <el-icon><Refresh /></el-icon>
                <span>Synchronization of multiple data sources</span>
              </el-menu-item>
              <el-menu-item index="capability-index">
                <el-icon><Collection /></el-icon>
                <span>Tool capability index</span>
              </el-menu-item>
            </template>
          </el-menu>
        </el-card>
      </el-col>

      <!-- Right: Setting content -->
      <el-col :span="18">
        <!-- General settings -->
        <el-card v-show="activeTab === 'general'" class="settings-content" shadow="never">
          <template #header>
            <h3>General settings</h3>
          </template>
          
          <el-form :model="generalSettings" label-width="120px">
            <el-form-item label="Username">
              <el-input v-model="generalSettings.username" disabled />
            </el-form-item>
            
            <el-form-item label="Email">
              <el-input v-model="generalSettings.email" />
            </el-form-item>
            
            <el-form-item label="language">
              <el-select v-model="generalSettings.language">
                <el-option label="Simplified Chinese" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="time zone">
              <el-select v-model="generalSettings.timezone">
                <el-option label="Beijing time (UTC+8)" value="Asia/Shanghai" />
                <el-option label="new york time (UTC-5)" value="America/New_York" />
                <el-option label="london time (UTC+0)" value="Europe/London" />
              </el-select>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveGeneralSettings">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Appearance settings -->
        <el-card v-show="activeTab === 'appearance'" class="settings-content" shadow="never">
          <template #header>
            <h3>Appearance settings</h3>
          </template>
          
          <el-form :model="appearanceSettings" label-width="120px">
            <el-form-item label="theme mode">
              <el-radio-group v-model="appearanceSettings.theme" @change="handleThemeChange">
                <el-radio label="light">light theme</el-radio>
                <el-radio label="dark">dark theme</el-radio>
                <el-radio label="auto">Follow the system</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="sidebar width">
              <el-slider
                v-model="appearanceSettings.sidebarWidth"
                :min="200"
                :max="400"
                :step="20"
                show-input
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveAppearanceSettings">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Analyze preferences -->
        <el-card v-show="activeTab === 'analysis'" class="settings-content" shadow="never">
          <template #header>
            <h3>Analyze preferences</h3>
          </template>
          
          <el-form :model="analysisSettings" label-width="120px">
            <el-form-item label="Default market">
              <el-select v-model="analysisSettings.defaultMarket">
                <el-option label="A shares" value="A shares" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="Default analysis depth">
              <el-select v-model="analysisSettings.defaultDepth">
                <el-option label="1 Level - Quick Analysis" value="1" />
                <el-option label="2 Level - Basic Analysis" value="2" />
                <el-option label="3 Level - Standard Analysis (recommended)" value="3" />
                <el-option label="4 Level - In-Depth Analysis" value="4" />
                <el-option label="5 Level - Comprehensive Analysis" value="5" />
              </el-select>
            </el-form-item>

            <el-form-item label="Default analyst">
              <el-checkbox-group v-model="analysisSettings.defaultAnalysts">
                <el-checkbox label="Market Analyst">🌐 Market Analyst</el-checkbox>
                <el-checkbox label="Sector Analyst">🏭 Sector Analyst</el-checkbox>
                <el-checkbox label="market analyst">📈 market analyst</el-checkbox>
                <el-checkbox label="fundamental analyst">📊 fundamental analyst</el-checkbox>
                <el-checkbox label="news analyst">📰 news analyst</el-checkbox>
                <el-checkbox label="social media analyst">💬 social media analyst</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-form-item label="risk appetite">
              <el-radio-group v-model="analysisSettings.riskPreference">
                <el-radio label="conservative">conservative</el-radio>
                <el-radio label="neutral">Neutral</el-radio>
                <el-radio label="aggressive">Radical</el-radio>
              </el-radio-group>
              <div class="setting-description">
                Select your risk preference and the system will adjust the style of analysis recommendations based on your selections
              </div>
            </el-form-item>

            <el-form-item label="Auto refresh">
              <el-switch v-model="analysisSettings.autoRefresh" />
              <span class="setting-description">Automatically refresh analysis results</span>
            </el-form-item>
            
            <el-form-item label="refresh interval">
              <el-input-number
                v-model="analysisSettings.refreshInterval"
                :min="10"
                :max="300"
                :step="10"
                :disabled="!analysisSettings.autoRefresh"
              />
              <span class="setting-description">seconds</span>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveAnalysisSettings">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Notification settings -->
        <el-card v-show="activeTab === 'notifications'" class="settings-content" shadow="never">
          <template #header>
            <h3>Notification settings</h3>
          </template>
          
          <el-form :model="notificationSettings" label-width="120px">
            <el-form-item label="Desktop notifications">
              <el-switch v-model="notificationSettings.desktop" />
              <span class="setting-description">Show desktop notifications</span>
            </el-form-item>

            <el-form-item label="Research completion notice">
              <el-switch v-model="notificationSettings.analysisComplete" />
            </el-form-item>

            <el-form-item label="System maintenance notification">
              <el-switch v-model="notificationSettings.systemMaintenance" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveNotificationSettings">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Security settings -->
        <el-card v-show="activeTab === 'security'" class="settings-content" shadow="never">
          <template #header>
            <h3>Security settings</h3>
          </template>

          <el-form label-width="120px">
            <!-- 🔧 JD Cloud mode: Passwords are managed uniformly by the JD Cloud platform. This application does not support changing passwords. -->
            <el-form-item v-if="!isJdyunMode()" label="Change password">
              <el-button type="primary" @click="changePasswordDialogVisible = true">
                Change password
              </el-button>
            </el-form-item>
            <el-form-item v-else label="Account security">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="Accounts are managed uniformly by the JD Cloud platform"
                description="Your access credentials are assigned and managed by the JD Cloud platform and are decoupled from this application. If you need to modify your account or credentials, please go to the JD Cloud platform console to complete."
              />
            </el-form-item>
          </el-form>
        </el-card>



        <!-- Assistant settings -->
        <el-card v-show="activeTab === 'assistant'" class="settings-content" shadow="never">
          <template #header>
            <h3>Assistant settings</h3>
          </template>

          <el-form :model="assistantSettings" label-width="120px">
            <el-form-item label="Assistant name">
              <el-input v-model="assistantSettings.name" placeholder="Such as: small fortune, investment research assistant" maxlength="20" show-word-limit style="max-width: 300px;" />
              <div class="setting-description">You can call this name directly in the conversation</div>
            </el-form-item>

            <el-form-item label="tone style">
              <el-radio-group v-model="assistantSettings.tone">
                <el-radio label="professional">Professional and rigorous</el-radio>
                <el-radio label="friendly">Relaxed and friendly</el-radio>
                <el-radio label="concise">Simple and efficient</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="Custom instructions">
              <el-input
                v-model="assistantSettings.customInstructions"
                type="textarea"
                :rows="3"
                placeholder="For example: keep answers as short as possible, use tables, and bring data sources when replying."
                maxlength="500"
                show-word-limit
              />
              <div class="setting-description">The assistant will refer to these instructions to adjust the answering style</div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveAssistantSettings">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Transaction rate settings -->
        <el-card v-show="activeTab === 'commission'" class="settings-content" shadow="never">
          <template #header>
            <h3>Transaction rate settings</h3>
          </template>

          <el-alert
            title="Transaction rates are used to calculate the true cost and profit and loss of holding a position"
            description="Commission deducted when buying+Transfer fee, commission deducted when selling+stamp duty+Transfer fee. Rate configuration applies to both real positions and simulated transactions."
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 20px;"
          />

          <el-form :model="commissionCN" label-width="120px">
                <el-form-item label="Commission rate">
                  <el-input-number
                    v-model="commissionCN.rate"
                    :min="0"
                    :max="1"
                    :step="0.00001"
                    :precision="5"
                    controls-position="right"
                  />
                  <span class="setting-description" style="margin-left: 8px;">
                    {{ commissionCN.rate > 0 ? `million${(commissionCN.rate * 10000).toFixed(1)}` : 'Commission free' }}
                  </span>
                </el-form-item>
                <el-form-item label="Minimum commission">
                  <el-input-number v-model="commissionCN.min" :min="0" :step="0.5" :precision="2" controls-position="right" />
                  <span class="setting-description" style="margin-left: 8px;">Yuan</span>
                </el-form-item>
                <el-form-item label="stamp duty">
                  <el-input-number
                    v-model="commissionCN.stampDutyRate"
                    :min="0"
                    :max="0.01"
                    :step="0.0001"
                    :precision="4"
                    controls-position="right"
                  />
                  <span class="setting-description" style="margin-left: 8px;">
                    {{ commissionCN.stampDutyRate > 0 ? `Thousand${(commissionCN.stampDutyRate * 1000).toFixed(1)} (Sell only)` : 'None' }}
                  </span>
                </el-form-item>
                <el-form-item label="Transfer fee">
                  <el-input-number
                    v-model="commissionCN.transferFeeRate"
                    :min="0"
                    :max="0.001"
                    :step="0.000001"
                    :precision="6"
                    controls-position="right"
                  />
                  <span class="setting-description" style="margin-left: 8px;">
                    {{ commissionCN.transferFeeRate > 0 ? `million${(commissionCN.transferFeeRate * 10000).toFixed(2)}` : 'None' }}
                  </span>
                </el-form-item>
              </el-form>

          <el-form label-width="120px" style="margin-top: 16px;">
            <el-form-item>
              <el-button type="primary" @click="saveCommissionSettings" :loading="commissionSaving">
                Save rate settings
              </el-button>
              <el-button @click="() => loadCommissionSettings(true)">
                Restore default
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>




        <!-- Configuration management (non-JD Cloud model) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'config'" class="settings-content" shadow="never">
          <template #header>
            <h3>Configuration management</h3>
          </template>

          <div class="config-content">
            <el-alert
              title="Configuration management"
              type="info"
              description="Manage LLM configuration, data source configuration, and market classification configuration"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToConfigManagement">
              Enter configuration management
            </el-button>
          </div>
        </el-card>

        <!-- System configuration (JD Cloud mode: read-only status page) -->
        <el-card v-if="isJdyunMode()" v-show="activeTab === 'jdyun-config'" class="settings-content" shadow="never">
          <template #header>
            <h3>System configuration</h3>
          </template>

          <div class="config-content">
            <el-alert
              title="JD Cloud Cooperation Edition"
              type="info"
              description="This version injects large models and data source configurations through environment variables, eliminating the need for manual configuration. If you need to modify it, please contact the administrator to update the environment variables."
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToJdyunConfig">
              View configuration status
            </el-button>
          </div>
        </el-card>

        <!-- Data source configuration (JD Cloud mode) -->
        <el-card v-if="isJdyunMode()" v-show="activeTab === 'datasource-config'" class="settings-content" shadow="never">
          <template #header>
            <h3>Data source configuration</h3>
          </template>

          <div class="config-content">
            <el-alert
              title="JD Cloud version data source"
              type="info"
              description="JD Cloud Cooperation Edition only supports Tushare and AKShare data sources. If you need to modify it, please operate on the data source management page."
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToDataSourceConfig">
              Manage data sources
            </el-button>
          </div>
        </el-card>

        <!-- usage statistics -->
        <el-card v-show="activeTab === 'usage'" class="settings-content" shadow="never">
          <template #header>
            <h3>usage statistics</h3>
          </template>

          <div class="cache-content">
            <el-alert
              title="Usage statistics and billing"
              type="info"
              description="View model usage, token consumption and cost statistics"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToUsageStatistics">
              View usage statistics
            </el-button>
          </div>
        </el-card>

        <!-- Cache management -->
        <el-card v-show="activeTab === 'cache'" class="settings-content" shadow="never">
          <template #header>
            <h3>Cache management</h3>
          </template>

          <div class="settings-section">
            <el-alert
              title="Cache management"
              type="info"
              description="Manage system cache and clean up expired data"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToCacheManagement">
              Enter cache management
            </el-button>
          </div>
        </el-card>

        <!-- Database management -->
        <el-card v-show="activeTab === 'database'" class="settings-content" shadow="never">
          <template #header>
            <h3>Database management</h3>
          </template>

          <div class="database-content">
            <el-alert
              title="Database management"
              type="info"
              description="Manage database connections, backup and recovery"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToDatabaseManagement">
              Enter database management
            </el-button>
          </div>
        </el-card>

        <!-- Operation log -->
        <el-card v-show="activeTab === 'logs'" class="settings-content" shadow="never">
          <template #header>
            <h3>Operation log</h3>
          </template>

          <div class="logs-content">
            <el-alert
              title="Operation log"
              type="info"
              description="View system operation logs and audit records"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToOperationLogs">
              View operation log
            </el-button>
          </div>
        </el-card>

        <!-- Synchronization of multiple data sources -->
        <el-card v-show="activeTab === 'sync'" class="settings-content" shadow="never">
          <template #header>
            <h3>Synchronization of multiple data sources</h3>
          </template>

          <div class="sync-content">
            <el-alert
              title="Synchronization of multiple data sources"
              type="info"
              description="Manage synchronization configuration and status of multiple data sources"
              :closable="false"
              style="margin-bottom: 20px;"
            />
            <el-button type="primary" @click="goToMultiSourceSync">
              Enter synchronization management
            </el-button>
          </div>
        </el-card>

        <!-- Tool capability index -->
        <el-card v-show="activeTab === 'capability-index'" class="settings-content" shadow="never">
          <template #header>
            <h3>Tool capability index</h3>
          </template>

          <div class="capability-index-content">
            <el-alert
              type="info"
              :closable="false"
              style="margin-bottom: 20px;"
            >
              <template #title>
                Tool Competencies Index is used for semantic search matching tools and skills. If the Embedding API is not available at system startup, index building will be skipped (using keyword matching fallback).
              </template>
            </el-alert>

            <el-descriptions :column="2" border style="margin-bottom: 20px;" v-loading="indexLoading">
              <el-descriptions-item label="synchronous mode">
                <el-tag :type="indexStateTagType">{{ indexStateText }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="vector backend">
                {{ indexState.vector_backend || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="Indexed tools">
                {{ indexState.indexed_documents ?? 0 }} / {{ indexState.total_documents ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="skip quantity">
                {{ indexState.skipped_documents ?? 0 }}
              </el-descriptions-item>
            </el-descriptions>

            <el-button
              type="primary"
              :loading="rebuildLoading"
              @click="handleRebuild"
            >
              Rebuild index
            </el-button>
          </div>
        </el-card>

      </el-col>
    </el-row>

    <!-- Change password dialog box -->
    <el-dialog
      v-model="changePasswordDialogVisible"
      title="Change password"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="changePasswordFormRef"
        :model="changePasswordForm"
        :rules="changePasswordRules"
        label-width="100px"
      >
        <el-form-item label="current password" prop="oldPassword">
          <el-input
            v-model="changePasswordForm.oldPassword"
            type="password"
            placeholder="Please enter current password"
            show-password
          />
        </el-form-item>

        <el-form-item label="new password" prop="newPassword">
          <el-input
            v-model="changePasswordForm.newPassword"
            type="password"
            placeholder="Please enter a new password (at least 6 digits)"
            show-password
          />
        </el-form-item>

        <el-form-item label="Confirm password" prop="confirmPassword">
          <el-input
            v-model="changePasswordForm.confirmPassword"
            type="password"
            placeholder="Please enter new password again"
            show-password
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="changePasswordDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="changePasswordLoading" @click="handleChangePassword">
          Confirm changes
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormRules } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { isJdyunMode } from '@/utils/config'
import {
  Setting,
  User,
  Brush,
  TrendCharts,
  Bell,
  Lock,
  Tools,
  Monitor,
  Coin,
  Document,
  Refresh,
  DataAnalysis,
  ChatDotRound,
  Collection,
  DataBoard
} from '@element-plus/icons-vue'
import { getCapabilityIndexState, rebuildCapabilityIndex, type CapabilityIndexState } from '@/api/capabilityIndex'
import request from '@/api/request'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

// Current grouping: personal (personal settings), config (system configuration), admin (system management)
const currentSection = ref('personal')

// Page title and description
const pageTitle = computed(() => {
  switch (currentSection.value) {
    case 'personal':
      return 'personal settings'
    case 'config':
      return 'System configuration'
    case 'admin':
      return 'System management'
    default:
      return 'settings'
  }
})

const pageDescription = computed(() => {
  switch (currentSection.value) {
    case 'personal':
      return 'Personalization and preferences'
    case 'config':
      return 'LLM, Data sources, usage statistics and cache configuration'
    case 'admin':
      return 'Database, log and sync management'
    default:
      return 'Personalized configuration and system management'
  }
})

// Responsive data
const activeTab = ref('general')

// Determine the current grouping and default activated tags based on the routing path and query parameters
const updateSectionFromRoute = () => {
  const path = route.path
  const tab = route.query.tab as string

  if (path === '/settings') {
    // Personal settings page
    currentSection.value = 'personal'
    // Switch tabs based on tab parameter
    if (tab) {
      activeTab.value = tab
    } else {
      activeTab.value = 'general'
    }
  } else if (path === '/settings/config') {
    currentSection.value = 'config'
    activeTab.value = 'config'
  } else if (path === '/settings/jdyun-config') {
    currentSection.value = 'config'
    activeTab.value = 'jdyun-config'
  } else if (path === '/settings/capability-index') {
    currentSection.value = 'admin'
    activeTab.value = 'capability-index'
  }
}

// Monitor routing changes (including query parameters)
watch(() => [route.path, route.query.tab], updateSectionFromRoute, { immediate: true })

// Get user information from authStore (use computed to implement responsiveness)
const generalSettings = ref({
  username: authStore.user?.username || 'admin',
  email: authStore.user?.email || 'admin@example.com',
  language: authStore.user?.preferences?.language || 'zh-CN',
  timezone: 'Asia/Shanghai'
})

const appearanceSettings = ref({
  theme: authStore.user?.preferences?.ui_theme || 'light',
  sidebarWidth: authStore.user?.preferences?.sidebar_width || 240
})

const analysisSettings = ref({
  defaultMarket: authStore.user?.preferences?.default_market || 'A shares',
  defaultDepth: authStore.user?.preferences?.default_depth || '3',
  defaultAnalysts: authStore.user?.preferences?.default_analysts || ['market analyst', 'fundamental analyst'],
  autoRefresh: authStore.user?.preferences?.auto_refresh ?? true,
  refreshInterval: authStore.user?.preferences?.refresh_interval || 30,
  riskPreference: authStore.user?.preferences?.risk_preference || 'neutral'
})

const notificationSettings = ref({
  desktop: authStore.user?.preferences?.desktop_notifications ?? true,
  analysisComplete: authStore.user?.preferences?.analysis_complete_notification ?? true,
  systemMaintenance: authStore.user?.preferences?.system_maintenance_notification ?? true
})

// Assistant settings
const assistantSettings = ref({
  name: authStore.user?.preferences?.assistant_settings?.name || 'Analysis Assistant',
  tone: authStore.user?.preferences?.assistant_settings?.tone || 'professional',
  customInstructions: authStore.user?.preferences?.assistant_settings?.custom_instructions || ''
})

// Transaction fee setting (A shares only)
const commissionSaving = ref(false)

const defaultCommissionCN = { rate: 0.0003, min: 5.0, stampDutyRate: 0.001, transferFeeRate: 0.00002 }

const commissionCN = ref({ ...defaultCommissionCN })


// Monitor user information changes and update settings synchronously
watch(() => authStore.user, (newUser) => {
  if (newUser) {
    // Update common settings
    generalSettings.value.username = newUser.username || 'admin'
    generalSettings.value.email = newUser.email || 'admin@example.com'
    generalSettings.value.language = newUser.preferences?.language || 'zh-CN'

    // Update appearance settings
    appearanceSettings.value.theme = newUser.preferences?.ui_theme || 'light'
    appearanceSettings.value.sidebarWidth = newUser.preferences?.sidebar_width || 240

    // Update analysis preferences
    analysisSettings.value.defaultMarket = newUser.preferences?.default_market || 'A shares'
    analysisSettings.value.defaultDepth = newUser.preferences?.default_depth || '3'
    analysisSettings.value.defaultAnalysts = newUser.preferences?.default_analysts || ['market analyst', 'fundamental analyst']
    analysisSettings.value.autoRefresh = newUser.preferences?.auto_refresh ?? true
    analysisSettings.value.refreshInterval = newUser.preferences?.refresh_interval || 30
    analysisSettings.value.riskPreference = newUser.preferences?.risk_preference || 'neutral'

    // Update notification settings
    notificationSettings.value.desktop = newUser.preferences?.desktop_notifications ?? true
    notificationSettings.value.analysisComplete = newUser.preferences?.analysis_complete_notification ?? true
    notificationSettings.value.systemMaintenance = newUser.preferences?.system_maintenance_notification ?? true

    // Update assistant settings
    const ast = newUser.preferences?.assistant_settings
    assistantSettings.value.name = ast?.name || 'Analysis Assistant'
    assistantSettings.value.tone = ast?.tone || 'professional'
    assistantSettings.value.customInstructions = ast?.custom_instructions || ''
  }
}, { deep: true })

// method
const handleMenuSelect = (index: string) => {
  // JD Cloud Mode: Click"System configuration"Menu item jumps to the independent JD Cloud configuration page
  if (index === 'jdyun-config') {
    router.push('/settings/jdyun-config')
    return
  }
  // JD Cloud Mode: Click"Data source configuration"Menu item jumps to the configuration management page (data source tab page)
  if (index === 'datasource-config') {
    router.push('/settings/config?tab=datasource')
    return
  }
  // Jump directly to an independent page to avoid displaying intermediate pages
  if (index === 'database') {
    router.push('/settings/database')
    return
  }
  if (index === 'logs') {
    router.push('/settings/logs')
    return
  }
  if (index === 'sync') {
    router.push('/settings/sync')
    return
  }
  if (index === 'usage') {
    router.push('/settings/usage')
    return
  }
  if (index === 'cache') {
    router.push('/settings/cache')
    return
  }
  if (index === 'config') {
    router.push('/settings/config')
    return
  }
  activeTab.value = index
}

const handleThemeChange = (theme: string | number | boolean | undefined) => {
  if (typeof theme === 'string') {
    appStore.setTheme(theme as any)
  }
}

const saveGeneralSettings = async () => {
  try {
    // Call authStore to update user information
    const success = await authStore.updateUserInfo({
      email: generalSettings.value.email,
      preferences: {
        language: generalSettings.value.language
      }
    })

    if (success) {
      ElMessage.success('General settings saved')
    }
  } catch (error) {
    console.error('Failed to save common settings:', error)
    ElMessage.error('Failed to save common settings')
  }
}

const saveAppearanceSettings = async () => {
  try {
    // Update local store (effective immediately)
    appStore.setSidebarWidth(appearanceSettings.value.sidebarWidth)
    appStore.setTheme(appearanceSettings.value.theme as any)

    // Save to backend
    const success = await authStore.updateUserInfo({
      preferences: {
        ui_theme: appearanceSettings.value.theme,
        sidebar_width: appearanceSettings.value.sidebarWidth
      }
    })

    if (success) {
      ElMessage.success('Appearance settings saved')
    }
  } catch (error) {
    console.error('Failed to save appearance settings:', error)
    ElMessage.error('Failed to save appearance settings')
  }
}

const saveAnalysisSettings = async () => {
  try {
    // Update local store (effective immediately)
    appStore.updatePreferences({
      defaultMarket: analysisSettings.value.defaultMarket as any,
      defaultDepth: analysisSettings.value.defaultDepth as any,
      autoRefresh: analysisSettings.value.autoRefresh,
      refreshInterval: analysisSettings.value.refreshInterval
    })

    // Save to backend
    const success = await authStore.updateUserInfo({
      preferences: {
        default_market: analysisSettings.value.defaultMarket,
        default_depth: analysisSettings.value.defaultDepth,
        default_analysts: analysisSettings.value.defaultAnalysts,
        auto_refresh: analysisSettings.value.autoRefresh,
        refresh_interval: analysisSettings.value.refreshInterval,
        risk_preference: analysisSettings.value.riskPreference
      }
    })

    if (success) {
      ElMessage.success('Analysis preferences saved')
    }
  } catch (error) {
    console.error('Failed to save analysis preferences:', error)
    ElMessage.error('Failed to save analysis preferences')
  }
}

const saveNotificationSettings = async () => {
  try {
    // Save to backend
    const success = await authStore.updateUserInfo({
      preferences: {
        desktop_notifications: notificationSettings.value.desktop,
        analysis_complete_notification: notificationSettings.value.analysisComplete,
        system_maintenance_notification: notificationSettings.value.systemMaintenance,
        notifications_enabled: notificationSettings.value.desktop || notificationSettings.value.analysisComplete || notificationSettings.value.systemMaintenance
      }
    })

    if (success) {
      ElMessage.success('Notification settings saved')
    }
  } catch (error) {
    console.error('Failed to save notification settings:', error)
    ElMessage.error('Failed to save notification settings')
  }
}

// Assistant settings
const saveAssistantSettings = async () => {
  try {
    const success = await authStore.updateUserInfo({
      preferences: {
        assistant_settings: {
          name: assistantSettings.value.name || 'Analysis Assistant',
          tone: assistantSettings.value.tone || 'professional',
          custom_instructions: assistantSettings.value.customInstructions || ''
        }
      }
    })
    if (success) {
      ElMessage.success('Assistant settings saved')
    }
  } catch (error) {
    console.error('Failed to save assistant settings:', error)
    ElMessage.error('Failed to save assistant settings')
  }
}

// Load transaction rate settings (A shares only)
const loadCommissionSettings = async (useDefaults = false) => {
  if (useDefaults) {
    commissionCN.value = { ...defaultCommissionCN }
    return
  }
  try {
    const { data } = await request.get('/api/paper/market-rules')
    if (data && Array.isArray(data)) {
      for (const rule of data) {
        if (rule.market === 'CN') {
          const c = rule.rules?.commission || {}
          commissionCN.value = {
            rate: c.rate ?? defaultCommissionCN.rate,
            min: c.min ?? defaultCommissionCN.min,
            stampDutyRate: c.stamp_duty_rate ?? defaultCommissionCN.stampDutyRate,
            transferFeeRate: c.transfer_fee_rate ?? defaultCommissionCN.transferFeeRate,
          }
        }
      }
    }
  } catch (e) {
    console.warn('Failed to load rate settings, using default values:', e)
  }
}

// Save transaction rate settings (A shares only)
const saveCommissionSettings = async () => {
  commissionSaving.value = true
  try {
    const rules = [
      {
        market: 'CN',
        commission: {
          rate: commissionCN.value.rate,
          min: commissionCN.value.min,
          stamp_duty_rate: commissionCN.value.stampDutyRate,
          transfer_fee_rate: commissionCN.value.transferFeeRate,
        }
      }
    ]
    await request.post('/api/paper/market-rules/commission', { rules })
    ElMessage.success('Transaction rate settings saved')
  } catch (e) {
    console.error('Failed to save rate settings:', e)
    ElMessage.error('Failed to save rate settings')
  } finally {
    commissionSaving.value = false
  }
}

// Get rates when page loads (called in main onMounted)


// Navigation function
const goToConfigManagement = () => {
  router.push('/settings/config')
}

const goToJdyunConfig = () => {
  router.push('/settings/jdyun-config')
}

const goToDataSourceConfig = () => {
  router.push('/settings/config?tab=datasource')
}

const goToUsageStatistics = () => {
  router.push('/settings/usage')
}

const goToCacheManagement = () => {
  router.push('/settings/cache')
}

const goToDatabaseManagement = () => {
  router.push('/settings/database')
}

const goToOperationLogs = () => {
  router.push('/settings/logs')
}

const goToMultiSourceSync = () => {
  router.push('/settings/sync')
}

// ========== Tool capability index ==========
const indexLoading = ref(false)
const rebuildLoading = ref(false)
const indexState = ref<CapabilityIndexState>({})

const indexStateText = computed(() => {
  const mode = indexState.value.sync_mode
  if (!mode) return 'not initialized'
  const map: Record<string, string> = {
    'full_rebuild': 'Full reconstruction',
    'incremental_sync': 'Incremental synchronization',
    'no_change': 'No change',
    'skipped_no_embedding': 'Skip (Embedding not configured)',
    'skipped_embedding_unavailable': 'Skip (Embedding API is not available)',
  }
  return map[mode] || mode
})

const indexStateTagType = computed(() => {
  const mode = indexState.value.sync_mode || ''
  if (mode.startsWith('skipped')) return 'warning'
  if (mode === 'full_rebuild' || mode === 'incremental_sync') return 'success'
  return 'info'
})

const loadIndexState = async () => {
  indexLoading.value = true
  try {
    const res = await getCapabilityIndexState()
    indexState.value = (res as any)?.data || {}
  } catch {
    indexState.value = {}
  } finally {
    indexLoading.value = false
  }
}

const handleRebuild = async () => {
  rebuildLoading.value = true
  try {
    const res = await rebuildCapabilityIndex()
    const data = (res as any)?.data || {}
    if (data.indexed_documents > 0) {
      ElMessage.success(`Index rebuild completed:${data.indexed_documents}/${data.total_documents} tools indexed`)
    } else {
      ElMessage.warning('Index skipping: Embedding API is not available, please set a valid one in configuration management first. API Key')
    }
    await loadIndexState()
  } catch {
    ElMessage.error('Index rebuild failed')
  } finally {
    rebuildLoading.value = false
  }
}

// Password modification related
const changePasswordDialogVisible = ref(false)
const changePasswordLoading = ref(false)
const changePasswordFormRef = ref()
const changePasswordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const validateConfirmPassword = (_rule: any, value: string, callback: (error?: string | Error) => void) => {
  if (value === '') {
    callback(new Error('Please enter new password again'))
    return
  }
  if (value !== changePasswordForm.value.newPassword) {
    callback(new Error('The passwords entered twice are inconsistent'))
    return
  }
  callback()
}

const changePasswordRules: FormRules = {
  oldPassword: [
    { required: true, message: 'Please enter current password', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: 'Please enter new password', trigger: 'blur' },
    { min: 6, message: 'Password length must be at least 6 characters', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const handleChangePassword = async () => {
  if (!changePasswordFormRef.value) return

  await changePasswordFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      changePasswordLoading.value = true
      try {
        const success = await authStore.changePassword(
          changePasswordForm.value.oldPassword,
          changePasswordForm.value.newPassword
        )

        if (success) {
          ElMessage.success('Password changed successfully, please log in again')
          changePasswordDialogVisible.value = false
          changePasswordForm.value = {
            oldPassword: '',
            newPassword: '',
            confirmPassword: ''
          }
          // Delay jump to login page
          setTimeout(() => {
            authStore.logout()
            router.push('/login')
          }, 1500)
        }
      } catch (error: any) {
        ElMessage.error(error.message || 'Password change failed')
      } finally {
        changePasswordLoading.value = false
      }
    }
  })
}



// life cycle
onMounted(() => {
  // Load settings from store
  appearanceSettings.value.theme = appStore.theme
  appearanceSettings.value.sidebarWidth = appStore.sidebarWidth

  analysisSettings.value.defaultMarket = appStore.preferences.defaultMarket
  analysisSettings.value.defaultDepth = appStore.preferences.defaultDepth
  analysisSettings.value.autoRefresh = appStore.preferences.autoRefresh
  analysisSettings.value.refreshInterval = appStore.preferences.refreshInterval

  // Load capability index status
  loadIndexState()

  // Load transaction rate settings
  loadCommissionSettings()
})
</script>

<style lang="scss" scoped>
.settings {
  .page-header {
    margin-bottom: 24px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
    }

    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .settings-menu {
    .settings-nav {
      border: none;
    }
  }

  .settings-content {
    min-height: 500px;

    .setting-description {
      margin-left: 8px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }

    .about-content {
      .system-info,
      .system-status,
      .links {
        margin-bottom: 32px;

        h4 {
          margin: 0 0 16px 0;
          color: var(--el-text-color-primary);
        }

        p {
          margin: 8px 0;
          color: var(--el-text-color-regular);
        }
      }

      .links {
        .el-link {
          margin-right: 16px;
          margin-bottom: 8px;
        }
      }
    }
  }
}
</style>
