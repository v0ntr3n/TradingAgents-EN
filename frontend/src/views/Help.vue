<template>
  <div class="help-page">
    <!-- Page header -->
    <div class="help-header">
      <div class="help-header-content">
        <h1 class="help-title">
          <el-icon><Document /></el-icon>
          {{ manualTitle }}
        </h1>
        <p class="help-subtitle">{{ manualDescription }}</p>
      </div>
      <div class="help-header-actions">
        <el-button text type="primary" @click="scrollToTop">
          <el-icon><Top /></el-icon>
          back to top
        </el-button>
        <el-button text type="primary" @click="downloadManual">
          <el-icon><Download /></el-icon>
          Download brochure
        </el-button>
      </div>
    </div>

    <!-- Subject: content + Sidebar table of contents -->
    <div class="help-body" v-loading="loading" element-loading-text="Loading manual...">
      <!-- Left: sidebar directory -->
      <aside class="help-toc" :class="{ 'toc-collapsed': tocCollapsed }">
        <div class="toc-header">
          <span class="toc-title">Directory</span>
          <el-button
            text
            size="small"
            class="toc-toggle"
            @click="tocCollapsed = !tocCollapsed"
            :title="tocCollapsed ? 'Expand directory' : 'Collapse table of contents'"
          >
            <el-icon><Fold v-if="!tocCollapsed" /><Expand v-else /></el-icon>
          </el-button>
        </div>
        <el-scrollbar v-show="!tocCollapsed" max-height="calc(100vh - 220px)">
          <ul class="toc-list">
            <li
              v-for="heading in tableOfContents"
              :key="heading.id"
              :class="['toc-item', `toc-level-${heading.level}`, { 'toc-active': heading.id === activeHeadingId }]"
              @click="scrollToHeading(heading.id)"
              :title="heading.text"
            >
              {{ heading.text }}
            </li>
          </ul>
        </el-scrollbar>
      </aside>

      <!-- Right: Manual contents -->
      <main class="help-content" ref="contentRef">
        <div class="markdown-body" v-html="manualHtml"></div>

        <!-- bottom back to top button -->
        <div class="content-footer" v-if="!loading && manualHtml">
          <el-divider />
          <p class="footer-tip">
            <el-icon><InfoFilled /></el-icon>
            The content of this manual is generated with AI assistance and is for learning and research purposes only and does not constitute investment advice.
          </p>
          <el-button type="primary" plain @click="scrollToTop">
            <el-icon><Top /></el-icon>
            back to top
          </el-button>
        </div>
      </main>
    </div>

    <!-- Mobile floating directory button -->
    <el-button
      v-if="!loading && manualHtml"
      class="mobile-toc-fab"
      type="primary"
      circle
      @click="mobileTocVisible = true"
    >
      <el-icon><List /></el-icon>
    </el-button>

    <!-- Mobile directory drawer -->
    <el-drawer
      v-model="mobileTocVisible"
      title="Directory"
      direction="ltr"
      size="280px"
    >
      <el-scrollbar max-height="calc(100vh - 100px)">
        <ul class="toc-list mobile-toc-list">
          <li
            v-for="heading in tableOfContents"
            :key="heading.id"
            :class="['toc-item', `toc-level-${heading.level}`]"
            @click="scrollToHeading(heading.id); mobileTocVisible = false"
            :title="heading.text"
          >
            {{ heading.text }}
          </li>
        </ul>
      </el-scrollbar>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  Document,
  Top,
  Download,
  Fold,
  Expand,
  List,
  InfoFilled
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'
import {
  getUserManualContent,
  getUserManualTitle,
  getUserManualDescription
} from '@/config/userManualContent'
import { isJdyunMode } from '@/utils/config'

const manualTitle = ref(getUserManualTitle())
const manualDescription = ref(getUserManualDescription())
const manualHtml = ref('')
const loading = ref(true)
const contentRef = ref<HTMLElement | null>(null)
const tocCollapsed = ref(false)
const mobileTocVisible = ref(false)

interface TocItem {
  id: string
  text: string
  level: number
}

const tableOfContents = ref<TocItem[]>([])
const activeHeadingId = ref<string>('')

let markdownRaw = ''

// Load manual content
const loadManual = async () => {
  loading.value = true
  try {
    markdownRaw = await getUserManualContent()
    manualHtml.value = renderMarkdown(markdownRaw)

    // Wait for the DOM rendering to complete before extracting the directory
    await nextTick()
    await nextTick()
    extractTableOfContents()
  } catch (err: any) {
    console.error('[Help] Failed to load user manual:', err)
    ElMessage.error('Failed to load user manual:' + (err.message || 'unknown error'))
    manualHtml.value = '<p style="color: var(--el-color-danger);">Failed to load the user manual, please refresh the page and try again.</p>'
  } finally {
    loading.value = false
  }
}

// Extract table of contents (scan h1-h4 from rendered HTML)
const extractTableOfContents = () => {
  const contentDiv = contentRef.value
  if (!contentDiv) return

  const headings = contentDiv.querySelectorAll('h1, h2, h3, h4')
  tableOfContents.value = []
  const seenText = new Set<string>()

  headings.forEach((heading, index) => {
    const level = parseInt(heading.tagName.charAt(1))
    const text = (heading.textContent || '').trim()
    if (!text) return

    // Skip duplicate titles (the directory list at the beginning of the manual will be marked and rendered as a link to avoid duplication)
    if (seenText.has(text)) return
    seenText.add(text)

    const id = `heading-${index}`
    heading.id = id

    tableOfContents.value.push({ id, text, level })
  })

  // The first title is activated by default
  if (tableOfContents.value.length > 0) {
    activeHeadingId.value = tableOfContents.value[0].id
  }
}

// Scroll to specified title
const scrollToHeading = (id: string) => {
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeHeadingId.value = id
  }
}

// scroll to top
const scrollToTop = () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// Download brochure
const downloadManual = () => {
  if (!markdownRaw) {
    ElMessage.warning('The manual content has not been loaded yet')
    return
  }
  try {
    const fileName = isJdyunMode()
      ? 'jdyun-user-manual-v3.0.md'
      : 'user-manual-v3.0.md'
    const blob = new Blob([markdownRaw], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('Manual download has started')
  } catch (err: any) {
    console.error('[Help] Download manual failed:', err)
    ElMessage.error('Download failed:' + (err.message || 'unknown error'))
  }
}

// Scroll monitoring: automatically highlight the current reading chapter
const handleScroll = () => {
  if (tableOfContents.value.length === 0) return

  // Find the title closest to the top of the viewport at the current scroll position
  let currentId = tableOfContents.value[0].id
  for (const item of tableOfContents.value) {
    const el = document.getElementById(item.id)
    if (!el) continue
    const rect = el.getBoundingClientRect()
    // The top of the header is within 100px above the top of the viewport (allowing for header height)
    if (rect.top <= 120) {
      currentId = item.id
    } else {
      break
    }
  }
  activeHeadingId.value = currentId
}

onMounted(() => {
  loadManual()
  window.addEventListener('scroll', handleScroll, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style lang="scss" scoped>
.help-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;

  .help-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
    padding: 24px 32px;
    background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-fill-color-light) 100%);
    border-radius: 12px;
    border: 1px solid var(--el-border-color-lighter);

    .help-header-content {
      flex: 1;
      min-width: 0;
    }

    .help-title {
      font-size: 26px;
      font-weight: 700;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
      display: flex;
      align-items: center;
      gap: 12px;

      .el-icon {
        font-size: 28px;
        color: var(--el-color-primary);
      }
    }

    .help-subtitle {
      font-size: 14px;
      color: var(--el-text-color-regular);
      margin: 0;
    }

    .help-header-actions {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex-shrink: 0;
    }
  }

  .help-body {
    display: flex;
    gap: 24px;
    align-items: flex-start;
  }

  .help-toc {
    position: sticky;
    top: 80px;
    width: 280px;
    flex-shrink: 0;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    padding: 12px;
    max-height: calc(100vh - 120px);
    overflow: hidden;
    display: flex;
    flex-direction: column;

    &.toc-collapsed {
      width: 56px;

      .toc-list {
        display: none;
      }
    }

    .toc-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--el-border-color-lighter);
      margin-bottom: 8px;

      .toc-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--el-text-color-primary);
      }

      .toc-toggle {
        padding: 4px;
      }
    }
  }

  .toc-list {
    list-style: none;
    margin: 0;
    padding: 0;

    .toc-item {
      padding: 6px 12px;
      font-size: 13px;
      line-height: 1.6;
      color: var(--el-text-color-regular);
      cursor: pointer;
      border-radius: 4px;
      transition: all 0.2s ease;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 2px;

      &:hover {
        background: var(--el-fill-color-light);
        color: var(--el-color-primary);
      }

      &.toc-active {
        background: var(--el-color-primary-light-9);
        color: var(--el-color-primary);
        font-weight: 600;
      }

      &.toc-level-1 {
        font-weight: 600;
        font-size: 14px;
        color: var(--el-text-color-primary);
        margin-top: 8px;

        &:first-child {
          margin-top: 0;
        }
      }

      &.toc-level-2 {
        padding-left: 16px;
      }

      &.toc-level-3 {
        padding-left: 28px;
        font-size: 12px;
      }

      &.toc-level-4 {
        padding-left: 40px;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
  }

  .help-content {
    flex: 1;
    min-width: 0;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    padding: 32px 40px;

    .content-footer {
      margin-top: 32px;
      text-align: center;

      .footer-tip {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        font-size: 13px;
        color: var(--el-text-color-secondary);
        margin: 16px 0;
      }
    }
  }
}

// Markdown Content styles (applied to content rendered by v-html)
:deep(.markdown-body) {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: var(--el-text-color-primary);
  line-height: 1.8;
  font-size: 14px;

  h1, h2, h3, h4, h5, h6 {
    color: var(--el-text-color-primary);
    font-weight: 600;
    margin-top: 28px;
    margin-bottom: 14px;
    line-height: 1.4;
    scroll-margin-top: 80px;
  }

  h1 {
    font-size: 26px;
    border-bottom: 2px solid var(--el-border-color);
    padding-bottom: 8px;
  }

  h2 {
    font-size: 22px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    padding-bottom: 6px;
  }

  h3 {
    font-size: 18px;
  }

  h4 {
    font-size: 16px;
  }

  p {
    margin: 12px 0;
  }

  a {
    color: var(--el-color-primary);
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }

  ul, ol {
    margin: 12px 0;
    padding-left: 28px;

    li {
      margin: 6px 0;
      line-height: 1.8;
    }
  }

  blockquote {
    margin: 16px 0;
    padding: 12px 16px;
    border-left: 4px solid var(--el-color-primary);
    background: var(--el-fill-color-light);
    border-radius: 4px;
    color: var(--el-text-color-regular);

    p {
      margin: 6px 0;
    }
  }

  code {
    background: var(--el-fill-color-dark);
    color: var(--el-color-danger);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
  }

  pre {
    background: var(--el-fill-color-darker, #1e1e1e);
    color: #e6e6e6;
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 16px 0;
    font-size: 13px;
    line-height: 1.6;

    code {
      background: transparent;
      color: inherit;
      padding: 0;
      font-size: inherit;
    }
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 13px;

    th, td {
      border: 1px solid var(--el-border-color);
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background: var(--el-fill-color-light);
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    tr:hover td {
      background: var(--el-fill-color-lighter);
    }
  }

  img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
    margin: 12px 0;
  }

  hr {
    border: none;
    border-top: 1px solid var(--el-border-color);
    margin: 24px 0;
  }

  strong {
    color: var(--el-text-color-primary);
    font-weight: 600;
  }

  // Leave head space when anchor point jumps
  :target {
    scroll-margin-top: 80px;
  }
}

// Mobile floating directory button
.mobile-toc-fab {
  display: none;
  position: fixed;
  right: 24px;
  bottom: 80px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

// Responsive design
@media (max-width: 1024px) {
  .help-page {
    .help-toc {
      display: none;
    }

    .help-content {
      padding: 20px 16px;
    }
  }

  .mobile-toc-fab {
    display: inline-flex;
  }

  .mobile-toc-list {
    .toc-item {
      &.toc-level-1 { padding-left: 8px; }
      &.toc-level-2 { padding-left: 20px; }
      &.toc-level-3 { padding-left: 32px; }
      &.toc-level-4 { padding-left: 44px; }
    }
  }
}

@media (max-width: 768px) {
  .help-page {
    padding: 12px;

    .help-header {
      padding: 16px 20px;
      flex-direction: column;
      gap: 12px;

      .help-title {
        font-size: 20px;

        .el-icon {
          font-size: 22px;
        }
      }

      .help-subtitle {
        font-size: 13px;
      }

      .help-header-actions {
        flex-direction: row;
        width: 100%;
      }
    }

    .help-content {
      padding: 16px 12px;

      :deep(.markdown-body) {
        font-size: 13px;

        h1 { font-size: 20px; }
        h2 { font-size: 18px; }
        h3 { font-size: 16px; }
        h4 { font-size: 14px; }
      }
    }
  }
}
</style>
