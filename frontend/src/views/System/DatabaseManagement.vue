<template>
  <div class="database-management">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><DataBoard /></el-icon>
        Database management
      </h1>
      <p class="page-description">
        MongoDB + Redis Database management and monitoring
      </p>
    </div>

    <!-- connection status -->
    <el-row :gutter="24">
      <el-col :span="12">
        <el-card class="connection-card" shadow="never">
          <template #header>
            <h3>🍃 MongoDB connection status</h3>
          </template>
          
          <div class="connection-status">
            <div class="status-indicator">
              <el-tag :type="mongoStatus.connected ? 'success' : 'danger'" size="large">
                {{ mongoStatus.connected ? 'Connected' : 'Not connected' }}
              </el-tag>
            </div>
            
            <div v-if="mongoStatus.connected" class="connection-info">
              <p><strong>server:</strong> {{ mongoStatus.host }}:{{ mongoStatus.port }}</p>
              <p><strong>database:</strong> {{ mongoStatus.database }}</p>
              <p><strong>version:</strong> {{ mongoStatus.version || 'Unknown' }}</p>
              <p v-if="mongoStatus.connected_at"><strong>connection time:</strong> {{ formatDateTime(mongoStatus.connected_at) }}</p>
              <p v-if="mongoStatus.uptime"><strong>running time:</strong> {{ formatUptime(mongoStatus.uptime) }}</p>
            </div>
            
            <div class="connection-actions">
              <el-button @click="testConnections" :loading="testing">
                test connection
              </el-button>
              <el-button @click="loadDatabaseStatus" :loading="loading" :icon="Refresh">
                refresh status
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="connection-card" shadow="never">
          <template #header>
            <h3>🔴 Redis connection status</h3>
          </template>
          
          <div class="connection-status">
            <div class="status-indicator">
              <el-tag :type="redisStatus.connected ? 'success' : 'danger'" size="large">
                {{ redisStatus.connected ? 'Connected' : 'Not connected' }}
              </el-tag>
            </div>
            
            <div v-if="redisStatus.connected" class="connection-info">
              <p><strong>server:</strong> {{ redisStatus.host }}:{{ redisStatus.port }}</p>
              <p><strong>database:</strong> {{ redisStatus.database }}</p>
              <p><strong>version:</strong> {{ redisStatus.version || 'Unknown' }}</p>
              <p v-if="redisStatus.memory_used"><strong>memory usage:</strong> {{ formatBytes(redisStatus.memory_used) }}</p>
              <p v-if="redisStatus.connected_clients"><strong>Number of connections:</strong> {{ redisStatus.connected_clients }}</p>
            </div>
            
            <div class="connection-actions">
              <el-button @click="testConnections" :loading="testing">
                test connection
              </el-button>
              <el-button @click="loadDatabaseStatus" :loading="loading" :icon="Refresh">
                refresh status
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Database statistics -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="8">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ dbStats.totalCollections }}</div>
            <div class="stat-label">MongoDB Number of sets</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ dbStats.totalDocuments }}</div>
            <div class="stat-label">Total number of documents</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ formatBytes(dbStats.totalSize) }}</div>
            <div class="stat-label">Database size</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Data management operations -->
    <el-card class="operations-card" shadow="never" style="margin-top: 24px">
      <template #header>
        <h3>🛠️ Data management operations</h3>
      </template>
      
      <!-- Line 1: Data import and export -->
      <el-row :gutter="24">
        <!-- Data export -->
        <el-col :span="12">
          <div class="operation-section">
            <h4>📤 Data export</h4>
            <p>Export database data to file</p>

            <el-form-item label="Export format">
              <el-select v-model="exportFormat" style="width: 100%">
                <el-option label="JSON" value="json" />
                <el-option label="CSV" value="csv" />
                <el-option label="Excel" value="xlsx" />
              </el-select>
            </el-form-item>

            <el-form-item label="data collection">
              <el-select v-model="exportCollection" style="width: 100%">
                <el-option label="Configuration and reporting (for migration)" value="config_and_reports" />
                <el-option label="Configuration data (for demo system, desensitized)" value="config_only" />
                <el-option label="research report" value="analysis_reports" />
                <el-option label="User configuration" value="user_configs" />
                <el-option label="Operation log" value="operation_logs" />
              </el-select>
            </el-form-item>

            <el-button @click="exportData" :loading="exporting">
              <el-icon><Download /></el-icon>
              Export data
            </el-button>
          </div>
        </el-col>

        <!-- Data import -->
        <el-col :span="12">
          <div class="operation-section">
            <h4>📥 Data import</h4>
            <p>Import data from export file</p>

            <el-form-item label="Select file">
              <el-upload
                ref="uploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleFileChange"
                :on-remove="handleFileRemove"
                accept=".json,.zip"
                drag
              >
                <el-icon class="el-icon--upload"><Upload /></el-icon>
                <div class="el-upload__text">
                  Drag and drop files here or<em>Click to upload</em>
                </div>
                <template #tip>
                  <div class="el-upload__tip">
                    Supports JSON format or ZIP compressed files (ZIP files will be automatically decompressed)
                  </div>
                </template>
              </el-upload>
            </el-form-item>

            <el-form-item label="Import options">
              <el-checkbox v-model="importOverwrite">
                Overwrite existing data
              </el-checkbox>
              <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                ⚠️ After checking, the existing data will be deleted and then imported.
              </div>
            </el-form-item>

            <el-button
              type="primary"
              @click="importData"
              :loading="importing"
              :disabled="!importFile"
            >
              <el-icon><Upload /></el-icon>
              Import data
            </el-button>
          </div>
        </el-col>
      </el-row>

      <!-- Second line: Data backup and restore instructions -->
      <el-row :gutter="24" style="margin-top: 24px">
        <el-col :span="24">
          <div class="operation-section">
            <h4>💾 Data backup and restore</h4>
            <el-alert
              title="Please use command line tools for backup and restore"
              type="info"
              :closable="false"
            >
              <template #default>
                <div style="line-height: 1.8;">
                  <p style="margin: 8px 0;">Due to the large amount of data and poor backup experience on the web interface, it is recommended to use MongoDB native tools:</p>
                  
                  <div style="background: #fff3cd; padding: 12px; border-radius: 4px; margin: 8px 0; border-left: 4px solid #ffc107;">
                    <p style="margin: 0; font-weight: bold; color: #856404;">⚠️ IMPORTANT NOTE:</p>
                    <p style="margin: 4px 0 0 0; font-size: 13px; color: #856404;">
                      Before executing the following command, please enter the application installation directory (project root directory) on the command line:
                    </p>
                    <div style="position: relative; margin-top: 8px;">
                      <code style="display: block; margin: 0; color: #856404; font-family: 'Consolas', 'Monaco', monospace; background: #fff; padding: 8px 80px 8px 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-all;">
{{ cdCommand }}
                      </code>
                      <div style="position: absolute; right: 4px; top: 50%; transform: translateY(-50%); display: flex; gap: 4px;">
                        <el-button
                          :icon="CopyDocument"
                          size="small"
                          text
                          type="primary"
                          @click="copyToClipboard(cdCommand, 'cd command')"
                          title="copy command"
                        />
                        <el-button
                          size="small"
                          text
                          type="info"
                          @click="showPlainText(cdCommand, 'cd Command - plain text')"
                          title="Show plain text (manually copied)"
                        >
                          display text
                        </el-button>
                      </div>
                    </div>
                  </div>

                  <div style="background: #f5f7fa; padding: 12px; border-radius: 4px; margin: 8px 0;">
                    <p style="margin: 4px 0; font-weight: bold;">📦 Backup command:</p>
                    <div style="position: relative; margin-bottom: 12px;">
                      <code style="display: block; margin: 0; color: #409eff; white-space: pre-wrap; word-break: break-all; font-family: 'Consolas', 'Monaco', monospace; background: #fff; padding: 8px 100px 8px 8px; border-radius: 4px; border: 1px solid #e4e7ed;">
{{ backupCommand }}
                      </code>
                      <div style="position: absolute; right: 4px; top: 50%; transform: translateY(-50%); display: flex; gap: 4px;">
                        <el-button
                          :icon="CopyDocument"
                          size="small"
                          text
                          type="primary"
                          @click="copyToClipboard(backupCommand, 'backup command')"
                          title="copy command"
                        />
                        <el-button
                          size="small"
                          text
                          type="info"
                          @click="showPlainText(backupCommand, 'Backup command - plain text')"
                          title="Show plain text (manually copied)"
                        >
                          display text
                        </el-button>
                      </div>
                    </div>
                    <p style="margin: 12px 0 4px 0; font-weight: bold;">🔄 Restore command:</p>
                    <div style="position: relative;">
                      <code style="display: block; margin: 0; color: #409eff; white-space: pre-wrap; word-break: break-all; font-family: 'Consolas', 'Monaco', monospace; background: #fff; padding: 8px 100px 8px 8px; border-radius: 4px; border: 1px solid #e4e7ed;">
{{ restoreCommand }}
                      </code>
                      <div style="position: absolute; right: 4px; top: 50%; transform: translateY(-50%); display: flex; gap: 4px;">
                        <el-button
                          :icon="CopyDocument"
                          size="small"
                          text
                          type="primary"
                          @click="copyToClipboard(restoreCommand, 'restore command')"
                          title="copy command"
                        />
                        <el-button
                          size="small"
                          text
                          type="info"
                          @click="showPlainText(restoreCommand, 'Restore command - plain text')"
                          title="Show plain text (manually copied)"
                        >
                          display text
                        </el-button>
                      </div>
                    </div>
                  </div>
                  <p style="margin: 8px 0; font-size: 12px; color: #909399;">
                    💡 Tips:
                  </p>
                  <ul style="margin: 4px 0; padding-left: 20px; font-size: 12px; color: #909399;">
                    <li>The URI in the command has been automatically generated based on the current configuration</li>
                    <li>If the MongoDB versions are different, please modify the version number in the path (mongodb-win32-x86_64-windows-8.0.13)</li>
                    <li>If you have added the MongoDB tools to your PATH, you can use the mongodump and mongorestore commands directly</li>
                    <li v-if="connectionInfo && connectionInfo.has_auth">The current connection has authentication enabled and the username and password are included in the command</li>
                    <li><strong>Copy tips:</strong>Click the copy button to the right of the command to copy plain text. If garbled characters appear when pasting (such as <code>^[[200~</code>) , Please use the right-click menu"Paste"or press <code>Shift+Insert</code>, or disable terminal Bracketed Paste Mode</li>
                  </ul>
                </div>
              </template>
            </el-alert>
          </div>
        </el-col>
      </el-row>
    </el-card>





    <!-- Data cleaning -->
    <el-card class="cleanup-card" shadow="never" style="margin-top: 24px">
      <template #header>
        <h3>🧹 Data cleaning</h3>
      </template>
      
      <el-alert
        title="Dangerous operation"
        type="warning"
        description="The following operations will permanently delete data, please operate with caution"
        :closable="false"
        style="margin-bottom: 16px"
      />
      
      <el-row :gutter="24">
        <el-col :span="12">
          <div class="cleanup-section">
            <h4>Clean up expired analysis results</h4>
            <p>Delete analysis results older than a specified number of days</p>
            <el-input-number v-model="cleanupDays" :min="1" :max="365" />
            <span style="margin-left: 8px">days ago</span>
            <br><br>
            <el-button type="warning" @click="cleanupAnalysisResults" :loading="cleaning">
              Clean analysis results
            </el-button>
          </div>
        </el-col>
        
        <el-col :span="12">
          <div class="cleanup-section">
            <h4>Clean operation log</h4>
            <p>Delete operation logs older than a specified number of days</p>
            <el-input-number v-model="logCleanupDays" :min="1" :max="365" />
            <span style="margin-left: 8px">days ago</span>
            <br><br>
            <el-button type="warning" @click="cleanupOperationLogs" :loading="cleaning">
              Clean operation log
            </el-button>
          </div>
        </el-col>
        

      </el-row>
    </el-card>

    <!-- Plain text display dialog (for manual copying) -->
    <el-dialog
      v-model="showPlainTextDialog"
      :title="plainTextTitle"
      width="80%"
      :close-on-click-modal="false"
    >
      <div style="margin-bottom: 16px;">
        <el-alert
          type="info"
          :closable="false"
          show-icon
        >
          <template #title>
            <div>
              <p style="margin: 0 0 8px 0;">If automatic copying fails or garbled characters appear when pasting, please copy the following text manually:</p>
              <p style="margin: 0; font-size: 12px; color: #909399;">
                Tip: When pasting in the command line, it is recommended to use the right-click menu"Paste"or press <code>Shift+Insert</code>, instead of <code>Ctrl+V</code>
              </p>
            </div>
          </template>
        </el-alert>
      </div>
      <el-input
        v-model="plainTextContent"
        type="textarea"
        :rows="10"
        readonly
        style="font-family: 'Consolas', 'Monaco', monospace;"
      />
      <template #footer>
        <el-button @click="showPlainTextDialog = false">close</el-button>
        <el-button type="primary" @click="copyPlainText">
          <el-icon><CopyDocument /></el-icon>
          copy to clipboard
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataBoard,
  Download,
  Upload,
  Refresh,
  CopyDocument
} from '@element-plus/icons-vue'

import {
  databaseApi,
  formatBytes,
  formatDateTime,
  formatUptime,
  type DatabaseStatus,
  type DatabaseStats
} from '@/api/database'

// Responsive data
const loading = ref(false)

const exporting = ref(false)
const importing = ref(false)
const testing = ref(false)
const cleaning = ref(false)

const exportFormat = ref('json')
const exportCollection = ref('config_and_reports')  // Default selection"Configuration and reporting"
const importFile = ref<File | null>(null)
const importOverwrite = ref(false)
const uploadRef = ref()
const cleanupDays = ref(30)
const logCleanupDays = ref(90)

// Plain text display dialog box
const showPlainTextDialog = ref(false)
const plainTextContent = ref('')
const plainTextTitle = ref('')

// Data status
const databaseStatus = ref<DatabaseStatus | null>(null)
const databaseStats = ref<DatabaseStats | null>(null)
const connectionInfo = ref<{
  mongo_uri: string
  display_uri: string
  database_name: string
  host: string
  port: number
  has_auth: boolean
  install_dir: string
} | null>(null)

// Computed properties
const mongoStatus = computed(() => databaseStatus.value?.mongodb || {
  connected: false,
  host: 'localhost',
  port: 27017,
  database: 'tradingagents'
})

const redisStatus = computed(() => databaseStatus.value?.redis || {
  connected: false,
  host: 'localhost',
  port: 6379,
  database: 0
})

const dbStats = computed(() => ({
  totalCollections: databaseStats.value?.total_collections || 0,
  totalDocuments: databaseStats.value?.total_documents || 0,
  totalSize: databaseStats.value?.total_size || 0
}))

// Data loading method
const loadDatabaseStatus = async () => {
  try {
    loading.value = true
    const status = await databaseApi.getStatus()
    databaseStatus.value = status
    console.log('📊 Database status loaded successfully:', status)
  } catch (error) {
    console.error('❌ Failed to load database status:', error)
    ElMessage.error('Failed to load database status')
  } finally {
    loading.value = false
  }
}

const loadDatabaseStats = async () => {
  try {
    const stats = await databaseApi.getStats()
    databaseStats.value = stats
    console.log('📈 Database statistics loaded successfully:', stats)
  } catch (error) {
    console.error('❌ Failed to load database statistics:', error)
    ElMessage.error('Failed to load database statistics')
  }
}

const loadConnectionInfo = async () => {
  try {
    const response = await databaseApi.getConnectionInfo()
    if (response.success && response.data) {
      connectionInfo.value = response.data
      console.log('🔗 MongoDB Connection information loaded successfully:', response.data)
    }
  } catch (error) {
    console.error('❌ Failed to load connection information:', error)
    // Do not display error messages and use default values
  }
}

// Computed Properties: Generate Backup Command
const backupCommand = computed(() => {
  if (!connectionInfo.value) {
    return 'vendors\\mongodb\\mongodb-win32-x86_64-windows-8.0.13\\bin\\mongodump.exe --uri="mongodb://localhost:27017" --db=tradingagents --out=./backup --gzip'
  }
  const mongoUri = connectionInfo.value.mongo_uri
  const dbName = connectionInfo.value.database_name
  return `vendors\\mongodb\\mongodb-win32-x86_64-windows-8.0.13\\bin\\mongodump.exe --uri="${mongoUri}" --db=${dbName} --out=./backup --gzip`
})

// Computed Properties: Generate Restore Command
const restoreCommand = computed(() => {
  if (!connectionInfo.value) {
    return 'vendors\\mongodb\\mongodb-win32-x86_64-windows-8.0.13\\bin\\mongorestore.exe --uri="mongodb://localhost:27017" --db=tradingagents --gzip ./backup/tradingagents'
  }
  const mongoUri = connectionInfo.value.mongo_uri
  const dbName = connectionInfo.value.database_name
  return `vendors\\mongodb\\mongodb-win32-x86_64-windows-8.0.13\\bin\\mongorestore.exe --uri="${mongoUri}" --db=${dbName} --gzip ./backup/${dbName}`
})

// Computed properties: generate cd command
const cdCommand = computed(() => {
  return `cd ${connectionInfo.value?.install_dir || 'C:\\TradingAgentsCN'}`
})

const bracketedPasteStart = `${String.fromCharCode(27)}[200~`
const bracketedPasteEnd = `${String.fromCharCode(27)}[201~`
const controlCharactersRegex = new RegExp(
  `[${String.fromCharCode(0)}-${String.fromCharCode(31)}${String.fromCharCode(127)}-${String.fromCharCode(159)}]`,
  'g'
)

// Clean text, removing possible escape sequences and special characters
const cleanText = (text: string): string => {
  // Remove all possible escape sequences and control characters
  return text
    .split('\u001b[200~').join('')
    .split('\u001b[201~').join('')
    .split('^[[200~').join('')
    .split('^[[201~').join('')
    .split(bracketedPasteStart).join('')
    .split(bracketedPasteEnd).join('')
    .replace(controlCharactersRegex, '')
    .trim()
}

// Copy command to clipboard (use most reliable method)
const copyToClipboard = async (text: string, commandName: string) => {
  // Clean the text and make sure it is plain text
  const cleanCommand = cleanText(text)
  
  try {
    // Method 1: Use Clipboard API writeText (the simplest and most reliable)
    await navigator.clipboard.writeText(cleanCommand)
    ElMessage.success(`${commandName}Copied to clipboard`)
  } catch (error) {
    // Method 2: Use traditional method (better compatibility)
    try {
      const textArea = document.createElement('textarea')
      textArea.value = cleanCommand
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      textArea.style.opacity = '0'
      textArea.setAttribute('readonly', '')
      textArea.setAttribute('aria-hidden', 'true')
      document.body.appendChild(textArea)
      
      // Select text
      if (navigator.userAgent.match(/ipad|iphone/i)) {
        // iOS Equipment requires special handling
        const range = document.createRange()
        range.selectNodeContents(textArea)
        const selection = window.getSelection()
        selection?.removeAllRanges()
        selection?.addRange(range)
        textArea.setSelectionRange(0, cleanCommand.length)
      } else {
        textArea.select()
        textArea.setSelectionRange(0, cleanCommand.length)
      }
      
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)
      
      if (successful) {
        ElMessage.success(`${commandName}Copied to clipboard`)
      } else {
        // If automatic copying fails, display a text-only dialog box
        showPlainTextDialog.value = true
        plainTextContent.value = cleanCommand
        plainTextTitle.value = commandName
      }
    } catch (err) {
      // If copying fails, display a text-only dialog box
      showPlainTextDialog.value = true
      plainTextContent.value = cleanCommand
      plainTextTitle.value = commandName
    }
  }
}

// Show text-only dialog (for manual copying)
const showPlainText = (text: string, title: string) => {
  const cleanCommand = cleanText(text)
  showPlainTextDialog.value = true
  plainTextContent.value = cleanCommand
  plainTextTitle.value = title
}

// Copy the contents of a plain text dialog box
const copyPlainText = async () => {
  try {
    await navigator.clipboard.writeText(plainTextContent.value)
    ElMessage.success('Copied to clipboard')
  } catch (error) {
    ElMessage.warning('Please select and copy text manually')
  }
}

const testConnections = async () => {
  try {
    testing.value = true
    const response = await databaseApi.testConnections()
    const results = response.data

    if (results.overall) {
      ElMessage.success('Database connection test successful')
    } else {
      ElMessage.warning('Some database connection tests failed')
    }

    // Show detailed results
    const mongoMsg = `MongoDB: ${results.mongodb.message} (${results.mongodb.response_time_ms}ms)`
    const redisMsg = `Redis: ${results.redis.message} (${results.redis.response_time_ms}ms)`

    ElMessage({
      message: `${mongoMsg}\n${redisMsg}`,
      type: results.overall ? 'success' : 'warning',
      duration: 5000
    })

    // Refresh status display after successful test
    await loadDatabaseStatus()

  } catch (error) {
    console.error('❌ Connection test failed:', error)
    ElMessage.error('Connection test failed')
  } finally {
    testing.value = false
  }
}

// Data management methods

const exportData = async () => {
  exporting.value = true
  try {
    // Configuration data collection list (for demonstration system)
    const configCollections = [
      // System configuration
      'system_configs',            // System configuration (including LLM configuration)
      'platform_configs',          // Platform configuration
      'llm_providers',             // LLM provider
      'model_catalog',             // Model catalog
      'smtp_config',               // SMTP Configuration
      'datasource_groupings',      // Data source grouping
      'market_categories',         // Market classification
      'stock_industry_mappings',   // Industry mapping data
      'mcp_server_configs',        // MCP Server configuration
      'sync_status',               // Sync status

      // User/Authentication
      'users',                     // User data (only the structure is exported in desensitization mode)
      'user_tags',                 // User tag

      // Agent/Workflow
      'workflow_definitions',      // Workflow definition
      'workflows',                 // Workflow example
      'agent_configs',             // Agent Configuration
      'agent_io_definitions',      // Agent IO definition
      'agent_specs',               // Agent Specification definition
      'agent_versions',            // Agent version
      'tool_configs',              // Tool configuration
      'tool_agent_bindings',       // Tool-Agent Binding
      'agent_workflow_bindings',   // Agent-workflow binding
      'skills',                    // Skill definition
      'custom_tools',              // Custom tools
      'external_skills',           // external Skill

      // Templates/Presets
      'prompt_templates',          // prompt word template
      'report_templates',          // report template
      'screening_presets',         // stock selection default
      'industry_analysis_profiles',// Industry analysis configuration
      'user_template_configs',     // User template configuration

      // trading system
      'trading_systems',           // Personal trading plan
      'trading_system_versions',   // Trading system version
      'paper_accounts',            // Demo account
      'paper_market_rules',        // Simulate market rules

      // Scheduling tasks
      'scheduled_analysis_configs', // Timing analysis configuration
      'scheduler_metadata',         // Scheduler metadata

      // Other configurations
      'watchlist_groups',           // Stock watchlist grouping

      // Note: Does not include market_quotes and stock_basic_info (large amount of data, not suitable for demonstration system)
      // Note: Does not contain runtime data (user_favorites, real_accounts, assistant_threads etc.)
    ]

    // Research report collection list
    const reportCollections = [
      'unified_analysis_tasks',    // Unified Analysis Tasks (v2.0)
      'analysis_tasks',            // Analysis tasks (v1.x)
      'analysis_reports',          // research report
      'position_analysis_reports', // Position research report
      'portfolio_analysis_reports' // Portfolio Research Report
    ]

    // List of history collections (optional, for full migration)
    const historyCollections = [
      'workflow_history',          // Workflow history
      'template_history',          // Template history
      'scheduled_analysis_history', // Regular analysis of history
      'notifications',             // Notification
      'email_records'              // Email history
    ]

    // Transaction collection list (optional, for full migration)
    const tradingCollections = [
      'paper_positions',           // Simulated position
      'paper_orders',              // Simulate orders
      'paper_trades',              // simulated trading
      'real_positions',            // Firm position
      'capital_transactions',      // Fund transactions
      'position_changes',          // Position changes
      'trade_reviews',             // Transaction review
      'trading_system_evaluations' // Trading system evaluation
    ]

    // List of configuration and reporting collections (for migration)
    const configAndReportsCollections = [
      ...configCollections,
      ...reportCollections,
      ...historyCollections,
      ...tradingCollections
    ]

    let collections: string[] = []
    let sanitize = false  // Whether to enable desensitization
    let exportType = ''   // Export type (for filename)

    if (exportCollection.value === 'config_only') {
      collections = configCollections // Export configuration data only
      sanitize = true  // Automatically enable desensitization when exporting configuration data (clear sensitive fields such as API key) - used for demonstration system
      exportType = '_config'
    } else if (exportCollection.value === 'config_and_reports') {
      collections = configAndReportsCollections // Export configuration and reports
      sanitize = false  // No desensitization - used for migration, complete data needs to be retained
      exportType = '_config_reports'
    } else {
      collections = [exportCollection.value] // Export a single collection
      exportType = `_${exportCollection.value}`
    }

    const blob = await databaseApi.exportData({
      collections,
      format: exportFormat.value,
      sanitize  // Pass desensitization parameters
    })

    // Create download link (backend compressed into zip file)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `database_export${exportType}_${new Date().toISOString().split('T')[0]}.zip`
    link.click()
    URL.revokeObjectURL(url)

    // Show different success messages based on export type
    if (exportCollection.value === 'config_only') {
      ElMessage.success('Configuration data exported successfully (desensitized: sensitive fields such as API key have been cleared, and only the structure of user data remains)')
    } else if (exportCollection.value === 'config_and_reports') {
      ElMessage.success('Configuration and reporting data exported successfully (contains complete data, ready for migration)')
    } else {
      ElMessage.success('Data export successful')
    }

  } catch (error) {
    console.error('❌ Data export failed:', error)
    ElMessage.error('Data export failed')
  } finally {
    exporting.value = false
  }
}

// File upload processing
const handleFileChange = (file: any) => {
  importFile.value = file.raw
  console.log('📁 Select file:', file.name)
}

const handleFileRemove = () => {
  importFile.value = null
  console.log('🗑️ Remove files')
}

// Data import
const importData = async () => {
  if (!importFile.value) {
    ElMessage.warning('Please select the file to import first')
    return
  }

  try {
    // Confirm import
    const confirmMessage = importOverwrite.value
      ? 'Are you sure you want to import data? This will overwrite existing data!'
      : 'Are you sure you want to import data?'

    await ElMessageBox.confirm(
      confirmMessage,
      'Confirm import',
      {
        type: 'warning',
        confirmButtonText: 'Confirm import',
        cancelButtonText: 'Cancel'
      }
    )

    importing.value = true

    const result = await databaseApi.importData(importFile.value, {
      collection: 'imported_data',  // The backend will automatically detect multi-collection mode
      format: 'json',
      overwrite: importOverwrite.value
    })

    console.log('✅ Import results:', result)

    // Display different success messages depending on the import mode
    if (result.data.mode === 'multi_collection') {
      ElMessage.success(
        `Data import successful! Total import ${result.data.total_collections} a collection,` +
        `${result.data.total_inserted} document`
      )
    } else {
      ElMessage.success(
        `Data import successful! import ${result.data.inserted_count} documents to collection ${result.data.collection}`
      )
    }

    // Clear file selection
    importFile.value = null
    uploadRef.value?.clearFiles()

    // Refresh database statistics
    await loadDatabaseStats()

  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('❌ Data import failed:', error)
      ElMessage.error(error.response?.data?.detail || 'Data import failed')
    }
  } finally {
    importing.value = false
  }
}

// Cleaning method
const cleanupAnalysisResults = async () => {
  try {
    await ElMessageBox.confirm(
      `sure to clean ${cleanupDays.value} The analysis results from days ago?`,
      'Confirm cleanup',
      { type: 'warning' }
    )

    cleaning.value = true
    const response = await databaseApi.cleanupAnalysisResults(cleanupDays.value)

    ElMessage.success(`The analysis results have been cleaned and deleted. ${response.data.deleted_count} records`)

    // Reload statistics
    await loadDatabaseStats()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('❌ Failed to clean up analysis results:', error)
      ElMessage.error('Failed to clean up analysis results')
    }
  } finally {
    cleaning.value = false
  }
}

const cleanupOperationLogs = async () => {
  try {
    await ElMessageBox.confirm(
      `sure to clean ${logCleanupDays.value} Operation log from days ago?`,
      'Confirm cleanup',
      { type: 'warning' }
    )

    cleaning.value = true
    const response = await databaseApi.cleanupOperationLogs(logCleanupDays.value)

    ElMessage.success(`The operation log has been cleaned and deleted. ${response.data.deleted_count} records`)

    // Reload statistics
    await loadDatabaseStats()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('❌ Failed to clear operation log:', error)
      ElMessage.error('Failed to clear operation log')
    }
  } finally {
    cleaning.value = false
  }
}





// life cycle
onMounted(async () => {
  console.log('🔄 Database management page initialization')

  // Load data in parallel
  await Promise.all([
    loadDatabaseStatus(),
    loadDatabaseStats(),
    loadConnectionInfo()
  ])

  console.log('✅ Database management page initialization completed')
})
</script>

<style lang="scss" scoped>
.database-management {
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

  .connection-card {
    .connection-status {
      .status-indicator {
        text-align: center;
        margin-bottom: 16px;
      }
      
      .connection-info {
        margin-bottom: 16px;
        
        p {
          margin: 4px 0;
          font-size: 14px;
        }
      }
      
      .connection-actions {
        display: flex;
        gap: 8px;
        justify-content: center;
      }
    }
  }

  .stat-card {
    .stat-content {
      text-align: center;
      
      .stat-value {
        font-size: 24px;
        font-weight: 600;
        color: var(--el-color-primary);
        margin-bottom: 8px;
      }
      
      .stat-label {
        font-size: 14px;
        color: var(--el-text-color-regular);
      }
    }
  }

  .operations-card {
    .operation-section {
      h4 {
        margin: 0 0 8px 0;
        font-size: 16px;
      }
      
      p {
        margin: 0 0 16px 0;
        font-size: 14px;
        color: var(--el-text-color-regular);
      }
      
      .file-info {
        margin-top: 12px;
        
        p {
          margin: 0 0 8px 0;
          font-size: 14px;
        }
      }
    }
  }



  .cleanup-card {
    .cleanup-section {
      h4 {
        margin: 0 0 8px 0;
        font-size: 16px;
      }
      
      p {
        margin: 0 0 12px 0;
        font-size: 14px;
        color: var(--el-text-color-regular);
      }
    }
  }
}
</style>
