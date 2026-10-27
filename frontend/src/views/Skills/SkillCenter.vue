<template>
  <div class="skill-center">
    <el-page-header title="Skill Center" content="Unified management of all skill assets">
      <template #extra>
        <el-space>
          <el-button type="primary" icon="Plus" @click="handleCreateSkill">
            New Skill
          </el-button>
        </el-space>
      </template>
    </el-page-header>

    <el-tabs v-model="activeTab" type="card" class="skill-tabs">
      <el-tab-pane label="mine Skill" name="my-skills">
        <div class="skill-stats">
          <el-statistic title="Skill total" :value="stats.total" suffix="a">
            <template #prefix>
              <el-icon class="icon" size="20"><Collection /></el-icon>
            </template>
          </el-statistic>
          <el-statistic title="Enabled" :value="stats.active" suffix="a">
            <template #prefix>
              <el-icon class="icon success" size="20"><CircleCheck /></el-icon>
            </template>
          </el-statistic>
          <el-statistic title="AI generate" :value="stats.external" suffix="a">
            <template #prefix>
              <el-icon class="icon" size="20"><MagicStick /></el-icon>
            </template>
          </el-statistic>
          <el-statistic title="Number of bindings" :value="stats.bindings" suffix="a">
            <template #prefix>
              <el-icon class="icon" size="20"><Link /></el-icon>
            </template>
          </el-statistic>
        </div>

        <el-card class="skill-list-card">
          <template #header>
            <el-space>
              <span>Skill list</span>
              <el-input
                v-model="searchQuery"
                placeholder="Search Skill name or description"
                class="search-input"
                clearable
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
              <el-select v-model="filterStatus" placeholder="Filter by status">
                <el-option label="All" value="" />
                <el-option label="Enabled" value="active" />
                <el-option label="Disabled" value="disabled" />
                <el-option label="draft" value="draft" />
                <el-option label="Archived" value="archived" />
              </el-select>
              <el-select v-model="filterSource" placeholder="Filter by source">
                <el-option label="All" value="" />
                <el-option label="import" value="imported" />
                <el-option label="AI generate" value="ai_generated" />
              </el-select>
            </el-space>
          </template>

          <el-table :data="filteredSkills" stripe border>
            <el-table-column prop="display_name" label="Name" min-width="180">
              <template #default="scope">
                <el-space>
                  <component :is="getSourceIcon(scope.row.source)" class="source-icon" />
                  <span>{{ scope.row.display_name }}</span>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="Description" min-width="200" />
            <el-table-column prop="type" label="Type" width="75">
              <template #default="scope">
                <el-tag :type="getTypeTagType(scope.row.type)" size="small">
                  {{ getTypeLabel(scope.row.type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="Source" width="75">
              <template #default="scope">
                <el-tag size="small">{{ getSourceLabel(scope.row.source) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="65">
              <template #default="scope">
                <el-tag :type="getStatusTagType(scope.row.status)" size="small">
                  {{ getStatusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="bindings" label="binding" width="110">
              <template #default="scope">
                <el-space v-if="scope.row.bindings?.agents?.length" wrap size="small">
                  <el-tag
                    v-for="aid in scope.row.bindings.agents.slice(0, 3)"
                    :key="aid"
                    size="small"
                    type="info"
                  >
                    {{ getAgentName(aid) }}
                  </el-tag>
                  <el-text v-if="scope.row.bindings.agents.length > 3" type="info" size="small">
                    +{{ scope.row.bindings.agents.length - 3 }}
                  </el-text>
                </el-space>
                <span v-else class="text-gray">Not bound</span>
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="280" align="center">
              <template #default="scope">
                <el-space>
                  <el-button
                    size="small"
                    icon="Play"
                    @click="handleTest(scope.row)"
                    :disabled="scope.row.status !== 'active'"
                  >test</el-button>
                  <el-button
                    size="small"
                    icon="Power"
                    type="warning"
                    @click="handleToggleStatus(scope.row)"
                    v-if="scope.row.status === 'active'"
                  >Disable</el-button>
                  <el-button
                    size="small"
                    icon="Check"
                    type="success"
                    @click="handleToggleStatus(scope.row)"
                    v-else
                  >enable</el-button>
                  <el-dropdown trigger="click" @command="(cmd: string) => handleMoreAction(cmd, scope.row)">
                    <el-button size="small" icon="MoreFilled" circle />
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="credentials">
                          <el-icon><Key /></el-icon> Credential configuration
                        </el-dropdown-item>
                        <el-dropdown-item command="bind">
                          <el-icon><Link /></el-icon> binding Agent
                        </el-dropdown-item>
                        <el-dropdown-item command="install_deps">
                          <el-icon><Download /></el-icon> Install dependencies
                        </el-dropdown-item>
                        <el-dropdown-item command="uninstall" divided>
                          <el-icon style="color: var(--el-color-danger)"><Delete /></el-icon>
                          <span style="color: var(--el-color-danger)">Uninstall</span>
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </el-space>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="ClawHub Installation" name="clawhub">
        <el-card class="clawhub-card">
          <template #header>
            <el-space>
              <span>ClawHub Scripted Skill Installation</span>
              <el-tag type="info">Only Python script types containing scripts/ are supported Skill</el-tag>
            </el-space>
          </template>

          <el-form :inline="true" @submit.prevent>
            <el-form-item label="Skill Slug">
              <el-input
                v-model="clawhubSlug"
                placeholder="Such as ifind-repilot-finance-data-search"
                style="width: 360px"
                clearable
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="clawhubInstalling" @click="() => installClawHubSkill()">
                Install and import
              </el-button>
              <el-button :loading="clawhubSearching" @click="searchClawHubSkills">
                Search
              </el-button>
              <el-button @click="loadLocalSkills">Refresh local package</el-button>
            </el-form-item>
          </el-form>

          <el-table v-if="clawhubResults.length" :data="clawhubResults" border style="margin-top: 12px">
            <el-table-column prop="display_name" label="Name" min-width="180" />
            <el-table-column prop="summary" label="Description" min-width="260" show-overflow-tooltip />
            <el-table-column prop="slug" label="Slug" min-width="220" />
            <el-table-column label="Operation" width="120">
              <template #default="scope">
                <el-button size="small" type="primary" @click="installClawHubSkill(scope.row.slug)">
                  Installation
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-divider />
          <h4>Skill package installed locally</h4>
          <el-table :data="localSkills" border>
            <el-table-column prop="name" label="Name" min-width="220" />
            <el-table-column prop="skill_dir" label="Directory" min-width="320" show-overflow-tooltip />
            <el-table-column label="Type" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.has_scripts ? 'success' : 'info'">
                  {{ scope.row.has_scripts ? 'Scripted' : 'Knowledge-based' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="database" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.imported_to_db ? 'success' : 'warning'">
                  {{ scope.row.imported_to_db ? 'Imported' : 'Not imported' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="180">
              <template #default="scope">
                <el-button size="small" :disabled="scope.row.imported_to_db" @click="importLocalSkill(scope.row.skill_dir)">
                  import
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="Install/Import" name="skillhub">
        <el-card class="clawhub-card">
          <template #header>
            <el-space>
              <span>Install/Import</span>
              <el-tag type="info">Supports ZIP file upload or download link import</el-tag>
            </el-space>
          </template>

          <el-row :gutter="24">
            <!-- Left: ZIP upload -->
            <el-col :span="12">
              <el-card shadow="never" style="height: 100%">
                <template #header>
                  <div style="display: flex; align-items: center;">
                    <el-icon style="margin-right: 8px;"><Upload /></el-icon>
                    <span>ZIP File upload</span>
                  </div>
                </template>
                <el-upload
                  ref="zipUploadRef"
                  drag
                  :auto-upload="false"
                  accept=".zip"
                  :limit="1"
                  :on-change="handleZipFileChange"
                  :on-remove="handleZipFileRemove"
                >
                  <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                  <div class="el-upload__text">Drag the ZIP file here, or<em>Click to upload</em></div>
                  <template #tip>
                    <div class="el-upload__tip">
                      Supports .zip format, up to 50MB. The package needs to contain the SKILL.md file.
                    </div>
                  </template>
                </el-upload>
                <div v-if="selectedZipFile" style="margin-top: 12px; text-align: right;">
                  <el-button type="primary" :loading="importingZip" @click="handleImportZip">
                    import
                  </el-button>
                </div>
              </el-card>
            </el-col>

            <!-- Right: URL import -->
            <el-col :span="12">
              <el-card shadow="never" style="height: 100%">
                <template #header>
                  <div style="display: flex; align-items: center;">
                    <el-icon style="margin-right: 8px;"><Link /></el-icon>
                    <span>Download link import</span>
                  </div>
                </template>
                <el-form label-position="top">
                  <el-form-item label="ZIP Download link">
                    <el-input
                      v-model="importUrl"
                      placeholder="https://example.com/skill-package.zip"
                      clearable
                      type="textarea"
                      :rows="2"
                    />
                  </el-form-item>
                  <el-form-item label="Custom name (optional)">
                    <el-input
                      v-model="importCustomName"
                      placeholder="Leave blank to automatically extract from ZIP package"
                      clearable
                    />
                  </el-form-item>
                  <el-form-item>
                    <el-button
                      type="primary"
                      :loading="importingUrl"
                      :disabled="!importUrl.trim()"
                      @click="handleImportUrl"
                    >
                      Download and import
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-card>
            </el-col>
          </el-row>

          <el-divider />
          <h4>Skill package installed locally</h4>
          <el-table :data="localSkills" border>
            <el-table-column prop="name" label="Name" min-width="220" />
            <el-table-column prop="skill_dir" label="Directory" min-width="320" show-overflow-tooltip />
            <el-table-column label="Type" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.has_scripts ? 'success' : 'info'">
                  {{ scope.row.has_scripts ? 'Scripted' : 'Knowledge-based' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="database" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.imported_to_db ? 'success' : 'warning'">
                  {{ scope.row.imported_to_db ? 'Imported' : 'Not imported' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="180">
              <template #default="scope">
                <el-button size="small" :disabled="scope.row.imported_to_db" @click="importLocalSkill(scope.row.skill_dir)">
                  import
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="AI generate" name="generate">
        <SkillGenerate @imported="handleSkillImported" />
      </el-tab-pane>

      <el-tab-pane label="execution log" name="logs">
        <div class="logs-container">
          <!-- Statistics cards -->
          <el-row :gutter="12" style="margin-bottom: 16px;">
            <el-col :span="6">
              <el-card shadow="never">
                <el-statistic title="total calls" :value="logStats.total" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="never">
                <el-statistic title="success" :value="logStats.success" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="never">
                <el-statistic title="failed" :value="logStats.failed" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="never">
                <div style="font-size: 12px; color: #909399; margin-bottom: 4px;">success rate</div>
                <div style="font-size: 24px; font-weight: 600;">
                  {{ logStats.total ? ((logStats.success / logStats.total) * 100).toFixed(1) : 0 }}%
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- filter bar -->
          <el-form :inline="true" style="margin-bottom: 12px;">
            <el-form-item label="Tools">
              <el-input v-model="logFilter.tool_id" placeholder="Tools ID" clearable style="width: 180px;" />
            </el-form-item>
            <el-form-item label="Agent">
              <el-input v-model="logFilter.agent_id" placeholder="Agent ID" clearable style="width: 180px;" />
            </el-form-item>
            <el-form-item label="Status">
              <el-select v-model="logFilter.success" placeholder="All" clearable style="width: 100px;">
                <el-option label="success" :value="true" />
                <el-option label="failed" :value="false" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadToolLogs">Query</el-button>
            </el-form-item>
          </el-form>

          <!-- log form -->
          <el-table :data="toolLogs" stripe style="width: 100%;" max-height="500">
            <el-table-column prop="tool_id" label="Tools" width="180" show-overflow-tooltip />
            <el-table-column prop="agent_id" label="Agent" width="180" show-overflow-tooltip />
            <el-table-column label="Status" width="80">
              <template #default="scope">
                <el-tag :type="scope.row.success ? 'success' : 'danger'" size="small">
                  {{ scope.row.success ? 'success' : 'failed' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="execution_time_ms" label="Time consuming" width="80">
              <template #default="scope">{{ scope.row.execution_time_ms }}ms</template>
            </el-table-column>
            <el-table-column prop="tool_args" label="parameters" show-overflow-tooltip>
              <template #default="scope">
                <pre style="margin: 0; font-size: 11px;">{{ JSON.stringify(scope.row.tool_args, null, 0) }}</pre>
              </template>
            </el-table-column>
            <el-table-column prop="result" label="result" show-overflow-tooltip>
              <template #default="scope">
                <span v-if="scope.row.error" style="color: #f56c6c;">{{ scope.row.error }}</span>
                <pre v-else style="margin: 0; font-size: 11px;">{{ String(scope.row.result).substring(0, 200) }}</pre>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="time" width="160">
              <template #default="scope">
                {{ scope.row.created_at ? new Date(scope.row.created_at).toLocaleString('zh-CN') : '' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="bindDialogVisible" title="bind to Agent" width="600px">
      <div v-if="currentSkill" class="bind-dialog-content">
        <p class="bind-skill-name">{{ currentSkill.display_name }}</p>
        
        <!-- bound Agent -->
        <div v-if="boundAgents.length" class="bound-section">
          <h4 style="margin: 0 0 8px;">Bound Agent</h4>
          <el-space wrap>
            <el-tag
              v-for="agent in boundAgents"
              :key="agent.agent_id"
              closable
              @close="unbindAgent(agent.agent_id)"
              style="margin: 4px;"
            >
              {{ agent.name }}
              <span v-if="agent.priority" style="color: #909399; font-size: 11px;"> (P{{ agent.priority }})</span>
            </el-tag>
          </el-space>
        </div>

        <el-divider v-if="boundAgents.length" />

        <!-- Add new binding (hidden when there is no optional Agent, such as community edition) -->
        <div v-if="availableAgents.length" class="bind-add-section">
          <h4 style="margin: 0 0 8px;">Add binding</h4>
          <el-form :model="bindForm" label-width="80px">
            <el-form-item label="Choose Agent">
              <el-select
                v-model="bindForm.agentIds"
                multiple
                filterable
                placeholder="Select one or more Agent"
                style="width: 100%;"
              >
                <el-option
                  v-for="agent in availableAgents"
                  :key="agent.id"
                  :label="agent.name"
                  :value="agent.id"
                  :disabled="boundAgents.some(b => b.agent_id === agent.id)"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="priority">
              <el-input-number v-model="bindForm.priority" :min="0" :max="100" style="width: 120px;" />
              <el-text type="info" size="small" style="margin-left: 8px;">The larger the number, the higher the priority.</el-text>
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="bindDialogVisible = false">close</el-button>
        <el-button
          v-if="availableAgents.length"
          type="primary"
          :loading="bindLoading"
          :disabled="!bindForm.agentIds.length"
          @click="confirmBatchBind"
        >
          Batch binding ({{ bindForm.agentIds.length }})
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testDialogVisible" title="test Skill" width="720px">
      <div v-if="currentTestSkill" class="test-dialog-content">
        <p class="test-skill-name">{{ currentTestSkill.display_name }}</p>
        <p class="test-skill-desc">Source:{{ currentTestSkill.source }} | Type:{{ currentTestSkill.type }}</p>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="The test method is consistent with the official Agent call"
          description="The backend will use the same LLM + Function Calling Mechanism: Use SKILL.md as the system prompt word, let LLM understand and call the tool independently, and return the complete call link."
          style="margin-bottom: 12px"
        />

        <el-form label-width="100px" style="margin-bottom: 16px">
          <el-form-item label="test questions">
            <el-input
              v-model="testQuestion"
              type="textarea"
              :rows="3"
              placeholder="For example: Help me check the latest news on the Federal Reserve s interest rate policy; or: Test whether this Skill can work properly"
              :disabled="testLoading"
            />
          </el-form-item>
        </el-form>

        <div v-if="testLoading" class="test-status">
          <el-icon class="is-loading"><Loading /></el-icon>
          Invoking LLM execution tool, may take 10-60 seconds...
        </div>

        <div v-else-if="testResult" class="test-result">
          <el-alert
            :title="testResult.success ? 'Test completed' : 'test failed'"
            :type="testResult.success ? 'success' : 'error'"
            :closable="false"
          />
          <div v-if="testResult.error" class="result-error">
            <strong>Error message:</strong>
            <pre>{{ testResult.error }}</pre>
          </div>

          <!-- Agent Call result display -->
          <template v-if="testResult.success && testResult.result">
            <div v-if="testResult.result.final_answer" class="result-section">
              <strong>LLM Final answer:</strong>
              <pre>{{ testResult.result.final_answer }}</pre>
            </div>

            <div v-if="testResult.result.tool_calls && testResult.result.tool_calls.length" class="result-section">
              <strong>Tool call track ({{ testResult.result.tool_calls_count || testResult.result.tool_calls.length }} times):</strong>
              <pre>{{ JSON.stringify(testResult.result.tool_calls, null, 2) }}</pre>
            </div>

            <div v-if="testResult.result.model" class="result-meta">
              model: {{ testResult.result.provider }}/{{ testResult.result.model }}
            </div>

            <!-- Compatible with non-Agent paths such as knowledge -->
            <div v-if="!testResult.result.final_answer && !testResult.result.tool_calls" class="result-section">
              <strong>Details:</strong>
              <pre>{{ formatTestResult(testResult.result) }}</pre>
            </div>
          </template>

          <div v-if="testResult.execution_time_ms > 0" class="result-meta">
            Execution time:{{ testResult.execution_time_ms }}ms
          </div>
        </div>

        <div v-else class="test-hint">
          <el-text type="info">After entering the test question, click"Run tests", LLM Tools will be automatically called based on SKILL.md</el-text>
        </div>
      </div>
      <template #footer>
        <el-button @click="testDialogVisible = false">close</el-button>
        <el-button type="primary" :loading="testLoading" @click="confirmTest">Run tests</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="credentialDialogVisible" title="Configure Skill Credentials" width="640px">
      <div v-if="credentialSkill" class="credential-dialog-content">
        <p class="bind-skill-name">{{ credentialSkill.display_name }}</p>
        <el-alert
          v-if="credentialStatus?.missing_required?.length"
          type="warning"
          :closable="false"
          :title="`Required credentials are missing:${credentialStatus.missing_required.join(', ')}`"
          style="margin-bottom: 12px"
        />
        <el-empty v-if="credentialStatus && !credentialStatus.required.length && !credentialStatus.extra.length" description="This skill does not declare a credential requirement" />
        <el-form v-else label-width="130px">
          <el-form-item
            v-for="item in credentialStatus?.required || []"
            :key="item.name"
            :label="item.name"
          >
            <el-input
              v-model="credentialForm[item.name]"
              :placeholder="item.configured ? item.masked_value : item.description || 'Please enter the credential value'"
              show-password
              style="width: 360px"
            />
            <el-tag v-if="item.required" type="danger" size="small" style="margin-left: 8px">Required</el-tag>
            <el-tag v-if="item.config_type === 'script_arg'" type="warning" size="small" style="margin-left: 8px">
              {{ item.config_command }}
            </el-tag>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="credentialDialogVisible = false">close</el-button>
        <el-button type="primary" :loading="credentialSaving" @click="saveCredentialConfig">Save credentials</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import type { Component } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection,
  CircleCheck,
  Link,
  Search,
  Download,
  MagicStick,
  WarningFilled,
  Loading,
  Key,
  Upload,
  UploadFilled
} from '@element-plus/icons-vue'
import SkillGenerate from './SkillCenter/SkillGenerate.vue'
import { skillCenterApi } from '@/api/skillCenter'
import { skillsApi } from '@/api/skills'
import { ApiClient } from '@/api/request'

interface SkillSummary {
  skill_id: string
  display_name: string
  description: string
  source: string
  type: string
  status: string
  bindable: boolean
  tool_id?: string
  test_status?: string
  last_tested_at?: string
  bindings: { agents: string[]; workflows: string[] }
  created_at?: string
  updated_at?: string
}

const activeTab = ref('my-skills')
const searchQuery = ref('')
const filterStatus = ref('')
const filterSource = ref('')
const skills = ref<SkillSummary[]>([])
const stats = ref({ total: 0, standard: 0, external: 0, active: 0, bindings: 0 })

// execution log
const toolLogs = ref<any[]>([])
interface LogStats {
  total: number
  success: number
  failed: number
  by_tool: Array<{ tool_id: string; count: number; avg_ms: number }>
  by_agent: Array<{ agent_id: string; count: number }>
}
const logStats = ref<LogStats>({ total: 0, success: 0, failed: 0, by_tool: [], by_agent: [] })
const logFilter = ref({ tool_id: '', agent_id: '', success: null as boolean | null })

const bindDialogVisible = ref(false)
const bindForm = ref({ agentIds: [] as string[], priority: 0 })
const bindLoading = ref(false)
const boundAgents = ref<Array<{ agent_id: string; name: string; category: string; priority: number }>>([])
const currentSkill = ref<SkillSummary | null>(null)
const availableAgents = ref<{ id: string; name: string }[]>([])
// Agent Whether the list has been loaded (success or failure counts), lazy loading guard used to bind the entry
const agentsLoaded = ref(false)

const testDialogVisible = ref(false)
const currentTestSkill = ref<SkillSummary | null>(null)
const testLoading = ref(false)
const testQuestion = ref('')
const testResult = ref<{ success: boolean; result?: any; error?: string; execution_time_ms: number } | null>(null)

const clawhubSlug = ref('')
const clawhubSearching = ref(false)
const clawhubInstalling = ref(false)
const clawhubResults = ref<any[]>([])
const localSkills = ref<any[]>([])

// ZIP / URL Import related
const zipUploadRef = ref<any>(null)
const selectedZipFile = ref<File | null>(null)
const importingZip = ref(false)
const importUrl = ref('')
const importCustomName = ref('')
const importingUrl = ref(false)

const credentialDialogVisible = ref(false)
const credentialSkill = ref<SkillSummary | null>(null)
const credentialStatus = ref<any | null>(null)
const credentialForm = ref<Record<string, string>>({})
const credentialSaving = ref(false)

const filteredSkills = computed(() => {
  return skills.value.filter(skill => {
    const matchSearch = !searchQuery.value ||
      skill.display_name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchStatus = !filterStatus.value || skill.status === filterStatus.value
    const matchSource = !filterSource.value || skill.source === filterSource.value
    return matchSearch && matchStatus && matchSource
  })
})

type ElTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

function getSourceIcon(source: string): Component {
  const icons: Record<string, Component> = {
    imported: Download,
    clawhub: Download,
    ai_generated: MagicStick,
    system: Collection,
    gap_generated: WarningFilled
  }
  return icons[source] || Collection
}

function getSourceLabel(source: string) {
  const labels: Record<string, string> = {
    imported: 'import',
    clawhub: 'ClawHub',
    ai_generated: 'AI generate',
    system: 'system',
    gap_generated: 'Gap generation'
  }
  return labels[source] || source
}

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    executable: 'Executable',
    knowledge: 'Knowledge-based',
    api: 'API',
    mcp: 'MCP'
  }
  return labels[type] || type
}

function getTypeTagType(type: string): ElTagType {
  const types: Record<string, ElTagType> = {
    executable: 'primary',
    knowledge: 'info',
    api: 'success',
    mcp: 'warning'
  }
  return types[type] || 'info'
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: 'Enabled',
    disabled: 'Disabled',
    draft: 'draft',
    testing: 'Under test',
    archived: 'Archived',
    failed: 'failed'
  }
  return labels[status] || status
}

function getStatusTagType(status: string): ElTagType {
  const types: Record<string, ElTagType> = {
    active: 'success',
    disabled: 'warning',
    draft: 'info',
    testing: 'primary',
    archived: 'info',
    failed: 'danger'
  }
  return types[status] || 'info'
}

function getAgentName(agentId: string): string {
  const agent = availableAgents.value.find(a => a.id === agentId)
  return agent ? agent.name : agentId
}

async function loadSkills() {
  try {
    skills.value = await skillCenterApi.listSkills()
  } catch (error) {
    console.error('Failed to load skills:', error)
  }
}

async function loadStats() {
  try {
    stats.value = await skillCenterApi.getStats()
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

async function loadAgents() {
  try {
    // Agent Metadata comes from Pro routing (app/pro/routers/agents.py), which is not available in the community version:
    // Silently downgrade to an empty list (close the global 404 pop-up window), and the binding drop-down is empty."No Agent to bind"
    const res: any = await ApiClient.get('/api/agents', undefined, { skipErrorHandler: true })
    const agents = Array.isArray(res) ? res : (res?.data || [])
    availableAgents.value = agents.map((a: any) => ({ id: a.id, name: a.name }))
  } catch (error) {
    console.debug('Agent The list is unavailable (the community version does not have an Agent management system), and the binding drop-down is left blank.')
  } finally {
    agentsLoaded.value = true
  }
}

function handleCreateSkill() {
  window.location.href = '/skills/generation/create'
}

async function searchClawHubSkills() {
  if (!clawhubSlug.value.trim()) {
    ElMessage.warning('Please enter search keywords or Skill slug')
    return
  }
  clawhubSearching.value = true
  try {
    const result = await skillsApi.searchClawHub({ q: clawhubSlug.value.trim(), limit: 20 })
    clawhubResults.value = result.results
    if (!result.results.length) ElMessage.info('No matching found ClawHub Skill')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Search ClawHub failed')
  } finally {
    clawhubSearching.value = false
  }
}

async function installClawHubSkill(slug?: string) {
  const targetSlug = typeof slug === 'string' ? slug : clawhubSlug.value.trim()
  if (!targetSlug) {
    ElMessage.warning('Please enter Skill slug')
    return
  }
  clawhubInstalling.value = true
  try {
    const result = await skillsApi.installClawHub({ slug: targetSlug })
    if (result.success) {
      ElMessage.success(result.message)
      await Promise.all([loadLocalSkills(), loadSkills(), loadStats()])
      activeTab.value = 'my-skills'
    } else {
      ElMessage.warning(result.message)
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Installation of ClawHub Skill failed')
  } finally {
    clawhubInstalling.value = false
  }
}

async function loadLocalSkills() {
  try {
    localSkills.value = await skillsApi.listLocalSkills()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Failed to load local Skill package')
  }
}

async function importLocalSkill(skillDir: string) {
  try {
    await skillsApi.importLocalSkill({ skill_dir: skillDir })
    ElMessage.success('Local Skill imported successfully')
    await Promise.all([loadLocalSkills(), loadSkills(), loadStats()])
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Failed to import local Skill')
  }
}

// ==================== ZIP / URL import ====================

function handleZipFileChange(file: any) {
  if (file && file.raw) {
    selectedZipFile.value = file.raw
  }
}

function handleZipFileRemove() {
  selectedZipFile.value = null
}

async function handleImportZip() {
  if (!selectedZipFile.value) return
  importingZip.value = true
  try {
    const result = await skillsApi.importZip(selectedZipFile.value)
    ElMessage.success(result.message || 'ZIP Import successful')
    selectedZipFile.value = null
    if (zipUploadRef.value) zipUploadRef.value.clearFiles()
    await Promise.all([loadLocalSkills(), loadSkills(), loadStats()])
    activeTab.value = 'my-skills'
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'ZIP Import failed')
  } finally {
    importingZip.value = false
  }
}

async function handleImportUrl() {
  if (!importUrl.value.trim()) return
  importingUrl.value = true
  try {
    const result = await skillsApi.importFromUrl({
      url: importUrl.value.trim(),
      name: importCustomName.value.trim() || undefined,
    })
    ElMessage.success(result.message || 'URL Import successful')
    importUrl.value = ''
    importCustomName.value = ''
    await Promise.all([loadLocalSkills(), loadSkills(), loadStats()])
    activeTab.value = 'my-skills'
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'URL Import failed')
  } finally {
    importingUrl.value = false
  }
}

async function handleSkillImported(skillName: string) {
  ElMessage.success(`Imported Skill: ${skillName}`)
  activeTab.value = 'my-skills'
  await loadSkills()
  loadStats()
  // Automatically pop up the binding dialog box
  const skill = skills.value.find(s => s.skill_id === skillName || s.display_name === skillName)
  if (skill) {
    handleBindAgent(skill)
  }
}

function handleTest(skill: SkillSummary) {
  currentTestSkill.value = skill
  testResult.value = null
  testQuestion.value = ''
  testDialogVisible.value = true
}

function formatTestResult(result: any): string {
  if (typeof result === 'string') return result
  // Friendly display of knowledge-based skills
  if (result.skill_type === 'knowledge') {
    const lines = [
      `Type: ${result.skill_type}`,
      `Name: ${result.name || '-'}`,
      `Description: ${result.description || '-'}`,
      result.category ? `Classification: ${result.category}` : '',
      result.parameters_count !== undefined ? `Number of parameters: ${result.parameters_count}` : '',
      `Registered to tool library: ${result.registered_in_registry ? 'Yes' : 'No'}`,
      result.note || ''
    ].filter(Boolean)
    return lines.join('\n')
  }
  return JSON.stringify(result, null, 2)
}

async function confirmTest() {
  if (!currentTestSkill.value) return
  testLoading.value = true
  testResult.value = null
  try {
    const result = await skillsApi.testSkill({
      skill_name: currentTestSkill.value.skill_id,
      args: {},
      question: testQuestion.value || '',
      timeout: 90,
    } as any)
    testResult.value = result
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.response?.data?.error || 'Test execution failed')
  } finally {
    testLoading.value = false
  }
}

function handleToggleStatus(skill: SkillSummary) {
  if (skill.source === 'ai_generated') {
    import('@/api/skillGeneration').then(api => {
      api.skillGenerationApi.updateSkillStatus(skill.skill_id, skill.status === 'active' ? 'disabled' : 'active')
        .then(() => loadSkills())
    })
  } else {
    import('@/api/skills').then(api => {
      api.skillsApi.toggleSkill(skill.skill_id.replace(/_/g, '-'), skill.status !== 'active')
        .then(() => loadSkills())
    })
  }
}

async function handleBindAgent(skill: SkillSummary) {
  // The binding pop-up window will not open when there is no bound Agent (the community version does not have an Agent workshop and the list is empty)
  if (!agentsLoaded.value) {
    await loadAgents()
  }
  if (!availableAgents.value.length) {
    ElMessage.warning('There is currently no binding Agent')
    return
  }
  currentSkill.value = skill
  bindForm.value = { agentIds: [], priority: 0 }
  bindDialogVisible.value = true
  // Load the bound Agent
  try {
    const result = await skillCenterApi.getSkillBindings(skill.skill_id)
    boundAgents.value = result.agents
  } catch {
    boundAgents.value = []
  }
}

async function handleUninstall(skill: SkillSummary) {
  try {
    await ElMessageBox.confirm(
      `Confirm to uninstall Skill "${skill.display_name}" ?\n\n Uninstalling will remove:\n• Skill record\n• local script directory\n• Credential configuration\n• Agent Binding relationship\n\n This action cannot be undone.`,
      'Uninstall confirmation',
      { type: 'warning', confirmButtonText: 'Confirm uninstall', cancelButtonText: 'Cancel' }
    )
  } catch {
    return
  }

  try {
    if (skill.source === 'ai_generated') {
      // AI Generated Skill usage skill-generation API
      const { skillGenerationApi } = await import('@/api/skillGeneration')
      const result = await skillGenerationApi.deleteSkill(skill.skill_id)
      ElMessage.success(result.message || result.data?.message || `Skill "${skill.display_name}" Uninstalled`)
    } else {
      // Manually installed Skill usage skills API
      const skillName = skill.skill_id.replace(/_/g, '-')
      const result = await skillsApi.deleteSkill(skillName)
      ElMessage.success(result.message || `Skill "${skill.display_name}" Uninstalled`)
    }
    await loadSkills()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Uninstall failed')
  }
}

// Dropdown menu operation distribution
function handleMoreAction(command: string, skill: any) {
  switch (command) {
    case 'credentials':
      handleCredentials(skill)
      break
    case 'bind':
      handleBindAgent(skill)
      break
    case 'install_deps':
      handleInstallDeps(skill)
      break
    case 'uninstall':
      handleUninstall(skill)
      break
  }
}

async function handleInstallDeps(skill: any) {
  const skillName = skill.skill_id ? skill.skill_id.replace(/_/g, '-') : skill.name
  const displayName = skill.display_name || skill.name || skill.skill_id || skillName
  const loadingMsg = ElMessage({
    message: `working on "${displayName}" Install dependencies...`,
    type: 'info',
    duration: 0,
  })
  try {
    const result = await skillsApi.installSkillDeps(skillName)
    loadingMsg.close()
    if (result.success && result.installed) {
      ElMessageBox.alert(
        `<pre style="max-height:400px;overflow:auto;font-size:12px;">${result.log}</pre>`,
        'Dependencies installed successfully',
        { dangerouslyUseHTMLString: true, type: 'success' }
      )
    } else if (!result.installed) {
      ElMessage.info(result.message)
    } else {
      ElMessageBox.alert(
        `<pre style="max-height:400px;overflow:auto;font-size:12px;color:#f56c6c;">${result.log}</pre>`,
        'Dependency installation failed',
        { dangerouslyUseHTMLString: true, type: 'error' }
      )
    }
  } catch (error: any) {
    loadingMsg.close()
    ElMessage.error(error?.response?.data?.detail || 'Failed to install dependencies')
  }
}

async function confirmBatchBind() {
  if (!currentSkill.value || !bindForm.value.agentIds.length) return
  bindLoading.value = true
  try {
    const result = await skillCenterApi.batchBindSkill(
      currentSkill.value.skill_id,
      bindForm.value.agentIds,
      bindForm.value.priority
    )
    ElMessage.success(result.message)
    bindForm.value = { agentIds: [], priority: 0 }
    // Refresh binding list
    const bindings = await skillCenterApi.getSkillBindings(currentSkill.value.skill_id)
    boundAgents.value = bindings.agents
    loadSkills()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Batch binding failed')
  } finally {
    bindLoading.value = false
  }
}

async function unbindAgent(agentId: string) {
  if (!currentSkill.value) return
  try {
    await skillCenterApi.unbindSkillFromAgent(currentSkill.value.skill_id, agentId)
    ElMessage.success('Unbound')
    boundAgents.value = boundAgents.value.filter(a => a.agent_id !== agentId)
    loadSkills()
    loadStats()
  } catch {
    ElMessage.error('Unbinding failed')
  }
}

async function handleCredentials(skill: SkillSummary) {
  credentialSkill.value = skill
  credentialForm.value = {}
  credentialStatus.value = null
  credentialDialogVisible.value = true
  try {
    credentialStatus.value = await skillsApi.getCredentialStatus(skill.skill_id)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || 'Failed to load credentials status')
  }
}

async function saveCredentialConfig() {
  if (!credentialSkill.value || !credentialStatus.value) return
  const filled = Object.fromEntries(
    Object.entries(credentialForm.value).filter(([, value]) => String(value || '').trim() !== '')
  ) as Record<string, string>
  if (!Object.keys(filled).length) {
    ElMessage.warning('Please enter at least one credential value')
    return
  }
  credentialSaving.value = true
  try {
    const scriptItems = (credentialStatus.value.required || []).filter((item: any) =>
      item.config_type === 'script_arg' && item.config_command && filled[item.name]
    )
    for (const item of scriptItems) {
      await skillsApi.configureCredentialViaScript(credentialSkill.value.skill_id, {
        config_command: item.config_command,
        credential_value: filled[item.name]
      })
      delete filled[item.name]
    }
    if (Object.keys(filled).length) {
      await skillsApi.saveCredentials(credentialSkill.value.skill_id, filled)
    }
    ElMessage.success('Voucher saved')
    credentialStatus.value = await skillsApi.getCredentialStatus(credentialSkill.value.skill_id)
    credentialForm.value = {}
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.response?.data?.message || 'Failed to save credentials')
  } finally {
    credentialSaving.value = false
  }
}

// execution log
async function loadToolLogs() {
  try {
    const params: any = { limit: 50 }
    if (logFilter.value.tool_id) params.tool_id = logFilter.value.tool_id
    if (logFilter.value.agent_id) params.agent_id = logFilter.value.agent_id
    if (logFilter.value.success !== null) params.success = logFilter.value.success
    const result = await skillCenterApi.getToolLogs(params)
    toolLogs.value = result.logs
  } catch {
    ElMessage.error('Failed to load execution log')
  }
}

async function loadLogStats() {
  try {
    logStats.value = await skillCenterApi.getToolLogStats()
  } catch {
    // ignore
  }
}

watch(activeTab, (val) => {
  if (val === 'logs') {
    loadToolLogs()
    loadLogStats()
  }
  if (val === 'clawhub') {
    loadLocalSkills()
  }
})

onMounted(() => {
  loadSkills()
  loadStats()
  loadAgents()
})
</script>

<style scoped>
.skill-center {
  padding: 20px;
}

.skill-tabs {
  margin-top: 20px;
}

.skill-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.skill-stats .el-statistic {
  flex: 1;
  text-align: center;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
}

.skill-stats .icon {
  color: #666;
}

.skill-stats .icon.success {
  color: #67c23a;
}

.skill-list-card {
  margin-top: 20px;
}

.search-input {
  width: 300px;
}

.source-icon {
  color: #409eff;
}

.text-gray {
  color: #999;
}

.el-table {
  --el-table-header-text-color: #666;
  --el-table-row-hover-bg-color: #fafafa;
}

.test-dialog-content {
  max-height: 500px;
  overflow-y: auto;
}

.test-skill-name {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 16px;
}

.test-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 4px;
  color: #606266;
}

.test-result {
  margin-top: 16px;
}

.result-section {
  margin-top: 12px;
}

.result-section strong {
  display: block;
  margin-bottom: 4px;
  color: #303133;
}

.test-result pre {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  margin: 8px 0;
}

.result-error {
  margin-top: 12px;
  color: #f56c6c;
}

.result-meta {
  margin-top: 12px;
  color: #909399;
  font-size: 12px;
}

.bind-dialog-content {
  max-height: 500px;
  overflow-y: auto;
}

.bind-skill-name {
  font-weight: 600;
  font-size: 15px;
  margin: 0 0 16px;
  color: var(--el-color-primary);
}

.bound-section {
  margin-bottom: 12px;
}

.bind-add-section {
  margin-top: 12px;
}

.logs-container {
  padding: 8px 4px;
}

.logs-container .el-card {
  background: #fafbfc;
}

.logs-container pre {
  margin: 0;
  font-size: 11px;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow: hidden;
}

.logs-container .el-table {
  font-size: 12px;
}
</style>