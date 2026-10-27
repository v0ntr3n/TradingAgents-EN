<template>
  <div class="learning-category">
    <el-page-header @back="goBack" :content="categoryInfo.title">
      <template #icon>
        <span class="category-icon">{{ categoryInfo.icon }}</span>
      </template>
    </el-page-header>

    <div class="category-content">
      <div class="category-description">
        <p>{{ categoryInfo.description }}</p>
      </div>

      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" v-for="article in articles" :key="article.id">
          <el-card class="article-card" shadow="hover" @click="openArticle(article.id)">
            <div class="article-header">
              <h3>{{ article.title }}</h3>
              <el-tag :type="article.difficulty" size="small">{{ article.difficultyText }}</el-tag>
            </div>
            <p class="article-desc">{{ article.description }}</p>
            <div class="article-footer">
              <span class="read-time">
                <el-icon><Clock /></el-icon>
                {{ article.readTime }}
              </span>
              <span class="views">
                <el-icon><View /></el-icon>
                {{ article.views }}
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Clock, View } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const category = computed(() => route.params.category as string)

// Classification information mapping
const categoryMap: Record<string, any> = {
  'ai-basics': {
    title: 'AI basic knowledge',
    icon: '🤖',
    description: 'Understand the basic concepts of artificial intelligence and large language models from scratch'
  },
  'prompt-engineering': {
    title: 'prompt word project',
    icon: '✍️',
    description: 'Learn how to write high-quality prompt words to let AI better understand your needs'
  },
  'model-selection': {
    title: 'Model Selection Guide',
    icon: '🎯',
    description: 'Understand the characteristics of different large models and choose the model that best suits you'
  },
  'analysis-principles': {
    title: 'AI Analyze stock principles',
    icon: '📊',
    description: 'Learn more about how multiple agents collaborate to analyze stocks'
  },
  'risks-limitations': {
    title: 'Risks and Limitations',
    icon: '⚠️',
    description: 'Understand potential problems with AI and proper ways to use it'
  },
  'resources': {
    title: 'Source projects and papers',
    icon: '📖',
    description: 'TradingAgents Project introduction and academic paper resources'
  },
  'tutorials': {
    title: 'Practical tutorial',
    icon: '🎓',
    description: 'Learn how to use this tool through practical cases'
  },
  'faq': {
    title: 'FAQ',
    icon: '❓',
    description: 'Quickly find answers to frequently asked questions'
  }
}

const categoryInfo = computed(() => {
  return categoryMap[category.value] || {
    title: 'Unknown classification',
    icon: '📚',
    description: ''
  }
})

// Article database
const articlesDatabase: Record<string, any[]> = {
  'ai-basics': [
    {
      id: 'what-is-llm',
      title: 'What is a large language model (LLM)?',
      description: 'In-depth understanding of the definition, working principle and application of large language models in stock analysis',
      readTime: '10 minutes',
      views: 2345,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    }
  ],
  'prompt-engineering': [
    {
      id: 'prompt-basics',
      title: 'Prompt word basics',
      description: 'Learn the basic concepts, structures and writing skills of prompt words',
      readTime: '10 minutes',
      views: 1876,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    },
    {
      id: 'best-practices',
      title: 'Prompt Word Engineering Best Practices',
      description: 'Master the core principles and practical skills of writing prompt words',
      readTime: '12 minutes',
      views: 1543,
      difficulty: 'warning',
      difficultyText: 'Advanced'
    }
  ],
  'model-selection': [
    {
      id: 'model-comparison',
      title: 'Comparison and selection of large language models',
      description: 'Compare the characteristics of mainstream large language models and learn to choose the most suitable model',
      readTime: '15 minutes',
      views: 1987,
      difficulty: 'warning',
      difficultyText: 'Advanced'
    }
  ],
  'analysis-principles': [
    {
      id: 'multi-agent-system',
      title: 'Detailed explanation of multi-agent systems',
      description: 'Deeply understand the multi-agent collaboration mechanism of TradingAgents-CN',
      readTime: '15 minutes',
      views: 1654,
      difficulty: 'warning',
      difficultyText: 'Advanced'
    }
  ],
  'risks-limitations': [
    {
      id: 'risk-warnings',
      title: 'AI Risks and Limitations of Stock Analysis',
      description: 'Understand the main limitations, risks of use and correct use of AI',
      readTime: '12 minutes',
      views: 2134,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    }
  ],
  'resources': [
    {
      id: 'tradingagents-intro',
      title: 'TradingAgents Project introduction',
      description: 'Understand the architecture and features of TradingAgents, the source project of TradingAgents-CN',
      readTime: '15 minutes',
      views: 1432,
      difficulty: 'warning',
      difficultyText: 'Advanced'
    },
    {
      id: 'paper-guide',
      title: 'TradingAgents Paper interpretation',
      description: 'In-depth interpretation of the core content and innovation points of TradingAgents academic papers',
      readTime: '20 minutes',
      views: 987,
      difficulty: 'danger',
      difficultyText: 'Advanced'
    }
  ],
  'tutorials': [
    {
      id: 'getting-started',
      title: 'Quick Start Tutorial',
      description: 'Learn how to use TradingAgents-CN for stock analysis from scratch',
      readTime: '10 minutes',
      views: 3456,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    },
    {
      id: 'usage-guide-preview',
      title: 'User Guide (Trial Version)',
      description: 'TradingAgents-CN v1.0.0-preview User Guide and Trial Instructions',
      readTime: '15 minutes',
      views: 1288,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    }
  ],
  'faq': [
    {
      id: 'general-questions',
      title: 'FAQ',
      description: 'Quickly find answers to common questions about features, model selection, usage tips, and more',
      readTime: '15 minutes',
      views: 2876,
      difficulty: 'success',
      difficultyText: 'Getting Started'
    }
  ]
}

// Get a list of articles based on the current category
const articles = computed(() => {
  return articlesDatabase[category.value] || []
})

const goBack = () => {
  router.push('/learning')
}

const openArticle = (articleId: string) => {
  // When the external link article is clicked on the list, it will be opened directly in a new tab without entering the details page.
  const externalMap: Record<string, string> = {
    'getting-started': 'https://mp.weixin.qq.com/s/uAk4RevdJHMuMvlqpdGUEw',
    'usage-guide-preview': 'https://mp.weixin.qq.com/s/ppsYiBncynxlsfKFG8uEbw'
  }
  const external = externalMap[articleId]
  if (external) {
    window.open(external, '_blank')
    return
  }
  router.push(`/learning/article/${articleId}`)
}
</script>

<style scoped lang="scss">
.learning-category {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;

  :deep(.el-page-header) {
    margin-bottom: 32px;
    border-bottom: 1px solid var(--el-border-color);
    background: var(--el-fill-color-blank);

    .category-icon {
      font-size: 24px;
      margin-right: 8px;
    }
  }

  .category-content {
    .category-description {
      margin-bottom: 32px;
      padding: 20px;
      background: var(--el-fill-color-light);
      border-radius: 8px;

      p {
        font-size: 16px;
        color: var(--el-text-color-regular);
        line-height: 1.6;
        margin: 0;
      }
    }

    .article-card {
      cursor: pointer;
      transition: all 0.3s ease;
      margin-bottom: 20px;
      min-height: 200px;
      background: var(--el-fill-color-blank);
      border: 1px solid var(--el-border-color);

      &:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
      }

      // Let the card content be arranged vertically and fill the height to avoid the bottom information being cropped
      :deep(.el-card__body) {
        display: flex;
        flex-direction: column;
        height: 100%;
        box-sizing: border-box;
      }

      .article-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;

        h3 {
          font-size: 16px;
          color: var(--el-text-color-primary);
          font-weight: 600;
          flex: 1;
          margin-right: 12px;
        }
      }

      .article-desc {
        font-size: 14px;
        color: var(--el-text-color-regular);
        line-height: 1.6;
        margin-bottom: 16px;
        min-height: 60px;
      }

      .article-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 12px;
        border-top: 1px solid var(--el-border-color);
        margin-top: auto;

        span {
          display: flex;
          align-items: center;
          font-size: 13px;
          color: var(--el-text-color-secondary);

          .el-icon {
            margin-right: 4px;
          }
        }
      }
    }
  }
}

// Dark mode overlay
:global(html.dark) {
  .learning-category {
    background: #000000 !important;

    :deep(.el-page-header) {
      background: #000000 !important;
      border-bottom-color: var(--el-border-color);
    }

    .category-content {
      .category-description {
        background: #000000 !important;
        border: 1px solid var(--el-border-color);
      }

      .article-card {
        background: #000000 !important;
        border-color: var(--el-border-color) !important;
      }
    }

    .article-footer {
      border-top-color: var(--el-border-color);
    }
  }
}
</style>

