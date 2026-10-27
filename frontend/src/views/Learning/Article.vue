<template>
  <div class="learning-article-wrapper">
    <!-- Page header -->
    <el-page-header @back="goBack" :content="article.title">
      <template #extra>
        <el-button type="primary" :icon="Download" @click="downloadArticle">Download</el-button>
      </template>
    </el-page-header>

    <!-- Main container: articles + sidebar -->
    <div class="learning-article">
      <div class="article-container">
        <div class="article-meta">
          <el-tag :type="article.categoryType" size="small">{{ article.category }}</el-tag>
          <span class="read-time">
            <el-icon><Clock /></el-icon>
            {{ article.readTime }}
          </span>
          <span class="views">
            <el-icon><View /></el-icon>
            {{ article.views }}
          </span>
          <span class="update-time">updated on {{ article.updateTime }}</span>
        </div>

        <div class="article-content" v-html="article.content"></div>

        <div class="article-footer">
          <el-divider />
          <div class="navigation">
            <el-button v-if="prevArticle" @click="navigateToArticle(prevArticle.id)">
              <el-icon><ArrowLeft /></el-icon>
              Previous article:{{ prevArticle.title }}
            </el-button>
            <el-button v-if="nextArticle" @click="navigateToArticle(nextArticle.id)">
              Next article:{{ nextArticle.title }}
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <!-- Sidebar table of contents -->
      <div class="article-toc">
        <div class="toc-title">Directory</div>
        <ul class="toc-list">
          <li v-for="heading in tableOfContents" :key="heading.id"
              :class="['toc-item', `toc-level-${heading.level}`]"
              @click="scrollToHeading(heading.id)">
            {{ heading.text }}
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Clock, View, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const route = useRoute()
const router = useRouter()

const articleId = computed(() => route.params.id as string)

// Fallback: No integration Mermaid

// Article registration form: supports local Markdown or external links (externalUrl)
type ArticleInfo = {
  title: string
  category: string
  categoryType: any
  readTime: string
  loader?: () => Promise<any>
  externalUrl?: string
}

const registry: Record<string, ArticleInfo> = {
  'what-is-llm': { title: 'What is a large language model (LLM)?', loader: () => import('../../../../docs/02-user-guide/learning-01-ai-basics/what-is-llm.md?raw'), category: 'AI basic knowledge', categoryType: 'primary', readTime: '10 minutes' },
  'prompt-basics': { title: 'Prompt word basics', loader: () => import('../../../../docs/02-user-guide/learning-02-prompt-engineering/prompt-basics.md?raw'), category: 'prompt word project', categoryType: 'success', readTime: '10 minutes' },
  'best-practices': { title: 'Prompt Word Engineering Best Practices', loader: () => import('../../../../docs/02-user-guide/learning-02-prompt-engineering/best-practices.md?raw'), category: 'prompt word project', categoryType: 'success', readTime: '12 minutes' },
  'model-comparison': { title: 'Comparison and selection of large language models', loader: () => import('../../../../docs/02-user-guide/learning-03-model-selection/model-comparison.md?raw'), category: 'Model Selection Guide', categoryType: 'warning', readTime: '15 minutes' },
  'multi-agent-system': { title: 'Detailed explanation of multi-agent systems', loader: () => import('../../../../docs/02-user-guide/learning-04-analysis-principles/multi-agent-system.md?raw'), category: 'AI Analysis principle', categoryType: 'info', readTime: '15 minutes' },
  'risk-warnings': { title: 'AI Risks and Limitations of Stock Analysis', loader: () => import('../../../../docs/02-user-guide/learning-05-risks-limitations/risk-warnings.md?raw'), category: 'Risks and Limitations', categoryType: 'danger', readTime: '12 minutes' },
  'tradingagents-intro': { title: 'TradingAgents Project introduction', loader: () => import('../../../../docs/02-user-guide/learning-06-resources/tradingagents-intro.md?raw'), category: 'Source projects and papers', categoryType: 'primary', readTime: '15 minutes' },
  'paper-guide': { title: 'TradingAgents Paper interpretation', loader: () => import('../../../../docs/02-user-guide/learning-06-resources/paper-guide.md?raw'), category: 'Source projects and papers', categoryType: 'primary', readTime: '20 minutes' },
  'TradingAgents_Chinese version of the paper': { title: 'TradingAgents Chinese version of the paper', loader: () => import('../../../../docs/02-user-guide/learning-06-resources/paper-TradingAgents_Chinese version of the paper.md?raw'), category: 'Source projects and papers', categoryType: 'primary', readTime: '40 minutes' },
  // The quick start is changed to an external link. Click to jump directly to the WeChat article.
  'getting-started': { title: 'Quick start tutorial (external link)', externalUrl: 'https://mp.weixin.qq.com/s/uAk4RevdJHMuMvlqpdGUEw', category: 'Practical tutorial', categoryType: 'success', readTime: '10 minutes' },
  // User guide (trial version) external link
  'usage-guide-preview': { title: 'User Guide (Trial Version)', externalUrl: 'https://mp.weixin.qq.com/s/ppsYiBncynxlsfKFG8uEbw', category: 'Practical tutorial', categoryType: 'success', readTime: '15 minutes' },
  'general-questions': { title: 'FAQ', loader: () => import('../../../../docs/02-user-guide/learning-08-faq/general-questions.md?raw'), category: 'FAQ', categoryType: 'info', readTime: '15 minutes' }
}

// Article order is used for previous page/next page
const articleOrder = [
  'what-is-llm',
  'prompt-basics',
  'best-practices',
  'model-comparison',
  'multi-agent-system',
  'risk-warnings',
  'tradingagents-intro',
  'paper-guide',
  'TradingAgents_Chinese version of the paper',
  'getting-started',
  'usage-guide-preview',
  'general-questions'
]

// Current article data
const article = ref({
  id: '',
  title: '',
  category: '',
  categoryType: 'primary' as any,
  readTime: '',
  views: 0,
  updateTime: '',
  content: ''
})

// Directory
const tableOfContents = ref<{ id: string; text: string; level: number }[]>([])

const prevArticle = ref<{ id: string; title: string } | null>(null)
const nextArticle = ref<{ id: string; title: string } | null>(null)

const goBack = () => {
  router.back()
}

const downloadArticle = async () => {
  if (!article.value.id) return
  const info = registry[article.value.id]
  if (!info) {
    ElMessage.warning('Article resource not found')
    return
  }
  // External link articles: The download button opens directly in a new tab
  if (info.externalUrl) {
    window.open(info.externalUrl, '_blank')
    return
  }
  try {
    const mod = info.loader ? await info.loader() : ''
    const md: string = typeof mod === 'string' ? mod : (mod.default || '')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${article.value.id}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error(e)
    ElMessage.error('Download failed')
  }
}

const navigateToArticle = (id: string) => {
  router.push(`/learning/article/${id}`)
}

const scrollToHeading = (id: string) => {
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// Convert local links in markdown to in-app routed links
function convertLocalLinks(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html

  // handle all links
  const links = div.querySelectorAll('a')
  for (const link of links) {
    const href = link.getAttribute('href')
    if (href && href.endsWith('.md')) {
      // Extract file name (without extension)
      const fileName = href.split('/').pop()?.replace('.md', '')
      if (fileName && registry[fileName]) {
        // Convert to in-app routing link
        link.setAttribute('href', `/learning/article/${fileName}`)
        link.setAttribute('data-internal', 'true')
      }
    }
    // Rewrite the PDF link as a static resource path and open it in a new tab
    else if (href && href.endsWith('.pdf')) {
      const fileName = href.split('/').pop() || ''
      if (fileName) {
        // If the original link points to paper/ in docs, it will be mapped to /paper/
        const target = href.includes('/paper/') ? `/paper/${fileName}` : `/assets/${fileName}`
        link.setAttribute('href', target)
        link.setAttribute('target', '_blank')
        link.setAttribute('rel', 'noopener noreferrer')
      }
    }
  }

  return div.innerHTML
}

// Rewrite the image path in Markdown into the packaged resource URL (adapt to assets/ in the root directory of the warehouse)
function rewriteImageSrc(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html

  const assetMap: Record<string, string> = {
    // Unified mapping to the front-end public static resource directory to avoid Vite s construction warning for cross-root directory new URLs
    'assets/schema.png': '/assets/schema.png',
    'assets/analyst.png': '/assets/analyst.png',
    'assets/researcher.png': '/assets/researcher.png',
    'assets/trader.png': '/assets/trader.png',
    'assets/risk.png': '/assets/risk.png'
  }

  const imgs = div.querySelectorAll('img')
  for (const img of imgs) {
    const src = img.getAttribute('src') || ''
    // Absolute paths starting with / (such as /assets/...) will not be rewritten and will be handled by public static resources.
    if (src.startsWith('/')) continue
    for (const key in assetMap) {
      if (src.endsWith(key)) {
        img.setAttribute('src', assetMap[key])
        break
      }
    }
  }

  return div.innerHTML
}

// Fallback: Keep original markdown code blocks without converting to Mermaid containers

// Mermaid rendering removed, normal code blocks retained

// Load articles from markdown
async function loadArticle(id: string) {
  const info = registry[id]
  if (!info) {
    ElMessage.error('No article found')
    return
  }
  // External link articles: automatically open in a new tab, and the current page remains in the system
  if (info.externalUrl) {
    window.open(info.externalUrl, '_blank')
    article.value = {
      id,
      title: info.title,
      category: info.category,
      categoryType: info.categoryType,
      readTime: info.readTime,
      views: 0,
      updateTime: new Date().toISOString().slice(0, 10),
      content: ''
    }
    ElMessage.info('External page opened in new tab')
    return
  }
  article.value = {
    id,
    title: info.title,
    category: info.category,
    categoryType: info.categoryType,
    readTime: info.readTime,
    views: 0,
    updateTime: new Date().toISOString().slice(0, 10),
    content: ''
  }

  try {
    const mod = info.loader ? await info.loader() : ''
    const md: string = typeof mod === 'string' ? mod : (mod.default || '')
    // parse markdown -> html, And turn on the title anchor (compatible with Chinese)
    const renderer = new marked.Renderer()
    renderer.heading = function ({ tokens, depth, text }: any) {
      let htmlText = ''
      if (Array.isArray(tokens) && tokens.length) {
        htmlText = this.parser.parseInline(tokens)
      } else if (typeof text === 'string') {
        htmlText = marked.parseInline(text) as string
      }
      // 🔐 Security: sanitize HTML within heading to prevent XSS
      htmlText = DOMPurify.sanitize(htmlText) as string
      const plain = (htmlText || '').replace(/<[^>]+>/g, '')
      const id = plain
        .toLowerCase()
        .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
        .replace(/^-+|-+$/g, '')
      return `<h${depth} class="article-heading" id="${id}">${htmlText}</h${depth}>`
    }
    // 🔐 Security: Use renderMarkdown to render uniformly (including DOMPurify sanitization)
    let html = renderMarkdown(md)
    // Convert local article links
    html = convertLocalLinks(html)
    // Rewrite the image resource path to ensure correct loading from assets/ in the root directory of the warehouse
    html = rewriteImageSrc(html)
    article.value.content = html
    await nextTick()
    buildTOCFromHTML(html)
    buildPrevNext(id)
    // Set up internal link handling after DOM update
    setupInternalLinks()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to load article: Document resource cannot be accessed')
  }
}

function buildTOCFromHTML(html: string) {
  const div = document.createElement('div')
  div.innerHTML = html
  const headings = Array.from(div.querySelectorAll('h2, h3, h4')) as HTMLHeadingElement[]
  tableOfContents.value = headings.map(h => ({
    id: h.id || h.textContent?.trim().toLowerCase().replace(/\s+/g, '-') || '',
    text: h.textContent || '',
    level: Number(h.tagName.substring(1))
  }))
}

// Handle internal links after DOM update
function setupInternalLinks() {
  nextTick(() => {
    const container = document.querySelector('.article-content')
    if (!container) return

    const links = container.querySelectorAll('a[data-internal="true"]')
    for (const link of links) {
      link.addEventListener('click', (e) => {
        e.preventDefault()
        const href = link.getAttribute('href')
        if (href) {
          router.push(href)
        }
      })
    }
  })
}

function buildPrevNext(id: string) {
  const idx = articleOrder.indexOf(id)
  prevArticle.value = idx > 0 ? { id: articleOrder[idx - 1], title: registry[articleOrder[idx - 1]].title } : null
  nextArticle.value = idx >= 0 && idx < articleOrder.length - 1 ? { id: articleOrder[idx + 1], title: registry[articleOrder[idx + 1]].title } : null
}

onMounted(() => {
  loadArticle(articleId.value)
})

watch(articleId, (id) => {
  loadArticle(id)
})
</script>

<style scoped lang="scss">
.learning-article-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;

  :deep(.el-page-header) {
    padding: 16px 24px;
    background: var(--el-fill-color-blank);
    border-bottom: 1px solid var(--el-border-color);
    flex-shrink: 0;
  }

  /* PageHeader Title color improves contrast */
  :deep(.el-page-header__content),
  :deep(.el-page-header__title) {
    color: var(--el-text-color-primary);
    font-weight: 600;
  }
}

  .learning-article {
    display: flex;
    padding: 24px;
    max-width: 1400px;
    margin: 0 auto;
    gap: 24px;
    flex: 1;
    width: 100%;

    .article-container {
      flex: 1;
      min-width: 0;
      background: var(--el-fill-color-blank);
      border-radius: 8px;
      padding: 32px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);

      .article-meta {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 32px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--el-border-color);

        span {
          display: flex;
          align-items: center;
          font-size: 14px;
          color: var(--el-text-color-regular);

          .el-icon {
            margin-right: 4px;
          }
        }
      }

      .article-content {
        font-size: 16px;
        line-height: 1.8;
        color: var(--el-text-color-primary);

        :deep(h1) {
          font-size: 28px;
          margin: 36px 0 18px;
          padding-bottom: 10px;
          border-bottom: 2px solid var(--el-border-color);
          color: var(--el-text-color-primary);
          font-weight: 700;
        }

        :deep(h2) {
          font-size: 24px;
          margin: 32px 0 16px;
          padding-bottom: 8px;
          border-bottom: 2px solid var(--el-border-color);
          color: var(--el-text-color-primary);
          font-weight: 600;
        }

        :deep(h3) {
          font-size: 20px;
          margin: 24px 0 12px;
          color: var(--el-text-color-regular);
          font-weight: 600;
        }

        :deep(h4) {
          font-size: 18px;
          margin: 20px 0 10px;
          color: var(--el-text-color-regular);
          font-weight: 600;
        }

        :deep(p) {
          margin: 16px 0;
          text-align: justify;
        }

        :deep(ul), :deep(ol) {
          margin: 16px 0;
          padding-left: 24px;

          li {
            margin: 8px 0;
          }
        }

        :deep(code) {
          background: var(--el-fill-color-light);
          padding: 2px 6px;
          border-radius: 4px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 14px;
          color: var(--el-text-color-primary);
        }

        :deep(pre) {
          background: var(--el-fill-color-light);
          color: var(--el-text-color-primary);
          padding: 16px;
          border-radius: 8px;
          overflow-x: auto;
          margin: 16px 0;

          code {
            background: none;
            padding: 0;
            color: inherit;
          }
        }


        :deep(blockquote) {
          border-left: 4px solid var(--el-color-primary);
          margin: 16px 0;
          padding: 12px 16px;
          color: var(--el-text-color-secondary);
          background: var(--el-fill-color-light);
          border-radius: 4px;
        }

        // The image adapts to the width of the container to avoid being too small or overflowing
        :deep(img) {
          max-width: 100%;
          height: auto;
          display: block;
          margin: 12px auto;
        }
      }

    .article-footer {
      margin-top: 48px;

      .navigation {
        display: flex;
        justify-content: space-between;
        gap: 16px;

        .el-button {
          flex: 1;
          max-width: 400px;
        }
      }
    }
  }

  .article-toc {
    width: 240px;
    position: sticky;
    top: 80px;
    height: fit-content;
    background: var(--el-fill-color-blank);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);

    .toc-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      color: var(--el-text-color-primary);
    }

    .toc-list {
      list-style: none;
      padding: 0;
      margin: 0;

      .toc-item {
        padding: 8px 0;
        cursor: pointer;
        color: var(--el-text-color-regular);
        font-size: 14px;
        transition: all 0.3s;
        border-left: 2px solid transparent;
        padding-left: 12px;

        &:hover {
          color: var(--el-color-primary);
          border-left-color: var(--el-color-primary);
        }

        &.toc-level-3 {
          padding-left: 24px;
          font-size: 13px;
        }

        &.toc-level-4 {
          padding-left: 36px;
          font-size: 12px;
        }
      }
    }
  }
}

// dark mode style
:global(html.dark) {
  .learning-article-wrapper {
    background: #000000 !important;
    :deep(.el-page-header) {
      background: #000000 !important;
      border-bottom-color: var(--el-border-color-light);
    }
    :deep(.el-page-header__content),
    :deep(.el-page-header__title) {
      color: var(--el-text-color-primary) !important;
      opacity: 1;
    }
  }

  .learning-article {
    background: #000000 !important;
    .article-container {
      background: #000000 !important;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.6);

      .article-meta {
        border-bottom-color: var(--el-border-color-light);

        span {
          color: var(--el-text-color-regular);
        }
      }

      .article-content {
        color: var(--el-text-color-primary) !important;

        :deep(.article-heading) {
          color: var(--el-text-color-primary) !important;
        }

        :deep(h1) {
          color: var(--el-text-color-primary) !important;
          border-bottom-color: var(--el-border-color) !important;
          font-weight: 800 !important;
        }

        :deep(h2) {
          color: var(--el-text-color-primary) !important;
          border-bottom-color: var(--el-border-color) !important;
          font-weight: 700 !important;
        }

        :deep(h3) {
          color: var(--el-text-color-primary) !important;
          font-weight: 700 !important;
        }

        :deep(h4) {
          color: var(--el-text-color-primary) !important;
          font-weight: 700 !important;
        }

        :deep(p) {
          color: var(--el-text-color-primary) !important;
        }

        :deep(li) {
          color: var(--el-text-color-primary) !important;
        }

        :deep(code) {
          background: var(--el-fill-color-light) !important;
          color: var(--el-text-color-primary) !important;
        }

        :deep(blockquote) {
          background: var(--el-fill-color-light) !important;
          color: var(--el-text-color-secondary) !important;
          border-left-color: var(--el-color-primary) !important;
        }
      }
    }

    .article-toc {
      background: #000000 !important;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.6);

      .toc-title {
        color: var(--el-text-color-primary) !important;
      }

      .toc-list {
        .toc-item {
          color: var(--el-text-color-regular) !important;

          &:hover {
            color: var(--el-color-primary) !important;
            border-left-color: var(--el-color-primary) !important;
          }
        }
      }
    }
  }
}

@media (max-width: 1200px) {
  .learning-article {
    .article-toc {
      display: none;
    }
  }
}

@media (max-width: 768px) {
  .learning-article {
    padding: 16px;

    .article-container {
      padding: 20px;

      .article-content {
        font-size: 15px;

        :deep(h2) {
          font-size: 20px;
        }

        :deep(h3) {
          font-size: 18px;
        }
      }

      .article-footer {
        .navigation {
          flex-direction: column;

          .el-button {
            max-width: 100%;
          }
        }
      }
    }
  }
}
</style>

