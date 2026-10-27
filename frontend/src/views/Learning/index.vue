<template>
  <div class="learning-center">
    <div class="learning-header">
      <h1>📚 Learning Center</h1>
      <p class="subtitle">Understand the AI, large model and multi-agent investment research process</p>
    </div>

    <el-row :gutter="20" class="learning-categories">
      <!-- AI basic knowledge -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('ai-basics')">
          <div class="card-icon">🤖</div>
          <h3>AI basic knowledge</h3>
          <p>What is AI? What is a large model? Understand the basic concepts of artificial intelligence</p>
          <el-tag type="primary" size="small">1 articles</el-tag>
        </el-card>
      </el-col>

      <!-- prompt word project -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('prompt-engineering')">
          <div class="card-icon">✍️</div>
          <h3>prompt word project</h3>
          <p>Learn how to write effective prompt words to let AI better understand your needs</p>
          <el-tag type="success" size="small">2 articles</el-tag>
        </el-card>
      </el-col>

      <!-- Model Selection Guide -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('model-selection')">
          <div class="card-icon">🎯</div>
          <h3>Model Selection Guide</h3>
          <p>Understand the characteristics of different large models and choose the model that best suits you</p>
          <el-tag type="warning" size="small">1 articles</el-tag>
        </el-card>
      </el-col>

      <!-- AI Analyze stock principles -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('analysis-principles')">
          <div class="card-icon">📊</div>
          <h3>AI Analyze stock principles</h3>
          <p>Learn more about how multiple agents collaborate to analyze stocks</p>
          <el-tag type="info" size="small">1 articles</el-tag>
        </el-card>
      </el-col>

      <!-- Risks and Limitations -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('risks-limitations')">
          <div class="card-icon">⚠️</div>
          <h3>Risks and Limitations</h3>
          <p>Understand potential problems with AI and proper ways to use it</p>
          <el-tag type="danger" size="small">1 articles</el-tag>
        </el-card>
      </el-col>

      <!-- Source projects and papers -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('resources')">
          <div class="card-icon">📖</div>
          <h3>Source projects and papers</h3>
          <p>TradingAgents Project introduction and academic paper resources</p>
          <el-tag type="primary" size="small">2 articles</el-tag>
        </el-card>
      </el-col>

      <!-- Practical tutorial -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('tutorials')">
          <div class="card-icon">🎓</div>
          <h3>Practical tutorial</h3>
          <p>Learn how to use this tool through practical cases</p>
          <el-tag type="success" size="small">2 articles</el-tag>
        </el-card>
      </el-col>

      <!-- FAQ -->
      <el-col :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="category-card" shadow="hover" @click="navigateTo('faq')">
          <div class="card-icon">❓</div>
          <h3>FAQ</h3>
          <p>Quickly find answers to frequently asked questions</p>
          <el-tag type="info" size="small">1 articles</el-tag>
        </el-card>
      </el-col>
    </el-row>

    <!-- Advanced course area -->
    <section class="advanced-courses-section">
      <div class="section-header">
        <div class="header-content">
          <h2>🎓 From retail investors to systematic traders: an evolvable investment approach empowered by AI</h2>
          <el-tag type="success" size="large">{{ freeLessonCount }}festival free</el-tag>
          <PaidCourseBadge variant="tag-short" size="large" />
        </div>
        <p class="section-subtitle">30 Systematic courses organized according to the full life cycle of stock trading: Discovery → Track → Position → Review → Extension. before{{ freeLessonCount }}Free preview.<PaidCourseBadge variant="text" /></p>
      </div>

      <!-- Course Category (visible to everyone) -->
      <div class="course-categories">
        <el-row :gutter="20">
          <el-col 
            v-for="category in advancedCourseCategories" 
            :key="category.id"
            :xs="24" :sm="12" :md="8" :lg="6"
          >
            <el-card 
              class="category-card" 
              shadow="hover" 
              @click="navigateToAdvanced(category.id)"
            >
              <div class="card-icon">{{ category.icon }}</div>
              <h3>{{ category.name }}</h3>
              <p>{{ category.description }}</p>
              <el-tag type="success" size="small">
                {{ category.lessonCount }}class
              </el-tag>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </section>

    <!-- Recommended articles -->
    <div class="recommended-section">
      <h2>🌟 Recommended reading</h2>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" v-for="article in recommendedArticles" :key="article.id">
          <el-card class="article-card" shadow="hover" @click="openArticle(article.id)">
            <div class="article-meta">
              <el-tag :type="article.tagType" size="small">{{ article.category }}</el-tag>
              <span class="read-time">{{ article.readTime }}</span>
            </div>
            <h4>{{ article.title }}</h4>
            <p>{{ article.description }}</p>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { advancedCourseCategories, FREE_LESSON_COUNT } from '@/config/advancedCourses'
import PaidCourseBadge from '@/components/PaidCourseBadge.vue'

const router = useRouter()

const freeLessonCount = FREE_LESSON_COUNT

// Define allowed union types for the type attribute of Element Plus Tag to avoid template type mismatches
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

interface RecommendedArticle {
  id: string
  category: string
  tagType: TagType
  title: string
  description: string
  readTime: string
}

// Recommended articles
const recommendedArticles = ref<RecommendedArticle[]>([
  {
    id: 'what-is-llm',
    category: 'AI Basics',
    tagType: 'primary',
    title: 'What is a large language model (LLM)?',
    description: 'Understand the basic concepts and working principles of large language models from scratch',
    readTime: '10 minutes'
  },
  {
    id: 'multi-agent-system',
    category: 'AI analysis',
    tagType: 'info',
    title: 'Detailed explanation of multi-agent systems',
    description: 'Learn how this tool collaborates with multiple AI agents to analyze stocks',
    readTime: '15 minutes'
  },
  {
    id: 'best-practices',
    category: 'prompt word',
    tagType: 'success',
    title: 'Prompt Word Engineering Best Practices',
    description: 'Learn how to write high-quality prompt words to improve AI analysis results',
    readTime: '12 minutes'
  }
])

const navigateTo = (category: string) => {
  router.push(`/learning/${category}`)
}

const openArticle = (articleId: string) => {
  // External link articles are opened directly in a new tab
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

const navigateToAdvanced = (categoryId: string) => {
  // Jump to the advanced course list page and pass the classification parameters (via query)
  router.push({ 
    path: '/learning/advanced',
    query: { category: categoryId }
  })
}
</script>

<style scoped lang="scss">
.learning-center {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;

  .learning-header {
    text-align: center;
    margin-bottom: 48px;
    padding: 40px 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    color: white;

    h1 {
      font-size: 36px;
      margin-bottom: 12px;
      font-weight: 600;
    }

    .subtitle {
      font-size: 18px;
      opacity: 0.9;
    }
  }

  .learning-categories {
    margin-bottom: 48px;

    .category-card {
      cursor: pointer;
      transition: all 0.3s ease;
      height: 220px;
      margin-bottom: 20px;
      background: var(--el-fill-color-blank);
      border-color: var(--el-border-color);

      &:hover {
        transform: translateY(-8px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
      }

      .card-icon {
        font-size: 48px;
        text-align: center;
        margin-bottom: 16px;
      }

      h3 {
        font-size: 18px;
        margin-bottom: 12px;
        color: var(--el-text-color-primary);
      }

      p {
        font-size: 14px;
        color: var(--el-text-color-regular);
        margin-bottom: 16px;
        line-height: 1.6;
        min-height: 60px;
      }

      .el-tag {
        margin-top: 8px;
      }
    }
  }

  .advanced-courses-section {
    margin-top: 48px;
    margin-bottom: 48px;

    .section-header {
      margin-bottom: 24px;

      .header-content {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;

        h2 {
          font-size: 24px;
          margin: 0;
          color: var(--el-text-color-primary);
        }
      }

      .section-subtitle {
        font-size: 14px;
        color: var(--el-text-color-regular);
        margin: 0;
        line-height: 1.6;
      }
    }

    .course-categories {
      .category-card {
        cursor: pointer;
        transition: all 0.3s ease;
        height: 220px;
        margin-bottom: 20px;
        background: var(--el-fill-color-blank);
        border-color: var(--el-border-color);

        &:hover {
          transform: translateY(-8px);
          box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
        }

        .card-icon {
          font-size: 48px;
          text-align: center;
          margin-bottom: 16px;
        }

        h3 {
          font-size: 18px;
          margin-bottom: 12px;
          color: var(--el-text-color-primary);
        }

        p {
          font-size: 14px;
          color: var(--el-text-color-regular);
          margin-bottom: 16px;
          line-height: 1.6;
          min-height: 60px;
        }

        .el-tag {
          margin-top: 8px;
        }
      }
    }
  }

  .recommended-section {
    margin-top: 48px;

    h2 {
      font-size: 24px;
      margin-bottom: 24px;
      color: var(--el-text-color-primary);
    }

    .article-card {
      cursor: pointer;
      transition: all 0.3s ease;
      margin-bottom: 20px;
      height: 180px;
      background: var(--el-fill-color-blank);
      border-color: var(--el-border-color);

      &:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
      }

      .article-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;

        .read-time {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }

      h4 {
        font-size: 16px;
        margin-bottom: 8px;
        color: var(--el-text-color-primary);
        font-weight: 600;
      }

      p {
        font-size: 14px;
        color: var(--el-text-color-regular);
        line-height: 1.6;
      }
    }
  }
}

// dark mode style
:global(html.dark) {
  .learning-center {
    background: #000000 !important;

    .learning-header {
      background: #000000 !important;
      border: 1px solid var(--el-border-color-light);
      color: var(--el-text-color-primary);
      h1 { color: var(--el-text-color-primary); }
      .subtitle { color: var(--el-text-color-regular); }
    }

    .learning-categories .category-card,
    .advanced-courses-section .course-categories .category-card,
    .recommended-section .article-card {
      background: #000000 !important;
      border-color: var(--el-border-color) !important;
    }

    .learning-categories .category-card h3,
    .advanced-courses-section .section-header .header-content h2,
    .advanced-courses-section .section-header .section-subtitle,
    .advanced-courses-section .course-categories .category-card h3,
    .recommended-section h2,
    .recommended-section .article-card h4,
    .recommended-section .article-card p,
    .recommended-section .article-card .read-time {
      color: var(--el-text-color-primary) !important;
    }

    .recommended-section .article-card p,
    .learning-categories .category-card p,
    .advanced-courses-section .course-categories .category-card p,
    .recommended-section .article-card .read-time {
      color: var(--el-text-color-regular) !important;
    }
  }
}

@media (max-width: 768px) {
  .learning-center {
    padding: 16px;

    .learning-header {
      padding: 24px 16px;

      h1 {
        font-size: 28px;
      }

      .subtitle {
        font-size: 16px;
      }
    }

    .advanced-courses-section {
      .section-header {
        .header-content h2 {
          font-size: 18px;
        }

        .section-subtitle {
          font-size: 12px;
        }
      }
    }
  }
}
</style>

