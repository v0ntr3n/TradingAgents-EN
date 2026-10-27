<template>
  <div class="scheduler-management">
    <!-- Page title and statistics -->
    <el-card class="header-card" shadow="never">
      <div class="header-content">
        <div class="title-section">
          <h2>
            <el-icon><Timer /></el-icon>
            Scheduled task management
          </h2>
          <p class="subtitle">Manage all scheduled tasks in the system, supporting pause, resume and manual triggering</p>
        </div>
        
        <div class="stats-section" v-if="stats">
          <el-statistic title="Total number of tasks" :value="stats.total_jobs">
            <template #prefix>
              <el-icon><List /></el-icon>
            </template>
          </el-statistic>
          <el-statistic title="Running" :value="stats.running_jobs">
            <template #prefix>
              <el-icon color="#67C23A"><VideoPlay /></el-icon>
            </template>
          </el-statistic>
          <el-statistic title="Suspended" :value="stats.paused_jobs">
            <template #prefix>
              <el-icon color="#E6A23C"><VideoPause /></el-icon>
            </template>
          </el-statistic>
        </div>
      </div>
      
      <div class="actions">
        <el-button @click="loadJobs" :loading="loading" :icon="Refresh">Refresh</el-button>
        <el-button @click="showHistoryDialog" :icon="Document">execution history</el-button>
      </div>
    </el-card>

    <!-- Search and filter -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" class="filter-form">
        <el-form-item label="Task name">
          <el-input
            v-model="searchKeyword"
            placeholder="Search task name"
            clearable
            :prefix-icon="Search"
            style="width: 240px"
            @clear="handleSearch"
            @input="handleSearch"
          />
        </el-form-item>

        <el-form-item label="data source">
          <el-select
            v-model="filterDataSource"
            placeholder="All data sources"
            clearable
            style="width: 180px"
            @change="handleSearch"
          >
            <el-option label="All data sources" value="" />
            <el-option label="Tushare" value="Tushare" />
            <el-option label="AKShare" value="AKShare" />
            <el-option label="BaoStock" value="BaoStock" />
            <el-option label="Multiple data sources" value="Multiple data sources" />
            <el-option label="Others" value="Others" />
          </el-select>
        </el-form-item>

        <el-form-item label="Status">
          <el-select
            v-model="filterStatus"
            placeholder="All status"
            clearable
            style="width: 150px"
            @change="handleSearch"
          >
            <el-option label="All status" value="" />
            <el-option label="Running" value="running" />
            <el-option label="Suspended" value="paused" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button :icon="Refresh" @click="handleReset">reset</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- task list -->
    <el-card class="table-card" shadow="never">
      <el-table
        :data="filteredJobs"
        v-loading="loading"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'paused', order: 'ascending' }"
      >
        <el-table-column prop="name" label="Task name" min-width="200" sortable>
          <template #default="{ row }">
            <div class="job-name">
              <div class="job-name-main">
                <el-tag :type="row.paused ? 'warning' : 'success'" size="small">
                  {{ row.paused ? 'Suspended' : 'Running' }}
                </el-tag>
                <el-tag v-if="isJobRunning(row)" type="danger" size="small">
                  Executing
                </el-tag>
                <span class="name-text">{{ row.name }}</span>
              </div>
              <div v-if="isJobRunning(row)" class="job-running-summary">
                <span v-if="getJobRunningProgress(row) !== null">Progress {{ getJobRunningProgress(row) }}%</span>
                <span v-if="getJobRunningStartedAt(row)">Started with {{ formatDateTime(getJobRunningStartedAt(row)!) }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="display_name" label="Trigger name" min-width="150">
          <template #default="{ row }">
            <el-text v-if="row.display_name" size="small">{{ row.display_name }}</el-text>
            <el-text v-else type="info" size="small">-</el-text>
          </template>
        </el-table-column>

        <el-table-column prop="trigger" label="trigger" min-width="180">
          <template #default="{ row }">
            <el-text size="small" type="info">{{ formatTrigger(row.trigger) }}</el-text>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="Remarks" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-text v-if="row.description" size="small">{{ row.description }}</el-text>
            <el-text v-else type="info" size="small">-</el-text>
          </template>
        </el-table-column>

        <el-table-column prop="next_run_time" label="Next execution time" min-width="180" sortable>
          <template #default="{ row }">
            <div v-if="row.next_run_time">
              <el-text size="small">{{ formatDateTime(row.next_run_time) }}</el-text>
              <br />
              <el-text size="small" type="info">{{ formatRelativeTime(row.next_run_time) }}</el-text>
            </div>
            <el-text v-else type="warning" size="small">Suspended</el-text>
          </template>
        </el-table-column>

        <el-table-column label="Operation" width="340" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button
                size="small"
                :icon="Edit"
                @click="showEditDialog(row)"
              >
                Edit
              </el-button>
              <el-button
                v-if="!row.paused"
                size="small"
                type="warning"
                :icon="VideoPause"
                @click="handlePause(row)"
                :loading="actionLoading[row.id]"
              >
                pause
              </el-button>
              <el-button
                v-else
                size="small"
                type="success"
                :icon="VideoPlay"
                @click="handleResume(row)"
                :loading="actionLoading[row.id]"
              >
                restore
              </el-button>
              <el-button
                size="small"
                type="primary"
                :icon="Promotion"
                @click="handleTrigger(row)"
                :loading="actionLoading[row.id]"
                :disabled="isJobRunning(row)"
              >
                Execute immediately
              </el-button>
              <el-button
                size="small"
                :icon="View"
                @click="showJobDetail(row)"
              >
                Details
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Edit task metadata dialog box -->
    <el-dialog
      v-model="editDialogVisible"
      title="Edit task information"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form v-if="editingJob" :model="editForm" label-width="120px">
        <el-form-item label="Task ID">
          <el-text>{{ editingJob.id }}</el-text>
        </el-form-item>
        <el-form-item label="Task name">
          <el-text>{{ editingJob.name }}</el-text>
        </el-form-item>
        <el-form-item label="Execution time" v-if="editForm.supports_cron">
          <div class="schedule-picker">
            <div class="schedule-row">
              <el-select v-model="editForm.frequency" placeholder="Select frequency" style="width: 140px;" @change="updateCronFromUI">
                <el-option label="every day" value="daily" />
                <el-option label="working day" value="weekdays" />
                <el-option label="weekend" value="weekend" />
                <el-option label="Every Monday" value="monday" />
                <el-option label="every friday" value="friday" />
              </el-select>
              <span class="schedule-sep">of</span>
              <el-time-select
                v-model="editForm.time"
                :start="'05:00'"
                :step="'00:30'"
                :end="'23:30'"
                placeholder="Select time"
                style="width: 120px;"
                @change="updateCronFromUI"
              />
              <span class="schedule-sep">execute</span>
            </div>
            <div class="schedule-preview">
              <el-tag type="info" size="small">
                <el-icon><Timer /></el-icon>
                {{ formatScheduleDescription(editForm.frequency, editForm.time) }}
              </el-tag>
            </div>
            <div class="schedule-advanced">
              <el-link type="info" :underline="false" @click="editForm.showAdvanced = !editForm.showAdvanced">
                {{ editForm.showAdvanced ? 'Collapse advanced options' : 'Advanced options (CRON expressions)' }}
                <el-icon><ArrowDown v-if="!editForm.showAdvanced" /><ArrowUp v-else /></el-icon>
              </el-link>
            </div>
            <div v-if="editForm.showAdvanced" class="schedule-cron">
              <el-input
                v-model="editForm.cron_expression"
                placeholder="CRON Expressions such as: 0 8 * * 1-5"
                @change="updateUIFromCron"
              >
                <template #prepend>CRON</template>
              </el-input>
              <div class="cron-help">
                Format: minute hour day month week | Example:<code>0 8 * * 1-5</code> = working day 8:00
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="Execution time" v-if="!editForm.supports_cron">
          <el-text type="warning">This task uses interval triggers and does not support modifying the execution time.</el-text>
        </el-form-item>
        <el-form-item label="Trigger name">
          <el-input
            v-model="editForm.display_name"
            placeholder="Please enter a trigger name (optional)"
            clearable
            maxlength="50"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="Remarks">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="4"
            placeholder="Please enter remark information (optional)"
            clearable
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="editDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleSaveMetadata" :loading="saveLoading">save</el-button>
      </template>
    </el-dialog>

    <!-- Task details dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      title="Mission details"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-descriptions v-if="currentJob" :column="1" border>
        <el-descriptions-item label="Task ID">{{ currentJob.id }}</el-descriptions-item>
        <el-descriptions-item label="Task name">{{ currentJob.name }}</el-descriptions-item>
        <el-descriptions-item label="Status">
          <el-tag :type="currentJob.paused ? 'warning' : 'success'">
            {{ currentJob.paused ? 'Suspended' : 'Running' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="trigger">{{ currentJob.trigger }}</el-descriptions-item>
        <el-descriptions-item label="Next execution time">
          {{ currentJob.next_run_time ? formatDateTime(currentJob.next_run_time) : 'Suspended' }}
        </el-descriptions-item>
        <el-descriptions-item label="Execute function" v-if="currentJob.func">
          <el-text size="small" type="info">{{ currentJob.func }}</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="parameters" v-if="currentJob.kwargs">
          <pre class="code-block">{{ JSON.stringify(currentJob.kwargs, null, 2) }}</pre>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button @click="detailDialogVisible = false">close</el-button>
        <el-button type="primary" @click="showJobHistory(currentJob!)">View execution history</el-button>
      </template>
    </el-dialog>

    <!-- Execution History Dialog -->
    <el-dialog
      v-model="historyDialogVisible"
      title="execution history"
      width="1200px"
      :close-on-click-modal="false"
    >
      <el-tabs v-model="activeHistoryTab" @tab-change="handleHistoryTabChange">
        <!-- Manual operation history -->
        <el-tab-pane label="Manual operation history" name="manual">
          <el-table :data="historyList" v-loading="historyLoading" stripe max-height="500">
            <el-table-column prop="job_name" label="Task name" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="Status" width="100">
              <template #default="{ row }">
                <el-tag
                  :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'partial' ? 'warning' : row.status === 'running' ? 'info' : 'warning'"
                  size="small"
                >
                  {{ formatExecutionStatus(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="progress" label="Progress" width="150">
              <template #default="{ row }">
                <div v-if="row.status === 'running' && row.progress !== undefined">
                  <el-progress :percentage="row.progress" :stroke-width="6" />
                  <el-text v-if="row.processed_items && row.total_items" size="small" type="info" style="margin-top: 4px">
                    {{ row.processed_items }}/{{ row.total_items }}
                  </el-text>
                </div>
                <el-text v-else-if="row.progress !== undefined" type="info" size="small">{{ row.progress }}%</el-text>
                <el-text v-else type="info" size="small">-</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="progress_message" label="current operation" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-text v-if="row.progress_message" size="small">
                  {{ row.progress_message }}
                </el-text>
                <el-text v-else-if="row.current_item" size="small">
                  {{ row.current_item }}
                </el-text>
                <el-text v-else type="info" size="small">-</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="timestamp" label="Execution time" width="120">
              <template #default="{ row }">
                <span v-if="row.execution_time !== undefined && row.execution_time !== null">
                  {{ row.execution_time.toFixed(2) }}seconds
                </span>
                <span v-else>
                  {{ calculateExecutionDurationFromTimes(row) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="estimated_time" label="remaining time" width="180">
              <template #default="{ row }">
                {{ calculateEstimatedCompletionTime(row) }}
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="280" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.error_message || row.status === 'running'"
                  link
                  type="primary"
                  size="small"
                  @click="showExecutionDetail(row)"
                >
                  Details
                </el-button>
                <!-- 🔥 Continue button: only displayed for pending tasks -->
                <el-button
                  v-if="row.status === 'suspended'"
                  link
                  type="success"
                  size="small"
                  :loading="actionLoading[`resume_${row.execution_id || row._id}`]"
                  @click="handleResumeSuspendedExecution(row)"
                >
                  Continue execution
                </el-button>
                <!-- 🔥 Retry failed items button: only displayed for historical data synchronization tasks -->
                <el-button
                  v-if="isHistoricalSyncJob(row.job_id) && (row.status === 'failed' || row.status === 'partial' || (row.status === 'success' && row.errors && row.errors.length > 0))"
                  link
                  type="success"
                  size="small"
                  :loading="actionLoading[`retry_${row.execution_id || row._id}`]"
                  @click="handleRetryFailedSymbols(row)"
                >
                  Retry failed items
                </el-button>
                <el-button
                  v-if="row.status === 'running' || row.status === 'suspended'"
                  link
                  type="warning"
                  size="small"
                  @click="handleCancelExecution(row)"
                >
                  terminate
                </el-button>
                <el-button
                  v-if="row.status === 'running' || row.status === 'suspended'"
                  link
                  type="danger"
                  size="small"
                  @click="handleMarkFailed(row)"
                >
                  Marking failed
                </el-button>
                <el-button
                  v-if="row.status !== 'running'"
                  link
                  type="danger"
                  size="small"
                  @click="handleDeleteExecution(row)"
                >
                  Delete
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-if="historyTotal > historyPageSize"
            class="pagination"
            :current-page="historyPage"
            :page-size="historyPageSize"
            :total="historyTotal"
            layout="total, prev, pager, next"
            @current-change="handleHistoryPageChange"
          />
        </el-tab-pane>

        <!-- Automate monitoring -->
        <el-tab-pane label="Automate monitoring" name="execution">
          <!-- Filter criteria -->
          <el-form :inline="true" style="margin-bottom: 16px">
            <el-form-item label="Status">
              <el-select
                v-model="executionStatusFilter"
                placeholder="All status"
                clearable
                style="width: 150px"
                @change="loadExecutions"
              >
                <el-option label="All status" value="" />
                <el-option label="Executing" value="running" />
                <el-option label="success" value="success" />
                <el-option label="failed" value="failed" />
                <el-option label="miss" value="missed" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button :icon="Refresh" @click="loadExecutions">Refresh</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="executionList" v-loading="executionLoading" stripe max-height="500">
            <el-table-column prop="job_name" label="Task name" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="Status" width="100">
              <template #default="{ row }">
                <el-tag
                  :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'partial' ? 'warning' : row.status === 'running' ? 'info' : 'warning'"
                  size="small"
                >
                  {{ formatExecutionStatus(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="progress" label="Progress" width="150">
              <template #default="{ row }">
                <div v-if="row.status === 'running' && row.progress !== undefined">
                  <el-progress :percentage="row.progress" :stroke-width="6" />
                  <el-text v-if="row.processed_items && row.total_items" size="small" type="info" style="margin-top: 4px">
                    {{ row.processed_items }}/{{ row.total_items }}
                  </el-text>
                </div>
                <el-text v-else-if="row.progress !== undefined" type="info" size="small">{{ row.progress }}%</el-text>
                <el-text v-else type="info" size="small">-</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="progress_message" label="current operation" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-text v-if="row.progress_message" size="small">
                  {{ row.progress_message }}
                </el-text>
                <el-text v-else-if="row.current_item" size="small">
                  {{ row.current_item }}
                </el-text>
                <el-text v-else type="info" size="small">-</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="execution_time" label="Execution time" width="120">
              <template #default="{ row }">
                <span v-if="row.execution_time !== undefined && row.execution_time !== null">
                  {{ row.execution_time.toFixed(2) }}seconds
                </span>
                <span v-else>
                  {{ calculateExecutionDurationFromTimes(row) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="scheduled_time" label="Planned start time" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.scheduled_time) }}
              </template>
            </el-table-column>
            <el-table-column prop="estimated_time" label="remaining time" width="180">
              <template #default="{ row }">
                {{ calculateEstimatedCompletionTime(row) }}
              </template>
            </el-table-column>
            <el-table-column label="Operation" width="280" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.error_message || row.status === 'running'"
                  link
                  type="primary"
                  size="small"
                  @click="showExecutionDetail(row)"
                >
                  Details
                </el-button>
                <!-- 🔥 Retry failed items button: only displayed for historical data synchronization tasks -->
                <el-button
                  v-if="isHistoricalSyncJob(row.job_id) && (row.status === 'failed' || row.status === 'partial' || (row.status === 'success' && row.errors && row.errors.length > 0))"
                  link
                  type="success"
                  size="small"
                  :loading="actionLoading[`retry_${row.execution_id || row._id}`]"
                  @click="handleRetryFailedSymbols(row)"
                >
                  Retry failed items
                </el-button>
                <el-button
                  v-if="row.status === 'running' || row.status === 'suspended'"
                  link
                  type="warning"
                  size="small"
                  @click="handleCancelExecution(row)"
                >
                  terminate
                </el-button>
                <el-button
                  v-if="row.status === 'running' || row.status === 'suspended'"
                  link
                  type="danger"
                  size="small"
                  @click="handleMarkFailed(row)"
                >
                  Marking failed
                </el-button>
                <el-button
                  v-if="row.status !== 'running'"
                  link
                  type="danger"
                  size="small"
                  @click="handleDeleteExecution(row)"
                >
                  Delete
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-if="executionTotal > executionPageSize"
            class="pagination"
            :current-page="executionPage"
            :page-size="executionPageSize"
            :total="executionTotal"
            layout="total, prev, pager, next"
            @current-change="handleExecutionPageChange"
          />
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="historyDialogVisible = false">close</el-button>
      </template>
    </el-dialog>

    <!-- Execution details dialog -->
    <el-dialog
      v-model="executionDetailDialogVisible"
      title="Execution details"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-descriptions v-if="currentExecution" :column="1" border>
        <el-descriptions-item label="Task name">
          {{ currentExecution.job_name }}
        </el-descriptions-item>
        <el-descriptions-item label="Task ID">
          {{ currentExecution.job_id }}
        </el-descriptions-item>
        <el-descriptions-item label="Status">
          <el-tag
            :type="currentExecution.status === 'success' ? 'success' : currentExecution.status === 'failed' ? 'danger' : currentExecution.status === 'partial' ? 'warning' : currentExecution.status === 'running' ? 'info' : 'warning'"
          >
            {{ formatExecutionStatus(currentExecution.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Progress" v-if="currentExecution.status === 'running' && currentExecution.progress !== undefined">
          <el-progress :percentage="currentExecution.progress" :stroke-width="8" />
          <div v-if="currentExecution.processed_items && currentExecution.total_items" style="margin-top: 8px">
            <el-text size="small">Processed: {{ currentExecution.processed_items }} / {{ currentExecution.total_items }}</el-text>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="current operation" v-if="currentExecution.progress_message || currentExecution.current_item">
          <el-text>{{ currentExecution.progress_message || currentExecution.current_item }}</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="Planned start time">
          {{ formatDateTime(currentExecution.scheduled_time) }}
        </el-descriptions-item>
        <el-descriptions-item label="Update time">
          {{ formatDateTime(currentExecution.updated_at || currentExecution.timestamp) }}
        </el-descriptions-item>
        <el-descriptions-item label="Execution time">
          {{ calculateExecutionDuration(currentExecution) }}
        </el-descriptions-item>
        <el-descriptions-item label="error message" v-if="currentExecution.error_message">
          <el-text type="danger">{{ currentExecution.error_message }}</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="error stack" v-if="currentExecution.traceback">
          <pre style="max-height: 300px; overflow-y: auto; background: #f5f5f5; padding: 12px; border-radius: 4px;">{{ currentExecution.traceback }}</pre>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button @click="executionDetailDialogVisible = false">close</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { ElMessage, ElMessageBox, type TabPaneName } from 'element-plus'
import {
  Timer,
  List,
  VideoPlay,
  VideoPause,
  Refresh,
  Document,
  Promotion,
  View,
  Edit,
  Search,
  ArrowDown,
  ArrowUp
} from '@element-plus/icons-vue'
import {
  getJobs,
  getJobDetail,
  pauseJob,
  resumeJob,
  triggerJob,
  updateJobMetadata,
  rescheduleJob,
  getSchedulerStats,
  getJobExecutions,
  getSingleJobExecutions,
  cancelExecution,
  markExecutionFailed,
  deleteExecution,
  retryFailedSymbols,
  resumeSuspendedExecution,
  type Job,
  type JobHistory,
  type JobExecution,
  type SchedulerStats
} from '@/api/scheduler'
import { formatDateTime, formatRelativeTime } from '@/utils/datetime'

// data
const loading = ref(false)
const jobs = ref<Job[]>([])
const stats = ref<SchedulerStats | null>(null)
const actionLoading = reactive<Record<string, boolean>>({})

// Search and filter
const searchKeyword = ref('')
const filterDataSource = ref('')
const filterStatus = ref('')

// Edit task metadata
const editDialogVisible = ref(false)
const editingJob = ref<Job | null>(null)
const editForm = reactive({
  display_name: '',
  description: '',
  cron_expression: '',
  original_cron: '',
  supports_cron: false,
  // Friendly time picker
  frequency: 'weekdays' as 'daily' | 'weekdays' | 'weekend' | 'monday' | 'friday',
  time: '08:00',
  showAdvanced: false
})
const saveLoading = ref(false)

// Mission details
const detailDialogVisible = ref(false)
const currentJob = ref<Job | null>(null)

// execution history
const historyDialogVisible = ref(false)
const historyLoading = ref(false)
const historyList = ref<JobHistory[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = ref(20)
const currentHistoryJobId = ref<string | null>(null)
const activeHistoryTab = ref<TabPaneName>('manual')

// Task execution monitoring
const executionLoading = ref(false)
const executionList = ref<JobExecution[]>([])
const executionTotal = ref(0)
const executionPage = ref(1)
const executionPageSize = ref(20)
const executionStatusFilter = ref('')
const executionDetailDialogVisible = ref(false)
const currentExecution = ref<JobExecution | null>(null)

// Computed properties
const filteredJobs = computed(() => {
  let result = [...jobs.value]

  // Search by task name
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(job =>
      job.name.toLowerCase().includes(keyword) ||
      job.id.toLowerCase().includes(keyword) ||
      (job.display_name && job.display_name.toLowerCase().includes(keyword)) ||
      (job.description && job.description.toLowerCase().includes(keyword))
    )
  }

  // Filter by data source
  if (filterDataSource.value) {
    if (filterDataSource.value === 'Others') {
      // Others: Does not include Tushare, AKShare, BaoStock, multiple data sources
      result = result.filter(job =>
        !job.name.includes('Tushare') &&
        !job.name.includes('AKShare') &&
        !job.name.includes('BaoStock') &&
        !job.name.includes('Multiple data sources')
      )
    } else {
      result = result.filter(job => job.name.includes(filterDataSource.value))
    }
  }

  // Filter by status
  if (filterStatus.value) {
    if (filterStatus.value === 'running') {
      result = result.filter(job => !job.paused)
    } else if (filterStatus.value === 'paused') {
      result = result.filter(job => job.paused)
    }
  }

  // Default sorting: running tasks first (paused=false first in line)
  result.sort((a, b) => {
    // Sort by status first (running first)
    if (a.paused !== b.paused) {
      return a.paused ? 1 : -1
    }
    // Sort by name when status is the same
    return a.name.localeCompare(b.name, 'zh-CN')
  })

  return result
})

const isJobRunning = (job: Job): boolean => {
  return Boolean(job.has_running_execution)
}

const getRunningJobHint = (job: Job): string => {
  const runningExecution = job.running_execution
  if (!runningExecution) {
    return 'This task already has unfinished execution instances, please wait for the current task to be completed.'
  }

  const progress = runningExecution.progress ?? 0
  const startedAt = runningExecution.started_at
  const parts = [`The task is being executed`]
  if (progress > 0) {
    parts.push(`Current progress ${progress}%`)
  }
  if (startedAt) {
    parts.push(`Started with ${formatDateTime(startedAt)}`)
  }
  return parts.join('，')
}

const getJobRunningProgress = (job: Job): number | null => {
  if (!job.running_execution) {
    return null
  }

  return job.running_execution.progress ?? 0
}

const getJobRunningStartedAt = (job: Job): string | null => {
  return job.running_execution?.started_at || null
}

// method
const loadJobs = async () => {
  loading.value = true
  try {
    const [jobsRes, statsRes] = await Promise.all([getJobs(), getSchedulerStats()])
    // ApiClient.get Return ApiResponse<T>, The data field is the data we need
    jobs.value = Array.isArray(jobsRes.data) ? jobsRes.data : []
    stats.value = statsRes.data || null
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to load task list')
    jobs.value = []
    stats.value = null
  } finally {
    loading.value = false
  }
}

// Extract CRON expression from trigger string
const extractCronFromTrigger = (trigger: string): string => {
  // Format: cron[month='*', day='*', day_of_week='1-5', hour='9', minute='30']
  if (!trigger || !trigger.includes('cron[')) {
    return ''
  }

  // Extract individual fields
  const monthMatch = trigger.match(/month='([^']*)'/)
  const dayMatch = trigger.match(/day='([^']*)'/)
  const dayOfWeekMatch = trigger.match(/day_of_week='([^']*)'/)
  const hourMatch = trigger.match(/hour='([^']*)'/)
  const minuteMatch = trigger.match(/minute='([^']*)'/)

  if (!minuteMatch || !hourMatch) {
    return ''
  }

  // Building CRON expressions: minutes hours days months weeks
  const minute = minuteMatch[1] || '*'
  const hour = hourMatch[1] || '*'
  const day = dayMatch ? dayMatch[1] : '*'
  const month = monthMatch ? monthMatch[1] : '*'
  const dayOfWeek = dayOfWeekMatch ? dayOfWeekMatch[1] : '*'

  return `${minute} ${hour} ${day} ${month} ${dayOfWeek}`
}

// Parse frequency and time from CRON expression
const parseCronToUI = (cron: string) => {
  const parts = cron.split(' ')
  if (parts.length !== 5) return

  const [minute, hour, , , dayOfWeek] = parts

  // parsing time
  const hourNum = parseInt(hour) || 8
  const minuteNum = parseInt(minute) || 0
  editForm.time = `${hourNum.toString().padStart(2, '0')}:${minuteNum.toString().padStart(2, '0')}`

  // Analyze frequency
  if (dayOfWeek === '*') {
    editForm.frequency = 'daily'
  } else if (dayOfWeek === '1-5') {
    editForm.frequency = 'weekdays'
  } else if (dayOfWeek === '0,6' || dayOfWeek === '6,0') {
    editForm.frequency = 'weekend'
  } else if (dayOfWeek === '1') {
    editForm.frequency = 'monday'
  } else if (dayOfWeek === '5') {
    editForm.frequency = 'friday'
  } else {
    editForm.frequency = 'weekdays' // Default
  }
}

// Generate CRON expression from UI selection
const updateCronFromUI = () => {
  const [hour, minute] = editForm.time.split(':')
  let dayOfWeek = '*'

  switch (editForm.frequency) {
    case 'daily':
      dayOfWeek = '*'
      break
    case 'weekdays':
      dayOfWeek = '1-5'
      break
    case 'weekend':
      dayOfWeek = '0,6'
      break
    case 'monday':
      dayOfWeek = '1'
      break
    case 'friday':
      dayOfWeek = '5'
      break
  }

  editForm.cron_expression = `${parseInt(minute)} ${parseInt(hour)} * * ${dayOfWeek}`
}

// Update UI from CRON expression (when user directly modifies CRON in advanced mode)
const updateUIFromCron = () => {
  parseCronToUI(editForm.cron_expression)
}

// Format schedule description
const formatScheduleDescription = (frequency: string, time: string) => {
  const freqMap: Record<string, string> = {
    daily: 'every day',
    weekdays: 'Working days (Monday to Friday)',
    weekend: 'Weekends (Saturday, Sunday)',
    monday: 'Every Monday',
    friday: 'every friday'
  }
  return `${freqMap[frequency] || frequency} ${time} execute`
}

const showEditDialog = (job: Job) => {
  editingJob.value = job
  editForm.display_name = job.display_name || ''
  editForm.description = job.description || ''
  editForm.showAdvanced = false

  // Determine whether CRON (cron trigger) is supported
  const isCronTrigger = Boolean(job.trigger?.includes('cron['))
  editForm.supports_cron = isCronTrigger

  if (isCronTrigger) {
    const cronExpr = extractCronFromTrigger(job.trigger ?? '')
    editForm.cron_expression = cronExpr
    editForm.original_cron = cronExpr
    // Parse CRON to UI selector
    parseCronToUI(cronExpr)
  } else {
    editForm.cron_expression = ''
    editForm.original_cron = ''
    editForm.frequency = 'weekdays'
    editForm.time = '08:00'
  }

  editDialogVisible.value = true
}

const handleSaveMetadata = async () => {
  if (!editingJob.value) return

  try {
    saveLoading.value = true

    // If the CRON expression is modified, call it first reschedule API
    if (editForm.supports_cron && editForm.cron_expression !== editForm.original_cron) {
      if (!editForm.cron_expression.trim()) {
        ElMessage.error('CRON Expression cannot be empty')
        return
      }
      await rescheduleJob(editingJob.value.id, editForm.cron_expression.trim())
    }

    // Update metadata
    await updateJobMetadata(editingJob.value.id, {
      display_name: editForm.display_name || undefined,
      description: editForm.description || undefined
    })
    ElMessage.success('Mission information has been updated')
    editDialogVisible.value = false
    await loadJobs()
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to update task information')
  } finally {
    saveLoading.value = false
  }
}

const showJobDetail = async (job: Job) => {
  try {
    const res = await getJobDetail(job.id)
    // request.get Already returned response.data
    currentJob.value = res.data || null
    detailDialogVisible.value = true
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to get task details')
  }
}

const handlePause = async (job: Job) => {
  try {
    await ElMessageBox.confirm(`Confirm to pause the task"${job.name}"?`, 'Confirm pause', {
      type: 'warning'
    })

    actionLoading[job.id] = true
    await pauseJob(job.id)
    ElMessage.success('Task is paused')
    await loadJobs()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Failed to suspend task')
    }
  } finally {
    actionLoading[job.id] = false
  }
}

const handleResume = async (job: Job) => {
  try {
    actionLoading[job.id] = true
    await resumeJob(job.id)
    ElMessage.success('Task has been resumed')
    await loadJobs()
  } catch (error: any) {
    ElMessage.error(error.message || 'Recovery task failed')
  } finally {
    actionLoading[job.id] = false
  }
}

const handleTrigger = async (job: Job) => {
  try {
    if (isJobRunning(job)) {
      ElMessage.warning(getRunningJobHint(job))
      return
    }

    await ElMessageBox.confirm(
      `Confirm that you want to perform the task now"${job.name}"? The task will be executed in the background.`,
      'Confirm execution',
      {
        type: 'warning'
      }
    )

    actionLoading[job.id] = true
    
    try {
      await triggerJob(job.id)
      ElMessage.success('Task execution has been triggered')
      await loadJobs()
      
      // 🔥 2 Refresh the task list again after seconds to ensure the status has been updated
      setTimeout(async () => {
        await loadJobs()
      }, 2000)
    } catch (error: any) {
      // 🔥 Handling 409 errors (the task is running and requires user confirmation whether to force execution)
      if (error.response?.status === 409) {
        const errorDetail = error.response?.data?.detail || {}
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
          await triggerJob(job.id, { force: true })
          ElMessage.success('Task has been enforced')
          await loadJobs()
          
          // 🔥 2 Refresh the task list again after seconds to ensure the status has been updated
          setTimeout(async () => {
            await loadJobs()
          }, 2000)
        } catch (confirmError: any) {
          // User cancels or closes the dialog box without performing any action
          if (confirmError !== 'cancel' && confirmError !== 'close') {
            ElMessage.error('Force execution failed: ' + (confirmError.message || 'unknown error'))
          }
        }
      } else {
        // Other errors
        throw error
      }
    }
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.message || 'Failed to trigger task')
    }
  } finally {
    actionLoading[job.id] = false
    await loadJobs()
  }
}

const showJobHistory = async (job: Job) => {
  currentHistoryJobId.value = job.id
  historyPage.value = 1
  detailDialogVisible.value = false
  historyDialogVisible.value = true
  await loadHistory()
}

const showHistoryDialog = async () => {
  currentHistoryJobId.value = null
  historyPage.value = 1
  historyDialogVisible.value = true
  await loadHistory()
}

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const params: any = {
      limit: historyPageSize.value,
      offset: (historyPage.value - 1) * historyPageSize.value,
      is_manual: true  // Only display manually triggered execution records
    }

    if (currentHistoryJobId.value) {
      params.job_id = currentHistoryJobId.value
    }

    const res = currentHistoryJobId.value
      ? await getSingleJobExecutions(currentHistoryJobId.value, params)
      : await getJobExecutions(params)

    // Use execution records directly without format conversion
    const executions = Array.isArray(res.data?.items) ? res.data.items : []
    historyList.value = executions
    historyTotal.value = res.data?.total || 0
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to load execution history')
    historyList.value = []
    historyTotal.value = 0
  } finally {
    historyLoading.value = false
  }
}

const handleHistoryPageChange = (page: number) => {
  historyPage.value = page
  loadHistory()
}

const handleHistoryTabChange = (tabName: TabPaneName) => {
  if (String(tabName) === 'execution') {
    executionPage.value = 1
    loadExecutions()
  } else {
    historyPage.value = 1
    loadHistory()
  }
  // Auto-refresh is enabled for both tabs
  startAutoRefresh()
}

// Auto refresh timer
let autoRefreshTimer: number | null = null

const startAutoRefresh = () => {
  // Clear old timers
  stopAutoRefresh()

  // Refresh every 5 seconds
  autoRefreshTimer = window.setInterval(() => {
    // Refresh the corresponding data according to the current tab page
    if (historyDialogVisible.value) {
      if (activeHistoryTab.value === 'execution') {
        loadExecutions()
      } else {
        loadHistory()
      }
    }
  }, 5000)
}

const stopAutoRefresh = () => {
  if (autoRefreshTimer) {
    window.clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }
}

// The listening dialog box is closed and automatic refresh is stopped.
watch(historyDialogVisible, (newVal) => {
  if (!newVal) {
    stopAutoRefresh()
  }
})

const loadExecutions = async () => {
  executionLoading.value = true
  try {
    const params: any = {
      limit: executionPageSize.value,
      offset: (executionPage.value - 1) * executionPageSize.value,
      is_manual: false  // Only display automatically triggered execution records
    }

    if (currentHistoryJobId.value) {
      params.job_id = currentHistoryJobId.value
    }

    if (executionStatusFilter.value) {
      params.status = executionStatusFilter.value
    }

    const res = currentHistoryJobId.value
      ? await getSingleJobExecutions(currentHistoryJobId.value, params)
      : await getJobExecutions(params)

    executionList.value = Array.isArray(res.data?.items) ? res.data.items : []
    executionTotal.value = res.data?.total || 0
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to load execution history')
    executionList.value = []
    executionTotal.value = 0
  } finally {
    executionLoading.value = false
  }
}

const handleExecutionPageChange = (page: number) => {
  executionPage.value = page
  loadExecutions()
}

const showExecutionDetail = (execution: JobExecution) => {
  currentExecution.value = execution
  executionDetailDialogVisible.value = true
}

const formatExecutionStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    running: 'Executing',
    success: 'success',
    failed: 'failed',
    partial: 'Partially successful',  // 🔥 New: Partial success status
    missed: 'miss',
    suspended: 'hang',
    cancelled: 'Canceled'
  }
  return statusMap[status] || status
}

// Calculate execution time (update time - planned start time)
const calculateExecutionDuration = (execution: JobExecution | null): string => {
  if (!execution) return '-'
  
  // If there is an execution_time field, use it directly
  if (execution.execution_time !== undefined && execution.execution_time !== null) {
    return `${execution.execution_time.toFixed(2)}seconds`
  }
  
  // Otherwise calculate: update time - scheduled start time
  const scheduledTime = execution.scheduled_time
  const updateTime = execution.updated_at || execution.timestamp
  
  if (!scheduledTime || !updateTime) {
    return '-'
  }
  
  try {
    // Process time strings to ensure there is zone information
    let scheduledStr = String(scheduledTime).trim()
    let updateStr = String(updateTime).trim()
    
    // If there is no time zone information, add +08:00 (The backend is stored as UTC+8) 
    if (scheduledStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !scheduledStr.endsWith('Z') && 
        !scheduledStr.includes('+') && 
        !scheduledStr.includes('-', 10)) {
      scheduledStr += '+08:00'
    }
    
    if (updateStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !updateStr.endsWith('Z') && 
        !updateStr.includes('+') && 
        !updateStr.includes('-', 10)) {
      updateStr += '+08:00'
    }
    
    const scheduledDate = new Date(scheduledStr)
    const updateDate = new Date(updateStr)
    
    if (isNaN(scheduledDate.getTime()) || isNaN(updateDate.getTime())) {
      return '-'
    }
    
    // Calculate time difference (seconds)
    const diffSeconds = (updateDate.getTime() - scheduledDate.getTime()) / 1000
    
    if (diffSeconds < 0) {
      return '-'
    }
    
    // Formatted display
    if (diffSeconds < 60) {
      return `${diffSeconds.toFixed(2)}seconds`
    } else if (diffSeconds < 3600) {
      const minutes = Math.floor(diffSeconds / 60)
      const seconds = diffSeconds % 60
      return `${minutes}points${seconds.toFixed(0)}seconds`
    } else {
      const hours = Math.floor(diffSeconds / 3600)
      const minutes = Math.floor((diffSeconds % 3600) / 60)
      const seconds = diffSeconds % 60
      return `${hours}hours${minutes}points${seconds.toFixed(0)}seconds`
    }
  } catch (e) {
    console.error('Failed to calculate execution time:', e)
    return '-'
  }
}

// Calculate execution time (update time - start time)
const calculateExecutionDurationFromTimes = (row: JobExecution): string => {
  try {
    // Start time: timestamp (creation time) is used first, if not, scheduled_time (scheduled start time) is used
    const startTime = row.timestamp || row.scheduled_time
    // End time: Use updated_at (updated time), if not then use the current time (for running tasks)
    const endTime = row.updated_at || (row.status === 'running' ? new Date().toISOString() : null)
    
    if (!startTime || !endTime) {
      return '-'
    }
    
    // Process time strings to ensure there is zone information
    let startStr = String(startTime).trim()
    let endStr = String(endTime).trim()
    
    // If there is no time zone information, add +08:00 (The backend is stored as UTC+8) 
    if (startStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !startStr.endsWith('Z') && 
        !startStr.includes('+') && 
        !startStr.includes('-', 10)) {
      startStr += '+08:00'
    }
    
    if (endStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !endStr.endsWith('Z') && 
        !endStr.includes('+') && 
        !endStr.includes('-', 10)) {
      endStr += '+08:00'
    }
    
    const startDate = new Date(startStr)
    const endDate = new Date(endStr)
    
    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      return '-'
    }
    
    // Calculate time difference (seconds)
    const diffSeconds = (endDate.getTime() - startDate.getTime()) / 1000
    
    if (diffSeconds < 0) {
      return '-'
    }
    
    // Formatted display
    if (diffSeconds < 60) {
      return `${diffSeconds.toFixed(2)}seconds`
    } else if (diffSeconds < 3600) {
      const minutes = Math.floor(diffSeconds / 60)
      const seconds = diffSeconds % 60
      return `${minutes}points${seconds.toFixed(0)}seconds`
    } else {
      const hours = Math.floor(diffSeconds / 3600)
      const minutes = Math.floor((diffSeconds % 3600) / 60)
      const seconds = diffSeconds % 60
      return `${hours}hours${minutes}points${seconds.toFixed(0)}seconds`
    }
  } catch (e) {
    console.error('Failed to calculate execution time:', e)
    return '-'
  }
}

// Calculate estimated completion time or remaining time
const calculateEstimatedCompletionTime = (row: JobExecution): string => {
  try {
    // If the task is completed or failed, the estimated completion time is not displayed
    if (row.status !== 'running') {
      return '-'
    }
    
    // Cannot be calculated without progress information
    if (row.progress === undefined || row.progress === null || row.progress <= 0) {
      return 'Calculating...'
    }
    
    // Calculate elapsed time (seconds)
    const startTime = row.timestamp || row.scheduled_time
    const endTime = row.updated_at || new Date().toISOString()
    
    if (!startTime || !endTime) {
      return 'Calculating...'
    }
    
    // Process time strings to ensure there is zone information
    let startStr = String(startTime).trim()
    let endStr = String(endTime).trim()
    
    // If there is no time zone information, add +08:00 (The backend is stored as UTC+8) 
    if (startStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !startStr.endsWith('Z') && 
        !startStr.includes('+') && 
        !startStr.includes('-', 10)) {
      startStr += '+08:00'
    }
    
    if (endStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && 
        !endStr.endsWith('Z') && 
        !endStr.includes('+') && 
        !endStr.includes('-', 10)) {
      endStr += '+08:00'
    }
    
    const startDate = new Date(startStr)
    const endDate = new Date(endStr)
    
    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      return 'Calculating...'
    }
    
    // Calculate elapsed time (seconds)
    const elapsedSeconds = (endDate.getTime() - startDate.getTime()) / 1000
    
    if (elapsedSeconds <= 0) {
      return 'Calculating...'
    }
    
    // Progress percentage (0-100)
    const progressPercent = row.progress / 100
    
    // If the progress is already 100%, it means it is completed
    if (progressPercent >= 1) {
      return 'Almost done'
    }
    
    // If the progress is 0 or close to 0, it cannot be accurately calculated
    if (progressPercent <= 0) {
      return 'Calculating...'
    }
    
    // Calculate estimated total time: elapsed time / progress percentage
    // For example: 100 seconds have been spent, 50% progress, estimated total time = 100 / 0.5 = 200 seconds
    const estimatedTotalSeconds = elapsedSeconds / progressPercent
    
    // Calculate remaining time: Estimated total time - elapsed time
    const remainingSeconds = estimatedTotalSeconds - elapsedSeconds
    
    if (remainingSeconds <= 0) {
      return 'Almost done'
    }
    
    // Format remaining time display
    if (remainingSeconds < 60) {
      return `Remaining ${remainingSeconds.toFixed(0)}seconds`
    } else if (remainingSeconds < 3600) {
      const minutes = Math.floor(remainingSeconds / 60)
      const seconds = Math.floor(remainingSeconds % 60)
      return `Remaining ${minutes}points${seconds}seconds`
    } else {
      const hours = Math.floor(remainingSeconds / 3600)
      const minutes = Math.floor((remainingSeconds % 3600) / 60)
      return `Remaining ${hours}hours${minutes}points`
    }
  } catch (e) {
    console.error('Calculating estimated completion time failed:', e)
    return 'Calculating...'
  }
}

const formatTrigger = (trigger: string) => {
  // Simplified trigger display
  if (trigger.includes('cron')) {
    return trigger.replace(/cron\[|\]/g, '')
  }
  if (trigger.includes('interval')) {
    return trigger.replace(/interval\[|\]/g, '')
  }
  return trigger
}

const handleSearch = () => {
  // Searching and filtering are automatically enabled via the computed attribute
}

const handleReset = () => {
  searchKeyword.value = ''
  filterDataSource.value = ''
  filterStatus.value = ''
}

// Cancel/terminate task execution
const handleCancelExecution = async (execution: any) => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to terminate this task? The task will stop executing on the next check.',
      'Confirm termination',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    await cancelExecution(execution._id)
    ElMessage.success('Cancellation flag set, task will be stopped on next check')

    // 🔥 Refresh list now
    if (activeHistoryTab.value === 'execution') {
      await loadExecutions()
    } else {
      await loadHistory()
    }
    
    // 🔥 Refresh task list
    await loadJobs()
    
    // 🔥 2 Refresh again after seconds to ensure the status has been updated to terminated
    setTimeout(async () => {
      if (activeHistoryTab.value === 'execution') {
        await loadExecutions()
      } else {
        await loadHistory()
      }
      await loadJobs()
    }, 2000)
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Failed to terminate task')
    }
  }
}

// Mark execution record as failed
const handleMarkFailed = async (execution: any) => {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      'Please enter the reason for failure (optional)',
      'Mark as failed',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        inputPlaceholder: 'For example: the process has been terminated manually',
        inputValue: 'Process has been terminated manually'
      }
    )

    await markExecutionFailed(execution._id, reason || 'User manually marks as failed')
    ElMessage.success('Marked as failed')

    // Refresh list
    if (activeHistoryTab.value === 'execution') {
      await loadExecutions()
    } else {
      await loadHistory()
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Marking failed')
    }
  }
}

// Delete execution record
const handleDeleteExecution = async (execution: any) => {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete this execution record? This operation is irreversible.`,
      'Confirm deletion',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    await deleteExecution(execution._id)
    ElMessage.success('Execution record deleted')

    // Refresh list
    if (activeHistoryTab.value === 'execution') {
      await loadExecutions()
    } else {
      await loadHistory()
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Delete failed')
    }
  }
}

// 🔥 Determine whether it is a historical data synchronization task
const isHistoricalSyncJob = (jobId: string | undefined): boolean => {
  if (!jobId) return false
  return jobId === 'tushare_historical_sync' ||
         jobId === 'akshare_historical_sync' ||
         jobId === 'baostock_historical_sync'
}

// 🔥 Resume suspended task execution
const handleResumeSuspendedExecution = async (row: JobExecution) => {
  const executionId = row.execution_id || row._id
  if (!executionId) {
    ElMessage.error('Execution record ID does not exist')
    return
  }

  try {
    // Confirm action
    await ElMessageBox.confirm(
      'Are you sure you want to continue executing this pending task?\n\n' +
      '• The task will resume execution where it left off\n' +
      `• Current progress: ${row.progress || 0}%\n` +
      (row.processed_items && row.total_items
        ? `• Processed: ${row.processed_items}/${row.total_items}\n`
        : '') +
      '• Once executed, it cannot be undone.',
      'Confirm to continue execution',
      {
        confirmButtonText: 'Continue execution',
        cancelButtonText: 'Cancel',
        type: 'info'
      }
    )

    actionLoading[`resume_${executionId}`] = true

    await resumeSuspendedExecution(executionId)
    ElMessage.success('The task has resumed execution and will continue from the last progress position')

    // Refresh list
    if (activeHistoryTab.value === 'execution') {
      await loadExecutions()
    } else {
      await loadHistory()
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Recovery task failed')
    }
  } finally {
    actionLoading[`resume_${executionId}`] = false
  }
}

// 🔥 Retry failed stocks
const handleRetryFailedSymbols = async (execution: any) => {
  const executionId = execution.execution_id || execution._id
  if (!executionId) {
    ElMessage.error('Execution record ID does not exist')
    return
  }

  try {
    // Confirm action
    await ElMessageBox.confirm(
      'Are you sure you want to retry the failed stock?\n\n' +
      '• Only retry retryable errors (network errors, API timeouts, etc.)\n' +
      '• Skip errors with no data (stock does not exist, date range is unreasonable, etc.)\n' +
      '• Retrying will create a new task execution',
      'Confirm retry failed items',
      {
        confirmButtonText: 'OK',
        cancelButtonText: 'Cancel',
        type: 'info'
      }
    )

    actionLoading[`retry_${executionId}`] = true

    const res = await retryFailedSymbols(executionId)
    
    if (res.success) {
      const data = res.data
      ElMessage.success(
        `Retry completed: Success ${data.success_count}/${data.total_retried} only stocks,` +
        `failed ${data.error_count} only,` +
        `No data ${data.no_data_count} Only (skipped)`
      )
      
      // Refresh list
      if (activeHistoryTab.value === 'execution') {
        await loadExecutions()
      } else {
        await loadHistory()
      }
    } else {
      ElMessage.error(res.message || 'Retry failed')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || 'Retry failed item failed')
    }
  } finally {
    actionLoading[`retry_${executionId}`] = false
  }
}

// life cycle
onMounted(() => {
  loadJobs()
})
</script>

<style scoped lang="scss">
.scheduler-management {
  padding: 20px;

  .header-card {
    margin-bottom: 16px;

    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 20px;

      .title-section {
        h2 {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 0 0 8px 0;
          font-size: 24px;
          font-weight: 600;
        }

        .subtitle {
          margin: 0;
          color: var(--el-text-color-secondary);
          font-size: 14px;
        }
      }

      .stats-section {
        display: flex;
        gap: 40px;
      }
    }

    .actions {
      display: flex;
      gap: 10px;
    }
  }

  .filter-card {
    margin-bottom: 16px;

    .filter-form {
      margin-bottom: 0;

      :deep(.el-form-item) {
        margin-bottom: 0;
      }
    }
  }

  .table-card {
    .job-name {
      display: flex;
      flex-direction: column;
      gap: 6px;

      .job-name-main {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      .name-text {
        font-weight: 500;
      }

      .job-running-summary {
        display: flex;
        gap: 12px;
        font-size: 12px;
        color: var(--el-color-danger);
        margin-left: 2px;
        flex-wrap: wrap;
      }
    }
  }

  .code-block {
    background: var(--el-fill-color-light);
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
    overflow-x: auto;
  }

  .pagination {
    margin-top: 20px;
    display: flex;
    justify-content: center;
  }
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;

  .el-link {
    font-size: 12px;
    vertical-align: baseline;
  }
}

.schedule-picker {
  width: 100%;

  .schedule-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .schedule-sep {
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }

  .schedule-preview {
    margin-top: 12px;

    .el-tag {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
  }

  .schedule-advanced {
    margin-top: 12px;

    .el-link {
      font-size: 12px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
  }

  .schedule-cron {
    margin-top: 8px;
    padding: 12px;
    background: var(--el-fill-color-light);
    border-radius: 4px;

    .cron-help {
      margin-top: 8px;
      font-size: 12px;
      color: var(--el-text-color-secondary);

      code {
        background: var(--el-fill-color);
        padding: 2px 6px;
        border-radius: 3px;
        font-family: 'Courier New', monospace;
      }
    }
  }
}
</style>

