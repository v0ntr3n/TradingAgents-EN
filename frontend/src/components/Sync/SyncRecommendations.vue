<template>
  <div class="scheduled-tasks">
    <el-card class="tasks-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon class="header-icon"><Clock /></el-icon>
          <span class="header-title">Scheduled task management</span>
          <el-button 
            type="primary" 
            size="small" 
            :loading="loading"
            @click="loadTasks"
          >
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
        </div>
      </template>

      <div v-loading="loading" class="tasks-content">
        <div v-if="error" class="error-message">
          <el-alert
            :title="error"
            type="error"
            :closable="false"
            show-icon
          />
        </div>

        <div v-else-if="taskGroups.length > 0" class="task-groups">
          <!-- Historical data synchronization task -->
          <div class="task-group">
            <h4 class="group-title">
              <el-icon class="title-icon"><DataLine /></el-icon>
              Historical data synchronization
            </h4>
            <div class="task-list">
              <div 
                v-for="task in getTasksByType('historical')" 
                :key="task.id"
                class="task-item"
              >
                <div class="task-header">
                  <div class="task-info">
                    <div class="task-name-row">
                      <span class="task-name">{{ task.display_name || task.name }}</span>
                      <el-tag 
                        :type="getDataSourceTagType(extractDataSource(task.id, task.name))" 
                        size="small"
                        class="source-tag"
                      >
                        {{ formatDataSourceName(extractDataSource(task.id, task.name)) }}
                        <span class="priority-badge">priority: {{ getDataSourcePriority(extractDataSource(task.id, task.name)) }}</span>
                      </el-tag>
                    </div>
                    <div class="task-meta">
                      <el-tag :type="!task.paused ? 'success' : 'info'" size="small">
                        {{ !task.paused ? 'Enabled' : 'Suspended' }}
                      </el-tag>
                      <el-tag v-if="isTaskRunning(task.id)" type="danger" size="small" style="margin-left: 8px;">
                        Executing
                      </el-tag>
                      <el-tag v-if="task.has_suspended_execution" type="warning" size="small" style="margin-left: 8px;">
                        ⏸️ There are pending tasks
                      </el-tag>
                      <span v-if="getTaskActiveProgress(task.id) !== null" class="task-running-meta">
                        Current progress: {{ getTaskActiveProgress(task.id) }}%
                      </span>
                      <span v-if="getTaskActiveStartedAt(task.id)" class="task-running-meta">
                        Started with {{ formatTime(getTaskActiveStartedAt(task.id)!) }}
                      </span>
                      <span v-if="formatScheduleDescription(task.trigger)" class="task-schedule">
                        <el-icon><Timer /></el-icon>
                        {{ formatScheduleDescription(task.trigger) }}
                      </span>
                      <span v-if="task.next_run_time && !task.paused" class="task-next-time">
                        Execute next time: {{ formatTime(task.next_run_time) }}
                      </span>
                    </div>
                  </div>
                  <div class="task-actions">
                    <div class="action-group">
                      <div class="action-label">
                        <span v-if="task.paused" class="status-hint">The task has been paused. Click the switch to enable scheduled execution.</span>
                        <span v-else class="status-hint">The task is enabled. Click the switch to pause scheduled execution.</span>
                      </div>
                      <div class="action-controls">
                        <el-switch
                          :model-value="!task.paused"
                          @change="(value) => handleToggleTask(task.id, Boolean(value))"
                          :loading="taskToggling[task.id]"
                          active-text="enable"
                          inactive-text="pause"
                        />
                        <el-dropdown
                          v-if="isHistoricalTask(task.id)"
                          trigger="click"
                          @command="(cmd: string) => handleTriggerTask(task.id, cmd === 'full')"
                        >
                          <el-button
                            size="small"
                            type="primary"
                            :loading="taskTriggering[task.id]"
                            :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                            style="margin-left: 8px"
                          >
                            Execute immediately
                            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                          </el-button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item 
                                command="incremental"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Incremental synchronization (only new data is synchronized)
                              </el-dropdown-item>
                              <el-dropdown-item 
                                command="full"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Full synchronization (synchronization of all historical data)
                              </el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                        <el-button
                          v-else
                          size="small"
                          type="primary"
                          :loading="taskTriggering[task.id]"
                          :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                          @click="handleTriggerTask(task.id)"
                          style="margin-left: 8px"
                        >
                          Execute immediately
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- Display of pending tasks -->
                <div v-if="task.has_suspended_execution && task.suspended_execution" class="suspended-execution">
                  <el-alert
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #title>
                      <span>The task has been suspended (interruption caused by service restart)</span>
                    </template>
                    <template #default>
                      <div class="suspended-info">
                        <div>Progress: {{ task.suspended_execution.progress }}%</div>
                        <div v-if="task.suspended_execution.processed_items !== undefined && task.suspended_execution.total_items !== undefined">
                          Processed: {{ task.suspended_execution.processed_items }}/{{ task.suspended_execution.total_items }}
                        </div>
                        <div v-if="task.suspended_execution.started_at">
                          start time: {{ formatTime(task.suspended_execution.started_at) }}
                        </div>
                        <el-button
                          size="small"
                          type="primary"
                          @click="handleResumeSuspendedTask(task.id, task.suspended_execution.execution_id)"
                          style="margin-top: 8px;"
                        >
                          Continue execution
                        </el-button>
                      </div>
                    </template>
                  </el-alert>
                </div>
                <!-- Task progress display -->
                <div v-if="displayTaskProgress[task.id]" class="task-progress">
                  <el-progress
                    :percentage="displayTaskProgress[task.id].progress || 0"
                    :status="getProgressStatus(displayTaskProgress[task.id].status)"
                    :stroke-width="6"
                  />
                  <div class="progress-info">
                    <div class="progress-row">
                      <span v-if="displayTaskProgress[task.id].message" class="progress-message">
                        {{ displayTaskProgress[task.id].message }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].processed_items !== undefined && displayTaskProgress[task.id].total_items !== undefined" class="progress-count">
                        {{ displayTaskProgress[task.id].processed_items }}/{{ displayTaskProgress[task.id].total_items }}
                      </span>
                    </div>
                    <div v-if="shouldShowProgressDetails(task.id)" class="progress-details">
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-time">
                        start time: {{ formatTime(displayTaskProgress[task.id].started_at) }}
                      </span>
                      <span class="progress-percentage">
                        Completeness: {{ displayTaskProgress[task.id].progress || 0 }}%
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-elapsed">
                        elapsed time: {{ calculateElapsedTime(displayTaskProgress[task.id].started_at!) }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at && (displayTaskProgress[task.id].progress || 0) > 0" class="progress-remaining">
                        remaining time: {{ calculateRemainingTime(displayTaskProgress[task.id].started_at!, displayTaskProgress[task.id].progress || 0) }}
                      </span>
                      <el-button
                        v-if="displayTaskProgress[task.id].execution_id"
                        size="small"
                        type="danger"
                        :icon="CircleClose"
                        @click="handleTerminateTask(task.id, displayTaskProgress[task.id].execution_id!)"
                        style="margin-left: 8px;"
                      >
                        terminate
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Financial data synchronization tasks -->
          <div class="task-group">
            <h4 class="group-title">
              <el-icon class="title-icon"><Money /></el-icon>
              Financial data synchronization
            </h4>
            <div class="task-list">
              <div 
                v-for="task in getTasksByType('financial')" 
                :key="task.id"
                class="task-item"
              >
                <div class="task-header">
                  <div class="task-info">
                    <div class="task-name-row">
                      <span class="task-name">{{ task.display_name || task.name }}</span>
                      <el-tag 
                        :type="getDataSourceTagType(extractDataSource(task.id, task.name))" 
                        size="small"
                        class="source-tag"
                      >
                        {{ formatDataSourceName(extractDataSource(task.id, task.name)) }}
                        <span class="priority-badge">priority: {{ getDataSourcePriority(extractDataSource(task.id, task.name)) }}</span>
                      </el-tag>
                    </div>
                    <div class="task-meta">
                      <el-tag :type="!task.paused ? 'success' : 'info'" size="small">
                        {{ !task.paused ? 'Enabled' : 'Suspended' }}
                      </el-tag>
                      <el-tag v-if="isTaskRunning(task.id)" type="danger" size="small" style="margin-left: 8px;">
                        Executing
                      </el-tag>
                      <el-tag v-if="task.has_suspended_execution" type="warning" size="small" style="margin-left: 8px;">
                        ⏸️ There are pending tasks
                      </el-tag>
                      <span v-if="getTaskActiveProgress(task.id) !== null" class="task-running-meta">
                        Current progress: {{ getTaskActiveProgress(task.id) }}%
                      </span>
                      <span v-if="getTaskActiveStartedAt(task.id)" class="task-running-meta">
                        Started with {{ formatTime(getTaskActiveStartedAt(task.id)!) }}
                      </span>
                      <span v-if="formatScheduleDescription(task.trigger)" class="task-schedule">
                        <el-icon><Timer /></el-icon>
                        {{ formatScheduleDescription(task.trigger) }}
                      </span>
                      <span v-if="task.next_run_time && !task.paused" class="task-next-time">
                        Execute next time: {{ formatTime(task.next_run_time) }}
                      </span>
                    </div>
                  </div>
                  <div class="task-actions">
                    <div class="action-group">
                      <div class="action-label">
                        <span v-if="task.paused" class="status-hint">The task has been paused. Click the switch to enable scheduled execution.</span>
                        <span v-else class="status-hint">The task is enabled. Click the switch to pause scheduled execution.</span>
                      </div>
                      <div class="action-controls">
                        <el-switch
                          :model-value="!task.paused"
                          @change="(value) => handleToggleTask(task.id, Boolean(value))"
                          :loading="taskToggling[task.id]"
                          active-text="enable"
                          inactive-text="pause"
                        />
                        <el-dropdown
                          v-if="isHistoricalTask(task.id)"
                          trigger="click"
                          @command="(cmd: string) => handleTriggerTask(task.id, cmd === 'full')"
                        >
                          <el-button
                            size="small"
                            type="primary"
                            :loading="taskTriggering[task.id]"
                            :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                            style="margin-left: 8px"
                          >
                            Execute immediately
                            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                          </el-button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item 
                                command="incremental"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Incremental synchronization (only new data is synchronized)
                              </el-dropdown-item>
                              <el-dropdown-item 
                                command="full"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Full synchronization (synchronization of all historical data)
                              </el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                        <el-button
                          v-else
                          size="small"
                          type="primary"
                          :loading="taskTriggering[task.id]"
                          :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                          @click="handleTriggerTask(task.id)"
                          style="margin-left: 8px"
                        >
                          Execute immediately
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- Display of pending tasks -->
                <div v-if="task.has_suspended_execution && task.suspended_execution" class="suspended-execution">
                  <el-alert
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #title>
                      <span>The task has been suspended (interruption caused by service restart)</span>
                    </template>
                    <template #default>
                      <div class="suspended-info">
                        <div>Progress: {{ task.suspended_execution.progress }}%</div>
                        <div v-if="task.suspended_execution.processed_items !== undefined && task.suspended_execution.total_items !== undefined">
                          Processed: {{ task.suspended_execution.processed_items }}/{{ task.suspended_execution.total_items }}
                        </div>
                        <div v-if="task.suspended_execution.started_at">
                          start time: {{ formatTime(task.suspended_execution.started_at) }}
                        </div>
                        <el-button
                          size="small"
                          type="primary"
                          @click="handleResumeSuspendedTask(task.id, task.suspended_execution.execution_id)"
                          style="margin-top: 8px;"
                        >
                          Continue execution
                        </el-button>
                      </div>
                    </template>
                  </el-alert>
                </div>
                <!-- Task progress display -->
                <div v-if="displayTaskProgress[task.id]" class="task-progress">
                  <el-progress
                    :percentage="displayTaskProgress[task.id].progress || 0"
                    :status="getProgressStatus(displayTaskProgress[task.id].status)"
                    :stroke-width="6"
                  />
                  <div class="progress-info">
                    <div class="progress-row">
                      <span v-if="displayTaskProgress[task.id].message" class="progress-message">
                        {{ displayTaskProgress[task.id].message }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].processed_items !== undefined && displayTaskProgress[task.id].total_items !== undefined" class="progress-count">
                        {{ displayTaskProgress[task.id].processed_items }}/{{ displayTaskProgress[task.id].total_items }}
                      </span>
                    </div>
                    <div v-if="shouldShowProgressDetails(task.id)" class="progress-details">
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-time">
                        start time: {{ formatTime(displayTaskProgress[task.id].started_at) }}
                      </span>
                      <span class="progress-percentage">
                        Completeness: {{ displayTaskProgress[task.id].progress || 0 }}%
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-elapsed">
                        elapsed time: {{ calculateElapsedTime(displayTaskProgress[task.id].started_at!) }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at && (displayTaskProgress[task.id].progress || 0) > 0" class="progress-remaining">
                        remaining time: {{ calculateRemainingTime(displayTaskProgress[task.id].started_at!, displayTaskProgress[task.id].progress || 0) }}
                      </span>
                      <el-button
                        v-if="displayTaskProgress[task.id].execution_id"
                        size="small"
                        type="danger"
                        :icon="CircleClose"
                        @click="handleTerminateTask(task.id, displayTaskProgress[task.id].execution_id!)"
                        style="margin-left: 8px;"
                      >
                        terminate
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- News data synchronization task -->
          <div class="task-group">
            <h4 class="group-title">
              <el-icon class="title-icon"><Document /></el-icon>
              News data synchronization
            </h4>
            <div class="task-list">
              <div 
                v-for="task in getTasksByType('news')" 
                :key="task.id"
                class="task-item"
              >
                <div class="task-header">
                  <div class="task-info">
                    <div class="task-name-row">
                      <span class="task-name">{{ task.display_name || task.name }}</span>
                      <el-tag 
                        :type="getDataSourceTagType(extractDataSource(task.id, task.name))" 
                        size="small"
                        class="source-tag"
                      >
                        {{ formatDataSourceName(extractDataSource(task.id, task.name)) }}
                        <span class="priority-badge">priority: {{ getDataSourcePriority(extractDataSource(task.id, task.name)) }}</span>
                      </el-tag>
                    </div>
                    <div class="task-meta">
                      <el-tag :type="!task.paused ? 'success' : 'info'" size="small">
                        {{ !task.paused ? 'Enabled' : 'Suspended' }}
                      </el-tag>
                      <el-tag v-if="isTaskRunning(task.id)" type="danger" size="small" style="margin-left: 8px;">
                        Executing
                      </el-tag>
                      <el-tag v-if="task.has_suspended_execution" type="warning" size="small" style="margin-left: 8px;">
                        ⏸️ There are pending tasks
                      </el-tag>
                      <span v-if="getTaskActiveProgress(task.id) !== null" class="task-running-meta">
                        Current progress: {{ getTaskActiveProgress(task.id) }}%
                      </span>
                      <span v-if="getTaskActiveStartedAt(task.id)" class="task-running-meta">
                        Started with {{ formatTime(getTaskActiveStartedAt(task.id)!) }}
                      </span>
                      <span v-if="formatScheduleDescription(task.trigger)" class="task-schedule">
                        <el-icon><Timer /></el-icon>
                        {{ formatScheduleDescription(task.trigger) }}
                      </span>
                      <span v-if="task.next_run_time && !task.paused" class="task-next-time">
                        Execute next time: {{ formatTime(task.next_run_time) }}
                      </span>
                    </div>
                  </div>
                  <div class="task-actions">
                    <div class="action-group">
                      <div class="action-label">
                        <span v-if="task.paused" class="status-hint">The task has been paused. Click the switch to enable scheduled execution.</span>
                        <span v-else class="status-hint">The task is enabled. Click the switch to pause scheduled execution.</span>
                      </div>
                      <div class="action-controls">
                        <el-switch
                          :model-value="!task.paused"
                          @change="(value) => handleToggleTask(task.id, Boolean(value))"
                          :loading="taskToggling[task.id]"
                          active-text="enable"
                          inactive-text="pause"
                        />
                        <el-dropdown
                          v-if="isHistoricalTask(task.id)"
                          trigger="click"
                          @command="(cmd: string) => handleTriggerTask(task.id, cmd === 'full')"
                        >
                          <el-button
                            size="small"
                            type="primary"
                            :loading="taskTriggering[task.id]"
                            :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                            style="margin-left: 8px"
                          >
                            Execute immediately
                            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                          </el-button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item 
                                command="incremental"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Incremental synchronization (only new data is synchronized)
                              </el-dropdown-item>
                              <el-dropdown-item 
                                command="full"
                                :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                              >
                                Full synchronization (synchronization of all historical data)
                              </el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                        <el-button
                          v-else
                          size="small"
                          type="primary"
                          :loading="taskTriggering[task.id]"
                          :disabled="taskTriggering[task.id] || isTaskRunning(task.id)"
                          @click="handleTriggerTask(task.id)"
                          style="margin-left: 8px"
                        >
                          Execute immediately
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- Display of pending tasks -->
                <div v-if="task.has_suspended_execution && task.suspended_execution" class="suspended-execution">
                  <el-alert
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #title>
                      <span>The task has been suspended (interruption caused by service restart)</span>
                    </template>
                    <template #default>
                      <div class="suspended-info">
                        <div>Progress: {{ task.suspended_execution.progress }}%</div>
                        <div v-if="task.suspended_execution.processed_items !== undefined && task.suspended_execution.total_items !== undefined">
                          Processed: {{ task.suspended_execution.processed_items }}/{{ task.suspended_execution.total_items }}
                        </div>
                        <div v-if="task.suspended_execution.started_at">
                          start time: {{ formatTime(task.suspended_execution.started_at) }}
                        </div>
                        <el-button
                          size="small"
                          type="primary"
                          @click="handleResumeSuspendedTask(task.id, task.suspended_execution.execution_id)"
                          style="margin-top: 8px;"
                        >
                          Continue execution
                        </el-button>
                      </div>
                    </template>
                  </el-alert>
                </div>
                <!-- Task progress display -->
                <div v-if="displayTaskProgress[task.id]" class="task-progress">
                  <el-progress
                    :percentage="displayTaskProgress[task.id].progress || 0"
                    :status="getProgressStatus(displayTaskProgress[task.id].status)"
                    :stroke-width="6"
                  />
                  <div class="progress-info">
                    <div class="progress-row">
                      <span v-if="displayTaskProgress[task.id].message" class="progress-message">
                        {{ displayTaskProgress[task.id].message }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].processed_items !== undefined && displayTaskProgress[task.id].total_items !== undefined" class="progress-count">
                        {{ displayTaskProgress[task.id].processed_items }}/{{ displayTaskProgress[task.id].total_items }}
                      </span>
                    </div>
                    <div v-if="shouldShowProgressDetails(task.id)" class="progress-details">
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-time">
                        start time: {{ formatTime(displayTaskProgress[task.id].started_at) }}
                      </span>
                      <span class="progress-percentage">
                        Completeness: {{ displayTaskProgress[task.id].progress || 0 }}%
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at" class="progress-elapsed">
                        elapsed time: {{ calculateElapsedTime(displayTaskProgress[task.id].started_at!) }}
                      </span>
                      <span v-if="displayTaskProgress[task.id].started_at && (displayTaskProgress[task.id].progress || 0) > 0" class="progress-remaining">
                        remaining time: {{ calculateRemainingTime(displayTaskProgress[task.id].started_at!, displayTaskProgress[task.id].progress || 0) }}
                      </span>
                      <el-button
                        v-if="displayTaskProgress[task.id].execution_id"
                        size="small"
                        type="danger"
                        :icon="CircleClose"
                        @click="handleTerminateTask(task.id, displayTaskProgress[task.id].execution_id!)"
                        style="margin-left: 8px;"
                      >
                        terminate
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <el-empty description="No scheduled tasks yet" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

// 🔥 Define events to notify the parent component to refresh
const emit = defineEmits<{
  (e: 'task-triggered'): void
  (e: 'task-resumed'): void
}>()
import {
  Clock,
  Refresh,
  DataLine,
  Money,
  Document,
  Timer,
  ArrowDown,
  CircleClose
} from '@element-plus/icons-vue'
import {
  getJobs,
  getJobProgress,
  triggerJob,
  pauseJob,
  resumeJob,
  cancelExecution,
  type JobStatus,
  type JobProgress
} from '@/api/scheduler'
import {
  getDataSourcesStatus,
  type DataSourceStatus
} from '@/api/sync'
import { isJdyunMode } from '@/utils/config'

// Responsive data
const loading = ref(false)
const error = ref('')
const allTasks = ref<JobStatus[]>([])
const dataSources = ref<DataSourceStatus[]>([])
const taskProgress = ref<Record<string, JobProgress>>({})
const taskToggling = ref<Record<string, boolean>>({})
const taskTriggering = ref<Record<string, boolean>>({})
const progressPollingTimer = ref<NodeJS.Timeout | null>(null)

const ACTIVE_PROGRESS_STATUSES = new Set<JobProgress['status']>(['running', 'cancelling', 'suspended'])
const TERMINAL_PROGRESS_STATUSES = new Set<JobProgress['status']>(['success', 'failed', 'cancelled', 'unknown'])

// JD Cloud version only displays Tushare / AKShare data source tasks
const JDYUN_ALLOWED_SOURCES = new Set(['tushare', 'akshare', 'multi_source'])
const isJdyunAllowedSource = (sourceName: string) =>
  JDYUN_ALLOWED_SOURCES.has((sourceName || '').toLowerCase())

// Task type keyword mapping
const taskTypeKeywords: Record<string, string[]> = {
  historical: ['historical data', 'historical'],
  financial: ['financial data', 'financial'],
  news: ['news data', 'news']
}

// Extract data source name from task ID or name
const extractDataSource = (jobId: string | undefined, jobName: string | undefined): string => {
  const id = (jobId || '').toLowerCase()
  const name = (jobName || '').toLowerCase()
  
  // 🔥 Special handling: Stock watchlist data synchronization task using multiple data sources (by priority)
  if (id === 'favorites_data_sync' || name.includes('Stock Watchlist') || name.includes('favorites')) {
    return 'multi_source'  // Multiple data sources
  }
  
  if (id.includes('akshare') || name.includes('akshare')) return 'akshare'
  if (id.includes('tushare') || name.includes('tushare')) return 'tushare'
  if (id.includes('baostock') || name.includes('baostock')) return 'baostock'
  
  return 'unknown'
}

// Extract task type from task ID or name
const extractTaskType = (jobId: string | undefined, jobName: string | undefined): string | null => {
  const id = (jobId || '').toLowerCase()
  const name = (jobName || '').toLowerCase()
  
  for (const [type, keywords] of Object.entries(taskTypeKeywords)) {
    if (keywords.some(keyword => id.includes(keyword.toLowerCase()) || name.includes(keyword.toLowerCase()))) {
      return type
    }
  }
  
  return null
}

// Determine whether the task is of the type we care about
const isRelevantTask = (task: JobStatus): boolean => {
  if (!task || !task.id) return false
  const taskType = extractTaskType(task.id, task.name)
  if (taskType === null || !['historical', 'financial', 'news'].includes(taskType)) {
    return false
  }
  // JD Cloud version only displays Tushare / AKShare / multi-data source tasks, filtering out BaoStock, etc.
  if (isJdyunMode()) {
    const source = extractDataSource(task.id, task.name)
    if (!isJdyunAllowedSource(source)) {
      return false
    }
  }
  return true
}

// Get data source priority
const getDataSourcePriority = (sourceName: string): number => {
  // 🔥 Special handling: Multi-data source tasks use the highest priority (because it automatically selects data sources by priority)
  if (sourceName === 'multi_source') {
    return 999  // Multiple data source tasks have the highest priority
  }
  
  const source = dataSources.value.find(s => s.name.toLowerCase() === sourceName.toLowerCase())
  return source?.priority || 999 // Not found has the lowest priority
}

// Group tasks by data source priority and task type
const groupedTasks = computed(() => {
  const groups: Record<string, Record<string, JobStatus[]>> = {
    historical: {},
    financial: {},
    news: {}
  }
  
  // Filter related tasks
  const relevantTasks = allTasks.value.filter(isRelevantTask)
  
  // Group by type and data source
  relevantTasks.forEach(task => {
    const taskType = extractTaskType(task.id, task.name)
    const dataSource = extractDataSource(task.id, task.name)
    
    if (taskType && ['historical', 'financial', 'news'].includes(taskType)) {
      if (!groups[taskType][dataSource]) {
        groups[taskType][dataSource] = []
      }
      groups[taskType][dataSource].push(task)
    }
  })
  
  // Sort by data source priority
  Object.keys(groups).forEach(type => {
    const sortedSources = Object.keys(groups[type]).sort((a, b) => {
      return getDataSourcePriority(b) - getDataSourcePriority(a) // Highest priority first
    })
    
        const sortedGroup: Record<string, JobStatus[]> = {}
    sortedSources.forEach(source => {
      sortedGroup[source] = groups[type][source]
    })
    groups[type] = sortedGroup
  })
  
  return groups
})

// Computed properties: task grouping
const taskGroups = computed(() => {
  const groups = []
  if (Object.keys(groupedTasks.value.historical).length > 0) groups.push('historical')
  if (Object.keys(groupedTasks.value.financial).length > 0) groups.push('financial')
  if (Object.keys(groupedTasks.value.news).length > 0) groups.push('news')
  return groups
})

// Get tasks by type (sorted by data source priority)
const getTasksByType = (type: string): JobStatus[] => {
  const tasks: JobStatus[] = []
  const group = groupedTasks.value[type] || {}
  
  // Add tasks in data source priority order
  Object.keys(group).sort((a, b) => {
    return getDataSourcePriority(b) - getDataSourcePriority(a)
  }).forEach(source => {
    tasks.push(...group[source])
  })
  
  return tasks
}

// Load data source status
const loadDataSources = async () => {
  try {
    const response = await getDataSourcesStatus()
    if (response.success) {
      // JD Cloud version only retains Tushare / AKShare
      if (isJdyunMode()) {
        dataSources.value = response.data.filter(s => isJdyunAllowedSource(s.name))
      } else {
        dataSources.value = response.data
      }
    }
  } catch (err: any) {
    console.error('Failed to load data source status:', err)
  }
}

// Load task list
const loadTasks = async () => {
  try {
    loading.value = true
    error.value = ''
    
    // Load data source information first
    await loadDataSources()
    
    // Load all tasks
    const response = await getJobs()
    if (response.success) {
      // Save all tasks
      allTasks.value = response.data
      
      // 🔍 Debugging: Print all task information
      console.log('📋 All tasks obtained:', allTasks.value.length, 'a')
      allTasks.value.forEach((task, index) => {
        console.log(`Task ${index + 1}:`, {
          id: task.id,
          name: task.name,
          paused: task.paused,
          extractedType: extractTaskType(task.id, task.name),
          extractedSource: extractDataSource(task.id, task.name),
          isRelevant: isRelevantTask(task)
        })
      })
      
      // Only progress for enabled tasks is loaded (unenabled tasks do not require progress)
      const relevantTasks = allTasks.value.filter(isRelevantTask)
      console.log('✅ Filtered related tasks:', relevantTasks.length, 'a')
      
      for (const task of relevantTasks) {
        if (!task.paused) {  // paused=false means enabled
          await loadTaskProgress(task.id)
        }
      }
      
      // Start polling for progress (only polling enabled tasks)
      startProgressPolling()
    } else {
      error.value = response.message || 'Failed to get task list'
    }
  } catch (err: any) {
    console.error('Failed to load scheduled task:', err)
    error.value = err.message || 'Network request failed'
  } finally {
    loading.value = false
  }
}

// Loading task progress
const loadTaskProgress = async (jobId: string) => {
  try {
    const response = await getJobProgress(jobId)
    if (response.success && response.data) {
      taskProgress.value[jobId] = response.data
    }
  } catch (err: any) {
    console.error(`Load task ${jobId} Progress failed:`, err)
  }
}

const buildRunningExecutionProgress = (jobId: string, task: JobStatus, storedProgress?: JobProgress): JobProgress | null => {
  const runningExecution = task.running_execution
  if (!runningExecution) return null

  const isSameExecution = storedProgress?.execution_id === runningExecution.execution_id
  return {
    job_id: jobId,
    execution_id: runningExecution.execution_id,
    progress: typeof runningExecution.progress === 'number'
      ? runningExecution.progress
      : (storedProgress?.progress || 0),
    status: isSameExecution && storedProgress?.status && ACTIVE_PROGRESS_STATUSES.has(storedProgress.status)
      ? storedProgress.status
      : 'running',
    message: isSameExecution
      ? (storedProgress?.message || 'Task in progress...')
      : 'Task in progress...',
    current_item: isSameExecution
      ? (storedProgress?.current_item || runningExecution.current_item)
      : runningExecution.current_item,
    total_items: isSameExecution
      ? (storedProgress?.total_items ?? runningExecution.total_items)
      : runningExecution.total_items,
    processed_items: isSameExecution
      ? (storedProgress?.processed_items ?? runningExecution.processed_items)
      : runningExecution.processed_items,
    started_at: runningExecution.started_at || storedProgress?.started_at,
    updated_at: runningExecution.updated_at || storedProgress?.updated_at,
  }
}

const resolveTaskDisplayProgress = (jobId: string): JobProgress | null => {
  const storedProgress = taskProgress.value[jobId]
  const task = allTasks.value.find(item => item.id === jobId)

  if (!task?.running_execution) {
    return storedProgress || null
  }

  const runningExecution = task.running_execution
  if (storedProgress?.execution_id === runningExecution.execution_id) {
    if (storedProgress.status && TERMINAL_PROGRESS_STATUSES.has(storedProgress.status)) {
      return storedProgress
    }

    return {
      ...buildRunningExecutionProgress(jobId, task, storedProgress)!,
      ...storedProgress,
      execution_id: runningExecution.execution_id,
      progress: typeof storedProgress.progress === 'number' ? storedProgress.progress : runningExecution.progress,
      started_at: storedProgress.started_at || runningExecution.started_at,
      updated_at: storedProgress.updated_at || runningExecution.updated_at,
      total_items: storedProgress.total_items ?? runningExecution.total_items,
      processed_items: storedProgress.processed_items ?? runningExecution.processed_items,
      current_item: storedProgress.current_item || runningExecution.current_item,
      status: storedProgress.status && ACTIVE_PROGRESS_STATUSES.has(storedProgress.status)
        ? storedProgress.status
        : 'running',
      message: storedProgress.message || 'Task in progress...',
    }
  }

  return buildRunningExecutionProgress(jobId, task, storedProgress)
}

const displayTaskProgress = computed<Record<string, JobProgress>>(() => {
  const displayProgressMap: Record<string, JobProgress> = {}
  const jobIds = new Set<string>([
    ...Object.keys(taskProgress.value),
    ...allTasks.value.map(task => task.id)
  ])

  for (const jobId of jobIds) {
    const progress = resolveTaskDisplayProgress(jobId)
    if (progress) {
      displayProgressMap[jobId] = progress
    }
  }

  return displayProgressMap
})

const getTaskDisplayProgress = (jobId: string): JobProgress | null => {
  return displayTaskProgress.value[jobId] || null
}

// Switch task enabled status
const handleToggleTask = async (jobId: string, enabled: boolean) => {
  try {
    taskToggling.value[jobId] = true
    
    if (enabled) {
      await resumeJob(jobId)
      ElMessage.success('Task is enabled')
      // Loading progress after enabling
      await loadTaskProgress(jobId)
      startProgressPolling()
    } else {
      await pauseJob(jobId)
      ElMessage.success('Task is paused')
      // Clear progress after pause
      delete taskProgress.value[jobId]
    }
    
    // Update task status
    const task = allTasks.value.find(t => t.id === jobId)
    if (task) {
      task.paused = !enabled  // paused=false means enabled
    }
    
    // Reload the task list to get the latest status
    await loadTasks()
  } catch (err: any) {
    ElMessage.error(`Operation failed: ${err.message}`)
    // restore state
    const task = allTasks.value.find(t => t.id === jobId)
    if (task) {
      task.paused = enabled  // Restore original state
    }
  } finally {
    taskToggling.value[jobId] = false
  }
}

// Determine whether it is a historical data synchronization task
const isHistoricalTask = (jobId: string): boolean => {
  return jobId.includes('historical_sync')
}

const isTaskRunning = (jobId: string): boolean => {
  const progress = getTaskDisplayProgress(jobId)
  if (progress?.status) {
    if (ACTIVE_PROGRESS_STATUSES.has(progress.status)) {
      return true
    }

    if (TERMINAL_PROGRESS_STATUSES.has(progress.status)) {
      return false
    }
  }

  const task = allTasks.value.find(item => item.id === jobId)
  if (task?.has_running_execution) {
    return true
  }

  return false
}

const shouldShowProgressDetails = (jobId: string): boolean => {
  const status = getTaskDisplayProgress(jobId)?.status
  return !!(status && ACTIVE_PROGRESS_STATUSES.has(status))
}

const getTaskRunningHint = (jobId: string): string => {
  const task = allTasks.value.find(item => item.id === jobId)
  const taskName = task?.display_name || task?.name || jobId
  const runningExecution = task?.running_execution

  if (runningExecution?.progress !== undefined) {
    return `${taskName}Executing, current progress ${runningExecution.progress}%, Please try again later`
  }

  const progress = getTaskDisplayProgress(jobId)
  if (progress?.progress !== undefined) {
    return `${taskName}Executing, current progress ${progress.progress}%, Please try again later`
  }

  return `${taskName}Executing, please try again later`
}

const getTaskActiveProgress = (jobId: string): number | null => {
  const progress = getTaskDisplayProgress(jobId)
  if (!progress || !ACTIVE_PROGRESS_STATUSES.has(progress.status)) {
    return null
  }

  return progress.progress !== undefined ? progress.progress : null
}

const getTaskActiveStartedAt = (jobId: string): string | null => {
  const progress = getTaskDisplayProgress(jobId)
  if (!progress || !ACTIVE_PROGRESS_STATUSES.has(progress.status)) {
    return null
  }

  return progress.started_at || null
}

// Calculate elapsed time
const calculateElapsedTime = (startedAt: string): string => {
  if (!startedAt) return '--'
  
  try {
    // Handling time zone issues: If the string has no time zone information, add +08:00 (The backend is stored as UTC+8) 
    let startedAtStr = String(startedAt).trim()
    if (startedAtStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !startedAtStr.endsWith('Z') && 
        !startedAtStr.includes('+') && 
        !startedAtStr.includes('-', 10)) {
      startedAtStr += '+08:00'
    }
    
    const start = new Date(startedAtStr)
    const now = new Date()
    
    // Check if the date is valid
    if (isNaN(start.getTime())) {
      console.warn('Invalid start time:', startedAt)
      return '--'
    }
    
    const diffMs = now.getTime() - start.getTime()
    
    // If the time difference is negative or too large (more than 7 days), it may be a data anomaly.
    if (diffMs < 0) {
      console.warn('Start time is later than current time:', startedAt, 'current time:', now.toISOString())
      return '--'
    }
    
    // If the time difference exceeds 7 days (604800000 milliseconds), the data may be abnormal and a warning will be displayed.
    if (diffMs > 7 * 24 * 60 * 60 * 1000) {
      console.warn('The elapsed time is unusually large (more than 7 days):', startedAt, 'elapsed time:', diffMs / 1000 / 60, 'minutes')
    }
    
    const seconds = Math.floor(diffMs / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    
    if (hours > 0) {
      return `${hours}hours${minutes % 60}minutes`
    } else if (minutes > 0) {
      return `${minutes}minutes${seconds % 60}seconds`
    } else {
      return `${seconds}seconds`
    }
  } catch (e) {
    console.error('Calculating elapsed time failed:', e, 'startedAt:', startedAt)
    return '--'
  }
}

// Calculate remaining time
const calculateRemainingTime = (startedAt: string, progress: number): string => {
  if (!startedAt || progress <= 0 || progress >= 100) return '--'
  
  try {
    // Handling time zone issues: If the string has no time zone information, add +08:00 (The backend is stored as UTC+8) 
    let startedAtStr = String(startedAt).trim()
    if (startedAtStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !startedAtStr.endsWith('Z') && 
        !startedAtStr.includes('+') && 
        !startedAtStr.includes('-', 10)) {
      startedAtStr += '+08:00'
    }
    
    const start = new Date(startedAtStr)
    const now = new Date()
    
    // Check if the date is valid
    if (isNaN(start.getTime())) {
      console.warn('Invalid start time:', startedAt)
      return '--'
    }
    
    const elapsedMs = now.getTime() - start.getTime()
    
    // If the time difference is negative or too large, it may be a data anomaly.
    if (elapsedMs < 0) {
      console.warn('Start time is later than current time:', startedAt)
      return '--'
    }
    
    // If the progress is 0 or 100%, the remaining time cannot be calculated
    if (progress <= 0 || progress >= 100) {
      return '--'
    }
    
    // Time spent / progress percentage = Estimated total time
    const progressDecimal = progress / 100
    if (progressDecimal <= 0 || progressDecimal >= 1) {
      return '--'
    }
    
    const totalMs = elapsedMs / progressDecimal
    const remainingMs = totalMs - elapsedMs
    
    // If the remaining time is negative or unusually large, return '--'
    if (remainingMs < 0 || remainingMs > 7 * 24 * 60 * 60 * 1000) {
      return '--'
    }
    
    const seconds = Math.floor(remainingMs / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    
    if (hours > 0) {
      return `${hours}hours${minutes % 60}minutes`
    } else if (minutes > 0) {
      return `${minutes}minutes${seconds % 60}seconds`
    } else {
      return `${seconds}seconds`
    }
  } catch (e) {
    console.error('Calculating remaining time failed:', e, 'startedAt:', startedAt, 'progress:', progress)
    return '--'
  }
}

// Resume a suspended task
const handleResumeSuspendedTask = async (jobId: string, executionId: string) => {
  try {
    const { resumeSuspendedExecution } = await import('@/api/scheduler')
    const response = await resumeSuspendedExecution(executionId)
    
    if (response.success) {
      ElMessage.success('The task has resumed execution and will continue from the last progress position')
      
      // 🔥 Clear pending task display immediately (no need to wait for backend query)
      // Find the corresponding task and clear the pending status
      const taskIndex = allTasks.value.findIndex(t => t.id === jobId)
      if (taskIndex !== -1) {
        allTasks.value[taskIndex].has_suspended_execution = false
        allTasks.value[taskIndex].suspended_execution = undefined
      }
      
      // Reload task list (make sure data is in sync)
      await loadTasks()
      
      // 🔥 2 Refresh the task list again after seconds to ensure the status has been updated
      setTimeout(async () => {
        await loadTasks()
        // 🔥 Notify the parent component to refresh (for multi-data source synchronization page)
        emit('task-resumed')
      }, 2000)
      
      // 🔥 Immediately notify the parent component to refresh
      emit('task-resumed')
      
      // Load progress and start polling
      await loadTaskProgress(jobId)
      startProgressPolling()
    } else {
      ElMessage.error(`Recovery task failed: ${response.message || 'unknown error'}`)
    }
  } catch (err: any) {
    ElMessage.error(`Recovery task failed: ${err.message}`)
    console.error('Failed to resume suspended task:', err)
  }
}

// 🔥 Terminate a running task
const handleTerminateTask = async (jobId: string, executionId: string) => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to terminate the currently executing task?',
      'Confirm termination',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning',
        center: true
      }
    )
    
    const response = await cancelExecution(executionId)
    
    if (response.success) {
      ElMessage.success('Termination request sent, task will be stopped on next check')
      
      // 🔥 Refresh progress and update status immediately
      await loadTaskProgress(jobId)
      
      // 🔥 2 Refresh again after seconds to ensure the status has been updated to terminated
      setTimeout(async () => {
        await loadTaskProgress(jobId)
        // Reload the task list to ensure the status is synchronized
        await loadTasks()
      }, 2000)
      
      // Keep polling for the latest status
      startProgressPolling()
    } else {
      ElMessage.error(`Failed to terminate task: ${response.message || 'unknown error'}`)
    }
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error(`Failed to terminate task: ${err.message}`)
      console.error('Failed to terminate task:', err)
    }
  }
}

// Trigger task execution
const handleTriggerTask = async (jobId: string, fullSync: boolean = false) => {
  try {
    if (isTaskRunning(jobId)) {
      ElMessage.warning(getTaskRunningHint(jobId))
      return
    }

    // 🔥 Check if there are any pending tasks
    const task = allTasks.value.find(t => t.id === jobId)
    if (task?.has_suspended_execution && task.suspended_execution) {
      // There are pending tasks, prompting the user to choose
      const suspendedExec = task.suspended_execution
      const progress = suspendedExec.progress || 0
      const processed = suspendedExec.processed_items || 0
      const total = suspendedExec.total_items || 0
      
      try {
        await ElMessageBox.confirm(
          `Pending tasks detected (progress: ${progress}%, Processed: ${processed}/${total}) \n\n Please select:`,
          'Pending task detected',
          {
            confirmButtonText: 'Resume execution from a suspended task',
            cancelButtonText: 'Start over',
            distinguishCancelAndClose: true,
            type: 'warning',
            center: true
          }
        )
        
        // User selection"Resume execution from a suspended task"
        if (suspendedExec.execution_id) {
          await handleResumeSuspendedTask(jobId, suspendedExec.execution_id)
          return
        }
      } catch (action: any) {
        // User selection"Start over"or cancel
        if (action === 'cancel') {
          // The user chooses to start over, clearing pending tasks first
          if (suspendedExec.execution_id) {
            try {
              const { cancelExecution } = await import('@/api/scheduler')
              await cancelExecution(suspendedExec.execution_id)
              ElMessage.success('Pending tasks have been cleared and execution will resume')
              
              // 🔥 Clear pending task display immediately (no need to wait for reload)
              const taskIndex = allTasks.value.findIndex(t => t.id === jobId)
              if (taskIndex !== -1) {
                allTasks.value[taskIndex].has_suspended_execution = false
                allTasks.value[taskIndex].suspended_execution = undefined
              }
              
              // Reload the task list to ensure data synchronization
              await loadTasks()
            } catch (err: any) {
              console.warn(`Failed to clear pending tasks: ${err.message}`)
              // Continue with new tasks even if cleanup fails
            }
          }
          // Continue executing the code below (start over)
        } else {
          // User closes dialog box without performing any action
          return
        }
      }
    }
    
    // Perform a new task (start over)
    taskTriggering.value[jobId] = true
    delete taskProgress.value[jobId]
    
    const options: { incremental?: boolean; force?: boolean } = {}
    if (isHistoricalTask(jobId)) {
      options.incremental = !fullSync  // fullSync=true when,incremental=false (Full synchronization)
    }
    
    try {
      await triggerJob(jobId, options)
      const syncMode = isHistoricalTask(jobId) ? (fullSync ? 'Full synchronization' : 'Incremental synchronization') : ''
      ElMessage.success(`Task execution has been triggered${syncMode ? ` (${syncMode}) ` : ''}`)
      
      // Reload task list (make sure data is in sync)
      await loadTasks()
      
      // 🔥 2 Refresh the task list again after seconds to ensure the status has been updated
      setTimeout(async () => {
        await loadTasks()
      }, 2000)
      
      // Start polling progress
      await loadTaskProgress(jobId)
      startProgressPolling()
    } catch (err: any) {
      // 🔥 Handling 409 errors (the task is running and requires user confirmation whether to force execution)
      if (err.response?.status === 409) {
        const errorDetail = err.response?.data?.detail || {}
        const message = errorDetail.message || 'An instance of the task is already running'
        const suggestion = errorDetail.suggestion || 'Is it enforceable? Forcing execution will skip concurrency checks, potentially causing duplicate executions.'
        const runningProgress = errorDetail.running_progress || 0
        const runningStartTime = errorDetail.running_start_time
        
        try {
          await ElMessageBox.confirm(
            `${message}\n\n${runningProgress > 0 ? `Current progress: ${runningProgress}%\n` : ''}${runningStartTime ? `start time: ${new Date(runningStartTime).toLocaleString()}\n\n` : ''}${suggestion}`,
            'Task is running',
            {
              confirmButtonText: 'enforce',
              cancelButtonText: 'Cancel',
              type: 'warning',
              distinguishCancelAndClose: true
            }
          )
          
          // User confirmation enforces, passing force=true
          options.force = true
          delete taskProgress.value[jobId]
          await triggerJob(jobId, options)
          const syncMode = isHistoricalTask(jobId) ? (fullSync ? 'Full synchronization' : 'Incremental synchronization') : ''
          ElMessage.success(`Task has been enforced${syncMode ? ` (${syncMode}) ` : ''}`)
          
          // Reload task list (make sure data is in sync)
          await loadTasks()
          
          // 🔥 2 Refresh the task list again after seconds to ensure the status has been updated
          setTimeout(async () => {
            await loadTasks()
            // 🔥 Notify the parent component to refresh (for multi-data source synchronization page)
            emit('task-triggered')
          }, 2000)
          
          // 🔥 Immediately notify the parent component to refresh
          emit('task-triggered')
          
          // Start polling progress
          await loadTaskProgress(jobId)
          startProgressPolling()
        } catch (confirmError: any) {
          // User cancels or closes the dialog box without performing any action
          if (confirmError !== 'cancel' && confirmError !== 'close') {
            ElMessage.error('Force execution failed: ' + (confirmError.message || 'unknown error'))
          }
        }
      } else {
        // Other errors
        throw err
      }
    }
  } catch (err: any) {
    // Ignore errors when user cancels dialog box
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(`Failed to trigger task: ${err.message}`)
    }
  } finally {
    taskTriggering.value[jobId] = false
  }
}

// Start progress polling
const startProgressPolling = () => {
  if (progressPollingTimer.value) {
    clearInterval(progressPollingTimer.value)
  }
  
  progressPollingTimer.value = setInterval(async () => {
    let hasRunningTask = false
    
    // Only poll related tasks that are enabled
    const relevantTasks = allTasks.value.filter(isRelevantTask).filter(t => !t.paused)
    
    for (const task of relevantTasks) {
      await loadTaskProgress(task.id)
      
      // Check if there are any running tasks (including suspended state)
      const progress = getTaskDisplayProgress(task.id)
      if (progress && ACTIVE_PROGRESS_STATUSES.has(progress.status)) {
        hasRunningTask = true
      }
    }
    
    // If there are no running tasks, stop polling
    if (!hasRunningTask) {
      await loadTasks()
      stopProgressPolling()
    }
  }, 3000) // Poll every 3 seconds
}

// Stop progress polling
const stopProgressPolling = () => {
  if (progressPollingTimer.value) {
    clearInterval(progressPollingTimer.value)
    progressPollingTimer.value = null
  }
}

// Get progress status
const getProgressStatus = (status?: string): 'success' | 'exception' | 'warning' => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'exception'
  return 'warning'
}

// Format data source name display
const formatDataSourceName = (sourceName: string): string => {
  const nameMap: Record<string, string> = {
    'akshare': 'AKSHARE',
    'tushare': 'TUSHARE',
    'baostock': 'BAOSTOCK',
    'multi_source': 'Multiple data sources',
    'unknown': 'UNKNOWN'
  }
  return nameMap[sourceName.toLowerCase()] || sourceName.toUpperCase()
}

// Get data source label type
const getDataSourceTagType = (sourceName: string): 'success' | 'warning' | 'info' | 'danger' => {
  // 🔥 Special handling: multi-data source tasks are displayed as success type
  if (sourceName === 'multi_source') {
    return 'success'
  }
  
  const priority = getDataSourcePriority(sourceName)
  if (priority >= 3) return 'success'
  if (priority >= 2) return 'warning'
  if (priority >= 1) return 'info'
  return 'danger'
}

// Format time
const formatTime = (isoString?: string) => {
  if (!isoString) return '-'
  try {
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return isoString
  }
}

// Extract CRON expression from trigger string
const extractCronFromTrigger = (trigger?: string): string => {
  if (!trigger) return ''
  
  // try to match cron[minute='X', hour='Y', ...] Format
  const cronMatch = trigger.match(/cron\[(.*?)\]/)
  if (cronMatch) {
    const params = cronMatch[1]
    const minuteMatch = params.match(/minute='([^']*)'/)
    const hourMatch = params.match(/hour='([^']*)'/)
    const dayMatch = params.match(/day='([^']*)'/)
    const monthMatch = params.match(/month='([^']*)'/)
    const dayOfWeekMatch = params.match(/day_of_week='([^']*)'/)
    
    const minute = minuteMatch ? minuteMatch[1] : '*'
    const hour = hourMatch ? hourMatch[1] : '*'
    const day = dayMatch ? dayMatch[1] : '*'
    const month = monthMatch ? monthMatch[1] : '*'
    const dayOfWeek = dayOfWeekMatch ? dayOfWeekMatch[1] : '*'
    
    return `${minute} ${hour} ${day} ${month} ${dayOfWeek}`
  }
  
  // If already in CRON format (5 space separated numbers/symbols)
  const parts = trigger.trim().split(/\s+/)
  if (parts.length === 5) {
    return trigger.trim()
  }
  
  return ''
}

// Format schedule description (convert CRON expression into human-readable description)
const formatScheduleDescription = (trigger?: string): string => {
  if (!trigger) return ''
  
  const cron = extractCronFromTrigger(trigger)
  if (!cron) {
    // If it is not in CRON format, try to display the original trigger
    if (trigger.includes('interval')) {
      const intervalMatch = trigger.match(/interval\[seconds=(\d+)\]/)
      if (intervalMatch) {
        const seconds = parseInt(intervalMatch[1])
        if (seconds < 60) {
          return `every${seconds}Execute once per second`
        } else if (seconds < 3600) {
          return `every${Math.floor(seconds / 60)}Execute once every minute`
        } else {
          return `every${Math.floor(seconds / 3600)}Execute once every hour`
        }
      }
    }
    return trigger
  }
  
  const parts = cron.split(' ')
  if (parts.length !== 5) return cron
  
  const [minute, hour, , , dayOfWeek] = parts
  
  // parsing time
  const hourNum = parseInt(hour)
  const minuteNum = parseInt(minute)
  const timeStr = hourNum >= 0 && hourNum < 24 && minuteNum >= 0 && minuteNum < 60
    ? `${hourNum.toString().padStart(2, '0')}:${minuteNum.toString().padStart(2, '0')}`
    : ''
  
  // Analyze frequency
  let freqDesc = ''
  if (dayOfWeek === '*') {
    freqDesc = 'every day'
  } else if (dayOfWeek === '1-5') {
    freqDesc = 'Working days (Monday to Friday)'
  } else if (dayOfWeek === '0,6' || dayOfWeek === '6,0') {
    freqDesc = 'Weekends (Saturday, Sunday)'
  } else if (dayOfWeek === '1') {
    freqDesc = 'Every Monday'
  } else if (dayOfWeek === '2') {
    freqDesc = 'Every Tuesday'
  } else if (dayOfWeek === '3') {
    freqDesc = 'every Wednesday'
  } else if (dayOfWeek === '4') {
    freqDesc = 'every Thursday'
  } else if (dayOfWeek === '5') {
    freqDesc = 'every friday'
  } else if (dayOfWeek === '6') {
    freqDesc = 'every Saturday'
  } else if (dayOfWeek === '0') {
    freqDesc = 'every sunday'
  } else if (dayOfWeek.includes(',')) {
    freqDesc = `weekly${dayOfWeek.split(',').map(d => {
      const dayNames = ['day', 'one', 'two', 'three', 'Four', 'five', 'six']
      return dayNames[parseInt(d)] || d
    }).join('、')}`
  } else {
    freqDesc = `CRON: ${cron}`
  }
  
  return timeStr ? `${freqDesc} ${timeStr} execute` : freqDesc
}

// Load data when component is mounted
onMounted(() => {
  loadTasks()
})

// Stop polling when component is uninstalled
onUnmounted(() => {
  stopProgressPolling()
})
</script>

<style scoped lang="scss">
.scheduled-tasks {
  .tasks-card {
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .header-icon {
        margin-right: 8px;
        color: var(--el-color-primary);
      }
      
      .header-title {
        font-weight: 600;
        flex: 1;
      }
    }
  }

  .tasks-content {
    min-height: 200px;
  }

  .task-groups {
    .task-group {
      margin-bottom: 32px;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      .group-title {
        display: flex;
        align-items: center;
        margin: 0 0 16px 0;
        font-size: 16px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        
        .title-icon {
          margin-right: 8px;
          color: var(--el-color-primary);
        }
      }
      
      .task-list {
        .task-item {
          padding: 16px;
          margin-bottom: 12px;
          border: 1px solid var(--el-border-color-light);
          border-radius: 8px;
          background: var(--el-bg-color-page);
          
          &:last-child {
            margin-bottom: 0;
          }
          
          .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            
            .task-info {
              flex: 1;
              
              .task-name-row {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 8px;
                flex-wrap: wrap;
                
                .task-name {
                  font-weight: 600;
                  font-size: 14px;
                  color: var(--el-text-color-primary);
                }
                
                .source-tag {
                  .priority-badge {
                    margin-left: 4px;
                    font-size: 11px;
                    opacity: 0.8;
                  }
                }
              }
              
              .task-meta {
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;

                .task-running-meta {
                  font-size: 12px;
                  color: var(--el-color-danger);
                  font-weight: 500;
                }
                
                .task-schedule {
                  display: flex;
                  align-items: center;
                  gap: 4px;
                  font-size: 12px;
                  color: var(--el-color-primary);
                  font-weight: 500;
                }
                
                .task-next-time {
                  font-size: 12px;
                  color: var(--el-text-color-secondary);
                }
              }
            }
            
            .task-actions {
              display: flex;
              align-items: center;
              
              .action-group {
                display: flex;
                flex-direction: column;
                gap: 8px;
                width: 100%;
                
                .action-label {
                  .status-hint {
                    font-size: 12px;
                    color: var(--el-text-color-secondary);
                    display: block;
                  }
                }
                
                .action-controls {
                  display: flex;
                  align-items: center;
                  justify-content: flex-end;
                }
              }
            }
          }
          
          .task-progress {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--el-border-color-lighter);
            
            .progress-info {
              margin-top: 8px;
              font-size: 12px;
              color: var(--el-text-color-secondary);
              
              .progress-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
                
                .progress-message {
                  flex: 1;
                  margin-right: 12px;
                }
                
                .progress-count {
                  font-weight: 500;
                  color: var(--el-color-primary);
                }
              }
              
              .progress-details {
                display: flex;
                flex-wrap: wrap;
                gap: 16px;
                margin-top: 8px;
                padding-top: 8px;
                border-top: 1px solid var(--el-border-color-lighter);
                
                .progress-time,
                .progress-percentage,
                .progress-elapsed,
                .progress-remaining {
                  font-size: 11px;
                  color: var(--el-text-color-regular);
                  
                  &:before {
                    content: '';
                    display: inline-block;
                    width: 4px;
                    height: 4px;
                    border-radius: 50%;
                    background-color: var(--el-color-primary);
                    margin-right: 6px;
                    vertical-align: middle;
                  }
                }
                
                .progress-percentage {
                  color: var(--el-color-primary);
                  font-weight: 500;
                }
                
                .progress-elapsed {
                  color: var(--el-color-warning);
                }
                
                .progress-remaining {
                  color: var(--el-color-info);
                }
              }
            }
          }
        }
      }
    }
  }

  .error-message {
    margin-bottom: 16px;
  }

  .empty-state {
    text-align: center;
    padding: 40px 0;
  }
}

@media (max-width: 768px) {
  .scheduled-tasks {
    .task-groups {
      .task-group {
        .task-list {
          .task-item {
            .task-header {
              flex-direction: column;
              align-items: flex-start;
              gap: 12px;
              
              .task-actions {
                width: 100%;
                justify-content: space-between;
              }
            }
          }
        }
      }
    }
  }
}
</style>
