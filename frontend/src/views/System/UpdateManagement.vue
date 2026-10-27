<template>
  <div class="update-management">
    <!-- Page title -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Upload /></el-icon>
        System update
      </h1>
      <p class="page-description">
        Check for and install system updates to keep your system up to date
      </p>
    </div>

    <!-- Current version information -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>📋 Current version information</span>
          <el-button text type="primary" :icon="Refresh" @click="loadVersionInfo" :loading="loadingVersion">
            Refresh
          </el-button>
        </div>
      </template>
      <el-descriptions :column="2" border v-if="versionInfo">
        <el-descriptions-item label="Current version">
          <el-tag type="primary" size="large">v{{ versionInfo.current_version }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Build type">
          {{ versionInfo.build_info?.build_type || 'unknown' }}
        </el-descriptions-item>
        <el-descriptions-item label="update channel">
          <el-tag :type="getChannelTagType(versionInfo.update_channel)">
            {{ formatUpdateChannel(versionInfo.update_channel) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Build time (UTC)">
          {{ formatBuildDateUtc(versionInfo.build_info?.build_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="Git Submit">
          <code>{{ versionInfo.build_info?.git_commit || 'unknown' }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="full version number" :span="2">
          {{ versionInfo.build_info?.full_version || 'unknown' }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="Loading..." />
    </el-card>

    <!-- Check for updates -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>🔍 Check for updates</span>
        </div>
      </template>

      <!-- Docker Deployment: Guided updates using docker pull -->
      <div v-if="versionInfo?.is_docker" class="docker-update-guide">
        <el-button type="primary" @click="doCheckUpdate" :loading="checking" :icon="Search" size="large" style="margin-bottom: 16px">
          Check for updates
        </el-button>
        <el-alert v-if="checkDone && updateInfo?.has_update" type="warning" :closable="false" show-icon style="margin-bottom: 16px">
          <template #title>new version found v{{ updateInfo?.latest_version }}</template>
          <template #default>
            <p>Please update your Docker deployment using:</p>
            <ul style="margin: 8px 0; padding-left: 20px;">
              <li><strong>Pull the latest image:</strong><code>docker pull &lt;Image name&gt;:latest</code></li>
              <li><strong>Using docker-compose:</strong><code>docker-compose pull &amp;&amp; docker-compose up -d</code></li>
            </ul>
          </template>
        </el-alert>
        <el-alert v-else-if="checkDone && updateInfo?.check_failed" type="error" :closable="false" show-icon style="margin-bottom: 16px">
          <template #title>Check for updates failed</template>
          <template #default>{{ updateInfo?.error_message || 'Unable to connect to update server, please check the network or try again later' }}</template>
        </el-alert>
        <el-alert v-else-if="checkDone && !updateInfo?.has_update" title="Currently the latest version" type="success" :closable="false" show-icon style="margin-bottom: 16px" />
        <el-alert type="info" :closable="false" show-icon>
          <template #title>Docker Update instructions</template>
          <template #default>
            <p>Docker This version does not support in-app downloading of update packages. Please use the following methods to obtain the latest version:</p>
            <ul style="margin: 8px 0; padding-left: 20px;">
              <li><strong>Pull the latest image:</strong><code>docker pull &lt;Image name&gt;:latest</code></li>
              <li><strong>Using docker-compose:</strong><code>docker-compose pull &amp;&amp; docker-compose up -d</code></li>
              <li>Or visit the official website to download the latest installation package</li>
            </ul>
          </template>
        </el-alert>
      </div>

      <!-- Windows Portable version/installation version: In-app inspection, download, and installation -->
      <div v-else-if="versionInfo?.supports_in_app_update !== false" class="check-update-section">
        <el-button type="primary" @click="doCheckUpdate" :loading="checking" :icon="Search" size="large">
          Check for updates
        </el-button>

        <!-- The check failed (the server cannot be connected, etc.) -->
        <el-alert v-if="checkDone && updateInfo?.check_failed"
          type="error" :closable="false" show-icon style="margin-top: 16px">
          <template #title>Check for updates failed</template>
          <template #default>{{ updateInfo?.error_message || 'Unable to connect to update server, please check the network or try again later' }}</template>
        </el-alert>
        <!-- No updates -->
        <el-alert v-else-if="checkDone && !updateInfo?.has_update"
          title="Currently the latest version" type="success" :closable="false" show-icon
          style="margin-top: 16px" />

        <!-- There is an update -->
        <div v-if="updateInfo?.has_update" class="update-available">
          <el-alert type="warning" :closable="false" show-icon style="margin-top: 16px">
            <template #title>
              New version found:<strong>v{{ updateInfo.latest_version }}</strong>
              <el-tag v-if="updateInfo.is_mandatory" type="danger" size="small" style="margin-left: 8px">Force update</el-tag>
            </template>
          </el-alert>

          <el-descriptions :column="2" border style="margin-top: 16px">
            <el-descriptions-item label="latest version">v{{ updateInfo.latest_version }}</el-descriptions-item>
            <el-descriptions-item label="package type">
              {{ formatPackageType(updateInfo.package_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="Release date">{{ updateInfo.release_date || 'unknown' }}</el-descriptions-item>
            <el-descriptions-item label="file size">{{ formatFileSize(updateInfo.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="Minimum required version">v{{ updateInfo.min_version || 'None' }}</el-descriptions-item>
          </el-descriptions>

          <!-- Update instructions -->
          <div v-if="updateInfo.release_notes" class="release-notes">
            <h4>📝 Update instructions</h4>
            <div class="release-notes-content" v-html="renderMarkdown(updateInfo.release_notes)"></div>
          </div>

          <!-- Download and install -->
          <div class="update-actions">
            <el-button type="primary" @click="doDownload" :loading="downloading"
              :disabled="isUpdatePackage && progress.status === 'completed'" size="large">
              {{ downloadButtonText }}
            </el-button>
            <el-button type="success" @click="doApply"
              :disabled="!isUpdatePackage || progress.status !== 'completed'" size="large">
              Apply updates and restart
            </el-button>
          </div>

          <el-alert v-if="!isUpdatePackage" type="info" :closable="false" show-icon style="margin-top: 16px">
            <template #title>What is currently returned is the installation package</template>
            <template #default>
              The client does not perform in-app replacement of installation packages. Please download and run the installer manually to complete the upgrade.
            </template>
          </el-alert>

          <!-- Download progress -->
          <div v-if="progress.status !== 'idle'" class="download-progress">
            <el-progress :percentage="progress.percent || 0" :status="progressBarStatus" :stroke-width="20" />
            <p class="progress-text">
              <template v-if="progress.status === 'downloading'">
                Downloading... {{ formatFileSize(progress.downloaded || 0) }} / {{ formatFileSize(progress.total || 0) }}
              </template>
              <template v-else-if="progress.status === 'completed'">
                <el-icon style="color: var(--el-color-success)"><SuccessFilled /></el-icon>
                Download complete, updates can be applied
              </template>
              <template v-else-if="progress.status === 'failed'">
                <el-icon style="color: var(--el-color-danger)"><CircleCloseFilled /></el-icon>
                Download failed, please try again
              </template>
              <template v-else-if="progress.status === 'verify_failed'">
                <el-icon style="color: var(--el-color-danger)"><CircleCloseFilled /></el-icon>
                File verification failed, please download again
              </template>
            </p>
          </div>

          <!-- Update warning -->
          <el-alert v-if="progress.status === 'completed'" type="warning" :closable="false" show-icon
            style="margin-top: 16px">
            <template #title>Application update instructions</template>
            <template #default>
              <ul style="margin: 8px 0; padding-left: 20px;">
                <li>During the update process all services will<strong>Automatically stop and restart</strong></li>
                <li>The system will automatically back up the current version to <code>backup/</code> Directory</li>
                <li>Your data (database, configuration files)<strong>will not be lost</strong></li>
                <li>After the update is complete, please<strong>Refresh browser page</strong></li>
              </ul>
            </template>
          </el-alert>
        </div>
      </div>

      <!-- Unknown build type -->
      <el-alert v-else type="warning" :closable="false" show-icon>
        <template #title>The current deployment method does not currently support in-app updates.</template>
        <template #default>
          Please visit the official website or contact the administrator for updates.
        </template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Refresh, Search, SuccessFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import {
  getVersionInfo,
  checkUpdate,
  getDownloadProgress,
  downloadUpdate,
  applyUpdate,
  type VersionInfo,
  type UpdateInfo,
  type DownloadProgress
} from '@/api/update'
import DOMPurify from 'dompurify'

// ── Status ──────────────────────────────────────────────
const loadingVersion = ref(false)
const checking = ref(false)
const downloading = ref(false)
const checkDone = ref(false)

const versionInfo = ref<VersionInfo | null>(null)
const updateInfo = ref<UpdateInfo | null>(null)
const progress = ref<DownloadProgress>({ status: 'idle' })

let progressTimer: ReturnType<typeof setInterval> | null = null

// ── Computed properties ──────────────────────────────────────────
const progressBarStatus = computed(() => {
  if (progress.value.status === 'completed') return 'success'
  if (progress.value.status === 'failed' || progress.value.status === 'verify_failed') return 'exception'
  return undefined
})

const isUpdatePackage = computed(() => updateInfo.value?.package_type === 'update')

const downloadButtonText = computed(() => {
  if (downloading.value) return 'Downloading...'
  return isUpdatePackage.value ? 'Download update package' : 'Download the installation package'
})

// ── method ──────────────────────────────────────────────
const formatBuildDateUtc = (dateStr: string | undefined) => {
  if (!dateStr) return 'unknown'
  try {
    const date = new Date(dateStr)
    const y = date.getUTCFullYear()
    const m = String(date.getUTCMonth() + 1).padStart(2, '0')
    const d = String(date.getUTCDate()).padStart(2, '0')
    const h = String(date.getUTCHours()).padStart(2, '0')
    const min = String(date.getUTCMinutes()).padStart(2, '0')
    const s = String(date.getUTCSeconds()).padStart(2, '0')
    return `${y}-${m}-${d} ${h}:${min}:${s} UTC`
  } catch {
    return dateStr
  }
}

const formatUpdateChannel = (channel: string | undefined) => {
  if (channel === 'test') return 'test'
  return 'formal'
}

const getChannelTagType = (channel: string | undefined) => {
  if (channel === 'test') return 'warning'
  return 'success'
}

const formatPackageType = (packageType: string | undefined) => {
  if (packageType === 'update') return 'Update package'
  return 'Installation package'
}

const loadVersionInfo = async () => {
  try {
    loadingVersion.value = true
    const res = await getVersionInfo()
    if (res.data) {
      versionInfo.value = res.data
    }
  } catch (e: any) {
    ElMessage.error('Failed to obtain version information: ' + (e.message || 'unknown error'))
  } finally {
    loadingVersion.value = false
  }
}

const doCheckUpdate = async () => {
  try {
    checking.value = true
    checkDone.value = false
    const res = await checkUpdate()
    if (res.data) {
      updateInfo.value = res.data
    }
    checkDone.value = true
  } catch (e: any) {
    ElMessage.error('Check for updates failed: ' + (e.message || 'network error'))
  } finally {
    checking.value = false
  }
}

const doDownload = async () => {
  try {
    if (!updateInfo.value) return
    if (!isUpdatePackage.value) {
      window.open(updateInfo.value.download_url, '_blank', 'noopener,noreferrer')
      ElMessage.success('The installation package download link has been opened')
      return
    }

    downloading.value = true
    progress.value = { status: 'downloading', percent: 0 }
    await downloadUpdate()
    startPollingProgress()
  } catch (e: any) {
    ElMessage.error('Failed to start download: ' + (e.message || 'unknown error'))
    downloading.value = false
  }
}

const startPollingProgress = () => {
  stopPollingProgress()
  progressTimer = setInterval(async () => {
    try {
      const res = await getDownloadProgress()
      if (res.data) {
        progress.value = res.data
        if (res.data.status === 'completed' || res.data.status === 'failed' || res.data.status === 'verify_failed') {
          stopPollingProgress()
          downloading.value = false
          if (res.data.status === 'completed') {
            ElMessage.success('Update package download completed')
          } else {
            ElMessage.error('Download failed, please try again')
          }
        }
      }
    } catch {
      // Silently handle polling errors
    }
  }, 2000)
}

const stopPollingProgress = () => {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

const doApply = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to apply the update? All services will be stopped and restarted automatically, and the system will be temporarily unavailable during the update process.',
      'Confirm update',
      { confirmButtonText: 'Confirm update', cancelButtonText: 'Cancel', type: 'warning' }
    )
  } catch {
    return // User cancels
  }

  try {
    const res = await applyUpdate()
    if (res.data?.success) {
      ElMessage.success('The update has been started and the service will be restarted soon...')
      // Show countdown prompt
      setTimeout(() => {
        ElMessageBox.alert(
          'The update is in progress and the service will restart in 1-2 minutes. Please refresh the page later.',
          'Update in progress',
          { confirmButtonText: 'Got it', type: 'info' }
        )
      }, 1000)
    } else {
      ElMessage.error('Application update failed: ' + (res.data?.error || 'unknown error'))
    }
  } catch (e: any) {
    // If the backend has exited, the connection will be disconnected, this is normal
    if (e.message?.includes('Network Error') || e.code === 'ERR_NETWORK') {
      ElMessage.success('The update has started and the service is restarting...')
      ElMessageBox.alert(
        'The update is in progress and the service will restart in 1-2 minutes. Please refresh the page later.',
        'Update in progress',
        { confirmButtonText: 'Got it', type: 'info' }
      )
    } else {
      ElMessage.error('Application update failed: ' + (e.message || 'unknown error'))
    }
  }
}

// ── Utility function ──────────────────────────────────────────
const formatFileSize = (bytes: number): string => {
  if (!bytes || bytes === 0) return 'unknown'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const renderMarkdown = (text: string): string => {
  if (!text) return ''
  // Simple Markdown rendering: title, list, bold, code
  const rawHtml = text
    .replace(/^### (.+)$/gm, '<h5>$1</h5>')
    .replace(/^## (.+)$/gm, '<h4>$1</h4>')
    .replace(/^# (.+)$/gm, '<h3>$1</h3>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
  // 🔐 Security: Use DOMPurify to sanitize HTML to prevent XSS
  return DOMPurify.sanitize(rawHtml) as string
}

// ── life cycle ──────────────────────────────────────────
onMounted(() => {
  loadVersionInfo()
})

onBeforeUnmount(() => {
  stopPollingProgress()
})
</script>


<style lang="scss" scoped>
.update-management {
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

  .section-card {
    margin-bottom: 24px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    font-size: 16px;
  }

  .check-update-section {
    .update-available {
      margin-top: 16px;
    }

    .update-actions {
      margin-top: 20px;
      display: flex;
      gap: 12px;
    }

    .download-progress {
      margin-top: 16px;

      .progress-text {
        margin-top: 8px;
        color: var(--el-text-color-regular);
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
    }

    .release-notes {
      margin-top: 16px;
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 8px;

      h4 {
        margin: 0 0 12px 0;
        font-size: 15px;
      }

      .release-notes-content {
        font-size: 14px;
        line-height: 1.8;
        color: var(--el-text-color-regular);

        :deep(code) {
          background: var(--el-fill-color);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 13px;
        }

        :deep(li) {
          margin-left: 20px;
          list-style: disc;
        }
      }
    }
  }
}
</style>
