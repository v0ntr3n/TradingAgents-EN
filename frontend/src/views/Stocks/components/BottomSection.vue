<template>
  <div class="bottom-grid" id="bottom-section">
    <!-- fundamental data -->
    <div class="card">
      <div class="card-header">
        <div class="section-title">
          <span>📚</span>
          <span>{{ isEtf ? 'ETF Basic data' : 'fundamental data' }}</span>
        </div>
        <el-tag v-if="basics.peIsRealtime" type="success" size="small">real time</el-tag>
      </div>
      <div class="card-body">
        <!-- ETF Basics -->
        <div v-if="isEtf" class="snapshot-grid">
          <div class="snapshot-item"><span class="snapshot-label">Fund type</span><span class="snapshot-value">{{ etfBasics.fundType || '-' }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">tracking index</span><span class="snapshot-value">{{ etfBasics.trackIndex || '-' }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Fund size</span><span class="snapshot-value">{{ fmtText(etfBasics.fundScale) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Fund shares</span><span class="snapshot-value">{{ fmtText(etfBasics.fundShare) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">net unit value</span><span class="snapshot-value">{{ fmtPrice(etfBasics.unitNav) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Cumulative net worth</span><span class="snapshot-value">{{ fmtPrice(etfBasics.accumNav) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Discount/premium rate</span><span class="snapshot-value">{{ fmtLoosePercent(etfBasics.premiumDiscountRate) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Net worth growth rate</span><span class="snapshot-value">{{ fmtLoosePercent(etfBasics.navGrowthRate) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">manager</span><span class="snapshot-value">{{ etfBasics.management || '-' }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">custodian</span><span class="snapshot-value">{{ etfBasics.custodian || '-' }}</span></div>
        </div>
        <!-- stock fundamentals -->
        <div v-else class="snapshot-grid">
          <div class="snapshot-item"><span class="snapshot-label">Industry</span><span class="snapshot-value">{{ basics.industry }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">plate</span><span class="snapshot-value">{{ basics.sector }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Total market capitalization</span><span class="snapshot-value">{{ fmtAmount(basics.marketCap) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">PE(TTM)</span><span class="snapshot-value">{{ fmtNum(basics.pe) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">PB(price to book ratio)</span><span class="snapshot-value">{{ fmtNum(basics.pb) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">PS(TTM)</span><span class="snapshot-value">{{ fmtNum(basics.ps) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">ROE</span><span class="snapshot-value">{{ fmtPercent(basics.roe) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Debt ratio</span><span class="snapshot-value">{{ fmtPercent(basics.debtRatio) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">dividend yield</span><span class="snapshot-value">{{ fmtPercent(basics.dividendYield) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">current ratio</span><span class="snapshot-value">{{ fmtRatio(basics.currentRatio) }}</span></div>
        </div>
      </div>
    </div>

    <!-- financial details -->
    <div v-if="!isEtf" class="card">
      <div class="card-header">
        <div class="section-title">
          <span>💰</span>
          <span>Snapshot of financial details</span>
        </div>
        <el-tag v-if="financialSnapshot.annDate" size="small" type="info" effect="plain">{{ financialSnapshot.annDate }}</el-tag>
      </div>
      <div class="card-body">
        <div class="snapshot-grid">
          <div class="snapshot-item"><span class="snapshot-label">Gross profit margin</span><span class="snapshot-value">{{ fmtPercent(financialSnapshot.grossMargin) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">net profit margin</span><span class="snapshot-value">{{ fmtPercent(financialSnapshot.netprofitMargin) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">Revenue</span><span class="snapshot-value">{{ fmtAmount(financialSnapshot.revenue) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">net profit</span><span class="snapshot-value">{{ fmtAmount(financialSnapshot.netProfit) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">operating cash flow</span><span class="snapshot-value">{{ fmtAmount(financialSnapshot.nCashflowAct) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">total assets</span><span class="snapshot-value">{{ fmtAmount(financialSnapshot.totalAssets) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">total liabilities</span><span class="snapshot-value">{{ fmtAmount(financialSnapshot.totalLiab) }}</span></div>
          <div class="snapshot-item"><span class="snapshot-label">data source</span><span class="snapshot-value">{{ financialSnapshot.dataSource || '-' }}</span></div>
        </div>
        <div v-if="financialRawSections.length" class="raw-section-summary">
          <div class="raw-title">raw_data Group</div>
          <div class="raw-tags">
            <el-tag v-for="section in financialRawSections" :key="section.key" size="small" type="info" effect="plain">
              {{ section.label }} {{ section.count }} Article
            </el-tag>
          </div>
          <div class="raw-hint">These original groupings have been exposed through the main stock interface, and subsequent pages or smart tools can directly drill down and call them.</div>
        </div>
      </div>
    </div>

    <!-- Recent News and Announcements -->
    <div class="card news-card">
      <div class="card-header">
        <div class="section-title">
          <span>📰</span>
          <span>{{ isEtf ? 'ETF News & Announcements' : 'Recent News and Announcements' }}</span>
        </div>
        <el-select :model-value="newsFilter" size="small" style="width: 120px" @change="(v: string) => $emit('newsFilterChange', v)">
          <el-option label="All" value="all" />
          <el-option label="News" value="news" />
          <el-option label="Announcement" value="announcement" />
        </el-select>
      </div>
      <div class="card-body">
        <div v-if="newsLoading" v-loading="true" style="min-height: 120px"></div>
        <el-empty v-else-if="!filteredNews.length" description="No news yet" :image-size="60" />
        <div v-else class="news-list">
          <div v-for="(n, i) in filteredNews" :key="i" class="news-item">
            <div class="news-header">
              <div class="news-title">
                <span class="news-tag" :class="n.type === 'announcement' ? 'tag-announcement' : 'tag-news'">
                  {{ n.type === 'announcement' ? 'Announcement' : 'News' }}
                </span>
                <a v-if="n.url && n.url !== '#'" :href="n.url" target="_blank" rel="noopener" class="news-link">{{ n.title || 'View details' }}</a>
                <span v-else>{{ n.title || ' (Untitled)' }}</span>
              </div>
              <div class="news-time">{{ formatNewsTime(n.time) }}</div>
            </div>
            <div class="news-source">{{ n.source || '-' }} · {{ newsSource || '-' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface BasicsData {
  industry: string
  sector: string
  marketCap: number
  pe: number
  pb: number
  ps: number
  roe: number
  debtRatio: number
  dividendYield: number
  currentRatio: number
  reportPeriod: string
  peIsRealtime: boolean
}

interface FinancialSnapshotData {
  annDate: string
  dataSource: string
  grossMargin: number
  netprofitMargin: number
  revenue: number
  netProfit: number
  nCashflowAct: number
  totalAssets: number
  totalLiab: number
}

interface EtfBasicsData {
  fundType: string
  trackIndex: string
  fundScale: string | number
  fundShare: string | number
  management: string
  custodian: string
  unitNav: number
  accumNav: number
  navGrowthRate: any
  premiumDiscountRate: any
}

const props = defineProps<{
  isEtf: boolean
  basics: BasicsData
  financialSnapshot: FinancialSnapshotData
  etfBasics: EtfBasicsData
  financialRawSections: Array<{ key: string; label: string; count: number }>
  newsItems: any[]
  newsFilter: string
  newsLoading: boolean
  newsSource?: string
}>()

defineEmits<{
  (e: 'newsFilterChange', filter: string): void
}>()

const filteredNews = computed(() => {
  if (props.newsFilter === 'news') return props.newsItems.filter(x => x.type === 'news')
  if (props.newsFilter === 'announcement') return props.newsItems.filter(x => x.type === 'announcement')
  return props.newsItems
})

function fmtNum(v: any) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

function fmtPercent(v: any) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  return n.toFixed(2) + '%'
}

function fmtRatio(v: any) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

function fmtAmount(v: any) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + 'billion'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + 'million'
  return n.toFixed(2)
}

function fmtPrice(v: any) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

function fmtText(v: any) {
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

function fmtLoosePercent(v: any) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return n.toFixed(2) + '%'
}

function formatNewsTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return String(dateStr)
    const now = new Date()
    const diff = (now.getTime() - d.getTime()) / 1000
    if (diff < 3600) return `${Math.floor(diff / 60)}minutes ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}hours ago`
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}days ago`
    return `${d.getMonth() + 1}-${d.getDate()}`
  } catch {
    return String(dateStr)
  }
}
</script>

<style scoped>
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.news-card {
  grid-column: 1 / -1;
}

.card {
  background: var(--el-bg-color, #fff);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  border: 1px solid #f1f5f9;
  overflow: hidden;
}

.card-header {
  padding: 14px 20px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1e293b;
}

.card-body {
  padding: 16px 20px;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.snapshot-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 13px;
}

.snapshot-label {
  color: #64748b;
}

.snapshot-value {
  font-weight: 600;
  color: #1e293b;
}

.raw-section-summary {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #f1f5f9;
}

.raw-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 8px;
}

.raw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.raw-hint {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.6;
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.news-item {
  padding: 10px;
  background: #f8fafc;
  border-radius: 6px;
  transition: background 0.2s;
}

.news-item:hover {
  background: #f5f3ff;
}

.news-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  gap: 8px;
}

.news-title {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}

.news-link {
  color: #1e293b;
  text-decoration: none;
}

.news-link:hover {
  color: #6b5ce7;
}

.news-tag {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.tag-news {
  background: #eff6ff;
  color: #3b82f6;
}

.tag-announcement {
  background: #fffbeb;
  color: #f59e0b;
}

.news-time {
  font-size: 11px;
  color: #94a3b8;
  flex-shrink: 0;
}

.news-source {
  font-size: 11px;
  color: #94a3b8;
}

@media (max-width: 1024px) {
  .bottom-grid {
    grid-template-columns: 1fr;
  }
}
</style>
