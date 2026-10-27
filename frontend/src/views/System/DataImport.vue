<template>
  <div class="data-import-container">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Upload /></el-icon>
        Data import management
      </h1>
      <p class="page-description">
        Import stock data, social media news and other data into the system in batches through API interface
      </p>
    </div>

    <el-row :gutter="20">
      <!-- Stock data batch import -->
      <el-col :span="12">
        <el-card class="import-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>
                <el-icon><TrendCharts /></el-icon>
                Stock data batch import
              </span>
              <el-tag v-if="!isPro" type="warning" size="small">Senior student</el-tag>
            </div>
          </template>

          <div class="card-content">
            <p class="description">
              Import basic stock information, real-time quotes, financial data, news data and historical K-line data in batches through the API interface
            </p>

            <div class="features">
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Batch import of basic stock information</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Batch import of real-time market data</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Batch import of financial data</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Batch import of news data</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Batch import of historical K-line data</span>
              </div>
            </div>

            <div class="actions">
              <el-button type="primary" @click="goToStockDataApiGuide">
                <el-icon><Document /></el-icon>
                View API documentation
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Batch import of social media messages -->
      <el-col :span="12">
        <el-card class="import-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>
                <el-icon><ChatDotRound /></el-icon>
                Batch import of social media messages
              </span>
              <el-tag v-if="!isPro" type="warning" size="small">Advanced</el-tag>
            </div>
          </template>

          <div class="card-content">
            <p class="description">
              Import social media message data in batches through API interface, supporting multi-platform data sources
            </p>

            <div class="features">
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Supports multi-platform message import</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Automatic sentiment analysis</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>Keyword extraction</span>
              </div>
              <div class="feature-item">
                <el-icon color="#409EFF"><Check /></el-icon>
                <span>importance assessment</span>
              </div>
            </div>

            <div class="actions">
              <el-button type="primary" @click="goToSocialMediaApiGuide">
                <el-icon><Document /></el-icon>
                View API documentation
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Advanced student permission tips -->
    <el-alert
      v-if="!isPro"
      type="warning"
      :closable="false"
      show-icon
      style="margin-top: 20px;"
    >
      <template #title>
        <strong>The batch import function is exclusive for advanced students</strong>
      </template>
      <p>
        You are currently a junior student and cannot use the batch import function.
        <router-link to="/settings/license">Go to authorization management</router-link> Complete Advanced Student Certification.
      </p>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Upload, TrendCharts, ChatDotRound, Document, Check } from '@element-plus/icons-vue'
import { useLicenseStore } from '@/stores/license'

const router = useRouter()
const licenseStore = useLicenseStore()

// Check if you are a PRO user
const isPro = computed(() => licenseStore.isPro)

// Jump to Stock Data API Guide
const goToStockDataApiGuide = () => {
  router.push('/settings/stock-data/api-guide')
}

// Jump to Social Media Messaging API Guide
const goToSocialMediaApiGuide = () => {
  router.push('/settings/social-media/api-guide')
}
</script>

<style scoped lang="scss">
.data-import-container {
  padding: 20px;

  .page-header {
    margin-bottom: 24px;

    .page-title {
      font-size: 24px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .page-description {
      font-size: 14px;
      color: var(--el-text-color-secondary);
      margin: 0;
    }
  }

  .import-card {
    height: 100%;

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 600;
      font-size: 16px;

      span {
        display: flex;
        align-items: center;
        gap: 8px;
      }
    }

    .card-content {
      .description {
        color: var(--el-text-color-regular);
        margin-bottom: 20px;
        line-height: 1.6;
      }

      .features {
        margin-bottom: 24px;

        .feature-item {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          color: var(--el-text-color-regular);

          .el-icon {
            font-size: 16px;
          }
        }
      }

      .actions {
        display: flex;
        gap: 12px;
      }
    }
  }
}
</style>

