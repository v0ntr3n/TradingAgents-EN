<template>
  <div class="single-analysis">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <h1 class="page-title">
            <el-icon class="title-icon"><Document /></el-icon>
            {{ analysisForm.market === 'ETF' ? 'ETF analysis' : 'single stock analysis' }}
          </h1>
          
          <!-- Risk warning -->
          <div class="risk-disclaimer">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
            >
              <template #title>
                <span style="font-size: 14px;">
                  <strong>⚠️ IMPORTANT NOTE:</strong>All analysis conclusions in this analysis are used to learn and verify AI securities analysis technology and are not used as real trading guidance.
                </span>
              </template>
            </el-alert>
          </div>
          
          <p class="page-description">
            AI Driven intelligent securities analysis, multi-dimensional assessment of investment value and risk
          </p>
        </div>
      </div>
    </div>

    <!-- Main analysis form -->
    <div class="analysis-container">
      <el-row :gutter="24">
        <!-- Left: Basic configuration -->
        <el-col :span="18">
          <el-card class="main-form-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <h3>Analysis configuration</h3>
                <el-tag type="info" size="small">Required information</el-tag>
              </div>
            </template>

            <el-form :model="analysisForm" label-width="100px" class="analysis-form">
              <!-- Target information -->
              <div class="form-section">
                <h4 class="section-title">📊 {{ analysisForm.market === 'ETF' ? 'ETF information' : 'stock information' }}</h4>
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item :label="analysisForm.market === 'ETF' ? 'ETF code' : 'Stock code'" required>
                      <el-input
                        v-model="analysisForm.stockCode"
                        placeholder="Such as: 000001,512400(ETF)"
                        clearable
                        size="large"
                        class="stock-input"
                        :class="{ 'is-error': stockCodeError }"
                        @blur="validateStockCodeInput"
                        @input="onStockCodeInput"
                      >
                        <template #prefix>
                          <el-icon><TrendCharts /></el-icon>
                        </template>
                      </el-input>
                      <div v-if="stockCodeError" class="error-message">
                        <el-icon><WarningFilled /></el-icon>
                        {{ stockCodeError }}
                      </div>
                      <div v-else-if="stockCodeHelp" class="help-message">
                        <el-icon><InfoFilled /></el-icon>
                        {{ stockCodeHelp }}
                      </div>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="market type">
                      <el-select
                        v-model="analysisForm.market"
                        placeholder="Choose a market"
                        size="large"
                        style="width: 100%"
                        @change="onMarketChange"
                      >
                        <el-option label="🇨🇳 A stock market" value="A shares">
                          <span>🇨🇳 A stock market</span>
                          <span style="color: #909399; font-size: 12px; margin-left: 8px;"> (6 digits)</span>
                        </el-option>
                        <el-option label="📈 ETF fund" value="ETF">
                          <span>📈 ETF fund</span>
                          <span style="color: #909399; font-size: 12px; margin-left: 8px;"> (510050, 159919 etc.)</span>
                        </el-option>
                      </el-select>
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-form-item label="Analysis date">
                  <div style="display: flex; align-items: center; gap: 8px; width: 100%">
                    <el-date-picker
                      v-model="analysisForm.analysisDate"
                      type="date"
                      placeholder="Select analysis base date"
                      size="large"
                      style="flex: 1"
                      :disabled-date="disabledDate"
                    />
                    <el-button
                      type="primary"
                      size="large"
                      :loading="validatingData"
                      @click="handleValidateData"
                      :disabled="!analysisForm.stockCode.trim()"
                      style="white-space: nowrap"
                    >
                      <el-icon><DocumentChecked /></el-icon>
                      Data inspection
                    </el-button>
                  </div>
                </el-form-item>
              </div>

              <!-- Analysis depth -->
              <div class="form-section">
                <h4 class="section-title">🎯 Analysis depth</h4>
                <div class="depth-selector">
                  <div
                    v-for="(depth, index) in depthOptions"
                    :key="index"
                    class="depth-option"
                    :class="{ active: analysisForm.researchDepth === index + 1 }"
                    @click="analysisForm.researchDepth = index + 1"
                  >
                    <div class="depth-icon">{{ depth.icon }}</div>
                    <div class="depth-info">
                      <div class="depth-name">{{ depth.name }}</div>
                      <div class="depth-desc">{{ depth.description }}</div>
                      <div class="depth-time">{{ depth.time }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Analyst Team -->
              <div class="form-section">
                <h4 class="section-title">👥 Analyst Team</h4>
                <div class="analysts-grid">
                  <div
                    v-for="analyst in availableAnalysts"
                    :key="analyst.id"
                    class="analyst-card"
                    :class="{ 
                      active: analysisForm.selectedAnalysts.includes(analyst.name),
                      disabled: analyst.disabled
                    }"
                    @click="!analyst.disabled && toggleAnalyst(analyst.name)"
                  >
                    <div class="analyst-avatar">
                      <el-icon>
                        <component :is="analyst.icon" />
                      </el-icon>
                    </div>
                    <div class="analyst-content">
                      <div class="analyst-name">
                        {{ analyst.name }}
                        <el-tag v-if="analyst.disabled" size="small" type="info" style="margin-left: 8px;">
                          A shares only
                        </el-tag>
                      </div>
                      <div class="analyst-desc">{{ analyst.description }}</div>
                    </div>
                    <div class="analyst-check">
                      <el-icon v-if="analysisForm.selectedAnalysts.includes(analyst.name)" class="check-icon">
                        <Check />
                      </el-icon>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Action button -->
              <div class="form-section">
                <!-- Execution trajectory switch -->
                <div style="display: flex; justify-content: center; margin-bottom: 12px;">
                  <el-tooltip
                    content="After being turned on, the system will record the complete execution process of each Agent (full text of Prompt, original return from LLM, verification results) for troubleshooting and analysis problems. The amount of data is large, so it is recommended to close it when not needed."
                    placement="top"
                  >
                    <el-checkbox v-model="analysisForm.enableTrace" size="small">
                      <el-icon style="margin-right: 4px;"><View /></el-icon>
                      Record execution trace (enabled when troubleshooting)
                    </el-checkbox>
                  </el-tooltip>
                </div>

                <div class="action-buttons" style="display: flex; justify-content: center; align-items: center; width: 100%; text-align: center;">
                  <el-button
                    v-if="analysisStatus === 'idle'"
                    type="primary"
                    size="large"
                    @click="submitAnalysis"
                    :loading="submitting"
                    :disabled="!analysisForm.stockCode.trim()"
                    class="submit-btn large-analysis-btn"
                    style="width: 280px; height: 56px; font-size: 18px; font-weight: 700; border-radius: 16px;"
                  >
                    <el-icon><TrendCharts /></el-icon>
                    Start smart analysis
                  </el-button>

                  <el-button
                    v-else-if="analysisStatus === 'running'"
                    type="warning"
                    size="large"
                    disabled
                    class="submit-btn large-analysis-btn"
                    style="width: 280px; height: 56px; font-size: 18px; font-weight: 700; border-radius: 16px;"
                  >
                    <el-icon><Loading /></el-icon>
                    Analysis in progress...
                  </el-button>

                  <div v-else-if="analysisStatus === 'completed'" style="display: flex; gap: 12px;">
                    <el-button
                      type="success"
                      size="large"
                      @click="showResults = !showResults"
                      class="submit-btn"
                      style="width: 180px; height: 56px; font-size: 16px; font-weight: 700; border-radius: 16px;"
                    >
                      <el-icon><Document /></el-icon>
                      {{ showResults ? 'Hide results' : 'View results' }}
                    </el-button>

                    <el-button
                      type="primary"
                      size="large"
                      @click="restartAnalysis"
                      class="submit-btn"
                      style="width: 180px; height: 56px; font-size: 16px; font-weight: 700; border-radius: 16px;"
                    >
                      <el-icon><Refresh /></el-icon>
                      Reanalyze
                    </el-button>
                  </div>

                  <el-button
                    v-else-if="analysisStatus === 'failed'"
                    type="danger"
                    size="large"
                    @click="restartAnalysis"
                    class="submit-btn large-analysis-btn"
                    style="width: 280px; height: 56px; font-size: 18px; font-weight: 700; border-radius: 16px;"
                  >
                    <el-icon><Refresh /></el-icon>
                    Reanalyze
                  </el-button>
                </div>
              </div>

              <!-- Analysis progress display -->
              <div v-if="analysisStatus === 'running'" class="progress-section">
                <el-card class="progress-card" shadow="hover">
                  <template #header>
                    <div class="progress-header">
                      <h4>
                        <el-icon class="rotating-icon">
                          <Loading />
                        </el-icon>
                        Analysis in progress...
                      </h4>
                      <el-button
                        type="primary"
                        size="small"
                        @click="startNewAnalysis"
                        style="margin-left: auto;"
                      >
                        <el-icon><Plus /></el-icon>
                        Start a new analysis
                      </el-button>
                      <!-- Task ID is hidden -->
                      <!-- <el-tag type="warning">{{ currentTaskId }}</el-tag> -->
                    </div>
                  </template>

                  <div class="progress-content">
                    <!-- Overall progress information -->
                    <div class="overall-progress-info">
                      <div class="progress-stats">
                        <!-- The current step is hidden -->
                        <!--
                        <div class="stat-item">
                          <div class="stat-label">current step</div>
                          <div class="stat-value">{{ progressInfo.currentStep || 'Initializing...' }}</div>
                        </div>
                        -->
                        <!-- Overall progress has been hidden -->
                        <!--
                        <div class="stat-item">
                          <div class="stat-label">overall progress</div>
                          <div class="stat-value">{{ progressInfo.progress.toFixed(1) }}%</div>
                        </div>
                        -->
                        <div class="stat-item">
                          <div class="stat-label">elapsed time</div>
                          <div class="stat-value">{{ formatTime(progressInfo.elapsedTime) }}</div>
                        </div>
                        <div class="stat-item">
                          <div class="stat-label">Estimated remaining</div>
                          <div class="stat-value">{{ formatTime(progressInfo.remainingTime) }}</div>
                        </div>
                        <div class="stat-item">
                          <div class="stat-label">Estimated total duration</div>
                          <div class="stat-value">{{ formatTime(progressInfo.totalTime) }}</div>
                        </div>
                      </div>
                    </div>

                    <!-- progress bar -->
                    <div class="progress-bar-section">
                      <el-progress
                        :percentage="Math.round(progressInfo.progress)"
                        :stroke-width="12"
                        :show-text="true"
                        :status="getProgressStatus()"
                        class="main-progress-bar"
                      />
                    </div>

                    <!-- Current task details -->
                    <div class="current-task-info">
                      <div class="task-title">
                        <el-icon class="task-icon">
                          <Loading />
                        </el-icon>
                        {{ progressInfo.currentStep || 'Initializing analysis engine...' }}
                      </div>
                      <div
                        class="task-description"
                        style="white-space: pre-wrap; line-height: 1.6;"
                      >
                        {{ progressInfo.currentStepDescription || progressInfo.message || 'AI We are analyzing relevant content based on your request.' }}
                      </div>
                    </div>

                    <!-- Analysis steps shown - hidden -->
                    <!--
                    <div v-if="analysisSteps.length > 0" class="analysis-steps">
                      <h5 class="steps-title">📋 Analysis steps</h5>
                      <div class="steps-container">
                        <div
                          v-for="(step, index) in analysisSteps"
                          :key="index"
                          class="step-item"
                          :class="{
                            'step-completed': step.status === 'completed',
                            'step-current': step.status === 'current',
                            'step-pending': step.status === 'pending'
                          }"
                        >
                          <div class="step-icon">
                            <el-icon v-if="step.status === 'completed'" class="completed-icon">
                              <Check />
                            </el-icon>
                            <el-icon v-else-if="step.status === 'current'" class="current-icon rotating-icon">
                              <Loading />
                            </el-icon>
                            <el-icon v-else class="pending-icon">
                              <Clock />
                            </el-icon>
                          </div>
                          <div class="step-content">
                            <div class="step-title">{{ step.title }}</div>
                            <div class="step-description">{{ step.description }}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                    -->
                  </div>
                </el-card>
              </div>
            </el-form>
          </el-card>
        </el-col>

        <!-- Right: Advanced configuration -->
        <el-col :span="6">
          <el-card class="config-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <h3>Advanced configuration</h3>
                <el-tag type="warning" size="small">Optional settings</el-tag>
              </div>
            </template>

            <div class="config-content">
              <!-- AI Model configuration -->
              <div class="config-section">
                <h4 class="config-title">🤖 AI Model configuration</h4>
                <div class="model-config">
                  <div class="model-item">
                    <div class="model-label">
                      <span>Quickly analyze models</span>
                      <el-tooltip content="Used for market analysis, news analysis, fundamental analysis, etc." placement="top">
                        <el-icon class="help-icon"><InfoFilled /></el-icon>
                      </el-tooltip>
                    </div>
                    <el-select v-model="modelSettings.quickAnalysisModel" size="small" style="width: 100%" filterable>
                      <el-option
                        v-for="model in availableModels"
                        :key="`quick-${model.provider}/${model.model_name}`"
                        :label="model.model_display_name || model.model_name"
                        :value="model.model_name"
                      >
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                          <span style="flex: 1;">{{ model.model_display_name || model.model_name }}</span>
                          <div style="display: flex; align-items: center; gap: 4px;">
                            <!-- Ability Level Badge -->
                            <el-tag
                              v-if="model.capability_level"
                              :type="getCapabilityTagType(model.capability_level)"
                              size="small"
                              effect="plain"
                            >
                              {{ getCapabilityText(model.capability_level) }}
                            </el-tag>
                            <!-- role tag -->
                            <el-tag
                              v-if="isQuickAnalysisRole(model.suitable_roles)"
                              type="success"
                              size="small"
                              effect="plain"
                            >
                              ⚡fast
                            </el-tag>
                            <span style="font-size: 12px; color: #909399;">{{ model.provider }}</span>
                          </div>
                        </div>
                      </el-option>
                    </el-select>
                  </div>

                  <div class="model-item">
                    <div class="model-label">
                      <span>Deep decision-making model</span>
                      <el-tooltip content="Used for comprehensive decision-making by research integrators and final assessment by risk assessors" placement="top">
                        <el-icon class="help-icon"><InfoFilled /></el-icon>
                      </el-tooltip>
                    </div>
                    <DeepModelSelector v-model="modelSettings.deepAnalysisModel" :available-models="availableModels" type="deep" size="small" width="100%" />
                  </div>
                </div>

                <!-- 🆕 Model recommendation tips -->
                <el-alert
                  v-if="modelRecommendation"
                  :title="modelRecommendation.title"
                  :type="modelRecommendation.type"
                  :closable="false"
                  style="margin-top: 12px;"
                >
                  <template #default>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                      <div style="font-size: 13px; line-height: 1.8; flex: 1; white-space: pre-line;">
                        {{ modelRecommendation.message }}
                      </div>
                      <el-button
                        v-if="modelRecommendation.quickModel && modelRecommendation.deepModel"
                        type="primary"
                        size="small"
                        @click="applyRecommendedModels"
                        style="flex-shrink: 0;"
                      >
                        Application recommendations
                      </el-button>
                    </div>
                  </template>
                </el-alert>
              </div>

              <!--  process selector -->
              <div class="config-section" v-if="workflowsSorted.length > 0">
                <h4 class="config-title">📋 Analysis process</h4>
                <el-select
                  :key="`workflow-select-${analysisForm.market}`"
                  v-model="selectedWorkflowId"
                  size="small"
                  style="width: 100%"
                  placeholder="Select analysis process"
                >
                  <el-option
                    v-for="workflow in workflowsSorted"
                    :key="workflow.id"
                    :label="`${workflow.name} v${workflow.version}`"
                    :value="workflow.id"
                  />
                </el-select>
                <el-tooltip content="Select different analysis processes, and the system will use the agents and steps corresponding to the process for analysis." placement="top">
                  <el-icon style="margin-left: 8px; color: #909399; cursor: help;"><InfoFilled /></el-icon>
                </el-tooltip>
              </div>

              <!-- Analysis options - hidden, built-in process -->
              <!--
              <div class="config-section">
                <h4 class="config-title">⚙️ Analysis options</h4>
                <div class="option-list">
                  <div class="option-item">
                    <div class="option-info">
                      <span class="option-name">sentiment analysis</span>
                      <span class="option-desc">Analyze market sentiment and investor psychology</span>
                    </div>
                    <el-switch v-model="analysisForm.includeSentiment" />
                  </div>

                  <div class="option-item">
                    <div class="option-info">
                      <span class="option-name">risk assessment</span>
                      <span class="option-desc">Contains detailed risk factor analysis</span>
                    </div>
                    <el-switch v-model="analysisForm.includeRisk" />
                  </div>

                  <div class="option-item">
                    <div class="option-info">
                      <span class="option-name">Language preference</span>
                    </div>
                    <el-select v-model="analysisForm.language" size="small" style="width: 100px">
                      <el-option label="Chinese" value="zh-CN" />
                      <el-option label="English" value="en-US" />
                    </el-select>
                  </div>
                </div>
              </div>
              -->

            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Analysis results show -->
      <div v-if="showResults && analysisResults" class="results-section">
        <el-row :gutter="24">
          <el-col :span="24">
            <el-card class="results-card" shadow="hover">
              <template #header>
                <div class="results-header">
                  <h3>📊 Analyze results</h3>
                  <div class="result-meta">
                    <el-tag type="success">{{ analysisResults.symbol || analysisResults.stock_symbol || analysisForm.symbol || analysisForm.stockCode }}</el-tag>
                    <el-tag>{{ analysisResults.analysis_date }}</el-tag>
                    <el-tag v-if="analysisResults.model_info && analysisResults.model_info !== 'Unknown'" type="info">
                      <el-icon><Cpu /></el-icon>
                      {{ analysisResults.model_info }}
                    </el-tag>
                  </div>
                </div>
              </template>

              <div class="results-content">
                <!-- Risk warning -->
                <div class="risk-disclaimer">
                  <el-alert
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #title>
                      <div class="disclaimer-content">
                        <el-icon class="disclaimer-icon"><WarningFilled /></el-icon>
                        <div class="disclaimer-text">
                          <p style="margin: 0 0 8px 0;"><strong>⚠️ Important Risk Warnings and Disclaimers</strong></p>
                          <ul style="margin: 0; padding-left: 20px; line-height: 1.8;">
                            <li><strong>Platform nature:</strong>This platform is an AI-assisted analysis technology learning platform, focusing on the application verification and technical learning of AI technology in the fields of securities and ETF analysis.</li>
                            <li><strong>Analysis purpose:</strong>All analysis conclusions are only used to learn and verify AI-assisted analysis technology and are not used as real trading guidance or investment basis.</li>
                            <li><strong>Non-investment advice:</strong>All analysis results, ratings, and recommendations are only for technical verification reference and do not constitute any buying and selling advice or the basis for investment decisions.</li>
                            <li><strong>Data limitations:</strong>The analysis is based on historical data and public information, which may be delayed, incomplete or inaccurate, and cannot predict future market trends.</li>
                            <li><strong>Investment risks:</strong>Both stock and ETF investments are subject to various risks such as market risk, liquidity risk, policy risk, etc., which may result in loss of principal.</li>
                            <li><strong>Independent decision-making:</strong>Investors should make investment decisions independently based on their own risk tolerance, investment objectives and financial status.</li>
                            <li><strong>Responsibility statement:</strong>Any investment decisions and consequences arising from the use of this platform are the sole responsibility of the user, and this platform does not assume any responsibility.</li>
                          </ul>
                        </div>
                      </div>
                    </template>
                  </el-alert>
                </div>

                <!-- Downgrade node warning -->
                <el-alert
                  v-if="analysisResults.degraded_nodes && Object.keys(analysisResults.degraded_nodes).length > 0"
                  type="warning"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 16px"
                >
                  <template #title>Some analysis nodes failed to execute (downgraded)</template>
                  <div style="margin-top: 4px; font-size: 13px; line-height: 1.6">
                    <div v-for="(info, nodeId) in analysisResults.degraded_nodes" :key="nodeId">
                      <strong>{{ info.label || nodeId }}</strong>: {{ info.error ? info.error.substring(0, 120) : 'unknown error' }}
                    </div>
                    <div style="margin-top: 4px; color: #909399">The analysis results of other nodes are not affected.</div>
                  </div>
                </el-alert>

                <!-- Analysis overview -->
                <div v-if="overviewBriefContent" class="overview-section">
                  <h4>📊 Analysis overview</h4>
                  <div class="overview-card">
                    <div class="overview-summary">
                      <div class="markdown-content" v-html="renderMarkdown(overviewBriefContent)"></div>
                    </div>

                    <!-- v2.1.0 The results page uses the research brief as the main entrance and no longer stacks another decision card here. -->
                  </div>
                </div>

                <TaskGrowthPanel
                  v-if="growthTaskId"
                  class="growth-panel-section"
                  :task-id="growthTaskId"
                />

                <!-- Detailed analysis report -->
                <div v-if="analysisResults.state || analysisResults.reports" class="reports-section">
                  <h4>📋 Detailed analysis report</h4>

                  <!-- Beautiful tab display -->
                  <div class="analysis-tabs-container">
                    <el-tabs
                      v-model="activeReportTab"
                      type="card"
                      class="analysis-tabs"
                      tab-position="top"
                      :key="analysisResults?.id || 'default'"
                    >
                      <el-tab-pane
                        v-for="(report, key) in getAnalysisReports(analysisResults)"
                        :key="key"
                        :name="key.toString()"
                        :label="report.title"
                        class="report-tab-pane"
                      >
                        <!-- Tab content header -->
                        <div class="report-header">
                          <div class="report-title">
                            <span class="report-icon">{{ getReportIcon(report.field, report.title) }}</span>
                            <span class="report-name">{{ getReportName(report.title) }}</span>
                          </div>
                          <div class="report-description">{{ getReportDescription(report.field, report.title) }}</div>
                        </div>

                        <!-- Report content -->
                        <div class="report-content-wrapper">
                          <!-- AI Analysis Disclaimer -->
                          <el-alert
                            type="info"
                            :closable="false"
                            show-icon
                            style="margin-bottom: 16px;"
                          >
                            <template #title>
                              <span style="font-size: 13px;">
                                ⚠️ Important note: This report is generated by AI based on limited data analysis and is for reference only and does not constitute investment advice. Investment is risky and decisions need to be made with caution.
                              </span>
                            </template>
                          </el-alert>
                          
                          <div
                            class="report-content"
                            v-html="formatReportContent(report.content)"
                            v-if="report.content"
                          ></div>
                          <div v-else class="no-content">
                            <el-empty description="No content yet" />
                          </div>
                        </div>
                      </el-tab-pane>
                    </el-tabs>
                  </div>
                </div>

                <!-- Action button -->
                <div class="result-actions">
                  <el-dropdown trigger="click" @command="downloadReport">
                    <el-button type="primary">
                      <el-icon><Download /></el-icon>
                      Download report
                      <el-icon class="el-icon--right"><arrow-down /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="markdown">
                          <el-icon><document /></el-icon> Markdown
                        </el-dropdown-item>
                        <el-dropdown-item command="docx">
                          <el-icon><document /></el-icon> Word Documentation
                        </el-dropdown-item>
                        <el-dropdown-item command="pdf">
                          <el-icon><document /></el-icon> PDF
                        </el-dropdown-item>
                        <el-dropdown-item command="json" divided>
                          <el-icon><document /></el-icon> JSON (raw data)
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>

                <!-- Risk warning -->
                <el-alert
                  type="warning"
                  :closable="false"
                  show-icon
                  class="risk-disclaimer"
                >
                  <template #title>
                    <span style="font-weight: bold;">The report is generated using AI analysis based on real transaction data and is for reference only and does not constitute any investment advice. The market is risky and investment needs to be cautious.</span>
                  </template>
                </el-alert>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </div>

    <!-- Data verification results dialog box -->
    <el-dialog
      v-model="showValidationDialog"
      title="Data inspection results"
      width="800px"
      :close-on-click-modal="false"
    >
      <div v-if="validationResult" class="validation-result">
        <!-- overall status -->
        <el-alert
          :type="validationResult.is_valid ? 'success' : 'warning'"
          :closable="false"
          show-icon
          style="margin-bottom: 20px"
        >
          <template #title>
            <strong>{{ validationResult.is_valid ? '✅ Data is normal' : '⚠️ Data is incomplete' }}</strong>
            <span style="margin-left: 10px; font-weight: normal;">{{ validationResult.message }}</span>
          </template>
        </el-alert>

        <!-- Missing data prompt -->
        <el-alert
          v-if="validationResult.missing_data && validationResult.missing_data.length > 0"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 20px"
        >
          <template #title>
            <strong>Missing data:</strong>{{ validationResult.missing_data.join(', ') }}
          </template>
        </el-alert>

        <!-- Detailed data table -->
        <div v-if="validationResult.details" class="validation-details">
          <div
            v-for="(table, index) in formatValidationDetails(validationResult.details)"
            :key="index"
            class="detail-table-section"
            style="margin-bottom: 24px"
          >
            <h4 style="margin-bottom: 12px; color: #409eff; font-size: 16px; font-weight: 600">
              {{ table.title }}
            </h4>
            <el-table
              :data="table.data"
              border
              stripe
              style="width: 100%"
              :show-header="false"
            >
              <el-table-column prop="label" width="180" label="Project">
                <template #default="{ row }">
                  <strong>{{ row.label }}</strong>
                </template>
              </el-table-column>
              <el-table-column prop="value" label="value">
                <template #default="{ row }">
                  <span v-html="row.value"></span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <template #footer>
        <div style="display: flex; align-items: center; gap: 12px; justify-content: space-between;">
          <div v-if="syncStatus !== 'idle'" style="display: flex; align-items: center; gap: 8px;">
            <el-icon v-if="syncStatus === 'running'" class="is-loading" style="animation: rotate 1.5s linear infinite;">
              <Loading />
            </el-icon>
            <el-icon v-else-if="syncStatus === 'success'" style="color: #67c23a;">
              <Check />
            </el-icon>
            <el-icon v-else style="color: #f56c6c;">
              <WarningFilled />
            </el-icon>
            <span>{{ syncStatus === 'running' ? 'Synchronizing...' : syncStatus === 'success' ? 'Synchronization completed' : 'Sync failed' }}</span>
          </div>
          <div style="display: flex; gap: 12px;">
            <el-button type="primary" :disabled="syncStatus === 'running'" @click="handleSyncMissingData">
              <el-icon><Refresh /></el-icon>
              Sync missing data
            </el-button>
            <el-button @click="showValidationDialog = false">close</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  TrendCharts,
  InfoFilled,
  Check,
  Loading,
  Refresh,
  Download,
  WarningFilled,
  Cpu,
  ArrowDown,
  Plus,
  DocumentChecked,
  View,
} from '@element-plus/icons-vue'
import { analysisApi, type SingleAnalysisRequest } from '@/api/analysis'
import { workflowApi, isSelectableAnalysisWorkflow, type WorkflowSummary } from '@/api/workflow'
import { stocksApi, type FundamentalsResponse } from '@/api/stocks'
import { stockSyncApi, type StockSyncTaskStatus, type SingleStockSyncResponse } from '@/api/stockSync'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { ApiClient } from '@/api/request'
import { configApi } from '@/api/config'
import DeepModelSelector from '@/components/DeepModelSelector.vue'
import TaskGrowthPanel from '@/components/growth/TaskGrowthPanel.vue'
import { ANALYSTS, convertAnalystNamesToIds } from '@/constants/analysts'
import { marked } from 'marked'
import { recommendModels } from '@/api/modelCapabilities'
import { validateStockCode, getStockCodeFormatHelp } from '@/utils/stockValidator'
import { normalizeMarketForAnalysis, getMarketByStockCode } from '@/utils/market'
import { fetchTaskResultWithRetry, hasTaskResultContent, mergeTaskResult } from '@/utils/taskResult'
import type { StockInfo } from '@/types/analysis'

// Configure marked options
marked.setOptions({
  breaks: true,        // Supports newline conversion to<br>
  gfm: true           // Enable GitHub style Markdown
})

// Market type definition
type MarketType = 'A shares' | 'ETF'

// Analysis engine type
type AnalysisEngineType = 'legacy' | 'v2'

// Form type definition
interface AnalysisForm {
  stockCode: string
  symbol: string
  market: MarketType
  analysisDate: Date
  researchDepth: number
  selectedAnalysts: string[]
  includeSentiment: boolean
  includeRisk: boolean
  language: 'zh-CN' | 'en-US'
  engine: AnalysisEngineType  // Analysis engine: Fixed using v2.0 engine
  enableTrace: boolean  // Execution trajectory switch: turned off by default, can be turned on when troubleshooting problems
}

// Use store
const router = useRouter()
const route = useRoute()

const submitting = ref(false)
const validatingData = ref(false)
const showValidationDialog = ref(false)
const validationResult = ref<any>(null)
const factorPreviewLoading = ref(false)
const factorPreview = ref<FundamentalsResponse | null>(null)
const syncStatus = ref<'idle' | 'running' | 'success' | 'error'>('idle')
const syncPollingTimer = ref<any>(null)

// Analyze progress and results related status
const currentTaskId = ref('')
const analysisStatus = ref('idle') // 'idle', 'running', 'completed', 'failed'
const showResults = ref(false)
const analysisResults = ref<any>(null)
const analysisReportManifest = ref<Array<{ field: string; display_name: string; icon?: string; description?: string }>>([])
const activeReportTab = ref('') // Currently active reporting tab
const growthTaskId = computed(() => analysisResults.value?.task_id || currentTaskId.value || null)
const progressInfo = ref({
  progress: 0,
  currentStep: '',
  currentStepDescription: '',  // Current step description
  message: '',
  elapsedTime: 0,      // Elapsed time (seconds)
  remainingTime: 0,    // Estimated remaining time (seconds)
  totalTime: 0         // Estimated total duration (seconds)
})
const pollingTimer = ref<any>(null)

const applyAnalysisResult = (result: any) => {
  analysisResults.value = result
  activeReportTab.value = ''
}

const loadCompletedAnalysisResult = async (taskId: string, status?: any) => {
  const statusResult = status?.result_data && typeof status.result_data === 'object' ? status.result_data : null
  const finalResult = await fetchTaskResultWithRetry(taskId, {
    seedData: statusResult,
    isComplete: result => {
      const merged = mergeTaskResult(statusResult, result)
      console.log('📦 Try to get analysis results:', {
        hasContent: hasTaskResultContent(merged),
        hasDecision: !!merged?.decision,
        hasSummary: !!merged?.summary,
        reportCount: Object.keys(merged?.reports || {}).length
      })
      return hasTaskResultContent(merged)
    }
  })

  return mergeTaskResult(statusResult, finalResult)
}

// Analysis step definition (dynamically generated)
const analysisSteps = ref<any[]>([])

// Generate front-end steps from back-end step data
const generateStepsFromBackend = (backendSteps: any[]) => {
  if (!backendSteps || !Array.isArray(backendSteps)) {
    return []
  }

  return backendSteps.map((step: any, index: number) => ({
    key: `step_${index}`,
    title: step.name || `steps ${index + 1}`,
    description: step.description || 'Processing...',
    status: 'pending'
  }))
}

// Model settings
const modelSettings = ref({
  quickAnalysisModel: 'qwen-turbo',
  deepAnalysisModel: 'qwen-max'
})

// List of available models (obtained from configuration)
const availableModels = ref<any[]>([])
const workflows = ref<WorkflowSummary[]>([])
const workflowsSorted = computed(() => {
  // Perform cascade filtering based on market type
  const expectedType = analysisForm.market === 'ETF' ? 'etf_analysis' : 'stock_analysis'
  const arr = workflows.value.filter(
    (w: WorkflowSummary) => isSelectableAnalysisWorkflow(w, expectedType)
  )
  
  // Sort by version number in descending order
  arr.sort((a, b) => {
    const vA = a.version || ''
    const vB = b.version || ''
    const verA = parseVersion(vA)
    const verB = parseVersion(vB)
    
    for (let i = 0; i < Math.max(verA.length, verB.length); i++) {
      const numA = verA[i] || 0
      const numB = verB[i] || 0
      if (numA !== numB) {
        return numB - numA
      }
    }
    return 0
  })
  
  return arr
})

// Parse version number as numeric array
function parseVersion(v: string | number): number[] {
  const str = String(v || '')
  return str.split('.').map(p => parseInt(p.trim(), 10) || 0)
}
const selectedWorkflowId = ref<string>('v2_stock_analysis')

// 🆕 Model recommendation tips
const modelRecommendation = ref<{
  title: string
  message: string
  type: 'success' | 'warning' | 'info' | 'error'
  quickModel?: string
  deepModel?: string
} | null>(null)

// Analysis form
const analysisForm = reactive<AnalysisForm>({
  stockCode: '',  // Reserved for form binding
  symbol: '',     // standardized code
  market: 'A shares',
  analysisDate: new Date(),
  researchDepth: 3, // Level 3 standard analysis is selected by default (recommended) and will be loaded from user preferences in onMounted
  selectedAnalysts: ['market analyst', 'fundamental analyst'], // will be loaded from user preferences in onMounted
  includeSentiment: true,
  includeRisk: true,
  language: 'zh-CN',
  engine: 'v2',  // Fixed using v2.0 engine
  enableTrace: false  // Execution trace: turned off by default, can be turned on when troubleshooting problems
})

// Monitor market type changes and automatically switch to the default process of the corresponding type
watch(
  () => analysisForm.market,
  () => {
    // Use a list filtered (excluding v1.0/quick/blank flows) and sorted by version
    const targetWorkflows = workflowsSorted.value
    
    if (targetWorkflows.length > 0) {
      // Look for is_default first
      const defaultWf = targetWorkflows.find(w => w.is_default)
      if (defaultWf) {
        selectedWorkflowId.value = defaultWf.id
      } else {
        // If not found, select the first one (highest version)
        selectedWorkflowId.value = targetWorkflows[0].id
      }
    }
  }
)

// Stock code verification related
const stockCodeError = ref<string>('')
const stockCodeHelp = ref<string>('')

// Depth options (5 levels, updated based on actual test data)
const depthOptions = [
  { icon: '⚡', name: '1 Level - Quick Analysis', description: 'Basic data overview, quick decision-making', time: '2-5 minutes' },
  { icon: '📈', name: '2 Level - Basic Analysis', description: 'Routine investment decisions', time: '3-6 minutes' },
  { icon: '🎯', name: '3 Level - Standard Analysis', description: 'technology+Fundamentals, recommended', time: '4-8 minutes' },
  { icon: '🔍', name: '4 Level - In-Depth Analysis', description: 'Multiple rounds of debate and in-depth research', time: '6-11 minutes' },
  { icon: '🏆', name: '5 Level - Comprehensive Analysis', description: 'The most comprehensive analysis report', time: '8-16 minutes' }
]

// Ban date
const disabledDate = (time: Date) => {
  return time.getTime() > Date.now()
}

const factorPreviewRow = computed<StockInfo>(() => ({
  symbol: analysisForm.stockCode || '',
  name: analysisForm.stockCode || '',
  market: analysisForm.market,
  report_period: factorPreview.value?.report_period,
  factor_diagnostics: factorPreview.value?.factor_diagnostics || {},
  factor_warnings: factorPreview.value?.factor_warnings || {},
}))

const clearFactorPreview = () => {
  factorPreview.value = null
}

const fetchFactorPreview = async (normalizedCode?: string) => {
  if (analysisForm.market !== 'A shares') {
    clearFactorPreview()
    return
  }

  const targetCode = String(normalizedCode || analysisForm.stockCode || '').trim()
  if (!targetCode) {
    clearFactorPreview()
    return
  }

  factorPreviewLoading.value = true
  try {
    const response = await stocksApi.getFundamentals(targetCode)
    factorPreview.value = ((response as any)?.data || null) as FundamentalsResponse | null
  } catch (error) {
    console.warn('Failed to get factor preview', error)
    clearFactorPreview()
  } finally {
    factorPreviewLoading.value = false
  }
}

// Processing when entering stock code
const onStockCodeInput = () => {
  // Clear error message
  stockCodeError.value = ''
  clearFactorPreview()
  // Show format tips
  stockCodeHelp.value = getStockCodeFormatHelp(analysisForm.market)
}

const ETF_ANALYST_NAMES = ['ETF analyst', 'market analyst', 'news analyst']

const normalizeSelectedAnalystsForMarket = (market: MarketType, analysts: string[]) => {
  if (market === 'ETF') {
    return [...ETF_ANALYST_NAMES]
  }

  const disallowedAnalysts = ['ETF analyst']
  if (market !== 'A shares') {
    disallowedAnalysts.push('Market Analyst', 'Sector Analyst')
  }

  return analysts.filter(name => !disallowedAnalysts.includes(name))
}

// 🔥 Filter available analysts based on market type (large market and sector analysts only support A shares, ETF only displays etf/market/news)
const availableAnalysts = computed(() => {
  const isAStock = analysisForm.market === 'A shares'
  const isETF = analysisForm.market === 'ETF'
  const etfAnalystIds = ['etf', 'market', 'news']

  return ANALYSTS.filter(analyst => {
    if (isETF) return etfAnalystIds.includes(analyst.id)
    if (analyst.id === 'etf') return false
    return true
  }).map(analyst => {
    const isMacroAnalyst = analyst.id === 'index_analyst' || analyst.id === 'sector_analyst'
    return {
      ...analyst,
      disabled: !isAStock && isMacroAnalyst
    }
  })
})

// What to do when the market type changes
const onMarketChange = () => {
  clearFactorPreview()
  // Re-verify ticker
  if (analysisForm.stockCode.trim()) {
    validateStockCodeInput()
  } else {
    // Show format tips for new markets
    stockCodeHelp.value = getStockCodeFormatHelp(analysisForm.market)
  }

  // 🔥 ETF Markets: Fixed Use ETFs / Markets / News Analysts
  if (analysisForm.market === 'ETF') {
    analysisForm.selectedAnalysts = [...ETF_ANALYST_NAMES]
    return
  }

  analysisForm.selectedAnalysts = normalizeSelectedAnalystsForMarket(
    analysisForm.market,
    analysisForm.selectedAnalysts
  )
}

// Validate stock code input
const validateStockCodeInput = () => {
  const code = analysisForm.stockCode.trim()

  if (!code) {
    stockCodeError.value = ''
    stockCodeHelp.value = ''
    return
  }

  // Validate ticker format
  let validation = validateStockCode(code, analysisForm.market)

  if (!validation.valid) {
    // 🔥 Smart reminder: When A-share verification fails but the code complies with the ETF format, the user is prompted to switch markets
    if (analysisForm.market === 'A shares') {
      const etfCheck = validateStockCode(code, 'ETF')
      if (etfCheck.valid) {
        stockCodeError.value = 'The code is ETF fund, please change the market type to ETF Fund '
        stockCodeHelp.value = ''
        return
      }
    }
    stockCodeError.value = validation.message || 'Stock symbol format is incorrect'
    stockCodeHelp.value = ''
  } else {
    stockCodeError.value = ''
    stockCodeHelp.value = `✓ ${validation.market}The code format is correct`

    // Automatically update market types (if the recognized market is different from the current selection)
    // V3.0 Focus on A shares, Hong Kong and US stocks have been suspended
    if (validation.market && validation.market !== analysisForm.market) {
      const validMarkets: MarketType[] = ['A shares', 'ETF']
      if ((validMarkets as string[]).includes(validation.market)) {
        analysisForm.market = validation.market as MarketType
        onMarketChange()  // Simultaneously update analyst selections (e.g. ETF fixed analysts)
        ElMessage.success(`has been automatically recognized as${validation.market}`)
      }
    }

    // standardized code
    if (validation.normalizedCode) {
      analysisForm.stockCode = validation.normalizedCode
    }
  }

  // Get stock information
  fetchStockInfo()
}

// Get stock information (real-time quotes, used to display stock names and current prices)
const fetchStockInfo = async () => {
  const code = analysisForm.stockCode.trim()
  if (!code) return

  try {
    const response = await stocksApi.getQuote(code)
    const data = (response as any)?.data
    if (data) {
      // Update the name in factorPreviewRow (if the quote returns a name)
      if (data.name && factorPreviewRow.value) {
        factorPreviewRow.value.name = data.name
      }
    }
  } catch (error) {
    // Failure to obtain market data does not affect the main process and is handled silently.
    console.warn('Failed to get stock quotes', error)
  }
}

// Switch analyst
const toggleAnalyst = (analystName: string) => {
  const index = analysisForm.selectedAnalysts.indexOf(analystName)
  if (index > -1) {
    analysisForm.selectedAnalysts.splice(index, 1)
  } else {
    analysisForm.selectedAnalysts.push(analystName)
  }
}

// Data verification
const handleValidateData = async () => {
  const stockCode = analysisForm.stockCode.trim()
  if (!stockCode) {
    ElMessage.warning('Please enter the stock code first')
    return
  }

  // Validate ticker format
  let validation = validateStockCode(stockCode, analysisForm.market)
  if (!validation.valid) {
    if (analysisForm.market === 'A shares') {
      const etfCheck = validateStockCode(stockCode, 'ETF')
      if (etfCheck.valid) {
        ElMessage.warning('This code is an ETF fund. Please change the market type to ETF Fund before verifying the data.')
        return
      }
    }
    ElMessage.error(validation.message || 'Stock symbol format is incorrect')
    return
  }

  // Use standardized code
  const normalizedCode = validation.normalizedCode || stockCode.toUpperCase()

  // Determine market type (for API calls)
  const marketTypeMap: Record<string, string> = {
    'A shares': 'cn',
    'ETF': 'cn'  // ETF For A-share exchange-traded funds
  }
  const marketType = marketTypeMap[analysisForm.market] || 'cn'

  // Format analysis date
  const analysisDate = analysisForm.analysisDate instanceof Date
    ? analysisForm.analysisDate.toISOString().split('T')[0]
    : analysisForm.analysisDate

  validatingData.value = true

  try {
    const response = await stocksApi.validateData(
      normalizedCode,
      analysisDate,
      marketType,
      {
        check_basic_info: true,
        check_historical_data: true,
        check_financial_data: true,
        check_realtime_quotes: true
      }
    )

    if (response.data) {
      const result = response.data
      await fetchFactorPreview(normalizedCode)
      
      // Show verification results dialog box
      showValidationResultDialog(result)
    } else {
      ElMessage.error('Data verification failed: no result returned')
    }
  } catch (error: any) {
    console.error('Data verification failed:', error)
    ElMessage.error(`Data verification failed:${error.response?.data?.detail || error.message || 'unknown error'}`)
  } finally {
    validatingData.value = false
  }
}

const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const isTerminalStockSyncStatus = (status?: string): boolean => {
  return status === 'success' || status === 'success_with_errors' || status === 'failed'
}

const buildSingleSyncTaskMessage = (task: StockSyncTaskStatus, symbol: string): string => {
  const result = task.result as SingleStockSyncResponse | null | undefined
  if (!result) {
    return task.error || task.message || `stocks ${symbol} Sync failed`
  }

  const parts = [`stocks ${symbol} Data synchronization completed`]

  if (result.realtime_sync) {
    if (result.realtime_sync.success) {
      const dataSourceUsed = (result.realtime_sync as any).data_source_used
      if (dataSourceUsed) {
        parts.push(`Real-time market synchronization successful (data source ${String(dataSourceUsed).toUpperCase()}) `)
      } else {
        parts.push('Real-time market synchronization successful')
      }
    } else {
      parts.push(`Real-time market synchronization failed: ${result.realtime_sync.error || 'unknown error'}`)
    }
  }

  if (result.historical_sync) {
    parts.push(result.historical_sync.success ? `historical data ${result.historical_sync.records || 0} Article` : `Historical data synchronization failed: ${result.historical_sync.error || 'unknown error'}`)
  }
  if (result.financial_sync) {
    parts.push(result.financial_sync.success ? 'Financial data synchronization successful' : `Financial data synchronization failed: ${result.financial_sync.error || 'unknown error'}`)
  }
  if (result.basic_sync) {
    parts.push(result.basic_sync.success ? 'Basic data synchronization successful' : `Basic data synchronization failed: ${result.basic_sync.error || 'unknown error'}`)
  }

  return parts.join('；')
}

const STOCK_SYNC_POLL_MAX_ATTEMPTS = 60
const STOCK_SYNC_POLL_INTERVAL_MS = 2000

const waitForStockSyncTask = async (taskId: string): Promise<StockSyncTaskStatus> => {
  for (let attempt = 0; attempt < STOCK_SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
    const res = await stockSyncApi.getTaskStatus(taskId)
    if (res.success && isTerminalStockSyncStatus(res.data.status)) {
      return res.data
    }

    await sleep(STOCK_SYNC_POLL_INTERVAL_MS)
  }

  throw new Error('The synchronization task execution timed out, please refresh the page later to view the results.')
}

const monitorSingleSyncTask = async (taskId: string, symbol: string) => {
  try {
    const task = await waitForStockSyncTask(taskId)
    const message = buildSingleSyncTaskMessage(task, symbol)
    if (task.status === 'success') {
      ElMessage.success(message)
    } else if (task.status === 'success_with_errors') {
      ElMessage.warning(message)
    } else {
      ElMessage.error(message)
    }

    // After synchronization is completed, call the data verification again
    await handleValidateData()
  } catch (error: any) {
    if (error?.message !== 'The page has been left, stop waiting for synchronization results') {
      ElMessage.error(error?.message || 'Synchronization result query failed, please refresh the page later to view')
    }
  } finally {
    clearSyncPolling()
  }
}

// Sync missing data
const handleSyncMissingData = async () => {
  const stockCode = analysisForm.stockCode.trim()
  const validation = validateStockCode(stockCode, analysisForm.market)

  if (!validation.valid) {
    ElMessage.error('Incorrect stock symbol')
    return
  }

  const normalizedCode = validation.normalizedCode || stockCode.toUpperCase()
  const missingData = validationResult.value?.missing_data || [] as string[]

  // Determine what to sync based on missing data
  const syncTypes: string[] = []
  if (missingData.includes('Real-time quotes')) syncTypes.push('realtime')
  if (missingData.includes('historical data')) syncTypes.push('historical')
  if (missingData.includes('financial data')) syncTypes.push('financial')
  if (missingData.includes('Basic information')) syncTypes.push('basic')

  // If missing is not explicitly specified, everything will be synchronized by default.
  if (syncTypes.length === 0) {
    syncTypes.push('realtime', 'historical', 'financial', 'basic')
  }

  try {
    syncStatus.value = 'running'
    const res = await stockSyncApi.syncSingle({
      symbol: normalizedCode,
      sync_realtime: syncTypes.includes('realtime'),
      sync_historical: syncTypes.includes('historical'),
      sync_financial: syncTypes.includes('financial'),
      sync_basic: syncTypes.includes('basic'),
      data_source: 'akshare',
      days: 365
    })

    if (res.success) {
      ElMessage.success(`stocks ${normalizedCode} The synchronization task has been submitted and is being executed in the background`)
      void monitorSingleSyncTask(res.data.task_id, normalizedCode)
    } else {
      syncStatus.value = 'error'
      ElMessage.error(res.message || 'Sync failed')
    }
  } catch (error: any) {
    console.error('Sync failed:', error)
    syncStatus.value = 'error'
    ElMessage.error(error.message || 'Synchronization failed, please try again later')
  }
}

// Clean up synchronous polling timer
const clearSyncPolling = () => {
  if (syncPollingTimer.value) {
    clearInterval(syncPollingTimer.value)
    syncPollingTimer.value = null
  }
}

// Show verification results dialog box
const showValidationResultDialog = (result: any) => {
  validationResult.value = result
  showValidationDialog.value = true
  syncStatus.value = 'idle' // Reset sync status
}

// Formatted verification result details are tabular data
const formatValidationDetails = (details: any) => {
  const tables: Array<{ title: string; data: Array<{ label: string; value: any }> }> = []
  
  // Basic information
  if (details.basic_info) {
    const basicInfo = details.basic_info
    tables.push({
      title: 'Basic information',
      data: [
        { label: 'Status', value: basicInfo.exists ? '✅ exist' : '❌ does not exist' },
        { label: analysisForm.market === 'ETF' ? 'ETF Name' : 'Stock name', value: basicInfo.name || '-' },
        { label: 'Listing date', value: basicInfo.list_date || '-' }
      ]
    })
  }
  
  // historical data
  if (details.historical_data) {
    const histData = details.historical_data
    tables.push({
      title: 'historical data',
      data: [
        { label: 'Status', value: histData.exists ? '✅ exist' : '❌ does not exist' },
        { label: 'Number of data items', value: histData.count || 0 },
        { label: 'earliest date', value: histData.earliest_date || '-' },
        { label: 'latest date', value: histData.latest_date || '-' },
        { label: 'Analyze date data', value: histData.analysis_date_exists ? '✅ exist' : '⚠️ does not exist' },
        { label: 'date range', value: histData.date_range || '-' },
        { label: 'warning', value: histData.warning ? '⚠️ Yes' : '✅ No' }
      ]
    })
  }
  
  // financial data
  if (details.financial_data !== undefined) {
    const finData = details.financial_data
    tables.push({
      title: 'financial data',
      data: [
        { label: 'Status', value: finData.exists ? '✅ exist' : '❌ does not exist' },
        { label: 'Latest reporting period', value: finData.latest_report_period || '-' },
        { label: 'report type', value: finData.report_type || '-' }
      ]
    })
  }
  
  // Real-time quotes
  if (details.realtime_quotes !== undefined) {
    const quotesData = details.realtime_quotes
    tables.push({
      title: 'Real-time quotes',
      data: [
        { label: 'Status', value: quotesData.exists ? '✅ exist' : '❌ does not exist' },
        { label: 'current price', value: quotesData.current_price ? `¥${quotesData.current_price}` : '-' },
        { label: 'Update time', value: quotesData.update_time || '-' }
      ]
    })
  }
  
  return tables
}



// Submit analysis
const submitAnalysis = async () => {
  const stockCode = analysisForm.stockCode.trim()
  if (!stockCode) {
    ElMessage.warning('Please enter stock code')
    return
  }

  // Validate ticker format
  let validation = validateStockCode(stockCode, analysisForm.market)
  if (!validation.valid) {
    if (analysisForm.market === 'A shares') {
      const etfCheck = validateStockCode(stockCode, 'ETF')
      if (etfCheck.valid) {
        const msg = 'This code is an ETF fund. Please change the market type to ETF Fund before starting analysis.'
        ElMessage.warning(msg)
        stockCodeError.value = msg
        return
      }
    }
    ElMessage.error(validation.message || 'Stock symbol format is incorrect')
    stockCodeError.value = validation.message || 'Stock symbol format is incorrect'
    return
  }

  // Use standardized code
  analysisForm.symbol = validation.normalizedCode || stockCode.toUpperCase()
  await fetchFactorPreview(analysisForm.symbol)

  if (analysisForm.selectedAnalysts.length === 0) {
    ElMessage.warning('Please select at least one analyst')
    return
  }

  // 🔥 Pre-analysis: Check data source configuration and basic data synchronization status
  try {
    const precheckResp = await analysisApi.precheck(analysisForm.symbol)
    const precheck = precheckResp.data || precheckResp
    if (!precheck.can_submit) {
      // Prevent submission and guide users to complete configuration/synchronization first
      const redirect = precheck.redirect || '/settings/config'
      const reason = precheck.reason || 'unknown'
      const message = precheck.message || 'Please complete system configuration first'

      // Set jump parameters according to reason
      let redirectUrl = redirect
      if (precheck.redirect_tab) {
        redirectUrl = `${redirect}?tab=${precheck.redirect_tab}`
      }

      await ElMessageBox.confirm(
        message,
        'Unable to start analysis',
        {
          confirmButtonText: reason === 'no_datasource' ? 'Go to configure data source' : 'To synchronize data',
          cancelButtonText: 'Cancel',
          type: 'warning',
          showClose: true,
        }
      )
      router.push(redirectUrl)
      return
    }
  } catch (precheckErr: any) {
    // When the user clicks cancel or the preflight is abnormal, the submission will not continue.
    if (precheckErr === 'cancel' || precheckErr?.toString?.().includes('cancel')) {
      return
    }
    // If the pre-check interface itself is abnormal, it will be allowed to be downgraded (the back-end worker also performs full verification)
    console.warn('⚠️ Analyze pre-check exceptions, downgrade and release:', precheckErr)
  }

  submitting.value = true

  try {
    // Make sure analysisDate is a Date object
    const analysisDate = analysisForm.analysisDate instanceof Date
      ? analysisForm.analysisDate
      : new Date(analysisForm.analysisDate)

    const request: SingleAnalysisRequest = {
      symbol: analysisForm.symbol,
      stock_code: analysisForm.symbol,  // Compatible fields
      parameters: {
        market_type: analysisForm.market,
        analysis_date: analysisDate.toISOString().split('T')[0],
        research_depth: getDepthDescription(analysisForm.researchDepth),
        selected_analysts: convertAnalystNamesToIds(analysisForm.selectedAnalysts),
        include_sentiment: analysisForm.includeSentiment,
        include_risk: analysisForm.includeRisk,
        language: analysisForm.language,
        quick_analysis_model: modelSettings.value.quickAnalysisModel,
        deep_analysis_model: modelSettings.value.deepAnalysisModel,
        engine: 'v2',  // 🔥 Fixed use of v2.0 engine (older engine has been hidden)
        workflow_id: selectedWorkflowId.value,
        enable_trace: analysisForm.enableTrace  // Execution trajectory switch
      }
    }

    const response = await analysisApi.startSingleAnalysis(request)

    console.log('🔍 Analyze response data:', response)
    console.log('🔍 response data structure:', response.data)
    console.log('🔍 Task ID:', response.data?.task_id)

    ElMessage.success('The analysis task has been submitted and is being processed...')

    // The response interceptor has returned response.data, so access it directly response.data.task_id
    currentTaskId.value = response.data.task_id

    if (!currentTaskId.value) {
      console.error('❌ Task ID is empty:', response)
      ElMessage.error('Failed to obtain task ID, please try again')
      return
    }

    console.log('✅ Task ID set successfully:', currentTaskId.value)

    // Save task status to cache
    saveTaskToCache(currentTaskId.value, {
      parameters: { ...analysisForm },
      submitTime: new Date().toISOString()
    })

    analysisStatus.value = 'running'
    showResults.value = false
    analysisResults.value = null
    activeReportTab.value = ''
    progressInfo.value = {
      progress: 0,
      currentStep: 'Initializing analysis...',
      currentStepDescription: 'The analysis task has been submitted and the analysis process is being started.',
      message: 'The analysis task has been submitted and the analysis process is being started.',
      elapsedTime: 0,
      remainingTime: 0,
      totalTime: 0
    }

    // Initialize an empty step list and wait for backend data
    analysisSteps.value = []

    // Start polling task status
    startPollingTaskStatus()

    // Query the status once immediately (without waiting for the first poll)
    setTimeout(async () => {
      try {
        const response = await analysisApi.getTaskStatus(currentTaskId.value)
        const status = response.data // Response interceptor returned response.data
        console.log('🔄 Check status now:', status)
        console.log('🔄 current analysisStatus:', analysisStatus.value)
        if (status.status === 'pending' || status.status === 'running') {
          analysisStatus.value = 'running'
          console.log('✅ Set analysisStatus to running')
          updateProgressInfo(status)
        }
      } catch (error) {
        console.error('Immediate query status failed:', error)
      }
    }, 1000) // 1 Query after seconds

  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to submit analysis')
  } finally {
    submitting.value = false
  }
}

// Polling task status
const startPollingTaskStatus = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
  }

  // Check if the task ID is valid
  if (!currentTaskId.value) {
    console.error('❌ The task ID is empty and polling cannot be started.')
    return
  }

  console.log('🔄 Start polling task status:', currentTaskId.value)

  pollingTimer.value = setInterval(async () => {
    try {
      if (!currentTaskId.value) {
        console.error('❌ The task ID in polling is empty')
        if (pollingTimer.value) {
          clearInterval(pollingTimer.value)
        }
        return
      }

      console.log('🔄 Start querying task status:', currentTaskId.value)
      const response = await analysisApi.getTaskStatus(currentTaskId.value)
      const status = response.data // Response interceptor returned response.data

      console.log('🔍 Task status response:', response)
      console.log('🔍 Task status data:', status)
      console.log('🔍 Current status:', status.status, 'Progress:', status.progress)

      if (status.status === 'completed') {
        if (pollingTimer.value) {
          clearInterval(pollingTimer.value)
          pollingTimer.value = null
        }

        // After the analysis is completed, call the dedicated results API to obtain complete data.
        console.log('🎉 Analysis completed, getting full results...')

        try {
          const finalResult = await loadCompletedAnalysisResult(currentTaskId.value, status)
          applyAnalysisResult(finalResult)
          console.log('✅ Obtaining complete analysis results successfully:', finalResult)

          // Add debugging information
          console.log('🔍 Complete result data structure:', {
            hasDecision: !!finalResult?.decision,
            hasState: !!finalResult?.state,
            hasReports: !!finalResult?.reports,
            hasSummary: !!finalResult?.summary,
            hasRecommendation: !!finalResult?.recommendation,
            keys: Object.keys(finalResult || {})
          })
        } catch (error) {
          console.error('❌ Exception in obtaining analysis results:', error)
          applyAnalysisResult(status.result_data || null)
        }

        analysisStatus.value = 'completed'
        showResults.value = true
        progressInfo.value.progress = 100
        progressInfo.value.currentStep = 'Analysis completed'
        progressInfo.value.message = 'Analysis is complete!'

        // Keep the cache after the task is completed so that you can see the results after refreshing
        // clearTaskCache() // Not cleared, allowing users to refresh and view results within 30 minutes

        ElMessage.success('Analysis completed!')

      } else if (status.status === 'failed') {
        // Analysis failed
        analysisStatus.value = 'failed'
        progressInfo.value.currentStep = 'Analysis failed'

        // Format error message (preserve newlines)
        const errorMessage = status.error_message || 'An error occurred during analysis'
        progressInfo.value.message = errorMessage

        if (pollingTimer.value) {
          clearInterval(pollingTimer.value)
          pollingTimer.value = null
        }

        // Clear cache when task fails
        clearTaskCache()

        // Display friendly error prompts (use dangerouslyUseHTMLString to support line breaks)
        ElMessage({
          type: 'error',
          message: errorMessage.replace(/\n/g, '<br>'),
          dangerouslyUseHTMLString: true,
          duration: 10000, // Display for 10 seconds to give users time to read
          showClose: true
        })

      } else if (status.status === 'pending' || status.status === 'running') {
        // Analysis in progress, update progress
        console.log('🔄 Set analysisStatus in polling to running')
        analysisStatus.value = 'running'
        updateProgressInfo(status)
      }

    } catch (error) {
      console.error('Failed to get task status:', error)
      // Continue polling without interruption
    }
  }, 5000) // Poll every 5 seconds
}

// Update progress information
const updateProgressInfo = (status: any) => {
  console.log('🔄 Update progress information:', status)
  console.log('🔄 Current progress information:', progressInfo.value)

  // Use the actual progress data returned by the backend
  if (status.progress !== undefined) {
    console.log('📊 update progress:', status.progress)
    progressInfo.value.progress = status.progress
  }

  if (status.current_step_name) {
    console.log('📋 Update steps:', status.current_step_name)
    progressInfo.value.currentStep = status.current_step_name
  }

  if (status.current_step_description) {
    console.log('📝 Update step description:', status.current_step_description)
    progressInfo.value.currentStepDescription = status.current_step_description
  }

  if (status.message) {
    console.log('💬 Update news:', status.message)
    progressInfo.value.message = status.message
  }

  // Receive time data returned by the backend
  if (status.elapsed_time !== undefined) {
    progressInfo.value.elapsedTime = status.elapsed_time
  }

  if (status.remaining_time !== undefined) {
    progressInfo.value.remainingTime = status.remaining_time
  }

  if (status.estimated_total_time !== undefined) {
    progressInfo.value.totalTime = status.estimated_total_time
  }

  // If the backend provides step data, update the step list
  if (status.steps && Array.isArray(status.steps)) {
    if (analysisSteps.value.length === 0) {
      // Generate step list for the first time
      analysisSteps.value = generateStepsFromBackend(status.steps)
      console.log('📋 Generate a list of steps from the backend:', analysisSteps.value.length, 'steps')
    }
  }

  console.log('🔄 Updated progress information:', progressInfo.value)

  // Update analysis step status
  updateAnalysisSteps(status)

  // The front end does not perform estimation, but only displays the data returned by the back end.
  progressInfo.value.message = status.message || 'Analysis in progress...'
}

// Restart analysis
const restartAnalysis = () => {
  // Clear task cache
  clearTaskCache()

  analysisStatus.value = 'idle'
  showResults.value = false
  analysisResults.value = null
  currentTaskId.value = ''
  progressInfo.value = {
    progress: 0,
    currentStep: '',
    currentStepDescription: '',
    message: '',
    elapsedTime: 0,
    remainingTime: 0,
    totalTime: 0
  }

  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

// Start a new analysis (leave the current analysis running in the background)
const startNewAnalysis = () => {
  // Stop polling for the current task (but do not clear the task ID and allow the background to continue running)
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }

  // Resets the analysis status and results, but does not clear the task ID (so users can view it in the task center)
  analysisStatus.value = 'idle'
  showResults.value = false
  analysisResults.value = null
  
  // Reset progress information
  progressInfo.value = {
    progress: 0,
    currentStep: '',
    currentStepDescription: '',
    message: '',
    elapsedTime: 0,
    remainingTime: 0,
    totalTime: 0
  }

  // Clear the stock code and let the user enter a new stock code
  analysisForm.stockCode = ''
  
  // Scroll to the top so users can enter a new stock symbol
  window.scrollTo({ top: 0, behavior: 'smooth' })
  
  ElMessage.success('You can start analyzing new stocks, while the previous analysis tasks are still in progress in the background.')
}


const analysisModuleMeta: Record<string, { title: string; description: string }> = {
  index_report: { title: '📊 market environment research', description: 'Research on market index trends, market environment and systemic risks' },
  sector_report: { title: '🏭 Industry sector research', description: 'Industry trends, sector rotation and peer comparison research' },
  market_report: { title: '📈 Market Technology Research', description: 'Technical Indicators, Trend Structure and Key Position Research' },
  fundamentals_report: { title: '💰 fundamental research', description: 'Research on financial quality, valuation level and profitability' },
  sentiment_report: { title: '💭 emotion research', description: 'Research on market popularity, investor sentiment and discussion bias' },
  news_report: { title: '📰 Journalism Research', description: 'Announcements, News Events and Catalytic Impact Research' },
  bull_researcher: { title: '🐂 Optimistic Scenario Researcher', description: 'Research and argumentation on revising the space around the conclusion' },
  bull_report: { title: '🐂 Optimistic Scenario Researcher', description: 'Research and argumentation on revising the space around the conclusion' },
  bear_researcher: { title: '🐻 Prudential Scenario Researcher', description: 'Research and argumentation around fragile premises and downward revision risks' },
  bear_report: { title: '🐻 Prudential Scenario Researcher', description: 'Research and argumentation around fragile premises and downward revision risks' },
  research_team_decision: { title: '🔬 Balanced Study Conclusions', description: 'Research conclusions based on a combination of optimistic and cautious materials' },
  investment_plan: { title: '📋 Research Manager Briefing', description: 'Integrated summary of multidimensional analysis for research managers' },
  trader_investment_plan: { title: '🧩 research brief', description: 'Comprehensive research briefing and reading portal for users' },
  risky_analyst: { title: '🔥 Highly resilient scenario perspective', description: 'Conclusion: Improved Conditions and Enhanced Catalysis Research' },
  risky_opinion: { title: '🔥 Highly resilient scenario perspective', description: 'Conclusion: Improved Conditions and Enhanced Catalysis Research' },
  safe_analyst: { title: '🛡️ defensive situational view', description: 'Research on fragile premises, key risks and downward revision conditions' },
  safe_opinion: { title: '🛡️ defensive situational view', description: 'Research on fragile premises, key risks and downward revision conditions' },
  neutral_analyst: { title: '⚖️ base case view', description: 'Research on baseline scenarios, evidence quality and information gaps' },
  neutral_opinion: { title: '⚖️ base case view', description: 'Research on baseline scenarios, evidence quality and information gaps' },
  risk_management_decision: { title: '⚠️ Risk review conclusion', description: 'Final robustness conclusion after comprehensive scenario review' },
  risk_assessment: { title: '⚠️ Risk review conclusion', description: 'Final robustness conclusion after comprehensive scenario review' },
  final_trade_decision: { title: '📝 Comprehensive research conclusion', description: 'Integrating research conclusions and risk review overview conclusions' },
}

const getResearchContentFingerprint = (moduleData: any) => {
  const prepared = prepareMarkdownContent(getModuleContent(moduleData) || '')
  if (!prepared) {
    return ''
  }

  return prepared
    .replace(/```[\s\S]*?```/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+[.)]\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\[(.*?)\]\([^)]*\)/g, '$1')
    .replace(/[>_*|~]/g, ' ')
    .replace(/[\s\u3000]+/g, '')
}

const shouldHideDuplicateResearchManagerBrief = (moduleKey: string, reportsData: any) => {
  if (moduleKey !== 'investment_plan') {
    return false
  }

  const researchDecision = getResearchContentFingerprint(reportsData?.research_team_decision)
  const managerBrief = getResearchContentFingerprint(reportsData?.investment_plan)

  return !!researchDecision && researchDecision === managerBrief
}

const extractReportsSource = (data: any): Record<string, any> | null => {
  if (data?.reports && typeof data.reports === 'object' && Object.keys(data.reports).length > 0) {
    return data.reports
  }

  if (data?.state && typeof data.state === 'object' && Object.keys(data.state).length > 0) {
    return data.state
  }

  return null
}

const normalizeDisplayedResearchText = (content: string) => {
  if (!content) return ''

  const replacements: Array<[RegExp, string]> = [
    [/Transaction Analysis Plan/g, 'research brief'],
    [/trader plan/g, 'research brief'],
    [/Initial investment plan/g, 'Balanced Study Conclusions'],
    [/investment plan/g, 'Research conclusion'],
    [/investment advice/g, 'Research conclusion'],
    [/Operation suggestions/g, 'research perspective'],
    [/Market index analysis/g, 'market environment research'],
    [/Industry sector analysis/g, 'Industry sector research'],
    [/Market Sentiment Analysis/g, 'emotion research'],
    [/News event analysis/g, 'Journalism Research'],
    [/risk management decisions/g, 'Risk review conclusion'],
    [/Risk review summary/g, 'Risk review conclusion'],
    [/Comprehensive Research Brief/g, 'Comprehensive research conclusion'],
    [/Final analysis results/g, 'Comprehensive research conclusion'],
    [/activist risk analyst/g, 'Highly Resilient Scenario Analyst'],
    [/conservative risk analyst/g, 'Defense Scenario Analyst'],
    [/Neutral Risk Analyst/g, 'Baseline Scenario Analyst'],
  ]

  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), content)
}

/**
 * Render a risk review JSON object to readable Markdown text.
 * Fields are consistent with the backend risk_assessment / risk_management_decision structures.
 */
const formatRiskAssessment = (value: any): string | null => {
  if (!value || typeof value !== 'object') return null
  const riskLevel = value.risk_level || value.riskLevel
  const riskScore = value.risk_score ?? value.riskScore
  const reasoning = value.reasoning || value.conclusion || value.summary || value.assessment
  const keyRisks = value.key_risks || value.keyRisks || value.risks
  const riskControl = value.risk_control || value.riskControl || value.control || value.suggestions
  const investmentAdjustment = value.investment_adjustment || value.investmentAdjustment || value.adjustment

  if (riskLevel === undefined && riskScore === undefined && !reasoning && !riskControl && !investmentAdjustment) {
    return null
  }

  const parts: string[] = []
  if (riskLevel !== undefined) {
    parts.push(`**risk level**: ${riskLevel}`)
  }
  if (riskScore !== undefined) {
    const score = typeof riskScore === 'number' ? riskScore.toFixed(2) : riskScore
    parts.push(`**risk score**: ${score}`)
  }
  if (reasoning) {
    parts.push(`**Assessment conclusion**: ${reasoning}`)
  }
  if (Array.isArray(keyRisks) && keyRisks.length > 0) {
    parts.push(`**core risk**: `)
    keyRisks.forEach((risk: any) => {
      if (risk) parts.push(`- ${String(risk).trim()}`)
    })
  }
  if (riskControl) {
    parts.push(`**Risk control suggestions**: ${riskControl}`)
  }
  if (investmentAdjustment) {
    parts.push(`**Investment adjustment suggestions**: ${investmentAdjustment}`)
  }

  return parts.join('\n\n')
}

const _stripJsonCodeFence = (text: string): string => {
  // remove ```json ... ``` or ``` ... ``` code block wrapper
  let t = text.trim()
  const fenceMatch = t.match(/^```(?:json|JSON)?\s*\n([\s\S]*?)\n```\s*$/i)
  if (fenceMatch) {
    t = fenceMatch[1].trim()
  }
  return t
}

const _looksLikeRiskJson = (text: string): boolean => {
  const lowered = text.toLowerCase()
  return (
    text.startsWith('{') &&
    (lowered.includes('"risk_level"') ||
      lowered.includes('"risk_score"') ||
      lowered.includes('"reasoning"') ||
      lowered.includes('"key_risks"') ||
      lowered.includes('"risk_control"') ||
      lowered.includes('"investment_adjustment"'))
  )
}

const extractStructuredText = (value: any): string | null => {
  if (!value) return null

  if (typeof value === 'string') {
    // Peel first ```json code block, and then determine whether it is a risk review JSON
    const stripped = _stripJsonCodeFence(value.trim())
    if (!stripped) return null

    if (_looksLikeRiskJson(stripped)) {
      try {
        const parsed = JSON.parse(stripped)
        const riskText = formatRiskAssessment(parsed)
        if (riskText) return riskText
      } catch {
        // Not valid JSON, return as normal text
      }
    }
    // If the original text is ```json Code block but not risky JSON, returns stripped content
    return stripped !== value.trim() ? stripped : value.trim()
  }

  if (typeof value === 'object') {
    // Risk review structured objects are rendered directly as readable text
    const riskText = formatRiskAssessment(value)
    if (riskText) return riskText

    // When content/text fields are nested in objects, recursive attempts are made to parse them.
    // real data structure: { content: "```json\n{...}\n```", success: true }
    for (const key of ['content', 'markdown', 'text', 'message', 'report', 'judge_decision', 'risk_assessment', 'risk_management_decision']) {
      const item = value[key]
      if (item) {
        const nested = extractStructuredText(item)
        if (nested) return nested
      }
    }
  }

  return null
}

const prepareMarkdownContent = (content: string) => {
  let preparedText = normalizeDisplayedResearchText(content || '').trim()

  if (
    ((preparedText.startsWith('"') && preparedText.endsWith('"')) ||
      (preparedText.startsWith("'") && preparedText.endsWith("'"))) &&
    preparedText.length >= 2
  ) {
    preparedText = preparedText.slice(1, -1).trim()
  }

  const fencedMarkdownMatch = preparedText.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i)
  if (fencedMarkdownMatch) {
    preparedText = fencedMarkdownMatch[1].trim()
  }

  return preparedText
}

const renderMarkdown = (content: string) => {
  if (!content) return ''

  try {
    return marked.parse(prepareMarkdownContent(content)) as string
  } catch {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${prepareMarkdownContent(content)}</pre>`
  }
}

const getModuleContent = (moduleData: any): string | null => {
  const extractedText = extractStructuredText(moduleData)
  if (extractedText) {
    return normalizeDisplayedResearchText(extractedText)
  }

  if (moduleData && typeof moduleData !== 'string') {
    return null
  }

  return typeof moduleData === 'string' ? normalizeDisplayedResearchText(moduleData) : null
}

const getOverviewBriefContent = (data: any): string | null => {
  const reportsData = extractReportsSource(data)
  const traderBrief = getModuleContent(reportsData?.trader_investment_plan)
  if (traderBrief) {
    return traderBrief
  }

  return getModuleContent(data?.summary) || getModuleContent(data?.recommendation)
}

const overviewBriefContent = computed(() => getOverviewBriefContent(analysisResults.value))

// Get analysis report
const getAnalysisReports = (data: any) => {
  const reports: Array<{field: string, title: string, content: any}> = []

  const reportsData = extractReportsSource(data)
  if (!reportsData) {
    return reports
  }

  const isEtfAnalysis = data?.task_type === 'etf_analysis' || (Array.isArray(data?.analysts) && data.analysts.includes('etf_analyst'))
  const addedKeys = new Set<string>()

  const pushReport = (key: string, title: string, content: any) => {
    if (!content || addedKeys.has(key)) {
      return
    }
    addedKeys.add(key)
    reports.push({ field: key, title, content })
  }

  // Dynamic mode: use report_manifest (custom workflow output description)
  const manifest = data?.report_manifest as Array<{
    field: string; display_name: string; icon?: string; description?: string; category: string; order: number; is_primary: boolean
  }> | undefined
  analysisReportManifest.value = manifest || []
  if (reportsData && manifest && manifest.length > 0) {
    const sorted = [...manifest].sort((a, b) => a.order - b.order)
    for (const m of sorted) {
      const content = reportsData[m.field]
      if (content) {
        pushReport(m.field, m.display_name || m.field.replace(/_/g, ' '), content)
      }
    }
  }

  // --- Old logic: Built-in workflows use hard-coded mappings ---
  const reportMappings = [
    { key: 'index_report', title: '📊 market environment research' },
    { key: 'sector_report', title: '🏭 Industry sector research' },
    { key: 'market_report', title: '📈 Market Technology Research' },
    { key: 'fundamentals_report', title: isEtfAnalysis ? '📊 ETF analysis' : '💰 fundamental research' },
    { key: 'sentiment_report', title: '💭 emotion research' },
    { key: 'news_report', title: '📰 Journalism Research' },
    { key: 'chip_report', title: '🧮 Chip distribution research' },
    // Workshop Agent added
    { key: 'valuation_report', title: '📊 Multi-dimensional valuation analysis' },
    // Research team (remove duplicates: give priority to those with suffixes)
    { key: 'bull_report', title: '🐂 Optimistic Scenario Researcher' },
    { key: 'bear_report', title: '🐻 Prudential Scenario Researcher' },
    { key: 'research_team_decision', title: '🔬 Balanced Study Conclusions' },
    { key: 'investment_plan', title: '📋 Research Manager Briefing' },
    { key: 'trader_investment_plan', title: '🧩 research brief' },
    // Risk team (remove duplicates: use those with suffixes first)
    { key: 'risky_opinion', title: '🔥 Highly resilient scenario perspective' },
    { key: 'safe_opinion', title: '🛡️ defensive situational view' },
    { key: 'neutral_opinion', title: '⚖️ base case view' },
    { key: 'risk_assessment', title: '⚠️ Risk review conclusion' },
    { key: 'final_trade_decision', title: '📝 Comprehensive research conclusion' },
  ]

  reportMappings.forEach(mapping => {
    if (addedKeys.has(mapping.key)) return
    if (shouldHideDuplicateResearchManagerBrief(mapping.key, reportsData)) {
      addedKeys.add(mapping.key)  // Mark as processed to avoid repeated additions
      return
    }
    const content = reportsData?.[mapping.key]
    if (content) {
      pushReport(mapping.key, mapping.title, content)
    }
  })

  Object.keys(reportsData).forEach(key => {
    if (key === 'structured_reports' || addedKeys.has(key)) {
      return
    }

    // Skip duplicate keys (avoid duplicates with researcher/analyst suffix)
    const skipPatterns = [
      // Research Team: Skip the _researcher suffix (use _report first)
      /^bull_researcher$/,
      /^bear_researcher$/,
      // Risk Team: Skip the _analyst suffix (prefer _opinion)
      /^risky_analyst$/,
      /^safe_analyst$/,
      /^neutral_analyst$/,
      /^risk_management_decision$/, // Skip this (use risk_assessment first)
    ]
    if (skipPatterns.some(p => p.test(key))) {
      addedKeys.add(key)
      return
    }

    const content = reportsData[key]
    if (content) {
      pushReport(key, key.replace(/_/g, ' '), content)
    }
  })

  console.log(`📊 Total found ${reports.length} reports`)

  // Set the first report as the default active tab
  if (reports.length > 0 && !activeReportTab.value) {
    activeReportTab.value = '0'
  }

  return reports
}

// Get report icon
const getReportIcon = (field: string, title: string) => {
  // 1. Get it from manifest first icon
  const manifestEntry = analysisReportManifest.value.find((m) => m.field === field)
  if (manifestEntry?.icon) {
    return manifestEntry.icon
  }
  // 2. Fallback to hardcoding iconMap
  const iconMap: Record<string, string> = {
    // 🆕 Macro analyst icon
    '📊 Market index analysis': '📊',
    '🏭 Industry sector analysis': '🏭',
    // Analyst team icon
    '📈 Market technical analysis': '📈',
    '💰 fundamental analysis': '💰',
    '📊 ETF analysis': '📊',
    '📰 News event analysis': '📰',
    '💭 Market Sentiment Analysis': '💭',
    '💡 Preliminary research observations': '💡',
    '🔬 Research team analysis': '🔬',
    '🐂 positive evidence research': '🐂',
    '🐻 careful evidence research': '🐻',
    '💼 research brief': '💼',
    '⚖️ risk management team': '⚖️',
    '🔥 Highly elastic scenario research observations': '🔥',
    '🛡️ Defense Scenario Research Observations': '🛡️',
    '⚖️ Baseline Scenario Research Observations': '⚖️',
    '⚠️ risk assessment': '⚠️',
    '🎯 Final analysis results': '🎯'
  }
  return iconMap[title] || '📊'
}

// Get the report name (remove the icon prefix)
const getReportName = (title: string) => {
  return title.replace(/^[^\s]+\s/, '')
}

// Get report description
const getReportDescription = (field: string, title: string) => {
  // 1. Get it from manifest first description
  const manifestEntry = analysisReportManifest.value.find((m) => m.field === field)
  if (manifestEntry?.description) {
    return manifestEntry.description
  }
  // 2. Fallback to hardcoding analysisModuleMeta
  const plainTitle = title.replace(/^[^\s]+\s/, '')
  return Object.values(analysisModuleMeta).find(meta => meta.title === title)?.description
    || Object.values(analysisModuleMeta).find(meta => meta.title.endsWith(plainTitle))?.description
    || 'Detailed research report'
}

// Format report content
const formatReportContent = (content: any) => {
  const normalizedContent = getModuleContent(content)
  return normalizedContent ? renderMarkdown(normalizedContent) : ''
}

// Download report
const downloadReport = async (format: string = 'markdown') => {
  try {
    if (!analysisResults.value && !currentTaskId.value) {
      ElMessage.error('The report has not been generated and cannot be downloaded')
      return
    }

    // Show loading prompt
    const loadingMsg = ElMessage({
      message: `Generating${getFormatName(format)}Format report...`,
      type: 'info',
      duration: 0
    })

    const reportId = (analysisResults.value?.id as any) || currentTaskId.value
    const res: any = await ApiClient.get(`/api/reports/${reportId}/download`, { format }, { responseType: 'blob' })

    loadingMsg.close()

    // The response interceptor directly returns Blob (response.data); compatible return { data: Blob } old implementation of
    const blob = res instanceof Blob ? res : (res?.data instanceof Blob ? res.data : new Blob([res]))
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const code =
      analysisResults.value?.stock_code ||
      analysisResults.value?.stock_symbol ||
      analysisResults.value?.symbol ||
      'stock'
    const dateStr = analysisResults.value?.analysis_date || new Date().toISOString().slice(0, 10)

    // Set file extension based on format
    const ext = getFileExtension(format)
    a.download = `${String(code)}_analysis report_${String(dateStr).slice(0, 10)}.${ext}`

    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    ElMessage.success(`${getFormatName(format)}Report download successful`)
  } catch (err: any) {
    console.error('Error downloading report:', err)

    // Show detailed error information
    if (err.message && err.message.includes('pandoc')) {
      ElMessage.error({
        message: 'Word Exporting requires the pandoc tool to be installed (PDF export does not require pandoc)',
        duration: 5000
      })
    } else if (err.message && (err.message.includes('weasyprint') || err.message.includes('pdfkit'))) {
      ElMessage.error({
        message: 'PDF Exporting requires installing the PDF engine: pip install weasyprint (recommended)',
        duration: 5000
      })
    } else {
      ElMessage.error(`Download report failed: ${err.message || 'unknown error'}`)
    }
  }
}

// Helper function: get format name
const getFormatName = (format: string): string => {
  const names: Record<string, string> = {
    'markdown': 'Markdown',
    'docx': 'Word',
    'pdf': 'PDF',
    'json': 'JSON'
  }
  return names[format] || format
}

// Helper function: get file extension
const getFileExtension = (format: string): string => {
  const extensions: Record<string, string> = {
    'markdown': 'md',
    'docx': 'docx',
    'pdf': 'pdf',
    'json': 'json'
  }
  return extensions[format] || 'txt'
}

// Cleanup timer when component is destroyed
onUnmounted(() => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  clearSyncPolling()
})

// Handling when page visibility changes
const handleVisibilityChange = () => {
  if (document.hidden) {
    console.log('📱 Page hidden, polling paused')
  } else {
    console.log('📱 The page is displayed and polling resumes.')
    // When the page becomes visible again, immediately query the status once
    if (currentTaskId.value && analysisStatus.value === 'running') {
      setTimeout(async () => {
        try {
          const response = await analysisApi.getTaskStatus(currentTaskId.value)
          const status = response.data // Response interceptor returned response.data
          console.log('🔄 Page recovery query status:', status)
          if (status.status === 'pending' || status.status === 'running') {
            analysisStatus.value = 'running'
            updateProgressInfo(status)
          }
        } catch (error) {
          console.error('Page recovery query status failed:', error)
        }
      }, 500)
    }
  }
}

// Monitor page visibility changes
document.addEventListener('visibilitychange', handleVisibilityChange)

// Get in-depth description
const getDepthDescription = (depth: number) => {
  const descriptions = ['fast', 'Basics', 'Standard', 'Depth', 'Comprehensive']
  return descriptions[depth - 1] || 'Standard'
}

// Get progress bar status
const getProgressStatus = () => {
  if (analysisStatus.value === 'completed') {
    return 'success'
  } else if (analysisStatus.value === 'failed') {
    return 'exception'
  } else if (analysisStatus.value === 'running') {
    return '' // In the default state, a blue progress bar is displayed.
  }
  return ''
}

// Simple time formatting method (only used to display the time returned by the backend)
const formatTime = (seconds: number) => {
  if (!seconds || seconds <= 0) {
    return 'Calculating...'
  }

  if (seconds < 60) {
    return `${Math.floor(seconds)}seconds`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = Math.floor(seconds % 60)
    return remainingSeconds > 0 ? `${minutes}points${remainingSeconds}seconds` : `${minutes}minutes`
  } else {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}hours${minutes}minutes`
  }
}

// Update analysis step status
const updateAnalysisSteps = (status: any) => {
  console.log('📋 step update input:', status)

  if (analysisSteps.value.length === 0) {
    console.log('📋 No step definition, skip update')
    return
  }

  // Prioritize detailed step-by-step information provided by the backend
  let currentStepIndex = 0

  if (status.current_step !== undefined) {
    // The backend provides precise step indexing
    currentStepIndex = status.current_step
    console.log('📋 Using backend step index:', currentStepIndex)
  } else {
    // Fault Solution: Use Progress Percent Estimates
    const progress = status.progress_percentage || status.progress || 0
    if (progress > 0) {
      const progressRatio = progress / 100
      currentStepIndex = Math.floor(progressRatio * (analysisSteps.value.length - 1))
      if (progress > 0 && currentStepIndex === 0) {
        currentStepIndex = 1
      }
    }
    console.log('📋 Using the progress estimation step index:', currentStepIndex, 'Progress:', progress)
  }

  // Make sure the index is within the valid range
  currentStepIndex = Math.max(0, Math.min(currentStepIndex, analysisSteps.value.length - 1))

  console.log('📋 final step index:', currentStepIndex, '/', analysisSteps.value.length)

  // Update all step status
  analysisSteps.value.forEach((step, index) => {
    if (index < currentStepIndex) {
      step.status = 'completed'
    } else if (index === currentStepIndex) {
      step.status = 'current'
    } else {
      step.status = 'pending'
    }
  })

  const statusSummary = analysisSteps.value.map((s, i) => `${i}:${s.status}`).join(', ')
  console.log('📋 Step status update completed:', statusSummary)
}

// Initialize model settings
const initializeModelSettings = async () => {
  try {
    // Get the default model
    const defaultModels = await configApi.getDefaultModels()
    modelSettings.value.quickAnalysisModel = defaultModels.quick_analysis_model
    modelSettings.value.deepAnalysisModel = defaultModels.deep_analysis_model

    // Get a list of all available models
    const llmConfigs = await configApi.getLLMConfigs()
    availableModels.value = llmConfigs.filter((config: any) => config.enabled)

    console.log('✅ Loading model configuration successfully:', {
      quick: modelSettings.value.quickAnalysisModel,
      deep: modelSettings.value.deepAnalysisModel,
      available: availableModels.value.length
    })
    console.log('🔍 Available model details:', availableModels.value.map(m => ({
      model_name: m.model_name,
      model_display_name: m.model_display_name,
      provider: m.provider
    })))
  } catch (error) {
    console.error('Failed to load default model configuration:', error)
    modelSettings.value.quickAnalysisModel = 'qwen-turbo'
    modelSettings.value.deepAnalysisModel = 'qwen-max'
  }
}

// Task status cache management
const TASK_CACHE_KEY = 'trading_analysis_task'
const TASK_CACHE_DURATION = 30 * 60 * 1000 // 30 minutes

// Save task status to cache
const saveTaskToCache = (taskId: string, taskData: any) => {
  const cacheData = {
    taskId,
    taskData,
    timestamp: Date.now()
  }
  localStorage.setItem(TASK_CACHE_KEY, JSON.stringify(cacheData))
  console.log('💾 Task status cached:', taskId)
}

// Get task status from cache
const getTaskFromCache = () => {
  try {
    const cached = localStorage.getItem(TASK_CACHE_KEY)
    if (!cached) return null

    const cacheData = JSON.parse(cached)
    const now = Date.now()

    // Check if expired (30 minutes)
    if (now - cacheData.timestamp > TASK_CACHE_DURATION) {
      localStorage.removeItem(TASK_CACHE_KEY)
      console.log('🗑️ The cache has expired and has been cleared')
      return null
    }

    console.log('📦 Restore tasks from cache:', cacheData.taskId)
    return cacheData
  } catch (error) {
    console.error('❌ Failed to read cache:', error)
    localStorage.removeItem(TASK_CACHE_KEY)
    return null
  }
}

// Clear task cache
const clearTaskCache = () => {
  localStorage.removeItem(TASK_CACHE_KEY)
  console.log('🗑️ Task cache cleared')
}

// Restore task status
const restoreTaskFromCache = async () => {
  const cached = getTaskFromCache()
  if (!cached) return false

  try {
    console.log('🔄 Try to restore task status:', cached.taskId)

    // Query the current status of a task
    const response = await analysisApi.getTaskStatus(cached.taskId)
    const status = response.data // Response interceptor returned response.data

    console.log('📊 Restored task status:', status)

    if (status.status === 'completed') {
      // Task completed, results displayed
      currentTaskId.value = cached.taskId
      analysisStatus.value = 'completed'
      showResults.value = true
      applyAnalysisResult(await loadCompletedAnalysisResult(cached.taskId, status))
      progressInfo.value.progress = 100
      progressInfo.value.currentStep = 'Analysis completed'
      progressInfo.value.message = 'Analysis completed'

      // Restoring analysis parameters
      if (cached.taskData.parameters) {
        Object.assign(analysisForm, cached.taskData.parameters)
      }

      console.log('✅ Task completed, results displayed')
      return true

    } else if (status.status === 'pending' || status.status === 'running') {
      // The task is still running and the recovery progress is shown
      currentTaskId.value = cached.taskId
      analysisStatus.value = 'running'
      showResults.value = false
      updateProgressInfo(status)

      // Restoring analysis parameters
      if (cached.taskData.parameters) {
        Object.assign(analysisForm, cached.taskData.parameters)
      }

      // Start polling
      startPollingTaskStatus()

      console.log('🔄 The task is still running and the recovery progress is shown')
      return true

    } else if (status.status === 'failed') {
      // Task failed
      analysisStatus.value = 'failed'
      progressInfo.value.currentStep = 'Analysis failed'
      progressInfo.value.message = status.error_message || 'An error occurred during analysis'

      // clear cache
      clearTaskCache()

      console.log('❌ Task failed')
      return true

    } else {
      // Other status, clear cache
      clearTaskCache()
      console.log('🤔 Unknown task status, clear cache')
      return false
    }

  } catch (error) {
    console.error('❌ Failed to restore task status:', error)
    // If the query fails, it may be that the task does not exist. Clear the cache.
    clearTaskCache()
    return false
  }
}

// 🆕 Model capability related auxiliary functions

/**
 * Get ability level text
 */
const getCapabilityText = (level: number): string => {
  const texts: Record<number, string> = {
    1: '⚡Basics',
    2: '📊Standard',
    3: '🎯Advanced',
    4: '🔥Professional',
    5: '👑flagship'
  }
  return texts[level] || '📊Standard'
}

/**
 * Get ability level label type
 */
const getCapabilityTagType = (level: number): 'success' | 'info' | 'warning' | 'danger' => {
  if (level >= 4) return 'danger'
  if (level >= 3) return 'warning'
  if (level >= 2) return 'success'
  return 'info'
}

/**
 * Determine whether it is suitable for rapid analysis
 */
const isQuickAnalysisRole = (roles: string[] | undefined): boolean => {
  if (!roles || !Array.isArray(roles)) return false
  return roles.includes('quick_analysis') || roles.includes('both')
}

/**
 * Determine whether it is suitable for in-depth analysis
 */
/**
 * Model recommendation description showing depth of analysis
 */
const checkModelSuitability = async () => {
  const depthNames: Record<number, string> = {
    1: 'fast',
    2: 'Basics',
    3: 'Standard',
    4: 'Depth',
    5: 'Comprehensive'
  }
  const depthName = depthNames[analysisForm.researchDepth] || 'Standard'

  try {
    // Get recommended models
    const recommendRes = await recommendModels(depthName)
    const responseData = recommendRes?.data?.data

    if (responseData) {
      const quickModel = responseData.quick_model || 'unknown'
      const deepModel = responseData.deep_model || 'unknown'

      // Get the display name of the model
      const quickModelInfo = availableModels.value.find(m => m.model_name === quickModel)
      const deepModelInfo = availableModels.value.find(m => m.model_name === deepModel)

      const quickDisplayName = quickModelInfo?.model_display_name || quickModel
      const deepDisplayName = deepModelInfo?.model_display_name || deepModel

      // Get recommendation reasons
      const reason = responseData.reason || ''

      // Build recommended instructions
      const depthDescriptions: Record<number, string> = {
        1: 'Browse quickly to get basic information',
        2: 'Basic analysis to understand the main indicators',
        3: 'Standard analysis to fully evaluate stocks',
        4: 'Conduct in-depth research and explore investment opportunities',
        5: 'Comprehensive analysis and professional investment decisions'
      }

      const message = `${depthDescriptions[analysisForm.researchDepth] || 'standard analysis'}\n\n Recommended model configuration:\n• Quick model:${quickDisplayName}\n• Deep model:${deepDisplayName}\n\n${reason}`

      modelRecommendation.value = {
        title: '💡 Model recommendation',
        message,
        type: 'info',
        quickModel,
        deepModel
      }
    } else {
      // If there is no recommended data, show a general description
      const generalDescriptions: Record<number, string> = {
        1: 'Quick analysis: Just use the basic model, focusing on speed and cost',
        2: 'Basic analysis: use the basic level for fast models and the standard level for deep models.',
        3: 'Standard analysis: Use basic level for fast models, and use standard level or above for deep models.',
        4: 'Depth analysis: Use standard level for fast models, and use advanced level or higher for deep models, which require reasoning capabilities.',
        5: 'Comprehensive analysis: use standard level for fast models, professional level or above for deep models, strong reasoning ability'
      }

      modelRecommendation.value = {
        title: '💡 Model recommendation',
        message: generalDescriptions[analysisForm.researchDepth] || generalDescriptions[3],
        type: 'info'
      }
    }
  } catch (error) {
    console.error('Failed to obtain model recommendations:', error)
    // Show general description
    const generalDescriptions: Record<number, string> = {
      1: 'Quick analysis: Just use the basic model, focusing on speed and cost',
      2: 'Basic analysis: use the basic level for fast models and the standard level for deep models.',
      3: 'Standard analysis: Use basic level for fast models, and use standard level or above for deep models.',
      4: 'Depth analysis: Use standard level for fast models, and use advanced level or higher for deep models, which require reasoning capabilities.',
      5: 'Comprehensive analysis: use standard level for fast models, professional level or above for deep models, strong reasoning ability'
    }

    modelRecommendation.value = {
      title: '💡 Model recommendation',
      message: generalDescriptions[analysisForm.researchDepth] || generalDescriptions[3],
      type: 'info'
    }
  }
}

// Apply the recommended model configuration
const applyRecommendedModels = () => {
  if (modelRecommendation.value?.quickModel && modelRecommendation.value?.deepModel) {
    modelSettings.value.quickAnalysisModel = modelRecommendation.value.quickModel
    modelSettings.value.deepAnalysisModel = modelRecommendation.value.deepModel

    // Clear recommendations
    modelRecommendation.value = null

    ElMessage.success('Recommended model configuration applied')
  }
}

// Monitor and analyze depth changes
import { watch } from 'vue'
watch(() => analysisForm.researchDepth, () => {
  checkModelSuitability()
})

// Listen for model selection changes
watch([() => modelSettings.value.quickAnalysisModel, () => modelSettings.value.deepAnalysisModel], () => {
  checkModelSuitability()
})

// Page initialization
onMounted(async () => {
  initializeModelSettings()

  // 🆕 Load default settings from user preferences
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // Read from authStore.user.preferences first, then appStore.preferences
  const userPrefs = authStore.user?.preferences
  if (userPrefs) {
    // Load default market
    if (userPrefs.default_market) {
      analysisForm.market = userPrefs.default_market as MarketType
    }

    // Load default analysis depth (convert to number)
    if (userPrefs.default_depth) {
      analysisForm.researchDepth = parseInt(userPrefs.default_depth)
    }

    // Load default analyst
    if (userPrefs.default_analysts && userPrefs.default_analysts.length > 0) {
      analysisForm.selectedAnalysts = normalizeSelectedAnalystsForMarket(
        analysisForm.market,
        [...userPrefs.default_analysts]
      )
    }

    console.log('✅ User preferences loaded:', {
      market: analysisForm.market,
      depth: analysisForm.researchDepth,
      analysts: analysisForm.selectedAnalysts
    })
  } else {
    // downgrade to appStore.preferences
    if (appStore.preferences.defaultMarket) {
      analysisForm.market = appStore.preferences.defaultMarket as MarketType
    }
    if (appStore.preferences.defaultDepth) {
      analysisForm.researchDepth = parseInt(appStore.preferences.defaultDepth)
    }
    console.log('✅ App preferences loaded (downgrade)')
  }

  // Receive routing parameters once (brought in from the filtering page) - routing parameters have the highest priority
  const q = route.query as any
  const hasNewStock = !!q?.stock
  if (hasNewStock) {
    analysisForm.stockCode = String(q.stock)
    // 🔥 Critical fix: Clear old task cache if there are new tickers
    clearTaskCache()
    console.log('🔄 New stock symbol detected, old task cache cleared:', q.stock)

    // 🆕 Automatic recognition of market type (if market parameter is not explicitly specified in the URL)
    if (!q?.market) {
      const detectedMarket = getMarketByStockCode(analysisForm.stockCode)
      analysisForm.market = detectedMarket as MarketType
      if (detectedMarket === 'ETF') {
        analysisForm.selectedAnalysts = [...ETF_ANALYST_NAMES]
      } else {
        analysisForm.selectedAnalysts = normalizeSelectedAnalystsForMarket(
          detectedMarket as MarketType,
          analysisForm.selectedAnalysts
        )
      }
      console.log('🔍 Automatically identify market types:', analysisForm.stockCode, '->', detectedMarket)
    }
  }
  if (q?.market) {
    analysisForm.market = normalizeMarketForAnalysis(q.market) as MarketType
    // 🔥 Analyst synchronization is also required if market type is set from routing parameters
    if (analysisForm.market === 'ETF') {
      analysisForm.selectedAnalysts = [...ETF_ANALYST_NAMES]
    } else {
      analysisForm.selectedAnalysts = normalizeSelectedAnalystsForMarket(
        analysisForm.market,
        analysisForm.selectedAnalysts
      )
    }
  }

  if (analysisForm.market === 'A shares' && analysisForm.stockCode) {
    await fetchFactorPreview(analysisForm.stockCode)
  }

  // Try to restore task status (only if there is no new ticker)
  if (!hasNewStock) {
    await restoreTaskFromCache()
  }

  // 🆕 Initial check of model suitability
  await checkModelSuitability()
  try {
    workflows.value = await workflowApi.listAll()
    console.log('[SingleAnalysis] All processes loaded:', workflows.value)
    console.log('[SingleAnalysis] filtered process:', workflowsSorted.value)
    
    // Prefer processes marked is_default
    const defaultWorkflow = workflowsSorted.value.find(w => w.is_default)
    if (defaultWorkflow) {
      selectedWorkflowId.value = defaultWorkflow.id
      console.log('[SingleAnalysis] Select the default process:', defaultWorkflow.id, defaultWorkflow.name)
    } else if (workflowsSorted.value.length > 0) {
      // If no default is marked, the first one is selected
      selectedWorkflowId.value = workflowsSorted.value[0].id
      console.log('[SingleAnalysis] There is no default process, select the first one:', workflowsSorted.value[0].id, workflowsSorted.value[0].name)
    }
  } catch (error) {
    console.debug('[SingleAnalysis] Failed to load workflow, retaining current default template:', error)
  }
})

</script>

<style lang="scss" scoped>
.single-analysis {
  min-height: 100vh;
  background: var(--el-bg-color-page);
  padding: 24px;

  .page-header {
    margin-bottom: 32px;

    .header-content {
      background: var(--el-bg-color);
      padding: 32px;
      border-radius: 16px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    }

    .title-section {
      .page-title {
        display: flex;
        align-items: center;
        font-size: 32px;
        font-weight: 700;
        color: #1a202c;
        margin: 0 0 12px 0;

        .title-icon {
          margin-right: 12px;
          color: #3b82f6;
        }
      }

      .risk-disclaimer {
        margin: 0 0 12px 0;
      }

      .page-description {
        font-size: 16px;
        color: #64748b;
        margin: 0;
      }
    }
  }

  .analysis-container {
    .main-form-card, .config-card {
      border-radius: 16px;
      border: none;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);

      :deep(.el-card__header) {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 16px 16px 0 0;
        padding: 20px 24px;

        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;

          h3 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
          }
        }
      }

      :deep(.el-card__body) {
        padding: 24px;
      }
    }

    .analysis-form {
      .form-section {
        margin-bottom: 32px;
        width: 100%;
        display: flex;
        flex-direction: column;

        .section-title {
          font-size: 16px;
          font-weight: 600;
          color: #1a202c;
          margin: 0 0 16px 0;
          padding-bottom: 8px;
          border-bottom: 2px solid #e2e8f0;
        }

        .factor-preview-card {
          padding: 16px;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          background: #f8fafc;
        }

        .factor-preview-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
          font-size: 13px;
          color: #475569;
        }

        .factor-preview-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .factor-preview-tag {
          cursor: help;
        }

        .factor-preview-popover {
          display: flex;
          flex-direction: column;
          gap: 6px;
          line-height: 1.6;
        }

        .factor-preview-popover-title {
          font-weight: 600;
          color: #1e293b;
        }

        .factor-preview-line {
          font-size: 13px;
          color: #475569;
        }
      }

      .stock-input {
        :deep(.el-input__inner) {
          font-weight: 600;
          text-transform: uppercase;
        }

        &.is-error {
          :deep(.el-input__inner) {
            border-color: #f56c6c;
          }
        }
      }

      .error-message {
        display: flex;
        align-items: center;
        gap: 4px;
        margin-top: 8px;
        font-size: 12px;
        color: #f56c6c;

        .el-icon {
          font-size: 14px;
        }
      }

      .help-message {
        display: flex;
        align-items: center;
        gap: 4px;
        margin-top: 8px;
        font-size: 12px;
        color: #67c23a;

        .el-icon {
          font-size: 14px;
        }
      }

      .depth-selector {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;

        .depth-option {
          display: flex;
          align-items: center;
          padding: 16px;
          border: 2px solid #e2e8f0;
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.3s ease;

          &:hover {
            border-color: #3b82f6;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
          }

          &.active {
            border-color: #3b82f6;
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            color: #1e40af;
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(59, 130, 246, 0.15);
          }

          .depth-icon {
            font-size: 24px;
            margin-right: 12px;
          }

          .depth-info {
            .depth-name {
              font-weight: 600;
              margin-bottom: 4px;
            }

            .depth-desc {
              font-size: 12px;
              opacity: 0.8;
              margin-bottom: 2px;
            }

            .depth-time {
              font-size: 11px;
              opacity: 0.7;
            }
          }
        }
      }

      .analysts-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;

        .analyst-card {
          display: flex;
          align-items: center;
          padding: 16px;
          border: 2px solid #e2e8f0;
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.3s ease;

          &:hover {
            border-color: #3b82f6;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
          }

          &.active {
            border-color: #3b82f6;
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            color: #1e40af;
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(59, 130, 246, 0.15);
          }

          &.disabled {
            opacity: 0.5;
            cursor: not-allowed;

            &:hover {
              transform: none;
              box-shadow: none;
              border-color: #e2e8f0;
            }
          }

          .analyst-avatar {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 16px;
            font-size: 20px;
          }

          .analyst-content {
            flex: 1;

            .analyst-name {
              font-weight: 600;
              margin-bottom: 4px;
            }

            .analyst-desc {
              font-size: 12px;
              opacity: 0.8;
            }
          }

          .analyst-check {
            .check-icon {
              font-size: 20px;
              color: #3b82f6;
            }
          }

          &.active .analyst-check .check-icon {
            color: #1e40af;
          }

          // 🔥 Disabled state style
          &.disabled {
            opacity: 0.5;
            cursor: not-allowed;
            background-color: #f9fafb;
            border-color: #e5e7eb;

            &:hover {
              transform: none;
              box-shadow: none;
              border-color: #e5e7eb;
            }

            .analyst-name {
              color: #9ca3af;
            }

            .analyst-desc {
              color: #9ca3af;
            }

            .analyst-avatar {
              opacity: 0.5;
            }
          }
        }
      }
    }

    .config-card {
      .config-content {
        .config-section {
          margin-bottom: 24px;

          .config-title {
            font-size: 14px;
            font-weight: 600;
            color: #1a202c;
            margin: 0 0 12px 0;
            display: flex;
            align-items: center;
            gap: 8px;
          }

          .model-config {
            .model-item {
              margin-bottom: 16px;

              .model-label {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
                font-size: 13px;
                color: #374151;

                .help-icon {
                  color: #9ca3af;
                  cursor: help;
                }
              }
            }
          }

          .option-list {
            .option-item {
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 12px 0;
              border-bottom: 1px solid #f3f4f6;

              &:last-child {
                border-bottom: none;
              }

              .option-info {
                .option-name {
                  font-size: 14px;
                  font-weight: 500;
                  color: #374151;
                  display: block;
                  margin-bottom: 2px;
                }

                .option-desc {
                  font-size: 12px;
                  color: #6b7280;
                }
              }
            }
          }

          .custom-input {
            :deep(.el-textarea__inner) {
              border-radius: 8px;
              border: 1px solid #d1d5db;

              &:focus {
                border-color: #3b82f6;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
              }
            }
          }

          .input-help {
            font-size: 12px;
            color: #6b7280;
            margin-top: 8px;
          }

          .action-buttons {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            margin-top: 24px !important;
            width: 100% !important;
            text-align: center !important;

            .submit-btn.el-button {
              width: 280px !important;
              height: 56px !important;
              font-size: 18px !important;
              font-weight: 700 !important;
              background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
              border: none !important;
              border-radius: 16px !important;
              transition: all 0.3s ease !important;
              box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2) !important;
              min-width: 280px !important;
              max-width: 280px !important;

              &:hover {
                transform: translateY(-3px) !important;
                box-shadow: 0 12px 30px rgba(59, 130, 246, 0.4) !important;
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
              }

              &:disabled {
                opacity: 0.6 !important;
                transform: none !important;
                box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1) !important;
              }

              .el-icon {
                margin-right: 8px !important;
                font-size: 20px !important;
              }

              span {
                font-size: 18px !important;
                font-weight: 700 !important;
              }
            }
          }
        }
      }
    }

    .action-section {
      margin-top: 24px;
      display: flex;
      gap: 16px;

      .submit-btn {
        flex: 1;
        height: 48px;
        font-size: 16px;
        font-weight: 600;
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        border: none;
        border-radius: 12px;
        transition: all 0.3s ease;

        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 25px rgba(59, 130, 246, 0.3);
        }

        &:disabled {
          opacity: 0.6;
          transform: none;
          box-shadow: none;
        }
      }

      .reset-btn {
        height: 48px;
        font-size: 16px;
        border-radius: 12px;
        border: 2px solid #e5e7eb;
        color: #6b7280;
        transition: all 0.3s ease;

        &:hover {
          border-color: #d1d5db;
          color: #374151;
          transform: translateY(-1px);
        }
      }
    }
  }
}

// Analysis step style
.step-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 0;
  border-left: 3px solid #e5e7eb;
  margin-left: 15px;
  position: relative;
  transition: all 0.3s ease;

  &.step-completed {
    border-left-color: #10b981;

    .step-icon {
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      color: white;
      box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
    }

    .step-title {
      color: #10b981;
      font-weight: 600;
    }

    .step-description {
      color: #059669;
    }
  }

  &.step-current {
    border-left-color: #3b82f6;
    background: linear-gradient(90deg, rgba(59, 130, 246, 0.05) 0%, transparent 100%);

    .step-icon {
      background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
      color: white;
      box-shadow: 0 2px 12px rgba(59, 130, 246, 0.4);
    }

    .step-title {
      color: #3b82f6;
      font-weight: 700;
    }

    .step-description {
      color: #1d4ed8;
      font-weight: 500;
    }
  }

  &.step-pending {
    .step-icon {
      background: #f3f4f6;
      color: #9ca3af;
      border: 2px solid #e5e7eb;
    }

    .step-title {
      color: #6b7280;
    }

    .step-description {
      color: #9ca3af;
    }
  }
}

.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: -16px;
  margin-right: 16px;
  font-size: 14px;
  flex-shrink: 0;
  z-index: 1;
  transition: all 0.3s ease;
}

.completed-icon {
  color: white;
}

.current-icon {
  color: white;
}

.pending-icon {
  color: #9ca3af;
}

.step-content {
  flex: 1;
  min-width: 0;
  padding-right: 16px;
}

.step-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
  line-height: 1.4;
}

.step-description {
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.9;
}

/* pulse animation */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

/* Add a pulsing effect to the current step icon */
.step-current .step-icon {
  animation: pulse 2s ease-in-out infinite;
}
</style>

<style>
/* Global styles ensure that button styles take effect */
.action-buttons {
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  width: 100% !important;
  text-align: center !important;
}


.large-analysis-btn.el-button {
  width: 280px !important;
  height: 56px !important;
  font-size: 18px !important;
  font-weight: 700 !important;
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
  border: none !important;
  border-radius: 16px !important;
  transition: all 0.3s ease !important;
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2) !important;
  min-width: 280px !important;
  max-width: 280px !important;
}

.large-analysis-btn.el-button:hover {
  transform: translateY(-3px) !important;
  box-shadow: 0 12px 30px rgba(59, 130, 246, 0.4) !important;
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
}

.large-analysis-btn.el-button:disabled {
  opacity: 0.6 !important;
  transform: none !important;
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1) !important;
}

.large-analysis-btn.el-button .el-icon {
  margin-right: 8px !important;
  font-size: 20px !important;
}

.large-analysis-btn.el-button span {
  font-size: 18px !important;
  font-weight: 700 !important;
}

/* Progress display style */
.progress-section {
  margin-top: 24px;
}

.progress-card .progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.progress-card .progress-header h4 {
  margin: 0;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

/* Rotation animation */
.rotating-icon {
  animation: rotate 2s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Overall progress information */
.overall-progress-info {
  margin-bottom: 24px;
}

.progress-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  font-weight: 500;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* progress bar area */
.progress-bar-section {
  margin-bottom: 24px;
}

.main-progress-bar {
  :deep(.el-progress-bar__outer) {
    background-color: var(--el-fill-color);
    border-radius: 8px;
  }

  :deep(.el-progress-bar__inner) {
    background: linear-gradient(90deg, #3b82f6 0%, #1d4ed8 100%);
    border-radius: 8px;
    transition: width 0.6s ease;
  }

  :deep(.el-progress__text) {
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
}

/* Current task information */
.current-task-info {
  background: var(--el-fill-color-light);
  border: 1px solid #3b82f6;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 24px;
}

.task-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 8px;
}

.task-icon {
  color: #3b82f6;
}

.task-description {
  font-size: 14px;
  color: #1e40af;
  line-height: 1.5;
}

/* Analysis steps */
.analysis-steps {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  padding: 20px;
}

.steps-title {
  margin: 0 0 16px 0;
  color: #1e293b;
  font-size: 16px;
  font-weight: 600;
}

.steps-container {
  max-height: 300px;
  overflow-y: auto;
}

/* Result display style */
.results-section {
  margin-top: 24px;
}

.results-card .results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.results-card .results-header h3 {
  margin: 0;
  color: #1f2937;
}

.results-card .result-meta {
  display: flex;
  gap: 8px;
}

.overview-section {
  margin-bottom: 32px;
}

.overview-section h4 {
  color: #1f2937;
  margin-bottom: 16px;
}

.overview-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 28px 32px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.overview-summary {
  color: #1f2937;
}

.overview-summary :deep(.markdown-content > *:first-child) {
  margin-top: 0;
}

.overview-summary :deep(.markdown-content > *:last-child) {
  margin-bottom: 0;
}

/* Risk warning style */
.risk-disclaimer {
  margin-bottom: 24px;
  animation: fadeInDown 0.5s ease-out;
}

.title-section .risk-disclaimer {
  margin-bottom: 12px;
  margin-top: 0;
}

.risk-disclaimer :deep(.el-alert) {
  background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%);
  border: 2px solid #ffc107;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 4px 12px rgba(255, 193, 7, 0.2);
}

.risk-disclaimer :deep(.el-alert__icon) {
  font-size: 24px;
  color: #ff6b00;
}

.disclaimer-content {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  line-height: 1.6;
}

.disclaimer-icon {
  font-size: 24px;
  color: #ff6b00;
  flex-shrink: 0;
  animation: pulse 2s ease-in-out infinite;
}

.disclaimer-text {
  color: #856404;
  flex: 1;
}

.disclaimer-text strong {
  color: #d63031;
  font-size: 16px;
  font-weight: 700;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.8;
  }
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.decision-section {
  margin-bottom: 32px;
}

.decision-section h4 {
  color: #1f2937;
  margin-bottom: 16px;
}

.decision-card {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  padding: 20px;
}

.decision-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.decision-action {
  display: flex;
  align-items: center;
  gap: 12px;
}

.decision-action .label {
  font-weight: 600;
  color: #374151;
}

.decision-metrics {
  display: flex;
  gap: 24px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.metric-item .label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.metric-item .value {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.decision-reasoning h5 {
  margin: 0 0 8px 0;
  color: #374151;
  font-size: 14px;
}

.decision-reasoning p {
  margin: 0;
  color: #6b7280;
  line-height: 1.6;
}

.reports-section {
  margin-bottom: 32px;
}

.reports-section h4 {
  color: #1f2937;
  margin-bottom: 16px;
}

.report-content {
  line-height: 1.6;
  color: #374151;
}

.report-content h1,
.report-content h2,
.report-content h3 {
  color: #1f2937;
  margin: 16px 0 8px 0;
}

.report-content strong {
  color: #1f2937;
}

.result-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  padding-top: 24px;
  border-top: 1px solid #e5e7eb;
}

/* Analysis report tab style */
.analysis-tabs-container {
  margin-top: 16px;
}

.analysis-tabs {
  /* Tab header style */
  :deep(.el-tabs__header) {
    margin: 0 0 20px 0;
    background: var(--el-fill-color-light);
    padding: 12px;
    border-radius: 15px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    border: 1px solid var(--el-border-color);
  }

  /* Tab navigation */
  :deep(.el-tabs__nav-wrap) {
    &::after {
      display: none; /* Hide default bottom border */
    }
  }

  /* Single tab style */
  :deep(.el-tabs__item) {
    height: 55px !important;
    line-height: 55px !important;
    padding: 0 20px !important;
    margin-right: 8px !important;
    background: var(--el-bg-color) !important;
    border: 2px solid var(--el-border-color) !important;
    border-radius: 12px !important;
    color: var(--el-text-color-regular) !important;
    font-weight: 600 !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
    position: relative !important;
    overflow: hidden !important;
    border-bottom: 2px solid var(--el-border-color) !important; /* Make sure the bottom border exists */

    &:hover {
      background: var(--el-fill-color-light) !important;
      border-color: #2196f3 !important;
      transform: translateY(-2px) scale(1.02) !important;
      box-shadow: 0 4px 15px rgba(33,150,243,0.3) !important;
      color: #1976d2 !important;
    }

    &.is-active {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
      color: white !important;
      border-color: #667eea !important;
      box-shadow: 0 6px 20px rgba(102,126,234,0.4) !important;
      transform: translateY(-3px) scale(1.05) !important;

      &::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.1) 100%);
        border-radius: 10px;
        pointer-events: none;
      }
    }
  }

  /* Tab content area */
  :deep(.el-tabs__content) {
    padding: 0;
  }

  :deep(.el-tab-pane) {
    padding: 25px;
    background: var(--el-bg-color);
    border-radius: 15px;
    border: 1px solid var(--el-border-color);
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    margin-top: 10px;
  }
}

/* Report header style */
.report-header {
  margin-bottom: 25px;
  padding: 20px;
  background: var(--el-fill-color-light);
  border-radius: 15px;
  border-left: 5px solid #667eea;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);

  .report-title {
    display: flex;
    align-items: center;
    margin-bottom: 8px;

    .report-icon {
      font-size: 24px;
      margin-right: 12px;
    }

    .report-name {
      font-size: 20px;
      font-weight: 700;
      color: #495057;
    }
  }

  .report-description {
    color: #6c757d;
    font-size: 16px;
    line-height: 1.5;
    margin-left: 36px; /* Align text after icon */
  }
}

/* Report content wrapper */
.report-content-wrapper {
  background: var(--el-bg-color);
  padding: 25px;
  border-radius: 12px;
  border: 1px solid var(--el-border-color);
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* Report content style enhancement */
.report-content,
.markdown-content {
  line-height: 1.7;
  color: #495057;
  font-size: 16px;

  /* Title style */
  h1, h2, h3, h4, h5, h6 {
    color: #1f2937 !important;
    margin: 20px 0 12px 0 !important;
    font-weight: 600 !important;
  }

  h1 { font-size: 30px !important; line-height: 1.3 !important; }
  h2 { font-size: 22px !important; line-height: 1.4 !important; }
  h3 { font-size: 18px !important; line-height: 1.5 !important; }
  h4 { font-size: 16px !important; }

  /* paragraph style */
  p {
    margin: 12px 0 !important;
    line-height: 1.7 !important;
  }

  /* emphasize text */
  strong, b {
    color: #1f2937 !important;
    font-weight: 600 !important;
  }

  /* italicized text */
  em, i {
    color: #4b5563 !important;
    font-style: italic !important;
  }

  /* list style */
  ul, ol {
    margin: 12px 0 !important;
    padding-left: 24px !important;

    li {
      margin: 6px 0 !important;
      line-height: 1.6 !important;
    }
  }

  /* code style */
  code {
    background: var(--el-fill-color-light) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace !important;
    font-size: 14px !important;
    color: #e11d48 !important;
  }

  /* Reference style */
  blockquote {
    border-left: 4px solid #3b82f6 !important;
    padding-left: 16px !important;
    margin: 16px 0 !important;
    background: var(--el-fill-color-light) !important;
    padding: 12px 16px !important;
    border-radius: 0 8px 8px 0 !important;
    font-style: italic !important;
    color: var(--el-text-color-regular) !important;
  }
}

/* Risk warning style */
.risk-disclaimer {
  margin-top: 24px;
  border-radius: 8px;

  :deep(.el-alert__content) {
    width: 100%;
  }

  :deep(.el-alert__title) {
    font-size: 14px;
    line-height: 1.6;
    color: #e6a23c;
  }
}

.growth-panel-section {
  margin-bottom: 24px;
}
</style>
