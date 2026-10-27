<template>
  <div class="about">
    <!-- Hero Section -->
    <div class="hero-section">
      <div class="hero-content">
        <div class="hero-text">
          <h1 class="hero-title">
            {{ isJdyun ? 'TradingAgents-CN JD Cloud Cooperation Edition' : 'TradingAgents-CN' }}
            <span class="version-badge">{{ isJdyun ? 'Jingdong cloud version' : 'v3.0' }}</span>
          </h1>
          <p class="hero-subtitle">
            AI Assisted stock analysis technology learning platform
          </p>
          <p class="hero-description" v-if="!isJdyun">
            A learning and verification platform focusing on AI-assisted analysis technology. Assisted by optimized workflow engines and full-process analysis,
            Help you systematically learn stock analysis methods and improve your analysis capabilities.
          </p>
          <p class="hero-description" v-else>
            <strong>Are you still troubled by these problems?</strong><br/>
            Half a day has passed since I assigned keys, selected models, and set up environments, and I still haven t started researching yet;<br/>
            Halfway through the research, the model was restricted and the results could not be produced;<br/>
            There is so much information online that I don t know what to believe.…
          </p>
          <p class="hero-description" v-else style="margin-top:-10px;">
            <strong>JD Cloud Cooperation Edition helps you solve the following problems with one click:</strong><br/>
            Ready to use, keys and data sources are all pre-configured;<br/>
            Built-in 429 current limiting response, in-depth analysis and stable running of the complete process;<br/>
            14 Structured research report across dimensions + Optimistic/cautious dual-scenario researcher helps you systematically establish your own analysis methodology.
          </p>
          <div class="hero-positioning" v-if="!isJdyun">
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>Used to learn AI stock analysis technology</span>
            </div>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>No operating guidance</span>
            </div>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>Practical Learning Methodology</span>
            </div>
          </div>
          <div class="hero-positioning" v-else>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>0 Configuration, ready to use</span>
            </div>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>429 Automatically retry 8 times</span>
            </div>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>14 Dimensional research report</span>
            </div>
            <div class="positioning-item">
              <el-icon><CircleCheck /></el-icon>
              <span>Only supports A shares</span>
            </div>
          </div>
          <div class="hero-acknowledgment" v-if="!isJdyun">
            <el-icon><Star /></el-icon>
            <span>Based on <a href="https://github.com/TauricResearch/TradingAgents" target="_blank" rel="noopener noreferrer">TradingAgents</a> Project development, thanks to the contribution of the original project</span>
          </div>
          <div class="hero-actions">
            <el-button type="primary" size="large" @click="goToAnalysis">
              <el-icon><TrendCharts /></el-icon>
              Start analysis
            </el-button>
            <el-button size="large" @click="goToLearning">
              <el-icon><Reading /></el-icon>
              View courses
            </el-button>
          </div>
        </div>
        <div class="hero-visual">
          <div class="hero-card">
            <div class="hero-stats">
              <div class="stat-item">
                <div class="stat-number">v3.0</div>
                <div class="stat-label">Brand new upgrade</div>
              </div>
              <div class="stat-item">
                <div class="stat-number">Much</div>
                <div class="stat-label">Agent collaboration</div>
              </div>
              <div class="stat-item">
                <div class="stat-number">AI</div>
                <div class="stat-label">Auxiliary analysis</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Learning Center Guide -->
    <div class="learning-banner">
      <div class="banner-content">
        <div class="banner-text">
          <el-icon class="banner-icon"><Reading /></el-icon>
          <div>
            <h3>Systematic learning courses</h3>
            <p>From entry to practice, 24 hours of core courses + Entry/improvement/full-process method construction to help you master AI-assisted stock analysis technology</p>
          </div>
        </div>
        <el-button type="primary" @click="goToLearning">
          View courses
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- Core functions / JD Cloud version features -->
    <div class="features-section">
      <div class="section-header" v-if="!isJdyun">
        <h2 class="section-title">Core functions</h2>
        <p class="section-subtitle">Optimize the analysis engine, provide full-process analysis assistance, and improve stock analysis and learning capabilities</p>
      </div>
      <div class="section-header" v-else>
        <h2 class="section-title">Features of JD Cloud Edition</h2>
        <p class="section-subtitle">Ready-to-use, zero-configuration, speed limit-friendly, compliance research, specially customized for JD Cloud users</p>
      </div>

      <div class="features-grid" v-if="!isJdyun">
        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon primary">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <h3>Optimize analysis engine</h3>
          </div>
          <p>v3.0 The workflow engine has been fully upgraded to support visual process definition, Agent workshop, Skill center and MCP server. Multi-agent collaboration provides a comprehensive analysis perspective from multiple dimensions such as fundamentals, technology, news, and social media.</p>
          <div class="feature-tags">
            <el-tag size="small">workflow engine</el-tag>
            <el-tag size="small">Visual configuration</el-tag>
            <el-tag size="small">multi-agent</el-tag>
            <el-tag size="small">Configurable architecture</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon success">
              <el-icon><Search /></el-icon>
            </div>
            <h3>Full process analysis assistance</h3>
          </div>
          <p>Complete process assistance from data collection, indicator calculation, agent analysis to report generation. Supports multiple analysis scenarios such as single stock analysis, batch analysis, position analysis, transaction review, etc., helping you systematically learn the complete analysis process</p>
          <div class="feature-tags">
            <el-tag size="small" type="success">Full process assistance</el-tag>
            <el-tag size="small" type="success">Multi-scenario analysis</el-tag>
            <el-tag size="small" type="success">process learning</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon warning">
              <el-icon><Files /></el-icon>
            </div>
            <h3>Improve learning ability</h3>
          </div>
          <p>Learn professional stock analysis methodology through AI-assisted analysis. View the detailed analysis process, reasoning logic and decision-making basis, understand the role of different analysis dimensions, and gradually improve your stock analysis skills</p>
          <div class="feature-tags">
            <el-tag size="small" type="warning">methodological learning</el-tag>
            <el-tag size="small" type="warning">Transparent process</el-tag>
            <el-tag size="small" type="warning">Skill improvement</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon primary">
              <el-icon><Setting /></el-icon>
            </div>
            <h3>Configurable architecture</h3>
          </div>
          <p>v3.0 Configurable architecture, workflow, agents, tools, and prompt words can all be dynamically configured. Supports visual workflow editor, Agent Workshop and Skill Center, allowing you to adjust the analysis process without modifying the code and flexibly adapt to different learning needs</p>
          <div class="feature-tags">
            <el-tag size="small">Dynamic configuration</el-tag>
            <el-tag size="small">Visual editing</el-tag>
            <el-tag size="small">Flexible adjustment</el-tag>
          </div>
        </div>
      </div>

      <!-- JD Cloud Version Featured Cards -->
      <div class="features-grid" v-else>
        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon primary">
              <el-icon><Box /></el-icon>
            </div>
            <h3>Ready out of the box</h3>
          </div>
          <p>Just log in and use it, it doesn t even take 5 minutes. No need to install an environment, configure a database, or type a single line of commands, JD Cloud does it all for you.</p>
          <div class="feature-tags">
            <el-tag size="small">No installation required</el-tag>
            <el-tag size="small">No deployment required</el-tag>
            <el-tag size="small">Log in and use</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon success">
              <el-icon><Key /></el-icon>
            </div>
            <h3>Zero configuration</h3>
          </div>
          <p>There is no need to understand what the API is, no need to apply for a Key, and no need to worry about which model to choose. Models, data sources, and vector libraries are all pre-configured on JD Cloud, so you just need to use them.</p>
          <div class="feature-tags">
            <el-tag size="small" type="success">Free Key</el-tag>
            <el-tag size="small" type="success">free model</el-tag>
            <el-tag size="small" type="success">Zero threshold</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon warning">
              <el-icon><DataAnalysis /></el-icon>
            </div>
            <h3>Cover the whole process</h3>
          </div>
          <p>Want to research a stock? Want to know which stocks are worth watching? Want to know if what you are doing is correct? Single stock analysis, intelligent screening, position review, and trading plan, all done in one system</p>
          <div class="feature-tags">
            <el-tag size="small" type="warning">single stock research</el-tag>
            <el-tag size="small" type="warning">Smart stock selection</el-tag>
            <el-tag size="small" type="warning">Position review</el-tag>
          </div>
        </div>

        <div class="feature-card">
          <div class="feature-header">
            <div class="feature-icon info">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <h3>Don t know how to use it? Just ask the AI</h3>
          </div>
          <p>The little dot in the lower right corner is your portable assistant."How to export the report?""How to set filter conditions?"——Asking it directly is much faster than flipping through documents</p>
          <div class="feature-tags">
            <el-tag size="small" type="info">Ask questions anytime</el-tag>
            <el-tag size="small" type="info">read manual</el-tag>
            <el-tag size="small" type="info">configuration operation</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- Version information -->
    <div class="version-section">
      <div class="section-header">
        <h2 class="section-title">Version information</h2>
      </div>

      <div class="version-info" v-loading="systemInfoLoading">
        <div class="version-card">
          <div class="version-main">
            <div class="version-number">{{ systemInfo.version || 'v3.0' }}</div>
            <div class="version-status" :class="versionStatusClass">{{ versionStatusText }}</div>
          </div>
          <div class="version-details">
            <div class="version-item" v-if="systemInfo.full_version">
              <span class="label">full version</span>
              <span class="value">{{ systemInfo.full_version }}</span>
            </div>
            <div class="version-item" v-if="systemInfo.build_date">
              <span class="label">Build time</span>
              <span class="value">{{ formatBuildDate(systemInfo.build_date) }}</span>
            </div>
            <div class="version-item" v-if="systemInfo.build_type">
              <span class="label">Build type</span>
              <span class="value">{{ formatBuildType(systemInfo.build_type) }}</span>
            </div>
            <div class="version-item" v-if="systemInfo.git_commit">
              <span class="label">Git Submit</span>
              <span class="value code">{{ systemInfo.git_commit }}</span>
            </div>
            <div class="version-item" v-if="!systemInfo.build_date">
              <span class="label">Build time</span>
              <span class="value">{{ buildTime }}</span>
            </div>
            <div class="version-item">
              <span class="label">API version</span>
              <span class="value">v3.0</span>
            </div>
          </div>
          <div class="version-actions" v-if="systemInfo.full_version">
            <el-button type="primary" size="small" @click="copyVersionInfo" plain>
              <el-icon><DocumentCopy /></el-icon>
              Copy version information
            </el-button>
          </div>
        </div>

        <div class="framework-info">
          <h4>Technical version</h4>
          <div class="framework-list">
            <div class="framework-item">
              <span class="name">Vue</span>
              <span class="version">3.4.0</span>
            </div>
            <div class="framework-item">
              <span class="name">Element Plus</span>
              <span class="version">2.4.4</span>
            </div>
            <div class="framework-item">
              <span class="name">FastAPI</span>
              <span class="version">0.104.0</span>
            </div>
            <div class="framework-item">
              <span class="name">Python</span>
              <span class="version">3.11.9</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Technical architecture -->
    <div class="tech-section">
      <div class="section-header">
        <h2 class="section-title">Technical architecture</h2>
        <p class="section-subtitle">v3.0 New architecture and configurable design provide strong support for the learning platform</p>
      </div>

      <div class="tech-stack">
        <div class="tech-category">
          <div class="tech-header">
            <div class="tech-icon frontend">
              <el-icon><Monitor /></el-icon>
            </div>
            <h3>Front-end technology</h3>
          </div>
          <div class="tech-list">
            <div class="tech-item">
              <span class="tech-name">Vue 3</span>
              <span class="tech-desc">Modern front-end framework</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">TypeScript</span>
              <span class="tech-desc">Type-safe development</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Element Plus</span>
              <span class="tech-desc">Enterprise-level UI component library</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Pinia</span>
              <span class="tech-desc">Status management</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Vite</span>
              <span class="tech-desc">Quick build tool</span>
            </div>
          </div>
        </div>

        <div class="tech-category">
          <div class="tech-header">
            <div class="tech-icon backend">
              <el-icon><Monitor /></el-icon>
            </div>
            <h3>Backend technology</h3>
          </div>
          <div class="tech-list">
            <div class="tech-item">
              <span class="tech-name">FastAPI</span>
              <span class="tech-desc">High performance API framework</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Python 3.11.9</span>
              <span class="tech-desc">Modern Python Development</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Redis</span>
              <span class="tech-desc">High performance caching and queuing</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">MongoDB</span>
              <span class="tech-desc">document database</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Asynchronous processing</span>
              <span class="tech-desc">Highly concurrent task processing</span>
            </div>
          </div>
        </div>

        <div class="tech-category">
          <div class="tech-header">
            <div class="tech-icon ai">
              <el-icon><Cpu /></el-icon>
            </div>
            <h3>v3.0 core engine</h3>
          </div>
          <div class="tech-list">
            <div class="tech-item">
              <span class="tech-name">workflow engine</span>
              <span class="tech-desc">Visual process definition</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Agent workshop</span>
              <span class="tech-desc">Custom agent development</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Skill Center</span>
              <span class="tech-desc">AI Generate analysis tools</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">MCP server</span>
              <span class="tech-desc">External capability expansion</span>
            </div>
            <div class="tech-item">
              <span class="tech-name">Capability Index Panel</span>
              <span class="tech-desc">Capability discovery and gap analysis</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Project source (hidden in JD Cloud version) -->
    <div class="origin-section" v-if="!isJdyun">
      <div class="section-header">
        <h2 class="section-title">Project source</h2>
        <p class="section-subtitle">Pay tribute to open source and thank you for your contribution to the original project</p>
      </div>

      <div class="origin-content">
        <div class="origin-card">
          <div class="origin-header">
            <div class="origin-icon">
              <el-icon><Link /></el-icon>
            </div>
            <div class="origin-info">
              <h3>TradingAgents</h3>
              <a href="https://github.com/TauricResearch/TradingAgents"
                 target="_blank"
                 rel="noopener noreferrer"
                 class="origin-link">
                <el-icon><Link /></el-icon>
                github.com/TauricResearch/TradingAgents
              </a>
            </div>
          </div>

          <div class="origin-description">
            <p>
              <strong>TradingAgents-CN</strong> is based on <strong>TradingAgents</strong> Chinese localized version of project development.
              The original project was developed by the Tauric Research team and is an innovative multi-agent stock analysis framework.
            </p>
            <p>
              We have made the following improvements and expansions based on the original project:
            </p>
            <ul class="origin-improvements">
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>v3.0 Workflow engine:</strong>Configurable architecture, supporting Agent workshop, Skill center and MCP server</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Full process analysis assistance:</strong>Complete process support from data collection to report generation, multi-scenario analysis and learning</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Chinese localization:</strong>Optimized for China s A-share market, integrating Chinese data sources such as Tushare/AKShare</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Full Chinese support:</strong>Optimized for China s A-share market, supporting Chinese data sources and analysis</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Modern web interface:</strong>Based on Vue 3 + Element Plus Developed new front-end interface</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Enhanced data sources:</strong>Integrate Chinese market data sources such as Tushare and AKShare</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Multiple LLM support:</strong>Supports domestic and foreign mainstream large language models (OpenAI, Claude, Zhipu AI, DeepSeek, etc.). It is recommended to use the Volcano Ark platform to uniformly access multi-vendor models.</span>
              </li>
              <li>
                <el-icon class="check-icon"><CircleCheck /></el-icon>
                <span><strong>Batch analysis function:</strong>Supports batch stock analysis and task management, suitable for comparative learning</span>
              </li>
            </ul>
            <p class="origin-thanks">
              <el-icon><Star /></el-icon>
              <strong>special thanks</strong> Tauric Research The team s open source contributions provide us with excellent technical foundation and design concepts.
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Sponsor (hidden in JD Cloud version) -->
    <div class="sponsor-section" v-if="!isJdyun">
      <div class="section-header">
        <h2 class="section-title">Sponsor</h2>
        <p class="section-subtitle">Thanks to the following companies for their sponsorship and support of this project</p>
      </div>
      <div class="sponsor-content">
        <div class="sponsor-card">
          <div class="sponsor-header">
            <div class="sponsor-icon">
              <el-icon><Star /></el-icon>
            </div>
            <div class="sponsor-info">
              <h3>Byte Volcano Engine</h3>
            </div>
          </div>
          <div class="sponsor-description">
            <p>Thanks to Byte Volcano Engine for sponsoring this project!</p>
            <p><strong> [Exclusive event discount] 19 yuan Tokens package!</strong>Xiangbyte s self-developed bean bag model+The full-blooded version of the open source SOTA model covers text, VLM, and image generation, and is available in one stop for all modes: Seed-2.1, Seedream-5.0, GLM-5.2, DeepSeek, etc. Not only programming, but also capable of solving Agent s complex long-term tasks.</p>
            <p>
              <el-button type="primary" size="small" @click="goToVolcengine">
                <el-icon><Link /></el-icon>
                Register and receive 25 million Tokens, go now
              </el-button>
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Contact us / JD Cloud version support channels -->
    <div class="contact-section">
      <div class="section-header" v-if="!isJdyun">
        <h2 class="section-title">Contact us</h2>
        <p class="section-subtitle">Get support, report questions or join community discussions</p>
      </div>
      <div class="section-header" v-else>
        <h2 class="section-title">Support and feedback</h2>
        <p class="section-subtitle">Exclusive support channel for JD Cloud Cooperation Edition</p>
      </div>

      <!-- Standard version contact channels -->
      <div class="contact-grid" v-if="!isJdyun">
        <div class="contact-card">
          <div class="contact-icon email">
            <el-icon><Message /></el-icon>
          </div>
          <h4>Email contact</h4>
          <p>hsliup@163.com</p>
          <span class="contact-desc">Technical support and business cooperation</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon qq">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <h4>QQ Communication group</h4>
          <p>1079484482</p>
          <span class="contact-desc">User communication and problem discussion</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon wechat">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <h4>WeChat public account</h4>
          <p>TradingAgents-CN</p>
          <span class="contact-desc">Latest news and tutorials</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon docs">
            <el-icon><Document /></el-icon>
          </div>
          <h4>Use documentation</h4>
          <p>
            <a href="https://mp.weixin.qq.com/s/ppsYiBncynxlsfKFG8uEbw"
               target="_blank"
               rel="noopener noreferrer"
               class="doc-link">
              View detailed documentation
            </a>
          </p>
          <span class="contact-desc">Complete usage guide and API documentation</span>
        </div>
      </div>

      <!-- JD Cloud version support channels -->
      <div class="contact-grid" v-else>
        <div class="contact-card">
          <div class="contact-icon wechat">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <h4>JD Cloud technical support</h4>
          <p>Contact your JD Cloud account manager</p>
          <span class="contact-desc">Issues such as account opening, permissions, speed limits, etc.</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon docs">
            <el-icon><Document /></el-icon>
          </div>
          <h4>System bug feedback</h4>
          <p>
            <a href="https://github.com/hsliuping/TradingAgents-CN-Pro/issues"
               target="_blank"
               rel="noopener noreferrer"
               class="doc-link">
              GitHub Issues
            </a>
          </p>
          <span class="contact-desc">Submit system defects and anomalies</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon email">
            <el-icon><Message /></el-icon>
          </div>
          <h4>Feature suggestions</h4>
          <p>within the system"feedback"button</p>
          <span class="contact-desc">Submit suggestions through the feedback portal in the upper right corner</span>
        </div>

        <div class="contact-card">
          <div class="contact-icon qq">
            <el-icon><Reading /></el-icon>
          </div>
          <h4>Use documentation</h4>
          <p>JD Cloud Edition User Manual</p>
          <span class="contact-desc">within the system"help"button to view the full manual</span>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="footer-section">
      <div class="footer-content">
        <p v-if="!isJdyun">&copy; 2025-2026 TradingAgents-CN. All rights reserved.</p>
        <p v-else>&copy; 2025-2026 TradingAgents-CN JD Cloud Cooperation Edition. All rights reserved.</p>
        <p v-if="!isJdyun">License description: The code in the tradingagents directory uses part of the original TradingAgents project code and follows the Apache 2.0 open source license; other parts are no longer open source because the code was stolen after version 1.0 was open sourced.</p>
        <p v-else>This system is supported by model services provided by JD Cloud and is only used for A-share research and study. All output does not constitute investment advice.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  TrendCharts,
  Search,
  Files,
  Document,
  Monitor,
  Setting,
  Message,
  ChatDotRound,
  Cpu,
  Star,
  Link,
  CircleCheck,
  DocumentCopy,
  Box,
  Key,
  DataAnalysis,
  Reading,
  ArrowRight
} from '@element-plus/icons-vue'
import { ApiClient } from '@/api/request'
import { isJdyunMode } from '@/utils/config'

const router = useRouter()
const isJdyun = computed(() => isJdyunMode())
const buildTime = ref(new Date().toLocaleString('zh-CN'))
const systemInfoLoading = ref(false)
const systemInfo = ref<{
  version?: string
  full_version?: string
  build_timestamp?: string
  build_date?: string
  build_unix?: number
  git_commit?: string
  build_type?: string
}>({})

// Version status text (automatically determined based on version number)
const versionStatusText = computed(() => {
  const v = systemInfo.value.version || systemInfo.value.full_version || ''
  if (v.includes('beta') || v.includes('alpha') || v.includes('rc')) return 'beta version'
  if (v.includes('dev')) return 'Development version'
  return 'Official version'
})

// Version status style class
const versionStatusClass = computed(() => {
  const text = versionStatusText.value
  if (text === 'beta version') return 'status-beta'
  if (text === 'Development version') return 'status-dev'
  return 'status-stable'
})

// Load system information
const loadSystemInfo = async () => {
  systemInfoLoading.value = true
  try {
    const response = await ApiClient.get('/api/system/info')
    if (response.success && response.data) {
      systemInfo.value = response.data
    }
  } catch (error) {
    console.error('Failed to load system information:', error)
  } finally {
    systemInfoLoading.value = false
  }
}

// Format build date
const formatBuildDate = (dateStr: string) => {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: 'Asia/Shanghai'
    })
  } catch {
    return dateStr
  }
}

// Format build type
const formatBuildType = (type: string) => {
  const typeMap: Record<string, string> = {
    docker: 'Docker mirror',
    installer: 'Windows Installation version',
    portable: 'Portable version'
  }
  return typeMap[type] || type
}

// Copy version information
const copyVersionInfo = async () => {
  const info = [
    `version number: ${systemInfo.value.version || 'v3.0'}`,
    systemInfo.value.full_version ? `full version: ${systemInfo.value.full_version}` : '',
    systemInfo.value.build_date ? `Build time: ${formatBuildDate(systemInfo.value.build_date)}` : '',
    systemInfo.value.build_type ? `Build type: ${formatBuildType(systemInfo.value.build_type)}` : '',
    systemInfo.value.git_commit ? `Git Submit: ${systemInfo.value.git_commit}` : ''
  ].filter(Boolean).join('\n')

  try {
    await navigator.clipboard.writeText(info)
    ElMessage.success('Version information copied to clipboard')
  } catch (error) {
    console.error('Copy failed:', error)
    ElMessage.error('Copy failed, please copy manually')
  }
}

const goToAnalysis = () => {
  router.push('/analysis/single')
}

const goToLearning = () => {
  router.push('/learning')
}

const goToVolcengine = () => {
  window.open('https://www.volcengine.com/product/ark?utm_campaign=hw&utm_content=TradingAgents-CN&utm_medium=devrel-1&utm_source=OWO&utm_term=TradingAgents-CN', '_blank')
}

// Get system information when page loads
onMounted(() => {
  loadSystemInfo()
})
</script>

<style lang="scss" scoped>
.about {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;

  // Hero Section
  .hero-section {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 60px 40px;
    margin-bottom: 48px;
    color: white;
    position: relative;
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="white" opacity="0.1"/><circle cx="75" cy="75" r="1" fill="white" opacity="0.1"/><circle cx="50" cy="10" r="0.5" fill="white" opacity="0.1"/><circle cx="10" cy="60" r="0.5" fill="white" opacity="0.1"/><circle cx="90" cy="40" r="0.5" fill="white" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
      pointer-events: none;
    }

    .hero-content {
      display: flex;
      align-items: center;
      gap: 60px;
      position: relative;
      z-index: 1;
    }

    .hero-text {
      flex: 1;

      .hero-title {
        font-size: 48px;
        font-weight: 700;
        margin: 0 0 16px 0;
        line-height: 1.2;

        .version-badge {
          display: inline-block;
          background: rgba(255, 255, 255, 0.2);
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 14px;
          font-weight: 500;
          margin-left: 16px;
          backdrop-filter: blur(10px);
        }
      }

      .hero-subtitle {
        font-size: 24px;
        font-weight: 500;
        margin: 0 0 16px 0;
        opacity: 0.9;
      }

      .hero-description {
        font-size: 16px;
        line-height: 1.6;
        margin: 0 0 20px 0;
        opacity: 0.8;
        max-width: 600px;
      }

      .hero-positioning {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin: 0 0 20px 0;

        .positioning-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          padding: 6px 12px;
          background: rgba(255, 255, 255, 0.15);
          border-radius: 16px;
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.2);

          .el-icon {
            font-size: 14px;
            color: #4ade80;
          }
        }
      }

      .hero-acknowledgment {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        opacity: 0.9;
        margin-bottom: 32px;
        padding: 12px 16px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        max-width: 600px;

        .el-icon {
          font-size: 16px;
          color: #ffd700;
        }

        a {
          color: white;
          text-decoration: none;
          font-weight: 500;
          border-bottom: 1px solid rgba(255, 255, 255, 0.3);
          transition: all 0.3s ease;

          &:hover {
            border-bottom-color: white;
          }
        }
      }

      .hero-actions {
        display: flex;
        gap: 16px;

        .el-button {
          padding: 12px 24px;
          font-size: 16px;
          border-radius: 8px;

          &.el-button--primary {
            background: white;
            color: #667eea;
            border: none;

            &:hover {
              background: rgba(255, 255, 255, 0.9);
              transform: translateY(-2px);
            }
          }

          &:not(.el-button--primary) {
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
            backdrop-filter: blur(10px);

            &:hover {
              background: rgba(255, 255, 255, 0.2);
              transform: translateY(-2px);
            }
          }
        }
      }
    }

    .hero-visual {
      .hero-card {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(20px);
        border-radius: 16px;
        padding: 32px;
        border: 1px solid rgba(255, 255, 255, 0.2);

        .hero-stats {
          display: flex;
          gap: 24px;

          .stat-item {
            text-align: center;

            .stat-number {
              font-size: 32px;
              font-weight: 700;
              margin-bottom: 8px;
            }

            .stat-label {
              font-size: 14px;
              opacity: 0.8;
            }
          }
        }
      }
    }
  }

  // Learning Banner
  .learning-banner {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 48px;

    .banner-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
    }

    .banner-text {
      display: flex;
      align-items: center;
      gap: 16px;

      .banner-icon {
        font-size: 32px;
        color: #0284c7;
      }

      h3 {
        margin: 0 0 4px 0;
        font-size: 16px;
        color: #0c4a6e;
      }

      p {
        margin: 0;
        font-size: 13px;
        color: #075985;
        line-height: 1.5;
      }
    }
  }

  // Section Headers
  .section-header {
    text-align: center;
    margin-bottom: 48px;

    .section-title {
      font-size: 36px;
      font-weight: 700;
      color: var(--el-text-color-primary);
      margin: 0 0 16px 0;
    }

    .section-subtitle {
      font-size: 18px;
      color: var(--el-text-color-regular);
      margin: 0;
      max-width: 600px;
      margin-left: auto;
      margin-right: auto;
    }
  }

  // Features Section
  .features-section {
    margin-bottom: 80px;

    .features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
      gap: 24px;

      .feature-card {
        background: var(--el-bg-color);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border: 1px solid var(--el-border-color-lighter);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-success));
        }

        &:hover {
          transform: translateY(-8px);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
        }

        .feature-header {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 16px;

          .feature-icon {
            width: 56px;
            height: 56px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            color: white;

            &.primary {
              background: linear-gradient(135deg, var(--el-color-primary), #667eea);
            }

            &.success {
              background: linear-gradient(135deg, var(--el-color-success), #52c41a);
            }

            &.warning {
              background: linear-gradient(135deg, var(--el-color-warning), #faad14);
            }

            &.info {
              background: linear-gradient(135deg, var(--el-color-info), #1890ff);
            }

            &.danger {
              background: linear-gradient(135deg, var(--el-color-danger), #ff4d4f);
            }
          }

          h3 {
            margin: 0;
            font-size: 20px;
            font-weight: 600;
            color: #1a202c;
          }
        }

        p {
          color: var(--el-text-color-regular);
          line-height: 1.6;
          margin: 0 0 20px 0;
        }

        .feature-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;

          .el-tag {
            border-radius: 12px;
            border: none;
            font-size: 12px;
          }
        }
      }
    }
  }

  // Origin Section
  .origin-section {
    margin-bottom: 80px;

    .origin-content {
      max-width: 900px;
      margin: 0 auto;

      .origin-card {
        background: var(--el-bg-color);
        border-radius: 16px;
        padding: 40px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border: 1px solid var(--el-border-color-lighter);
        position: relative;
        overflow: hidden;

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, #667eea, #764ba2);
        }

        .origin-header {
          display: flex;
          align-items: center;
          gap: 20px;
          margin-bottom: 32px;
          padding-bottom: 24px;
          border-bottom: 2px solid var(--el-border-color-lighter);

          .origin-icon {
            width: 64px;
            height: 64px;
            border-radius: 16px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            color: white;
            flex-shrink: 0;
          }

          .origin-info {
            flex: 1;

            h3 {
              margin: 0 0 8px 0;
              font-size: 24px;
              font-weight: 700;
              color: var(--el-text-color-primary);
            }

            .origin-link {
              display: inline-flex;
              align-items: center;
              gap: 6px;
              color: var(--el-color-primary);
              text-decoration: none;
              font-size: 14px;
              font-weight: 500;
              transition: all 0.3s ease;

              .el-icon {
                font-size: 14px;
              }

              &:hover {
                color: #667eea;
                text-decoration: underline;
              }
            }
          }
        }

        .origin-description {
          p {
            color: var(--el-text-color-regular);
            line-height: 1.8;
            margin: 0 0 20px 0;
            font-size: 15px;

            strong {
              color: var(--el-text-color-primary);
              font-weight: 600;
            }
          }

          .origin-improvements {
            list-style: none;
            padding: 0;
            margin: 24px 0;

            li {
              display: flex;
              align-items: flex-start;
              gap: 12px;
              padding: 12px 0;
              color: var(--el-text-color-regular);
              line-height: 1.6;
              font-size: 15px;

              .check-icon {
                color: var(--el-color-success);
                font-size: 18px;
                margin-top: 2px;
                flex-shrink: 0;
              }

              strong {
                color: var(--el-text-color-primary);
                font-weight: 600;
              }
            }
          }

          .origin-thanks {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 32px;
            padding: 20px;
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
            border-radius: 12px;
            border-left: 4px solid #667eea;
            font-size: 15px;
            color: var(--el-text-color-regular);

            .el-icon {
              color: #ffd700;
              font-size: 20px;
              flex-shrink: 0;
            }

            strong {
              color: var(--el-text-color-primary);
              font-weight: 600;
            }
          }
        }
      }
    }
  }

  // Tech Section
  .tech-section {
    margin-bottom: 80px;

    .tech-stack {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 32px;

      .tech-category {
        background: var(--el-bg-color);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border: 1px solid var(--el-border-color-lighter);
        transition: all 0.3s ease;

        &:hover {
          transform: translateY(-4px);
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
        }

        .tech-header {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 24px;

          .tech-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: white;

            &.frontend {
              background: linear-gradient(135deg, #42b883, #35495e);
            }

            &.backend {
              background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            }

            &.ai {
              background: linear-gradient(135deg, #a55eea, #26de81);
            }
          }

          h3 {
            margin: 0;
            font-size: 20px;
            font-weight: 600;
            color: #1a202c;
          }
        }

        .tech-list {
          .tech-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--el-border-color-extra-light);

            &:last-child {
              border-bottom: none;
            }

            .tech-name {
              font-weight: 500;
              color: #1a202c;
            }

            .tech-desc {
              font-size: 14px;
              color: var(--el-text-color-regular);
            }
          }
        }
      }
    }
  }

  // Version Section
  .version-section {
    margin-bottom: 80px;

    .version-info {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 32px;

      .version-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 32px;
        color: white;
        position: relative;
        overflow: hidden;

        &::before {
          content: '';
          position: absolute;
          top: -50%;
          right: -50%;
          width: 100%;
          height: 100%;
          background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
          pointer-events: none;
        }

        .version-main {
          text-align: center;
          margin-bottom: 24px;
          position: relative;
          z-index: 1;

          .version-number {
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 8px;
          }

          .version-status {
            background: rgba(255, 255, 255, 0.2);
            padding: 4px 16px;
            border-radius: 20px;
            font-size: 14px;
            display: inline-block;
            backdrop-filter: blur(10px);

            &.status-stable {
              background: #67c23a;
              color: white;
            }

            &.status-beta {
              background: #e6a23c;
              color: white;
            }

            &.status-dev {
              background: #909399;
              color: white;
            }
          }
        }

        .version-details {
          position: relative;
          z-index: 1;

          .version-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);

            &:last-child {
              border-bottom: none;
            }

            .label {
              opacity: 0.8;
            }

            .value {
              font-weight: 500;

              &.code {
                font-family: 'Courier New', monospace;
                font-size: 13px;
                background: rgba(255, 255, 255, 0.1);
                padding: 2px 8px;
                border-radius: 4px;
              }
            }
          }
        }

        .version-actions {
          margin-top: 24px;
          text-align: center;
          position: relative;
          z-index: 1;
        }
      }

      .framework-info {
        background: var(--el-bg-color);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border: 1px solid var(--el-border-color-lighter);

        h4 {
          margin: 0 0 24px 0;
          font-size: 20px;
          font-weight: 600;
          color: #1a202c;
        }

        .framework-list {
          .framework-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--el-border-color-extra-light);

            &:last-child {
              border-bottom: none;
            }

            .name {
              font-weight: 500;
              color: #1a202c;
            }

            .version {
              background: var(--el-color-primary-light-9);
              color: var(--el-color-primary);
              padding: 4px 12px;
              border-radius: 12px;
              font-size: 12px;
              font-weight: 500;
            }
          }
        }
      }
    }
  }
  // Contact Section
  .contact-section {
    margin-bottom: 80px;

    .contact-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 24px;

      .contact-card {
        background: var(--el-bg-color);
        border-radius: 16px;
        padding: 32px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border: 1px solid var(--el-border-color-lighter);
        transition: all 0.3s ease;

        &:hover {
          transform: translateY(-4px);
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
        }

        .contact-icon {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 20px;
          font-size: 24px;
          color: white;

          &.email {
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
          }

          &.qq {
            background: linear-gradient(135deg, #12c2e9, #c471ed);
          }

          &.wechat {
            background: linear-gradient(135deg, #07c160, #00d4aa);
          }

          &.docs {
            background: linear-gradient(135deg, #667eea, #764ba2);
          }
        }

        h4 {
          margin: 0 0 12px 0;
          font-size: 18px;
          font-weight: 600;
          color: #1a202c;
        }

        p {
          margin: 0 0 8px 0;
          font-size: 16px;
          font-weight: 500;
          color: #1a202c;

          .doc-link {
            color: var(--el-color-primary);
            text-decoration: none;
            font-weight: 500;

            &:hover {
              text-decoration: underline;
            }
          }
        }

        .contact-desc {
          font-size: 14px;
          color: var(--el-text-color-regular);
        }
      }
    }
  }

  // Footer Section
  .footer-section {
    text-align: center;
    padding: 40px 0;
    border-top: 1px solid var(--el-border-color-extra-light);
    color: var(--el-text-color-regular);

    .footer-content {
      p {
        margin: 8px 0;
        font-size: 14px;
      }
    }
  }
}

// Responsive design
@media (max-width: 1024px) {
  .about {
    .version-section .version-info {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 768px) {
  .about {
    padding: 0 16px;

    .hero-section {
      padding: 40px 24px;

      .hero-content {
        flex-direction: column;
        gap: 32px;
        text-align: center;
      }

      .hero-text {
        .hero-title {
          font-size: 36px;

          .version-badge {
            display: block;
            margin: 16px auto 0;
            width: fit-content;
          }
        }

        .hero-subtitle {
          font-size: 20px;
        }

        .hero-actions {
          justify-content: center;
          flex-wrap: wrap;
        }
      }
    }

    .section-header {
      .section-title {
        font-size: 28px;
      }

      .section-subtitle {
        font-size: 16px;
      }
    }

    .features-section .features-grid {
      grid-template-columns: 1fr;
    }

    .tech-section .tech-stack {
      grid-template-columns: 1fr;
    }

    .contact-section .contact-grid {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 480px) {
  .about {
    .hero-section {
      padding: 32px 20px;

      .hero-text {
        .hero-title {
          font-size: 28px;
        }

        .hero-subtitle {
          font-size: 18px;
        }

        .hero-actions {
          .el-button {
            padding: 10px 20px;
            font-size: 14px;
          }
        }
      }
    }

    .features-section .features-grid .feature-card {
      padding: 24px;
    }

    .tech-section .tech-stack .tech-category {
      padding: 24px;
    }

    .contact-section .contact-grid .contact-card {
      padding: 24px;
    }
  }

  // Sponsor Section
  .sponsor-section {
    margin-bottom: 80px;

    .sponsor-content {
      max-width: 900px;
      margin: 0 auto;

      .sponsor-card {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.05), rgba(236, 72, 153, 0.05));
        border-radius: 16px;
        padding: 40px;
        border: 2px solid rgba(102, 126, 234, 0.2);
        position: relative;
        overflow: hidden;

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, #667eea, #ec4899);
        }

        .sponsor-header {
          display: flex;
          gap: 20px;
          align-items: center;
          margin-bottom: 24px;

          .sponsor-icon {
            width: 56px;
            height: 56px;
            border-radius: 16px;
            background: linear-gradient(135deg, #667eea, #ec4899);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            color: white;
            flex-shrink: 0;
          }

          .sponsor-info {
            flex: 1;

            h3 {
              margin: 0;
              font-size: 22px;
              font-weight: 700;
              color: var(--el-text-color-primary);
            }
          }
        }

        .sponsor-description {
          p {
            color: var(--el-text-color-regular);
            line-height: 1.8;
            margin: 0 0 16px 0;
            font-size: 15px;

            strong {
              color: var(--el-color-primary);
              font-weight: 600;
            }
          }
        }
      }
    }
  }
}
</style>
