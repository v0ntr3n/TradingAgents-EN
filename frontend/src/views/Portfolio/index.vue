<template>
  <div class="portfolio-page">
    <div class="header">
      <div class="title">
        <el-icon style="margin-right:8px"><PieChart /></el-icon>
        <span>Position analysis</span>
        <el-tag type="success" size="small" style="margin-left: 8px;">Advanced</el-tag>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" text size="small" @click="refreshData">Refresh</el-button>
        <el-button v-if="activeTab === 'real' && !isJdyunMode()" type="success" plain :loading="qmtSyncing" @click="syncPositionsFromQmt">QMT sync</el-button>
        <el-button v-if="activeTab === 'real'" type="primary" :icon="Plus" @click="showAddDialog = true">Add position</el-button>
        <el-button v-if="activeTab === 'real'" type="info" :icon="List" @click="showChangesDialog = true">Change history</el-button>
        <el-button v-if="activeTab === 'real'" type="warning" :icon="Clock" @click="showHistoryDialog = true">Historical positions</el-button>
        <el-button v-if="activeTab === 'real'" type="danger" plain size="small" @click="confirmResetAll">Clear all positions</el-button>
        <!-- Temporarily hidden, the function is not perfect -->
        <!-- <el-button type="success" :icon="DataAnalysis" @click="startAnalysis" :loading="analyzing">
          AI analysis
        </el-button>
        <el-button type="info" :icon="Document" @click="showAnalysisHistoryDialog = true">Analyze history</el-button> -->
      </div>
    </div>

    <!-- Compliance Disclaimer -->
    <el-alert
      title="This function is only a personal position management tool"
      type="info"
      description="Position data, profit and loss statistics and operation suggestions are all entered or synchronized by you. The system only records and displays them and does not constitute any investment advice. Please make independent judgments based on information from multiple parties for actual investment decisions."
      show-icon
      :closable="false"
      style="margin-bottom: 16px;"
    />

    <!-- Main Tab Page: User Positions vs Simulated Positions -->
    <el-tabs v-model="activeTab" type="card" class="main-tabs" @tab-change="handleTabChange">
      <!-- ==================== User positions Tab ==================== -->
      <el-tab-pane label="💰 User positions" name="real">
        <!-- Fund account card -->
        <AccountCard ref="accountCardRef" @updated="refreshData" />

        <!-- Statistics cards -->
        <el-row :gutter="16" class="stats-row">
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-label">Total market value of positions</div>
              <div class="stat-value">¥{{ formatNumber(realStats.total_value) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-label">Holding cost</div>
              <div class="stat-value">¥{{ formatNumber(realStats.total_cost) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-label">floating profit and loss</div>
              <div class="stat-value" :class="pnlClass(realStats.unrealized_pnl)">
                {{ formatPnl(realStats.unrealized_pnl) }}
                <span class="pnl-pct">({{ formatPct(realStats.unrealized_pnl_pct) }})</span>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-label">Position quantity</div>
              <div class="stat-value">{{ realStats.total_positions }} only</div>
            </el-card>
          </el-col>
        </el-row>

        <!-- Position list -->
        <el-row :gutter="16" class="main-content">
          <el-col :span="16">
            <el-card shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>User position details</span>
                  <el-radio-group v-model="selectedMarket" size="small" @change="filterPositions">
                    <el-radio-button value="all">All</el-radio-button>
                    <el-radio-button value="CN">A shares</el-radio-button>
                    <el-radio-button value="ETF">ETF</el-radio-button>
                  </el-radio-group>
                </div>
              </template>

              <!-- Display grouped by market -->
              <div v-if="paperSelectedMarket === 'all'" class="market-groups">
                <template v-for="market in ['CN']" :key="market">
                  <div v-if="getPositionsByMarket(realPositions, market).length > 0" class="market-group">
                    <div class="market-group-header">
                      <el-tag :type="getMarketTagType(market)" size="small">{{ getMarketName(market) }}</el-tag>
                      <span class="market-summary">
                        {{ getPositionsByMarket(realPositions, market).length }}only |
                        <template v-if="getEtfCountByMarket(realPositions, market) > 0">
                          ETF {{ getEtfCountByMarket(realPositions, market) }}only |
                        </template>
                        Market value: {{ getCurrencySymbol(market) }}{{ formatNumber(getMarketValue(realPositions, market)) }}
                      </span>
                    </div>
                    <el-table :data="getPositionsByMarket(realPositions, market)" stripe size="small">
                      <el-table-column label="code" width="100">
                        <template #default="{ row }">
                          <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.code }}</el-button>
                        </template>
                      </el-table-column>
                      <el-table-column label="Name" width="170">
                        <template #default="{ row }">
                          <div class="name-cell">
                            <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.name }}</el-button>
                            <el-tag v-if="isEtfPosition(row)" type="success" size="small" effect="plain">ETF</el-tag>
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
                      <el-table-column label="original cost" width="110" align="right">
                        <template #default="{ row }">
                          <span v-if="(row as any).price_adjust_type === 'none' && (row as any).original_cost_price">
                            {{ (row as any).original_cost_price?.toFixed(2) }}
                            <el-tag size="small" type="warning" effect="plain" style="margin-left:2px;font-size:10px">Loss of power</el-tag>
                          </span>
                          <span v-else>{{ ((row as any).original_avg_cost ?? row.cost_price)?.toFixed(2) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="diluted costs" width="100" align="right">
                        <template #default="{ row }">{{ row.cost_price?.toFixed(2) }}</template>
                      </el-table-column>
                      <el-table-column label="Current price" width="100" align="right">
                        <template #default="{ row }">{{ row.current_price?.toFixed(2) || '-' }}</template>
                      </el-table-column>
                      <el-table-column label="Market value" width="120" align="right">
                        <template #default="{ row }">{{ formatNumber(row.market_value) }}</template>
                      </el-table-column>
                      <el-table-column label="Profit and loss" width="120" align="right">
                        <template #default="{ row }">
                          <span :class="pnlClass(row.unrealized_pnl)">{{ formatPnl(row.unrealized_pnl) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="Profit and loss%" width="80" align="right">
                        <template #default="{ row }">
                          <span :class="pnlClass(row.unrealized_pnl_pct)">{{ formatPct(row.unrealized_pnl_pct) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="Operation" width="280" fixed="right">
                        <template #default="{ row }">
                          <el-button link type="warning" size="small" @click="quickAddPosition(row)">Add to position</el-button>
                          <el-button link type="danger" size="small" @click="quickSellPosition(row)">sell</el-button>
                          <el-button link type="success" size="small" @click="analyzePosition(row)">analysis</el-button>
                          <el-button v-if="row.position_count > 1" link type="info" size="small" @click="showPositionDetails(row)">Details</el-button>
                          <el-dropdown trigger="click" @command="(cmd: string) => handleMoreAction(cmd, row)">
                            <el-button link type="info" size="small">More<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
                            <template #dropdown>
                              <el-dropdown-menu>
                                <el-dropdown-item command="history">Operation history</el-dropdown-item>
                                <!-- Temporarily hidden, the function is not perfect -->
                                <!-- <el-dropdown-item command="analysisHistory">Analyze history</el-dropdown-item> -->
                                <el-dropdown-item command="edit" divided>Edit</el-dropdown-item>
                                <el-dropdown-item command="dividend">dividend</el-dropdown-item>
                                <el-dropdown-item command="split">stock split</el-dropdown-item>
                                <el-dropdown-item command="merge">partnership</el-dropdown-item>
                                <el-dropdown-item command="adjust">Adjustment costs</el-dropdown-item>
                                <el-dropdown-item command="reset" divided>Reset positions</el-dropdown-item>
                                <el-dropdown-item command="delete">Delete</el-dropdown-item>
                              </el-dropdown-menu>
                            </template>
                          </el-dropdown>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </template>
                <el-empty v-if="realPositions.length === 0" description="There are currently no user positions" />
              </div>

              <!-- Single market display -->
              <div v-else>
                <el-table :data="filteredPositions" v-loading="loading" stripe>
                  <el-table-column label="code" width="100">
                    <template #default="{ row }">
                      <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.code }}</el-button>
                    </template>
                  </el-table-column>
                  <el-table-column label="Name" width="170">
                    <template #default="{ row }">
                      <div class="name-cell">
                        <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.name }}</el-button>
                        <el-tag v-if="isEtfPosition(row)" type="success" size="small" effect="plain">ETF</el-tag>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="market" width="90">
                    <template #default="{ row }">
                      <el-tag :type="getDisplayMarketTagType(row.market, row.code)" size="small">{{ getDisplayMarketName(row.market, row.code) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
                  <el-table-column label="original cost" width="110" align="right">
                    <template #default="{ row }">
                      <span v-if="(row as any).price_adjust_type === 'none' && (row as any).original_cost_price">
                        {{ (row as any).original_cost_price?.toFixed(2) }}
                        <el-tag size="small" type="warning" effect="plain" style="margin-left:2px;font-size:10px">Loss of power</el-tag>
                      </span>
                      <span v-else>{{ ((row as any).original_avg_cost ?? row.cost_price)?.toFixed(2) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="diluted costs" width="100" align="right">
                    <template #default="{ row }">{{ row.cost_price?.toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="Current price" width="100" align="right">
                    <template #default="{ row }">{{ row.current_price?.toFixed(2) || '-' }}</template>
                  </el-table-column>
                  <el-table-column label="Market value" width="120" align="right">
                    <template #default="{ row }">{{ formatNumber(row.market_value) }}</template>
                  </el-table-column>
                  <el-table-column label="Profit and loss" width="120" align="right">
                    <template #default="{ row }">
                      <span :class="pnlClass(row.unrealized_pnl)">{{ formatPnl(row.unrealized_pnl) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Profit and loss%" width="80" align="right">
                    <template #default="{ row }">
                      <span :class="pnlClass(row.unrealized_pnl_pct)">{{ formatPct(row.unrealized_pnl_pct) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Operation" width="280" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="warning" size="small" @click="quickAddPosition(row)">Add to position</el-button>
                      <el-button link type="danger" size="small" @click="quickSellPosition(row)">sell</el-button>
                      <el-button link type="success" size="small" @click="analyzePosition(row)">analysis</el-button>
                      <el-button v-if="row.position_count > 1" link type="info" size="small" @click="showPositionDetails(row)">Details</el-button>
                      <el-dropdown trigger="click" @command="(cmd: string) => handleMoreAction(cmd, row)">
                        <el-button link type="info" size="small">More<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item command="history">Operation history</el-dropdown-item>
                            <!-- Temporarily hidden, the function is not perfect -->
                            <!-- <el-dropdown-item command="analysisHistory">Analyze history</el-dropdown-item> -->
                            <el-dropdown-item command="edit" divided>Edit</el-dropdown-item>
                            <el-dropdown-item command="dividend">dividend</el-dropdown-item>
                            <el-dropdown-item command="split">stock split</el-dropdown-item>
                            <el-dropdown-item command="merge">partnership</el-dropdown-item>
                            <el-dropdown-item command="adjust">Adjustment costs</el-dropdown-item>
                            <el-dropdown-item command="reset" divided>Reset positions</el-dropdown-item>
                            <el-dropdown-item command="delete">Delete</el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                    </template>
                  </el-table-column>
                </el-table>
                <el-empty v-if="filteredPositions.length === 0" description="There are currently no positions in this market" />
              </div>
            </el-card>
          </el-col>

          <!-- Industry distribution -->
          <el-col :span="8">
            <el-card shadow="hover" class="industry-card">
              <template #header><span>Industry distribution</span></template>
              <div v-if="realIndustryDistribution.length" class="industry-list">
                <div v-for="item in realIndustryDistribution" :key="item.industry" class="industry-item">
                  <div class="industry-name">{{ item.industry }}</div>
                  <div class="industry-bar">
                    <el-progress :percentage="item.percentage" :stroke-width="12" :show-text="false" />
                  </div>
                  <div class="industry-pct">{{ item.percentage.toFixed(1) }}%</div>
                </div>
              </div>
              <el-empty v-else description="No data yet" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ==================== Simulated position Tab ==================== -->
      <el-tab-pane label="📊 Simulated position" name="paper">
        <!-- Demo account funds -->
        <el-card shadow="hover" class="paper-account-card">
          <template #header>
            <div class="card-header">
              <span>Demo account funds</span>
              <el-tag type="info" size="small">For reference only</el-tag>
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="account-item">
                <div class="account-label">Simulated total assets</div>
                <div class="account-value">¥{{ formatNumber(paperStats.total_assets) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="account-item">
                <div class="account-label">Position market value</div>
                <div class="account-value">¥{{ formatNumber(paperStats.total_value) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="account-item">
                <div class="account-label">floating profit and loss</div>
                <div class="account-value" :class="pnlClass(paperStats.unrealized_pnl)">
                  {{ formatPnl(paperStats.unrealized_pnl) }}
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="account-item">
                <div class="account-label">Position quantity</div>
                <div class="account-value">{{ paperStats.total_positions }} only</div>
              </div>
            </el-col>
          </el-row>
        </el-card>

        <!-- Simulated position list -->
        <el-row :gutter="16" class="main-content">
          <el-col :span="16">
            <el-card shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>Simulated position details</span>
                  <el-radio-group v-model="paperSelectedMarket" size="small">
                    <el-radio-button value="all">All</el-radio-button>
                    <el-radio-button value="CN">A shares</el-radio-button>
                    <el-radio-button value="ETF">ETF</el-radio-button>
                  </el-radio-group>
                </div>
              </template>

              <!-- Display grouped by market -->
              <div v-if="paperSelectedMarket === 'all'" class="market-groups">
                <template v-for="market in ['CN']" :key="market">
                  <div v-if="getPositionsByMarket(paperPositions, market).length > 0" class="market-group">
                    <div class="market-group-header">
                      <el-tag :type="getMarketTagType(market)" size="small">{{ getMarketName(market) }}</el-tag>
                      <span class="market-summary">
                        {{ getPositionsByMarket(paperPositions, market).length }}only |
                        <template v-if="getEtfCountByMarket(paperPositions, market) > 0">
                          ETF {{ getEtfCountByMarket(paperPositions, market) }}only |
                        </template>
                        Market value: {{ getCurrencySymbol(market) }}{{ formatNumber(getMarketValue(paperPositions, market)) }}
                      </span>
                    </div>
                    <el-table :data="getPositionsByMarket(paperPositions, market)" stripe size="small">
                      <el-table-column label="code" width="100">
                        <template #default="{ row }">
                          <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.code }}</el-button>
                        </template>
                      </el-table-column>
                      <el-table-column label="Name" width="170">
                        <template #default="{ row }">
                          <div class="name-cell">
                            <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.name }}</el-button>
                            <el-tag v-if="isEtfPosition(row)" type="success" size="small" effect="plain">ETF</el-tag>
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
                      <el-table-column label="cost price" width="100" align="right">
                        <template #default="{ row }">{{ row.cost_price?.toFixed(2) }}</template>
                      </el-table-column>
                      <el-table-column label="Current price" width="100" align="right">
                        <template #default="{ row }">{{ row.current_price?.toFixed(2) || '-' }}</template>
                      </el-table-column>
                      <el-table-column label="Market value" width="120" align="right">
                        <template #default="{ row }">{{ formatNumber(row.market_value) }}</template>
                      </el-table-column>
                      <el-table-column label="Profit and loss" width="120" align="right">
                        <template #default="{ row }">
                          <span :class="pnlClass(row.unrealized_pnl)">{{ formatPnl(row.unrealized_pnl) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="Profit and loss%" width="80" align="right">
                        <template #default="{ row }">
                          <span :class="pnlClass(row.unrealized_pnl_pct)">{{ formatPct(row.unrealized_pnl_pct) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="Operation" width="160" fixed="right">
                        <template #default="{ row }">
                          <el-button link type="success" size="small" @click="analyzePosition(row)">analysis</el-button>
                          <el-button v-if="row.position_count > 1" link type="info" size="small" @click="showPositionDetails(row)">Details</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </template>
                <el-empty v-if="paperPositions.length === 0" description="No simulated positions yet" />
              </div>

              <!-- Single market display -->
              <div v-else>
                <el-table :data="filteredPaperPositions" v-loading="loading" stripe>
                  <el-table-column label="code" width="100">
                    <template #default="{ row }">
                      <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.code }}</el-button>
                    </template>
                  </el-table-column>
                  <el-table-column label="Name" width="170">
                    <template #default="{ row }">
                      <div class="name-cell">
                        <el-button link type="primary" @click="goToStockDetail(row.code)">{{ row.name }}</el-button>
                        <el-tag v-if="isEtfPosition(row)" type="success" size="small" effect="plain">ETF</el-tag>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="market" width="90">
                    <template #default="{ row }">
                      <el-tag :type="getDisplayMarketTagType(row.market, row.code)" size="small">{{ getDisplayMarketName(row.market, row.code) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="quantity" label="Quantity" width="80" align="right" />
                  <el-table-column label="cost price" width="100" align="right">
                    <template #default="{ row }">{{ row.cost_price?.toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="Current price" width="100" align="right">
                    <template #default="{ row }">{{ row.current_price?.toFixed(2) || '-' }}</template>
                  </el-table-column>
                  <el-table-column label="Market value" width="120" align="right">
                    <template #default="{ row }">{{ formatNumber(row.market_value) }}</template>
                  </el-table-column>
                  <el-table-column label="Profit and loss" width="120" align="right">
                    <template #default="{ row }">
                      <span :class="pnlClass(row.unrealized_pnl)">{{ formatPnl(row.unrealized_pnl) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Profit and loss%" width="80" align="right">
                    <template #default="{ row }">
                      <span :class="pnlClass(row.unrealized_pnl_pct)">{{ formatPct(row.unrealized_pnl_pct) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Operation" width="160" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="success" size="small" @click="analyzePosition(row)">analysis</el-button>
                      <el-button v-if="row.position_count > 1" link type="info" size="small" @click="showPositionDetails(row)">Details</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-empty v-if="filteredPaperPositions.length === 0" description="There are currently no simulated positions in this market" />
              </div>
            </el-card>
          </el-col>

          <!-- Simulation disk industry distribution -->
          <el-col :span="8">
            <el-card shadow="hover" class="industry-card">
              <template #header><span>Industry distribution</span></template>
              <div v-if="paperIndustryDistribution.length" class="industry-list">
                <div v-for="item in paperIndustryDistribution" :key="item.industry" class="industry-item">
                  <div class="industry-name">{{ item.industry }}</div>
                  <div class="industry-bar">
                    <el-progress :percentage="item.percentage" :stroke-width="12" :show-text="false" />
                  </div>
                  <div class="industry-pct">{{ item.percentage.toFixed(1) }}%</div>
                </div>
              </div>
              <el-empty v-else description="No data yet" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <!-- Add position dialog -->
    <AddPositionDialog 
      v-model:visible="showAddDialog" 
      :edit-data="editingPosition"
      @success="onPositionSaved" 
    />

    <!-- Analyze results dialog box -->
    <AnalysisResultDialog
      v-model:visible="showAnalysisDialog"
      :report="analysisReport"
    />

    <!-- Single stock position analysis dialog box -->
    <PositionAnalysisDialog
      v-model="showPositionAnalysisDialog"
      :position="selectedPosition"
      :workflow-id="selectedWorkflowId"
    />

    <!-- Position change record dialog box -->
    <PositionChangesDialog v-model="showChangesDialog" @refresh="refreshData" />

    <!-- Historical positions dialog box -->
    <HistoryPositionsDialog v-model="showHistoryDialog" />

    <!-- Position analysis history dialog box -->
    <AnalysisHistoryDialog v-model="showAnalysisHistoryDialog" />

    <!-- Single stock analysis history dialog box -->
    <PositionAnalysisHistoryDialog
      v-model="showPositionAnalysisHistoryDialog"
      :position="selectedPositionForAnalysisHistory"
    />

    <!-- Position details dialog box -->
    <PositionDetailsDialog
      v-model="showPositionDetailsDialog"
      :position="selectedAggregatedPosition"
      @edit="handleEditFromDetails"
      @refresh="refreshData"
      @operation="handlePositionOperation"
    />

    <!-- Position operation dialog box -->
    <PositionOperationDialog
      v-model="showPositionOperationDialog"
      :position="selectedAggregatedPosition"
      :operation-type="operationType"
      @refresh="refreshData"
    />

    <!-- Single stock operation history dialog box -->
    <StockOperationHistoryDialog
      v-model="showStockHistoryDialog"
      :stock="selectedStockForHistory"
      source="real"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isJdyunMode } from '@/utils/config'
import { Refresh, Plus, PieChart, List, Clock, ArrowDown } from '@element-plus/icons-vue'
import type { TabPaneName } from 'element-plus'
import { portfolioApi, type PositionItem, type PortfolioStats, type PortfolioAnalysisReport, type QMTPositionSyncPreview } from '@/api/portfolio'
import AddPositionDialog from './components/AddPositionDialog.vue'
import AnalysisResultDialog from './components/AnalysisResultDialog.vue'
import PositionAnalysisDialog from './components/PositionAnalysisDialog.vue'
import PositionChangesDialog from './components/PositionChangesDialog.vue'
import HistoryPositionsDialog from './components/HistoryPositionsDialog.vue'
import AnalysisHistoryDialog from './components/AnalysisHistoryDialog.vue'
import PositionAnalysisHistoryDialog from './components/PositionAnalysisHistoryDialog.vue'
import PositionDetailsDialog from './components/PositionDetailsDialog.vue'
import PositionOperationDialog from './components/PositionOperationDialog.vue'
import StockOperationHistoryDialog from './components/StockOperationHistoryDialog.vue'
import AccountCard from './components/AccountCard.vue'
import { getMarketByStockCode } from '@/utils/market'

// Router
const router = useRouter()

// Status
const loading = ref(false)
const positions = ref<PositionItem[]>([])
const stats = ref<PortfolioStats | null>(null)
const accountCardRef = ref<InstanceType<typeof AccountCard> | null>(null)
const activeTab = ref<'real' | 'paper'>('real')
const selectedMarket = ref<'all' | 'CN' | 'ETF'>('all')
const paperSelectedMarket = ref<'all' | 'CN' | 'ETF'>('all')
const showAddDialog = ref(false)
const showAnalysisDialog = ref(false)
const showPositionAnalysisDialog = ref(false)
const showChangesDialog = ref(false)
const showHistoryDialog = ref(false)
const showAnalysisHistoryDialog = ref(false)
const showPositionAnalysisHistoryDialog = ref(false)
const showPositionDetailsDialog = ref(false)
const showPositionOperationDialog = ref(false)
const showStockHistoryDialog = ref(false)
const editingPosition = ref<PositionItem | null>(null)
const selectedPosition = ref<PositionItem | null>(null)
const selectedWorkflowId = ref<string>('')
const selectedAggregatedPosition = ref<AggregatedPosition | null>(null)
const selectedStockForHistory = ref<{ code: string; name?: string; market: string } | null>(null)
const selectedPositionForAnalysisHistory = ref<PositionItem | null>(null)
const operationType = ref<'add' | 'reduce' | 'dividend' | 'split' | 'merge' | 'adjust' | 'other'>('add')
const analysisReport = ref<PortfolioAnalysisReport | null>(null)
const qmtSyncing = ref(false)

const QMT_ACCOUNT_ID_STORAGE_KEY = 'portfolio:qmt-account-id'

// User positions and simulated positions
const realPositions = ref<PositionItem[]>([])
const paperPositions = ref<PositionItem[]>([])
const filteredPositions = ref<PositionItem[]>([])
const filteredPaperPositions = ref<PositionItem[]>([])

// Statistics
interface StatsData {
  total_value: number
  total_cost: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  total_positions: number
  total_assets: number
}
const realStats = ref<StatsData>({
  total_value: 0,
  total_cost: 0,
  unrealized_pnl: 0,
  unrealized_pnl_pct: 0,
  total_positions: 0,
  total_assets: 0
})
const paperStats = ref<StatsData>({
  total_value: 0,
  total_cost: 0,
  unrealized_pnl: 0,
  unrealized_pnl_pct: 0,
  total_positions: 0,
  total_assets: 0
})

// Industry distribution
interface IndustryItem {
  industry: string
  percentage: number
}
const realIndustryDistribution = ref<IndustryItem[]>([])
const paperIndustryDistribution = ref<IndustryItem[]>([])

// formatting method
const formatNumber = (val?: number) => {
  // 🔥 Fix: Handle NaN and non-numeric values
  if (val === undefined || val === null || Number.isNaN(val) || typeof val !== 'number') return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatPnl = (val?: number) => {
  if (val === undefined || val === null || Number.isNaN(val) || typeof val !== 'number') return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + formatNumber(val)
}

const formatPct = (val?: number) => {
  if (val === undefined || val === null || Number.isNaN(val) || typeof val !== 'number') return '-'
  const prefix = val >= 0 ? '+' : ''
  return prefix + val.toFixed(2) + '%'
}

const formatSyncMoney = (val?: number | null, symbol = '¥') => {
  if (val === undefined || val === null || Number.isNaN(val) || typeof val !== 'number') return '-'
  return `${symbol}${formatNumber(val)}`
}

const pnlClass = (val?: number) => {
  if (val === undefined || val === null) return ''
  return val >= 0 ? 'profit' : 'loss'
}

const isEtfCode = (code?: string) => getMarketByStockCode(code || '') === 'ETF'

const isEtfPosition = (position: Pick<PositionItem, 'code' | 'market'>) => {
  return position.market === 'CN' && isEtfCode(position.code)
}

const getDisplayMarketName = (market: string, code?: string) => {
  if (market === 'CN' && isEtfCode(code)) return 'ETF'
  return getMarketName(market)
}

const getDisplayMarketTagType = (market: string, code?: string) => {
  if (market === 'CN' && isEtfCode(code)) return 'success'
  return getMarketTagType(market)
}

const getEtfCountByMarket = (positions: PositionItem[], market: string) => {
  return positions.filter(p => p.market === market && isEtfPosition(p)).length
}

const getIndustryCategory = (position: PositionItem) => {
  if (isEtfPosition(position)) return 'ETF/fund'
  return position.industry || 'unknown'
}

const matchesSelectedMarket = (position: PositionItem, selected: string) => {
  if (selected === 'all') return true
  if (selected === 'ETF') return isEtfPosition(position)
  if (selected === 'CN') return position.market === 'CN' && !isEtfPosition(position)
  return position.market === selected
}

// market related approach
const getMarketName = (market: string) => {
  const map: Record<string, string> = {
    CN: 'A shares'
  }
  return map[market] || market
}

const getMarketTagType = (market: string) => {
  const map: Record<string, any> = {
    CN: 'danger'
  }
  return map[market] || 'info'
}

// currency symbol
const getCurrencySymbol = (market: string) => {
  const map: Record<string, string> = {
    CN: '¥'
  }
  return map[market] || '¥'
}

// Obtain the effective market value of the position: use market_value if there is a market price, use cost price if there is no market price.*Quantity (to avoid showing -100% floating loss)
const getPositionValue = (p: PositionItem): number => {
  if (p.market_value != null && p.market_value !== undefined) return p.market_value
  return (p.cost_price ?? 0) * (p.quantity ?? 0)
}

// Aggregate positions of the same symbol (merged by ticker)
interface AggregatedPosition extends PositionItem {
  position_count: number  // The number of position records for this stock
  positions: PositionItem[]  // All position records for this stock
}

const aggregatePositionsByCode = (positions: PositionItem[]): AggregatedPosition[] => {
  const map = new Map<string, PositionItem[]>()

  // Group by code
  for (const pos of positions) {
    const key = pos.code
    if (!map.has(key)) {
      map.set(key, [])
    }
    map.get(key)!.push(pos)
  }

  // Combine data from each group
  const aggregated: AggregatedPosition[] = []
  for (const [, positionList] of map.entries()) {
    const totalQuantity = positionList.reduce((sum, p) => sum + p.quantity, 0)
    const totalCostDiluted = positionList.reduce((sum, p) => sum + (p.cost_price * p.quantity), 0)
    const totalCostOriginal = positionList.reduce((sum, p) => {
      const cost = (p.original_avg_cost ?? p.cost_price) * p.quantity
      return sum + cost
    }, 0)
    const avgCostPrice = totalQuantity > 0 ? totalCostDiluted / totalQuantity : 0
    const avgCostOriginal = totalQuantity > 0 ? totalCostOriginal / totalQuantity : 0
    const totalMarketValue = positionList.reduce((sum, p) => sum + getPositionValue(p), 0)
    const totalUnrealizedPnl = totalMarketValue - totalCostDiluted
    const totalUnrealizedPnlPct = totalCostDiluted > 0 ? (totalUnrealizedPnl / totalCostDiluted) * 100 : 0

    // Use the first record as the basis to update the aggregated data
    const basePos = positionList[0]
    const aggregated_pos: AggregatedPosition = {
      ...basePos,
      quantity: totalQuantity,
      cost_price: avgCostPrice,
      original_avg_cost: avgCostOriginal,
      market_value: totalMarketValue,
      unrealized_pnl: totalUnrealizedPnl,
      unrealized_pnl_pct: totalUnrealizedPnlPct,
      position_count: positionList.length,
      positions: positionList
    }
    aggregated.push(aggregated_pos)
  }

  return aggregated
}

// Get positions by market (aggregated version)
const getPositionsByMarket = (positions: PositionItem[], market: string) => {
  const filtered = positions.filter(p => p.market === market)
  return aggregatePositionsByCode(filtered)
}

// Get the total market capitalization
const getMarketValue = (positions: PositionItem[], market: string) => {
  return positions
    .filter(p => p.market === market)
    .reduce((sum, p) => sum + getPositionValue(p), 0)
}

// Calculate statistics
const calculateStats = (positions: PositionItem[]): StatsData => {
  const total_value = positions.reduce((sum, p) => sum + getPositionValue(p), 0)
  const total_cost = positions.reduce((sum, p) => sum + (p.cost_price || 0) * (p.quantity || 0), 0)
  const unrealized_pnl = total_value - total_cost
  const unrealized_pnl_pct = total_cost > 0 ? (unrealized_pnl / total_cost) * 100 : 0
  return {
    total_value,
    total_cost,
    unrealized_pnl,
    unrealized_pnl_pct,
    total_positions: positions.length,
    total_assets: total_value
  }
}

// Calculate industry distribution
const calculateIndustryDistribution = (positions: PositionItem[]): IndustryItem[] => {
  const total = positions.reduce((sum, p) => sum + getPositionValue(p), 0)
  if (total === 0) return []

  const industryMap: Record<string, number> = {}
  positions.forEach(p => {
    const industry = getIndustryCategory(p)
    industryMap[industry] = (industryMap[industry] || 0) + getPositionValue(p)
  })

  return Object.entries(industryMap)
    .map(([industry, value]) => ({
      industry,
      percentage: (value / total) * 100
    }))
    .sort((a, b) => b.percentage - a.percentage)
}

// Data loading
const loadPositions = async () => {
  loading.value = true
  try {
    const res = await portfolioApi.getPositions('all')
    positions.value = res.data?.items || []

    // Separate user positions and simulated positions
    realPositions.value = positions.value.filter(p => p.source !== 'paper')
    paperPositions.value = positions.value.filter(p => p.source === 'paper')

    // Calculate statistics
    realStats.value = calculateStats(realPositions.value)
    paperStats.value = calculateStats(paperPositions.value)

    // Calculate industry distribution
    realIndustryDistribution.value = calculateIndustryDistribution(realPositions.value)
    paperIndustryDistribution.value = calculateIndustryDistribution(paperPositions.value)

    // Apply Market Filter
    filterPositions()
    filterPaperPositions()
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to load positions')
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const res = await portfolioApi.getStatistics()
    stats.value = res.data || null
  } catch (e: any) {
    console.error('Failed to load statistics:', e)
  }
}

// Tab switch
const handleTabChange = (_tabName: TabPaneName) => {
  selectedMarket.value = 'all'
  paperSelectedMarket.value = 'all'
  filterPositions()
  filterPaperPositions()
}

// Market Screening - User Positions
const filterPositions = () => {
  let filtered: PositionItem[]
  if (selectedMarket.value === 'all') {
    filtered = realPositions.value
  } else {
    filtered = realPositions.value.filter(p => matchesSelectedMarket(p, selectedMarket.value))
  }
  // Aggregation is also required when displaying a single market
  filteredPositions.value = aggregatePositionsByCode(filtered) as any
}

// Market Screening - Simulated Positions
const filterPaperPositions = () => {
  let filtered: PositionItem[]
  if (paperSelectedMarket.value === 'all') {
    filtered = paperPositions.value
  } else {
    filtered = paperPositions.value.filter(p => matchesSelectedMarket(p, paperSelectedMarket.value))
  }
  // Aggregation is also required when displaying a single market
  filteredPaperPositions.value = aggregatePositionsByCode(filtered) as any
}

// Monitor market screening changes
watch(paperSelectedMarket, filterPaperPositions)
watch(selectedMarket, filterPositions)

const refreshData = () => {
  loadPositions()
  loadStats()
  accountCardRef.value?.loadData()
}

const getLastQmtAccountId = () => {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(QMT_ACCOUNT_ID_STORAGE_KEY) || ''
}

const setLastQmtAccountId = (accountId: string) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(QMT_ACCOUNT_ID_STORAGE_KEY, accountId)
}

const buildQmtPreviewMessage = (preview: QMTPositionSyncPreview) => {
  const lines = [
    `QMT Account:${preview.account_id}`,
    '',
    `Positions will be overwritten locally:${preview.will_replace_position_count} a`,
    `The local change record will be cleared:${preview.will_clear_change_count} Article`,
    `Local current CNY cash:${formatSyncMoney(preview.local_cash)}`,
    `Local current CNY total assets:${formatSyncMoney(preview.local_total_assets)}`,
    '',
    `QMT Return to position:${preview.qmt_position_count} Article`,
    `Positions that can be imported:${preview.qmt_importable_count} Article`,
    `QMT Cash available:${formatSyncMoney(preview.qmt_cash)}`,
    `QMT Position market value:${formatSyncMoney(preview.qmt_market_value)}`,
    `QMT Total assets:${formatSyncMoney(preview.qmt_total_asset)}`,
    '',
    `Description:${preview.sync_note}`
  ]
  return `<div style="white-space: pre-line; line-height: 1.7;">${lines.join('\n')}</div>`
}

const syncPositionsFromQmt = async () => {
  try {
    const { value } = await ElMessageBox.prompt(
      'Please enter the QMT fund account number. The system will display a preview of the coverage first, and then perform synchronization after confirmation.',
      'QMT Position synchronization',
      {
        confirmButtonText: 'View preview',
        cancelButtonText: 'Cancel',
        inputValue: getLastQmtAccountId(),
        inputPattern: /^\d{4,}$/,
        inputErrorMessage: 'Please enter the digital fund account number'
      }
    )

    const accountId = String(value || '').trim()
    if (!accountId) {
      ElMessage.warning('Please enter QMT fund account number')
      return
    }

    qmtSyncing.value = true

    const previewRes = await portfolioApi.previewQmtPositionImport({
      account_id: accountId,
      account_type: 'STOCK'
    })
    const preview = previewRes.data
    if (!preview) {
      ElMessage.error('QMT synchronization preview not obtained')
      return
    }

    await ElMessageBox.confirm(
      buildQmtPreviewMessage(preview),
      'Confirm coverage synchronization',
      {
        type: 'warning',
        confirmButtonText: 'Start syncing',
        cancelButtonText: 'Cancel',
        dangerouslyUseHTMLString: true
      }
    )

    const syncRes = await portfolioApi.importPositionsFromQmt({
      account_id: accountId,
      account_type: 'STOCK'
    })
    const syncResult = syncRes.data

    setLastQmtAccountId(accountId)

    const cashHint = syncResult?.cash_synced
      ? `, CNY Cash sync is ${formatSyncMoney(syncResult.synced_cash)}`
      : ''
    ElMessage.success(
      `QMT Synchronization completed: overwrite ${syncResult?.deleted_positions ?? 0} Gejiu position, import ${syncResult?.imported_count ?? 0} Article${cashHint}`
    )
    refreshData()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e?.message || 'QMT Sync failed')
    }
  } finally {
    qmtSyncing.value = false
  }
}

// Position operation
const editPosition = (row: AggregatedPosition) => {
  // If there are multiple position records, open a detailed dialog box for the user to choose
  if (row.position_count > 1) {
    selectedAggregatedPosition.value = row
    showPositionDetailsDialog.value = true
    ElMessage.info('Please select the position record to be edited in the details')
    return
  }
  // There is only one record, edit it directly
  editingPosition.value = row.positions ? row.positions[0] : row
  showAddDialog.value = true
}

const deletePosition = async (row: AggregatedPosition) => {
  try {
    // If there are multiple position records, you need to confirm whether to delete them all.
    if (row.position_count > 1) {
      await ElMessageBox.confirm(
        `${row.code} ${row.name || ''} Yes ${row.position_count} Records of opening positions, are you sure to delete them all?`,
        'Confirm deletion',
        { type: 'warning' }
      )
      // Delete all position records
      for (const pos of row.positions) {
        await portfolioApi.deletePosition(pos.id)
      }
      ElMessage.success('Delete successfully')
    } else {
      await ElMessageBox.confirm(`Confirm to delete position ${row.code} ${row.name || ''} ?`, 'Confirm deletion', { type: 'warning' })
      const posId = row.positions ? row.positions[0].id : row.id
      await portfolioApi.deletePosition(posId)
      ElMessage.success('Delete successfully')
    }
    refreshData()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || 'Delete failed')
    }
  }
}

const resetPosition = async (row: AggregatedPosition) => {
  try {
    await ElMessageBox.confirm(
      `Confirm reset ${row.code} ${row.name || ''} of the entire position? All change records and positions of the stock will be deleted, and this operation cannot be restored.`,
      'Confirm reset',
      { type: 'warning' }
    )
    const res = await portfolioApi.resetPosition(row.code, row.market)
    ElMessage.success(`Reset successful, deleted ${res.data?.deleted_changes ?? 0} records`)
    refreshData()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || 'Reset failed')
  }
}

const confirmResetAll = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to clear all positions? All positions and change records will be deleted, and the capital account will be completely cleared (total assets, available funds, initial funds, etc. will all be reset to zero), and this operation cannot be restored. After clearing, the initial funds need to be reset before you can continue to use them.',
      'Confirm clearing',
      { type: 'warning' }
    )
    const res = await portfolioApi.resetAllPositions()
    ElMessage.success(`Cleared successfully, deleted ${res.data?.deleted_positions ?? 0} positions,${res.data?.deleted_changes ?? 0} records`)
    refreshData()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || 'Clearing failed')
  }
}

const onPositionSaved = () => {
  showAddDialog.value = false
  editingPosition.value = null
  refreshData()
}

// Jump to stock details page
const goToStockDetail = (code: string) => {
  const market = getMarketByStockCode(code)
  router.push({
    name: 'StockDetail',
    params: { code },
    query: market === 'ETF' ? { market: 'ETF' } : undefined
  })
}

// Single stock position analysis
const analyzePosition = (row: PositionItem) => {
  selectedPosition.value = row
  showPositionAnalysisDialog.value = true
}

// View position details
const showPositionDetails = (row: AggregatedPosition) => {
  selectedAggregatedPosition.value = row
  showPositionDetailsDialog.value = true
}

// Edit a position from the details dialog
const handleEditFromDetails = (position: PositionItem) => {
  editingPosition.value = position
  showAddDialog.value = true
}

// Processing position operations (increasing positions, reducing positions, dividends, etc.)
const handlePositionOperation = (data: { type: string; position: AggregatedPosition }) => {
  operationType.value = data.type as 'add' | 'reduce' | 'other'
  selectedAggregatedPosition.value = data.position
  showPositionDetailsDialog.value = false
  showPositionOperationDialog.value = true
}

// Quickly add positions
const quickAddPosition = (row: AggregatedPosition) => {
  operationType.value = 'add'
  selectedAggregatedPosition.value = row
  showPositionOperationDialog.value = true
}

// sell quickly
const quickSellPosition = (row: AggregatedPosition) => {
  operationType.value = 'reduce'
  selectedAggregatedPosition.value = row
  showPositionOperationDialog.value = true
}

// More operation menus
const handleMoreAction = (command: string, row: AggregatedPosition) => {
  selectedAggregatedPosition.value = row
  switch (command) {
    case 'history':
      // Display the operation history of this stock
      selectedStockForHistory.value = {
        code: row.code,
        name: row.name,
        market: row.market
      }
      showStockHistoryDialog.value = true
      break
    case 'analysisHistory':
      // Show analysis history for this stock
      selectedPositionForAnalysisHistory.value = {
        code: row.code,
        name: row.name,
        market: row.market,
        quantity: row.quantity,
        cost_price: row.cost_price,
        current_price: row.current_price,
        market_value: row.market_value,
        unrealized_pnl: row.unrealized_pnl,
        unrealized_pnl_pct: row.unrealized_pnl_pct,
        industry: row.industry
      } as PositionItem
      showPositionAnalysisHistoryDialog.value = true
      break
    case 'edit':
      editPosition(row)
      break
    case 'delete':
      deletePosition(row)
      break
    case 'dividend':
      operationType.value = 'dividend'
      showPositionOperationDialog.value = true
      break
    case 'split':
      operationType.value = 'split'
      showPositionOperationDialog.value = true
      break
    case 'merge':
      operationType.value = 'merge'
      showPositionOperationDialog.value = true
      break
    case 'adjust':
      operationType.value = 'adjust'
      showPositionOperationDialog.value = true
      break
    case 'reset':
      resetPosition(row)
      break
  }
}

onMounted(() => {
  refreshData()
})
</script>

<style scoped>
.portfolio-page {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.title {
  display: flex;
  align-items: center;
  font-size: 20px;
  font-weight: 600;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 10px 0;
}

.stat-label {
  color: #909399;
  font-size: 14px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.stat-value .pnl-pct {
  font-size: 14px;
  margin-left: 4px;
}

.profit {
  color: #F56C6C; /* Red indicates profit (Chinese stock market norm) */
}

.loss {
  color: #67C23A; /* Green indicates loss (Chinese stock market norm) */
}

.main-content {
  margin-top: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.industry-card {
  height: 100%;
}

.industry-list {
  max-height: 400px;
  overflow-y: auto;
}

.industry-item {

.name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.industry-name {
  width: 80px;
  font-size: 13px;
  color: #606266;
}

.industry-bar {
  flex: 1;
  margin: 0 12px;
}

.industry-pct {
  width: 50px;
  text-align: right;
  font-size: 13px;
  color: #909399;
}

/* Main Tab page style */
.main-tabs {
  margin-top: 16px;
}

.main-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.main-tabs :deep(.el-tabs__item) {
  font-size: 15px;
  font-weight: 500;
}

/* Demo account card */
.paper-account-card {
  margin-bottom: 16px;
}

.account-item {
  text-align: center;
  padding: 12px 0;
}

.account-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.account-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

/* market grouping */
.market-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.market-group {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
}

.market-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.market-summary {
  font-size: 13px;
  color: #909399;
}
</style>

