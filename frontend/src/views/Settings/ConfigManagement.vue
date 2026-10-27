<template>
  <div class="config-management">
    <!-- Page title -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <el-icon><Setting /></el-icon>
          Configuration management
        </h1>
        <p class="page-description">
          Manage system configuration, large models, data sources and other settings
        </p>
      </div>
      <div class="header-right">
        <el-button v-if="!isJdyunMode()" type="success" @click="handleReloadConfig" :loading="reloadLoading">
          <el-icon><Refresh /></el-icon>
          Overload configuration
        </el-button>
      </div>
    </div>

    <el-row :gutter="24">
      <!-- Left: Configuration menu -->
      <el-col :span="4">
        <el-card class="config-menu" shadow="never">
          <el-menu
            :default-active="activeTab"
            @select="handleMenuSelect"
            class="config-nav"
          >
            <!-- JD Cloud mode: only display data source configuration -->
            <template v-if="isJdyunMode()">
              <el-menu-item index="datasource">
                <el-icon><DataBoard /></el-icon>
                <span>Data source configuration</span>
              </el-menu-item>
            </template>
            <!-- Non-JD Cloud mode: Show all menus -->
            <template v-else>
              <el-menu-item index="providers">
                <el-icon><OfficeBuilding /></el-icon>
                <span>Factory management</span>
              </el-menu-item>
              <el-menu-item index="model-catalog">
                <el-icon><Collection /></el-icon>
                <span>Model catalog</span>
              </el-menu-item>
              <el-menu-item index="llm">
                <el-icon><Cpu /></el-icon>
                <span>Large model configuration</span>
              </el-menu-item>
              <el-menu-item index="datasource">
                <el-icon><DataBoard /></el-icon>
                <span>Data source configuration</span>
              </el-menu-item>
              <el-menu-item index="database">
                <el-icon><Coin /></el-icon>
                <span>Database configuration</span>
              </el-menu-item>
              <el-menu-item index="system">
                <el-icon><Tools /></el-icon>
                <span>System settings</span>
              </el-menu-item>
              <el-menu-item index="gateway">
                <el-icon><Connection /></el-icon>
                <span>Gateway Configuration</span>
              </el-menu-item>
              <el-menu-item index="validation">
                <el-icon><CircleCheck /></el-icon>
                <span>Configuration verification</span>
              </el-menu-item>
              <!-- hidden menu items -->
              <!-- <el-menu-item index="api-keys">
                <el-icon><Key /></el-icon>
                <span>API Key status</span>
              </el-menu-item> -->
              <!-- <el-menu-item index="import-export">
                <el-icon><Download /></el-icon>
                <span>Import and export</span>
              </el-menu-item> -->
            </template>
          </el-menu>
        </el-card>
      </el-col>

      <!-- Right: Configuration content -->
      <el-col :span="20">
        <!-- Gateway Configuration (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'gateway'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>Gateway IM Platform configuration</h3>
            </div>
          </template>

          <div v-loading="gatewayLoading">
            <el-alert
              title="Description"
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 20px"
            >
              Configure access credentials for the IM platform (QQ Bot/Feishu/DingTalk). After the configuration is saved, the adapter will automatically hot-reload without restarting the service.
            </el-alert>

            <!-- QQ Bot Configuration -->
            <h4 style="margin-bottom: 16px;">QQ Bot</h4>
            <el-form :model="gatewayQQConfig" label-width="140px" style="max-width: 600px">
              <el-form-item label="AppID" required>
                <el-input v-model="gatewayQQConfig.app_id" placeholder="Get it on the QQ robot development settings page" />
              </el-form-item>
              <el-form-item label="AppSecret" required>
                <el-input
                  v-model="gatewayQQConfig.app_secret"
                  placeholder="Get it on the QQ robot development settings page"
                  show-password
                />
              </el-form-item>
              <el-form-item label="connection mode" required>
                <el-radio-group v-model="gatewayQQConfig.connection_mode">
                  <el-radio value="websocket">WebSocket (Recommended)</el-radio>
                  <el-radio value="webhook">Webhook</el-radio>
                </el-radio-group>
                <div class="form-tip">
                  <template v-if="gatewayQQConfig.connection_mode === 'websocket'">
                    Actively connect to QQ gateway to receive messages,<strong>No public network required IP</strong>, Suitable for local development and intranet deployment
                  </template>
                  <template v-else>
                    QQ The platform pushes messages to your server,<strong>A callback address that is reachable by the public network is required.</strong>
                  </template>
                </div>
              </el-form-item>
              <el-form-item v-if="gatewayQQConfig.connection_mode === 'webhook'" label="Bot Secret (signing key)">
                <el-input
                  v-model="gatewayQQConfig.bot_secret"
                  placeholder="For webhook signature verification (Ed25519), optional"
                  show-password
                />
                <div class="form-tip">Used for Webhook callback address verification. If not filled in, signature verification will be skipped.</div>
              </el-form-item>
              <el-form-item label="enable">
                <el-switch v-model="gatewayQQConfig.enabled" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleSaveGatewayConfig('qq')" :loading="gatewaySaving">
                  Save configuration
                </el-button>
                <el-button
                  @click="handleTestGatewayConnection('qq')"
                  :loading="gatewayTesting"
                  :disabled="!gatewayQQConfig.configured"
                >
                  test connection
                </el-button>
                <el-tag v-if="gatewayQQConfig.configured" type="success" style="margin-left: 12px">configured</el-tag>
                <el-tag v-else type="info" style="margin-left: 12px">Not configured</el-tag>
              </el-form-item>
            </el-form>

            <el-divider />

            <!-- Feishu Bot configuration -->
            <h4 style="margin-bottom: 16px;">Feishu Bot</h4>
            <el-form :model="gatewayFeishuConfig" label-width="160px" style="max-width: 600px">
              <el-form-item label="App ID" required>
                <el-input v-model="gatewayFeishuConfig.app_id" placeholder="Feishu open platform application App ID" />
              </el-form-item>
              <el-form-item label="App Secret" required>
                <el-input
                  v-model="gatewayFeishuConfig.app_secret"
                  placeholder="Feishu open platform application App Secret"
                  show-password
                />
              </el-form-item>
              <el-form-item label="Verification Token">
                <el-input v-model="gatewayFeishuConfig.verification_token" placeholder="Event subscription verification token (optional)" />
                <div class="form-tip">Feishu open platform → Application → event subscription → Verification Token</div>
              </el-form-item>
              <el-form-item label="Encrypt Key">
                <el-input
                  v-model="gatewayFeishuConfig.encrypt_key"
                  placeholder="Event encryption key (optional)"
                  show-password
                />
                <div class="form-tip">When enabled, Feishu event push will be encrypted and needs to be configured in the Feishu backend at the same time.</div>
              </el-form-item>
              <el-form-item label="enable">
                <el-switch v-model="gatewayFeishuConfig.enabled" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleSaveGatewayConfig('feishu')" :loading="gatewaySaving">
                  Save configuration
                </el-button>
                <el-button
                  @click="handleTestGatewayConnection('feishu')"
                  :loading="gatewayTesting"
                  :disabled="!gatewayFeishuConfig.configured"
                >
                  test connection
                </el-button>
                <el-tag v-if="gatewayFeishuConfig.configured" type="success" style="margin-left: 12px">configured</el-tag>
                <el-tag v-else type="info" style="margin-left: 12px">Not configured</el-tag>
              </el-form-item>
            </el-form>

            <el-divider />

            <!-- DingTalk Bot configuration -->
            <h4 style="margin-bottom: 16px;">DingTalk Bot</h4>
            <el-form :model="gatewayDingtalkConfig" label-width="160px" style="max-width: 600px">
              <el-form-item label="AppKey" required>
                <el-input v-model="gatewayDingtalkConfig.app_key" placeholder="DingTalk open platform application AppKey" />
              </el-form-item>
              <el-form-item label="AppSecret" required>
                <el-input
                  v-model="gatewayDingtalkConfig.app_secret"
                  placeholder="DingTalk open platform application AppSecret"
                  show-password
                />
              </el-form-item>
              <el-form-item label="Robot Coding (Robot Code)">
                <el-input v-model="gatewayDingtalkConfig.robot_code" placeholder="Used to proactively send messages (optional)" />
                <div class="form-tip">DingTalk Open Platform → Application → robot → Robot code, required when actively sending messages</div>
              </el-form-item>
              <el-form-item label="enable">
                <el-switch v-model="gatewayDingtalkConfig.enabled" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleSaveGatewayConfig('dingtalk')" :loading="gatewaySaving">
                  Save configuration
                </el-button>
                <el-button
                  @click="handleTestGatewayConnection('dingtalk')"
                  :loading="gatewayTesting"
                  :disabled="!gatewayDingtalkConfig.configured"
                >
                  test connection
                </el-button>
                <el-tag v-if="gatewayDingtalkConfig.configured" type="success" style="margin-left: 12px">configured</el-tag>
                <el-tag v-else type="info" style="margin-left: 12px">Not configured</el-tag>
              </el-form-item>
            </el-form>
          </div>
        </el-card>

        <!-- Configuration verification (hidden in JD Cloud mode) -->
        <div v-if="!isJdyunMode()" v-show="activeTab === 'validation'">
          <ConfigValidator />
        </div>

        <!-- Model directory management (hidden in JD Cloud mode) -->
        <div v-if="!isJdyunMode()" v-show="activeTab === 'model-catalog'">
          <ModelCatalogManagement />
        </div>

        <!-- Manufacturer management (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'providers'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>Large model manufacturer management</h3>
              <el-button type="primary" @click="showAddProviderDialog">
                <el-icon><Plus /></el-icon>
                Add manufacturer
              </el-button>
            </div>
          </template>

          <div v-loading="providersLoading">
            <el-table :data="sortedProviders" style="width: 100%">
              <el-table-column label="Manufacturer information" width="200">
                <template #default="{ row }">
                  <div class="provider-info">
                    <div class="provider-name">{{ row.display_name }}</div>
                    <div class="provider-id">{{ row.name }}</div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="API key" width="120">
                <template #default="{ row }">
                  <div class="api-key-status">
                    <el-tag
                      :type="row.extra_config?.has_api_key ? 'success' : 'danger'"
                      size="small"
                    >
                      {{ row.extra_config?.has_api_key ? 'configured' : 'Not configured' }}
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="description" label="Description" />
              <el-table-column label="Status" width="120">
                <template #default="{ row }">
                  <div class="status-column">
                    <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                      {{ row.is_active ? 'enable' : 'Disable' }}
                    </el-tag>
                    <el-tag
                      v-if="row.extra_config?.has_api_key"
                      :type="row.extra_config?.source === 'environment' ? 'warning' : 'success'"
                      size="small"
                      class="key-source-tag"
                    >
                      {{ row.extra_config?.source === 'environment' ? 'ENV' : 'DB' }}
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="Support functions" width="200">
                <template #default="{ row }">
                  <div class="features">
                    <el-tag
                      v-for="feature in row.supported_features"
                      :key="feature"
                      size="small"
                      class="feature-tag"
                    >
                      {{ feature }}
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="Operation" width="280" fixed="right">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    @click.stop="editProvider(row)"
                  >
                    Edit
                  </el-button>
                  <el-button
                    v-if="row.extra_config?.has_api_key"
                    size="small"
                    type="info"
                    @click.stop="testProviderAPI(row)"
                    :loading="testingProviders[row.id]"
                  >
                    test
                  </el-button>
                  <el-button
                    size="small"
                    :type="row.is_active ? 'warning' : 'success'"
                    @click.stop="toggleProvider(row)"
                  >
                    {{ row.is_active ? 'Disable' : 'enable' }}
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    @click.stop="deleteProvider(row)"
                  >
                    Delete
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>

        <!-- Large model configuration (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'llm'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>Large model configuration</h3>
              <div>
                <el-button type="success" plain @click="handleBatchImport" :loading="batchImporting">
                  <el-icon><Download /></el-icon>
                  One-click import
                </el-button>
                <el-button type="primary" @click="showAddLLMDialog">
                  <el-icon><Plus /></el-icon>
                  Add model
                </el-button>
              </div>
            </div>
          </template>

          <div v-loading="llmLoading">
            <!-- Card layout grouped by manufacturer -->
            <div v-if="llmConfigGroups.length === 0" class="empty-state">
              <el-empty description="No large model configuration yet">
                <el-button type="primary" @click="showAddLLMDialog">
                  <el-icon><Plus /></el-icon>
                  Add first model
                </el-button>
              </el-empty>
            </div>

            <div v-else class="provider-groups">
              <div
                v-for="group in llmConfigGroups"
                :key="group.provider"
                class="provider-group"
              >
                <!-- Manufacturer head -->
                <div class="provider-header">
                  <div class="provider-info">
                    <el-tag :type="getProviderTagType(group.provider)" size="large" class="provider-tag">
                      <el-icon><OfficeBuilding /></el-icon>
                      {{ group.display_name }}
                    </el-tag>
                    <span class="model-count">{{ group.models.length }} models</span>
                    <el-tag
                      :type="group.is_active ? 'success' : 'danger'"
                      size="small"
                      class="status-tag"
                    >
                      {{ group.is_active ? 'Enabled' : 'Disabled' }}
                    </el-tag>
                  </div>
                  <div class="provider-actions">
                    <el-button
                      size="small"
                      type="primary"
                      @click="addModelToProvider(group)"
                    >
                      <el-icon><Plus /></el-icon>
                      Add model
                    </el-button>
                    <el-button
                      size="small"
                      :type="group.is_active ? 'warning' : 'success'"
                      @click="toggleProviderStatus(group)"
                    >
                      {{ group.is_active ? 'Disable' : 'enable' }}
                    </el-button>
                  </div>
                </div>

                <!-- Model List - Tabular Layout -->
                <el-table :data="group.models" style="width: 100%" stripe>
                  <!-- Model name -->
                  <el-table-column label="Model name" width="200">
                    <template #default="{ row }">
                      <div class="model-name-cell">
                        <div class="model-display-name">
                          {{ row.model_display_name || row.model_name }}
                        </div>
                        <div v-if="row.model_display_name" class="model-code-text">{{ row.model_name }}</div>
                      </div>
                    </template>
                  </el-table-column>

                  <!-- Status -->
                  <el-table-column label="Status" width="80" align="center">
                    <template #default="{ row }">
                      <el-tag :type="row.enabled ? 'success' : 'danger'" size="small">
                        {{ row.enabled ? 'enable' : 'Disable' }}
                      </el-tag>
                    </template>
                  </el-table-column>

                  <!-- Basic configuration -->
                  <el-table-column label="Basic configuration" width="200">
                    <template #default="{ row }">
                      <div class="config-cell">
                        <div>Token: {{ row.max_tokens }}</div>
                        <div>temperature: {{ row.temperature }} | timeout: {{ row.timeout }}s</div>
                      </div>
                    </template>
                  </el-table-column>

                  <!-- Pricing -->
                  <el-table-column label="Pricing" width="180">
                    <template #default="{ row }">
                      <div v-if="row.input_price_per_1k || row.output_price_per_1k" class="pricing-cell">
                        <div>input: {{ formatPrice(row.input_price_per_1k) }} {{ row.currency || 'CNY' }}/1K</div>
                        <div>output: {{ formatPrice(row.output_price_per_1k) }} {{ row.currency || 'CNY' }}/1K</div>
                      </div>
                      <span v-else class="text-muted">-</span>
                    </template>
                  </el-table-column>

                  <!-- Model capabilities -->
                  <el-table-column label="Model capabilities" width="280">
                    <template #default="{ row }">
                      <div class="capability-cell">
                        <div v-if="row.capability_level" class="capability-row-item">
                          <span class="label">Level:</span>
                          <el-tag :type="getCapabilityLevelType(row.capability_level)" size="small">
                            {{ getCapabilityLevelText(row.capability_level) }}
                          </el-tag>
                        </div>
                        <div v-if="row.suitable_roles && row.suitable_roles.length > 0" class="capability-row-item">
                          <span class="label">role:</span>
                          <el-tag
                            v-for="role in row.suitable_roles"
                            :key="role"
                            type="info"
                            size="small"
                            style="margin-right: 4px;"
                          >
                            {{ getRoleText(role) }}
                          </el-tag>
                        </div>
                        <div v-if="row.recommended_depths && row.recommended_depths.length > 0" class="capability-row-item">
                          <span class="label">Depth:</span>
                          <el-tag
                            v-for="depth in row.recommended_depths"
                            :key="depth"
                            type="success"
                            size="small"
                            style="margin-right: 4px;"
                          >
                            {{ depth }}
                          </el-tag>
                        </div>
                      </div>
                    </template>
                  </el-table-column>

                  <!-- Operation -->
                  <el-table-column label="Operation" width="260" fixed="right">
                    <template #default="{ row }">
                      <el-button size="small" @click="editLLMConfig(row)">
                        Edit
                      </el-button>
                      <el-button
                        size="small"
                        type="primary"
                        @click="testLLMConfig(row)"
                      >
                        test
                      </el-button>
                      <el-button
                        size="small"
                        :type="row.enabled ? 'warning' : 'success'"
                        @click="toggleLLMConfig(row)"
                      >
                        {{ row.enabled ? 'Disable' : 'enable' }}
                      </el-button>
                      <el-button
                        size="small"
                        type="danger"
                        @click="deleteLLMConfig(row)"
                      >
                        Delete
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </el-card>

        <!-- Data source configuration -->
        <el-card v-show="activeTab === 'datasource'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>Data source configuration</h3>
              <!-- Hide adding and managing category buttons in JD Cloud mode -->
              <div class="header-actions">
                <el-button v-if="!isJdyunMode()" @click="showMarketCategoryManagement">
                  <el-icon><Setting /></el-icon>
                  Management classification
                </el-button>
                <el-button type="primary" @click="showAddDataSourceDialog">
                  <el-icon><Plus /></el-icon>
                  Add data source
                </el-button>
              </div>
            </div>
          </template>

          <div v-loading="dataSourceLoading" class="datasource-content">
            <!-- Data source group display -->
            <div v-if="dataSourceGroups.length > 0" class="datasource-groups">
              <SortableDataSourceList
                v-for="group in dataSourceGroups"
                :key="group.categoryId"
                :category-id="group.categoryId"
                :category-display-name="group.categoryDisplayName"
                :data-sources="group.dataSources"
                @update-order="handleUpdateDataSourceOrder"
                @edit-datasource="editDataSourceConfig"
                @manage-grouping="showDataSourceGroupingDialog"
                @manage-category="showMarketCategoryManagement"
                @add-datasource="showAddDataSourceDialog"
                @delete-datasource="deleteDataSourceConfig"
              />
            </div>

            <!-- Ungrouped data source -->
            <div v-if="ungroupedDataSources.length > 0" class="ungrouped-section">
              <el-card shadow="never">
                <template #header>
                  <div class="section-header">
                    <h4>Ungrouped data source</h4>
                    <el-tag type="warning" size="small">{{ ungroupedDataSources.length }} a</el-tag>
                  </div>
                </template>

                <div class="ungrouped-list">
                  <div
                    v-for="dataSource in ungroupedDataSources"
                    :key="dataSource.name"
                    class="ungrouped-item"
                  >
                    <div class="item-info">
                      <span class="item-name">{{ dataSource.display_name || dataSource.name }}</span>
                      <el-tag :type="dataSource.enabled ? 'success' : 'danger'" size="small">
                        {{ dataSource.enabled ? 'enable' : 'Disable' }}
                      </el-tag>
                      <span class="item-type">{{ dataSource.type }}</span>
                    </div>
                    <div class="item-actions">
                      <el-button size="small" @click="editDataSourceConfig(dataSource)">
                        Edit
                      </el-button>
                      <el-button size="small" @click="showDataSourceGroupingDialog(dataSource.name)">
                        Group
                      </el-button>
                      <el-button size="small" type="primary" @click="testDataSource(dataSource)">
                        test
                      </el-button>
                      <el-button size="small" type="danger" @click="deleteDataSourceConfig(dataSource)">
                        Delete
                      </el-button>
                    </div>
                  </div>
                </div>
              </el-card>
            </div>

            <!-- Empty state -->
            <div v-if="dataSourceConfigs.length === 0" class="empty-state">
              <el-empty description="No data source configuration yet">
                <el-button type="primary" @click="showAddDataSourceDialog">
                  Add first data source
                </el-button>
              </el-empty>
            </div>
          </div>
        </el-card>

        <!-- Database configuration (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'database'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>Database configuration</h3>
              <el-text type="info" size="small">System core database configuration, only supports editing and testing</el-text>
            </div>
          </template>

          <div v-loading="databaseLoading">
            <el-table :data="databaseConfigs" style="width: 100%">
              <el-table-column prop="name" label="Name" width="150" />
              <el-table-column prop="type" label="Type" width="120" />
              <el-table-column prop="host" label="Host" width="150" />
              <el-table-column prop="port" label="port" width="100" />
              <el-table-column label="Status" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.enabled ? 'success' : 'danger'">
                    {{ row.enabled ? 'enable' : 'Disable' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="Operation" width="200">
                <template #default="{ row }">
                  <el-button size="small" @click="editDatabaseConfig(row)">Edit</el-button>
                  <el-button size="small" type="primary" @click="testDatabase(row)">
                    test connection
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>

        <!-- System settings (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'system'" class="config-content" shadow="never">
          <template #header>
            <h3>System settings</h3>
          </template>

          <el-alert type="info" show-icon :closable="false"
            title="Sensitive/ENV source items are locked"
            description="Settings from environment variables or marked as sensitive will be displayed read-only. Only editable items are submitted when saving."
            style="margin-bottom: 12px;"
          />

          <el-form :model="systemSettings" label-width="150px" v-loading="systemLoading">
            <!-- Basic settings -->
            <el-divider content-position="left">Basic settings</el-divider>

            <el-form-item label="Quickly analyze models">
              <el-select
                v-model="systemSettings.quick_analysis_model_config_id"
                :disabled="!isEditable('quick_analysis_model')"
                placeholder="Choose a quick analysis model"
                filterable
              >
                <el-option-group
                  v-for="group in groupedAvailableModels"
                  :key="group.provider"
                  :label="group.providerLabel"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.config_id || `${model.provider}/${model.model_name}`"
                    :label="formatModelSelectionLabel(model)"
                    :value="model.config_id"
                  >
                    <div style="display: flex; flex-direction: column;">
                      <span>{{ formatModelSelectionLabel(model) }}</span>
                      <span style="font-size: 12px; color: #909399;">{{ formatModelSelectionMeta(model) }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="setting-description">Used for market analysis, news analysis, fundamental analysis, researchers, etc., with fast response speed. Can choose from all vendor-enabled models</div>
            </el-form-item>

            <el-form-item label="Deep decision-making model">
              <el-select
                v-model="systemSettings.deep_analysis_model_config_id"
                :disabled="!isEditable('deep_analysis_model')"
                placeholder="Choose a deep decision-making model"
                filterable
              >
                <el-option-group
                  v-for="group in groupedAvailableModels"
                  :key="group.provider"
                  :label="group.providerLabel"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.config_id || `${model.provider}/${model.model_name}`"
                    :label="formatModelSelectionLabel(model)"
                    :value="model.config_id"
                  >
                    <div style="display: flex; flex-direction: column;">
                      <span>{{ formatModelSelectionLabel(model) }}</span>
                      <span style="font-size: 12px; color: #909399;">{{ formatModelSelectionMeta(model) }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="setting-description">Used for comprehensive decision-making by research integrators and final assessment by risk assessors, with strong reasoning ability. Can choose from all vendor-enabled models</div>
            </el-form-item>

            <el-form-item label="Deep inference model">
              <el-select
                v-model="systemSettings.deep_reasoning_model_config_id"
                :disabled="!isEditable('deep_reasoning_model')"
                placeholder="Optional, used in strong inference scenarios"
                filterable
                clearable
              >
                <el-option-group
                  v-for="group in groupedAvailableModels"
                  :key="group.provider"
                  :label="group.providerLabel"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.config_id || `${model.provider}/${model.model_name}`"
                    :label="formatModelSelectionLabel(model)"
                    :value="model.config_id"
                  >
                    <div style="display: flex; flex-direction: column;">
                      <span>{{ formatModelSelectionLabel(model) }}</span>
                      <span style="font-size: 12px; color: #909399;">{{ formatModelSelectionMeta(model) }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="setting-description">Used for strong reasoning scenarios such as intelligent assistant planning and strategy generation. Uses deep decision models when not configured, selectable from all vendor-enabled models</div>
            </el-form-item>

            <el-form-item label="programming model">
              <el-select
                v-model="systemSettings.coding_model_config_id"
                :disabled="!isEditable('coding_model')"
                placeholder="Optional, used for policy DSL generation"
                filterable
                clearable
              >
                <el-option-group
                  v-for="group in groupedAvailableModels"
                  :key="group.provider"
                  :label="group.providerLabel"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.config_id || `${model.provider}/${model.model_name}`"
                    :label="formatModelSelectionLabel(model)"
                    :value="model.config_id"
                  >
                    <div style="display: flex; flex-direction: column;">
                      <span>{{ formatModelSelectionLabel(model) }}</span>
                      <span style="font-size: 12px; color: #909399;">{{ formatModelSelectionMeta(model) }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="setting-description">Used for policy DSL generation, specializing in JSON output. Uses deep inference/deep decision-making models when not configured, selectable from all vendor-enabled models</div>
            </el-form-item>

            <!-- 🔥 New: Default Embedding model configuration -->
            <el-form-item label="Default Embedding model">
              <el-select
                v-model="systemSettings.default_embedding_model"
                :disabled="!isEditable('default_embedding_model')"
                placeholder="Select the default Embedding model"
                filterable
                clearable
              >
                <el-option-group
                  v-for="provider in embeddingProviders"
                  :key="provider.name"
                  :label="provider.display_name"
                >
                  <el-option
                    v-for="model in getEmbeddingModelsForProvider(provider.name)"
                    :key="`${provider.name}/${model}`"
                    :label="formatEmbeddingSelectionLabel(provider, model)"
                    :value="`${provider.name}:${model}`"
                  >
                    <div style="display: flex; flex-direction: column;">
                      <span>{{ formatEmbeddingSelectionLabel(provider, model) }}</span>
                      <span style="font-size: 12px; color: #909399;">{{ formatEmbeddingSelectionMeta(provider, model) }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="setting-description">
                For text vectorization and memoization functions, choose from all vendors that support embedding (format: vendor:Model name, such as:dashscope:text-embedding-v3) 
                <!-- Vector migration feature deprecated: Vector storage has been migrated from Qdrant to MongoDB, Qdrant migration is no longer required -->
                <!--
                <el-button
                  type="warning"
                  size="small"
                  @click="openMigrationDialog"
                  style="margin-left: 12px;"
                >
                  Migrate vector data
                </el-button>
                -->
              </div>
            </el-form-item>

            <el-form-item label="Enable cost tracking">
              <el-switch v-model="systemSettings.enable_cost_tracking" :disabled="!isEditable('enable_cost_tracking')" />
            </el-form-item>

            <el-form-item label="Cost warning threshold">
              <el-input-number v-model="systemSettings.cost_alert_threshold" :min="0" :step="10" :disabled="!isEditable('cost_alert_threshold')" />
              <span class="setting-description">Yuan</span>
            </el-form-item>

            <el-form-item label="currency preference">
              <el-select v-model="systemSettings.currency_preference" :disabled="!isEditable('currency_preference')">
                <el-option label="RMB (CNY)" value="CNY" />
                <el-option label="US dollars (USD)" value="USD" />
                <el-option label="Euro (EUR)" value="EUR" />
              </el-select>
            </el-form-item>

            <el-form-item label="System time zone">
              <el-select v-model="systemSettings.app_timezone" :disabled="!isEditable('app_timezone')" filterable>
                <el-option label="Asia/Shanghai (UTC+8)" value="Asia/Shanghai" />
                <el-option label="UTC (UTC+0)" value="UTC" />
              </el-select>
              <div class="setting-description">A unified time zone used for back-end storage and display; the newly written time after modification will be saved and returned according to this time zone.</div>
            </el-form-item>


            <!-- Performance settings -->
            <el-divider content-position="left">Performance settings</el-divider>

            <el-form-item label="Analysis timeout">
              <el-input-number v-model="systemSettings.default_analysis_timeout" :min="60" :max="1800" :disabled="!isEditable('default_analysis_timeout')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="Enable caching">
              <el-switch v-model="systemSettings.enable_cache" :disabled="!isEditable('enable_cache')" />
            </el-form-item>

            <el-form-item label="cache TTL">
              <el-input-number v-model="systemSettings.cache_ttl" :min="300" :max="86400" :disabled="!isEditable('cache_ttl')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <!-- Backtest DSL generation -->
            <el-divider content-position="left">Backtest strategy generation</el-divider>
            <el-form-item label="Verify when generating DSL">
              <el-switch v-model="systemSettings.dsl_validate_on_generate" :disabled="!isEditable('dsl_validate_on_generate')" />
              <span class="setting-description">Enable L2 semantic verification and automatically let LLM correct it when it fails</span>
            </el-form-item>
            <el-form-item label="Perform verification">
              <el-switch v-model="systemSettings.dsl_run_execution_check" :disabled="!isEditable('dsl_run_execution_check')" />
              <span class="setting-description">Enable L3 lightweight backtest verification (the backtest service needs to be started)</span>
            </el-form-item>

            <!-- Queue vs. Worker -->
            <el-divider content-position="left">Queue vs. Worker</el-divider>

            <el-form-item label="Worker heartbeat interval">
              <el-input-number v-model="systemSettings.worker_heartbeat_interval_seconds" :min="1" :step="1" :disabled="!isEditable('worker_heartbeat_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="Worker Heartbeat reporting cycle; if it is too small, it will increase the load; if it is too large, it may affect the health check." placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <el-form-item label="Queue polling interval">
              <el-input-number v-model="systemSettings.queue_poll_interval_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('queue_poll_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="Frequency of queue pull tasks; too small will increase Redis pressure, too large will affect task delay" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <el-form-item label="Queue cleaning interval">
              <el-input-number v-model="systemSettings.queue_cleanup_interval_seconds" :min="1" :step="1" :disabled="!isEditable('queue_cleanup_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="How often to clean up timed/failed tasks; recommended≥60 seconds" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <!-- SSE settings -->
            <el-divider content-position="left">SSE</el-divider>

            <el-form-item label="SSE Poll timeout">
              <el-input-number v-model="systemSettings.sse_poll_timeout_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('sse_poll_timeout_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="Task progress SSE waits for each timeout; too small will generate more requests" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <el-form-item label="SSE heartbeat interval">
              <el-input-number v-model="systemSettings.sse_heartbeat_interval_seconds" :min="1" :step="1" :disabled="!isEditable('sse_heartbeat_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="SSE Maintain the heartbeat event sending cycle of a long connection" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <!-- TradingAgents (optional) -->
            <el-divider content-position="left">TradingAgents (optional)</el-divider>
            <el-form-item label="Use app cache first">
              <el-switch v-model="systemSettings.ta_use_app_cache" :disabled="!isEditable('ta_use_app_cache')" />
              <div class="setting-description">Prioritize the use of App cache (stock_basic_info / market_quotes), and automatically fall back to the direct data source if it is not hit.</div>
            </el-form-item>


            <el-form-item label="Minimum request interval for Hong Kong stocks">
              <el-input-number v-model="systemSettings.ta_hk_min_request_interval_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('ta_hk_min_request_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="The minimum interval for Hong Kong stock data requests, used for throttling" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <el-form-item label="Hong Kong stock request timed out">
              <el-input-number v-model="systemSettings.ta_hk_timeout_seconds" :min="1" :step="1" :disabled="!isEditable('ta_hk_timeout_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="The biggest retest of Hong Kong stocks">
              <el-input-number v-model="systemSettings.ta_hk_max_retries" :min="0" :step="1" :disabled="!isEditable('ta_hk_max_retries')" />
            </el-form-item>

            <el-form-item label="Hong Kong stocks speed limit waiting">
              <el-input-number v-model="systemSettings.ta_hk_rate_limit_wait_seconds" :min="1" :step="1" :disabled="!isEditable('ta_hk_rate_limit_wait_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="Hong Kong stock cache TTL">
              <el-input-number v-model="systemSettings.ta_hk_cache_ttl_seconds" :min="10" :step="10" :disabled="!isEditable('ta_hk_cache_ttl_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="A Minimum stock call interval">
              <el-input-number v-model="systemSettings.ta_china_min_api_interval_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('ta_china_min_api_interval_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="Minimum call interval for U.S. stocks">
              <el-input-number v-model="systemSettings.ta_us_min_api_interval_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('ta_us_min_api_interval_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="GoogleNews Minimum delay">
              <el-input-number v-model="systemSettings.ta_google_news_sleep_min_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('ta_google_news_sleep_min_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="GoogleNews maximum delay">
              <el-input-number v-model="systemSettings.ta_google_news_sleep_max_seconds" :min="0.1" :step="0.1" :disabled="!isEditable('ta_google_news_sleep_max_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>


            <el-form-item label="Task flow maximum idle">
              <el-input-number v-model="systemSettings.sse_task_max_idle_seconds" :min="10" :step="10" :disabled="!isEditable('sse_task_max_idle_seconds')" />
              <span class="setting-description">seconds</span>
            </el-form-item>

            <el-form-item label="Batch stream polling interval">
              <el-input-number v-model="systemSettings.sse_batch_poll_interval_seconds" :min="0.5" :step="0.5" :disabled="!isEditable('sse_batch_poll_interval_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="Batch progress refresh frequency; too small will increase server load" placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <el-form-item label="Batch stream maximum idle">
              <el-input-number v-model="systemSettings.sse_batch_max_idle_seconds" :min="10" :step="10" :disabled="!isEditable('sse_batch_max_idle_seconds')" />
              <span class="setting-description">seconds</span>
              <el-tooltip effect="dark" content="The maximum idle time allowed for the batch stream without events. Timeout will close the connection." placement="top">
                <i class="el-icon-info" style="margin-left:8px; color:#909399;" />
              </el-tooltip>
            </el-form-item>

            <!-- Logging and monitoring -->
            <el-divider content-position="left">Logging and monitoring</el-divider>

            <el-form-item label="Log level">
              <el-select v-model="systemSettings.log_level" :disabled="!isEditable('log_level')">
                <el-option label="DEBUG" value="DEBUG" />
                <el-option label="INFO" value="INFO" />
                <el-option label="WARNING" value="WARNING" />
                <el-option label="ERROR" value="ERROR" />
              </el-select>
            </el-form-item>

            <el-form-item label="Enable monitoring">
              <el-switch v-model="systemSettings.enable_monitoring" :disabled="!isEditable('enable_monitoring')" />
            </el-form-item>

            <!-- Data management -->
            <el-divider content-position="left">Data management</el-divider>

            <el-form-item label="Automatically save usage records">
              <el-switch v-model="systemSettings.auto_save_usage" :disabled="!isEditable('auto_save_usage')" />
            </el-form-item>

            <el-form-item label="Maximum number of usage records">
              <el-input-number v-model="systemSettings.max_usage_records" :min="1000" :max="100000" :step="1000" :disabled="!isEditable('max_usage_records')" />
            </el-form-item>

            <el-form-item label="Automatically create directories">
              <el-switch v-model="systemSettings.auto_create_dirs" :disabled="!isEditable('auto_create_dirs')" />
            </el-form-item>

            <!-- Agent configuration -->
            <el-divider content-position="left">network proxy</el-divider>

            <el-alert
              type="info"
              show-icon
              :closable="false"
              style="margin-bottom: 16px;"
            >
              <template #title>
                <span>Proxy is used to access data sources that need to bypass the firewall (such as Yahoo Finance, Google News, etc.)</span>
              </template>
              <template #default>
                <div style="font-size: 12px; color: #909399;">
                  Domestic data sources (Oriental Fortune, Sina, Tencent, etc.) have automatically been added to the NO_PROXY list and no proxy is required.
                  Needed after modification<strong>Restart the backend service</strong>to take effect.
                </div>
              </template>
            </el-alert>

            <el-form-item label="Enable proxy">
              <el-switch
                v-model="systemSettings.proxy_enabled"
                :disabled="!isEditable('proxy_enabled')"
                active-text="turn on"
                inactive-text="close"
              />
              <div class="setting-description">
                Control whether to use a proxy to access foreign data sources. When closed, all requests will be connected directly (you may not be able to access Yahoo Finance, Google News, etc.)
              </div>
            </el-form-item>

            <el-form-item label="HTTP agent">
              <el-input
                v-model="systemSettings.http_proxy"
                :disabled="!isEditable('http_proxy')"
                placeholder="For example: 127.0.0.1:7890 or http://127.0.0.1:7890"
                clearable
              />
              <div class="setting-description">Proxy server address used for HTTP requests, can be omitted http:// prefix</div>
            </el-form-item>

            <el-form-item label="HTTPS agent">
              <el-input
                v-model="systemSettings.https_proxy"
                :disabled="!isEditable('https_proxy')"
                placeholder="For example: 127.0.0.1:7890 or http://127.0.0.1:7890"
                clearable
              />
              <div class="setting-description">Proxy server address to use for HTTPS requests (usually the same as the HTTP proxy), can be omitted http:// prefix</div>
            </el-form-item>

            <el-form-item label="Not using a proxy">
              <el-input
                v-model="systemSettings.no_proxy"
                type="textarea"
                :rows="3"
                :disabled="!isEditable('no_proxy')"
                placeholder="localhost,127.0.0.1,eastmoney.com,..."
              />
              <div class="setting-description">
                List of domain names that do not use proxies, separated by commas. Domestic data sources have been preset, and other domain names can be added as needed.
              </div>
            </el-form-item>

            <el-form-item label="proxy test">
              <div style="display: flex; gap: 12px; align-items: center;">
                <el-button
                  type="info"
                  @click="testProxyConnection"
                  :loading="proxyTesting"
                  :disabled="!systemSettings.http_proxy && !systemSettings.https_proxy"
                >
                  <el-icon><Connection /></el-icon>
                  Test proxy connection
                </el-button>
                <span v-if="proxyTestResult" :class="['proxy-test-result', proxyTestResult.success ? 'success' : 'error']">
                  {{ proxyTestResult.message }}
                </span>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveSystemSettings" :loading="systemSaving">
                Save settings
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- API Key status (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'api-keys'" class="config-content" shadow="never">
          <template #header>
            <div class="card-header">
              <h3>API Key status</h3>
              <el-button @click="loadProviders" :loading="providersLoading">
                <el-icon><Refresh /></el-icon>
                refresh status
              </el-button>
            </div>
          </template>

          <div class="api-keys-content" v-loading="providersLoading">
            <el-row :gutter="24">
              <el-col :span="12">
                <h4>🔑 AI Manufacturer key status</h4>
                <div
                  v-for="provider in providers"
                  :key="provider.id"
                  class="api-key-item"
                >
                  <el-icon><Key /></el-icon>
                  <span class="key-name">{{ provider.display_name }}</span>
                  <el-tag
                    :type="getKeyStatusType(provider)"
                    size="small"
                  >
                    {{ getKeyStatusText(provider) }}
                  </el-tag>
                  <el-button
                    v-if="!provider.extra_config?.has_api_key"
                    size="small"
                    type="primary"
                    link
                    @click="editProvider(provider)"
                  >
                    Configuration
                  </el-button>
                </div>

                <div v-if="providers.length === 0" class="empty-state">
                  <el-empty description="No factory configuration yet">
                    <el-button type="primary" @click="activeTab = 'providers'">
                      Add manufacturer
                    </el-button>
                  </el-empty>
                </div>
              </el-col>

              <el-col :span="12">
                <h4>📊 Configuration statistics</h4>
                <div class="stats-grid">
                  <div class="stat-item">
                    <div class="stat-number">{{ providers.length }}</div>
                    <div class="stat-label">Total number of manufacturers</div>
                  </div>
                  <div class="stat-item">
                    <div class="stat-number">{{ configuredProvidersCount }}</div>
                    <div class="stat-label">Configured key</div>
                  </div>
                  <div class="stat-item">
                    <div class="stat-number">{{ activeProvidersCount }}</div>
                    <div class="stat-label">Enable manufacturer</div>
                  </div>
                  <div class="stat-item">
                    <div class="stat-number">{{ llmConfigs.length }}</div>
                    <div class="stat-label">Configure model</div>
                  </div>
                </div>
              </el-col>
            </el-row>

            <el-divider />

            <div class="api-key-help">
              <h4>💡 Configuration instructions</h4>
              <el-row :gutter="16">
                <el-col :span="8">
                  <el-card shadow="never" class="help-card">
                    <h5>How to configure API key?</h5>
                    <ol>
                      <li>in"Factory management"Add AI manufacturers to</li>
                      <li>Edit the manufacturer information and fill in the API key</li>
                      <li>in"Large model configuration"Select manufacturer and model</li>
                      <li>The system automatically uses the manufacturer s API key</li>
                    </ol>
                  </el-card>
                </el-col>
                <el-col :span="8">
                  <el-card shadow="never" class="help-card">
                    <h5>🔄 Migrate from environment variables</h5>
                    <p>If you have configured an API key in the .env file before, you can migrate to manufacturer management with one click:</p>
                    <el-button
                      type="primary"
                      @click="migrateFromEnv"
                      :loading="migrateLoading"
                      size="small"
                    >
                      Migrate environment variables
                    </el-button>
                  </el-card>
                </el-col>
                <el-col :span="8">
                  <el-alert
                    title="🔒 Safety tips"
                    type="warning"
                    description="Sensitive keys are injected through environment variables/operation and maintenance configurations, and backend responses have been uniformly desensitized; please do not save real keys in the interface or export file."
                    show-icon
                    :closable="false"
                  />
                </el-col>
              </el-row>
            </div>
          </div>
        </el-card>

        <!-- Import and export (hidden in JD Cloud mode) -->
        <el-card v-if="!isJdyunMode()" v-show="activeTab === 'import-export'" class="config-content" shadow="never">
          <template #header>
            <h3>Import and export</h3>
          </template>

          <div class="import-export-content">
            <el-row :gutter="24">
              <el-col :span="12">
                <h4>Export configuration</h4>
                <p>Export current system configuration as JSON file</p>
                <el-button type="primary" @click="exportConfig" :loading="exportLoading">
                  <el-icon><Download /></el-icon>
                  Export configuration
                </el-button>
              </el-col>

              <el-col :span="12">
                <h4>Import configuration</h4>
                <p>Import configuration from JSON file (will overwrite existing configuration)</p>
                <el-upload
                  :before-upload="handleImportConfig"
                  :show-file-list="false"
                  accept=".json"
                >
                  <el-button type="success" :loading="importLoading">
                    <el-icon><Upload /></el-icon>
                    Import configuration
                  </el-button>
                </el-upload>
              </el-col>
            </el-row>

            <el-divider />

            <div class="legacy-migration">
              <h4>Traditional configuration migration</h4>
              <p>Migrate old version configuration files to new system</p>
              <el-button type="warning" @click="migrateLegacyConfig" :loading="migrateLoading">
                <el-icon><Refresh /></el-icon>
                Migrate legacy configuration
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Manufacturer management dialog box (hidden in JD Cloud mode) -->
    <ProviderDialog
      v-if="!isJdyunMode()"
      v-model:visible="providerDialogVisible"
      :provider="currentProvider"
      @success="handleProviderSuccess"
    />

    <!-- Large model configuration dialog box (hidden in JD Cloud mode) -->
    <LLMConfigDialog
      v-if="!isJdyunMode()"
      v-model:visible="llmDialogVisible"
      :config="currentLLMConfig"
      @success="handleLLMConfigSuccess"
    />

    <!-- One-click import dialog box -->
    <el-dialog v-model="batchImportDialogVisible" title="Import large model configurations with one click" width="480px">
      <p style="margin-bottom: 16px; color: var(--el-text-color-regular); font-size: 14px;">
        Select the manufacturer to be imported, and the system will automatically import all model configurations of this manufacturer from the model directory.
      </p>
      <el-checkbox-group v-model="selectedImportProviders">
        <div v-for="p in importableProviders" :key="p.name" style="margin-bottom: 8px;">
          <el-checkbox :label="p.name" :value="p.name">
            {{ p.display_name }}
            <el-tag v-if="p.extra_config?.has_api_key" size="small" type="success" style="margin-left: 4px;">Configured key</el-tag>
            <el-tag v-else size="small" type="info" style="margin-left: 4px;">No key configured</el-tag>
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <div v-if="importableProviders.length === 0" style="text-align: center; padding: 20px; color: var(--el-text-color-secondary);">
        There are currently no enabled manufacturers
      </div>
      <template #footer>
        <el-button @click="batchImportDialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="batchImporting" :disabled="selectedImportProviders.length === 0" @click="confirmBatchImport">
          Import selected manufacturers
        </el-button>
      </template>
    </el-dialog>

    <!-- Data source configuration dialog -->
    <DataSourceConfigDialog
      v-model:visible="dataSourceDialogVisible"
      :config="currentDataSourceConfig"
      @success="handleDataSourceConfigSuccess"
    />

    <!-- Market classification management dialog box (hidden in JD Cloud mode) -->
    <el-dialog
      v-if="!isJdyunMode()"
      v-model="marketCategoryManagementVisible"
      title="Market classification management"
      width="80%"
      :close-on-click-modal="false"
    >
      <MarketCategoryManagement @success="handleMarketCategorySuccess" />
    </el-dialog>

    <!-- Data source grouping dialog box -->
    <DataSourceGroupingDialog
      v-model:visible="dataSourceGroupingDialogVisible"
      :data-source-name="currentDataSourceName"
      @success="handleDataSourceGroupingSuccess"
    />

    <!-- Database configuration dialog box (hidden in JD Cloud mode) -->
    <el-dialog
      v-if="!isJdyunMode()"
      v-model="databaseDialogVisible"
      title="Edit database configuration"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="Tips"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        Database configuration is the core configuration of the system, and the configuration name and type cannot be modified. If the username and password are not filled in in the configuration, the system will use the configuration in the environment variable (.env file).
      </el-alert>

      <el-form :model="currentDatabaseConfig" label-width="120px">
        <el-form-item label="Configuration name" required>
          <el-input
            v-model="currentDatabaseConfig.name"
            placeholder="Please enter configuration name"
            disabled
          />
        </el-form-item>

        <el-form-item label="Database type" required>
          <el-select v-model="currentDatabaseConfig.type" placeholder="Please select database type" disabled>
            <el-option label="MongoDB" value="mongodb" />
            <el-option label="Redis" value="redis" />
            <el-option label="MySQL" value="mysql" />
            <el-option label="PostgreSQL" value="postgresql" />
            <el-option label="SQLite" value="sqlite" />
          </el-select>
        </el-form-item>

        <el-form-item label="host address" required>
          <el-input v-model="currentDatabaseConfig.host" placeholder="For example: localhost" />
        </el-form-item>

        <el-form-item label="port number" required>
          <el-input-number
            v-model="currentDatabaseConfig.port"
            :min="1"
            :max="65535"
            placeholder="For example: 27017"
          />
        </el-form-item>

        <el-form-item label="Username">
          <el-input v-model="currentDatabaseConfig.username" placeholder="Please enter username" />
        </el-form-item>

        <el-form-item label="Password">
          <el-input
            v-model="currentDatabaseConfig.password"
            type="password"
            placeholder="Please enter password"
            show-password
          />
        </el-form-item>

        <el-form-item label="Database name">
          <el-input v-model="currentDatabaseConfig.database" placeholder="Please enter database name" />
        </el-form-item>

        <el-form-item label="Connection pool size">
          <el-input-number v-model="currentDatabaseConfig.pool_size" :min="1" :max="100" />
        </el-form-item>

        <el-form-item label="Maximum overflow connection">
          <el-input-number v-model="currentDatabaseConfig.max_overflow" :min="0" :max="200" />
        </el-form-item>

        <el-form-item label="Enabled status">
          <el-switch v-model="currentDatabaseConfig.enabled" />
        </el-form-item>

        <el-form-item label="Description">
          <el-input
            v-model="currentDatabaseConfig.description"
            type="textarea"
            :rows="3"
            placeholder="Please enter configuration description"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="databaseDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveDatabaseConfig">save</el-button>
      </template>
    </el-dialog>

    <!-- Vector migration dialog is deprecated: vector storage has been migrated from Qdrant to MongoDB -->
    <!--
    <el-dialog
      v-if="!isJdyunMode()"
      v-model="migrationDialogVisible"
      title="Migrate vector data"
      width="780px"
      :close-on-click-modal="false"
      @opened="loadMigrationData"
    >
      <el-alert
        title="Description"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        <template #default>
          <div>
            Change Embedding model (currently:<strong>{{ migrationCurrentModel }}</strong>) Finally, the old vector data needs to be regenerated with the new model.
            Status tag:<el-tag type="warning" size="small">To be migrated</el-tag> never migrated,
            <el-tag type="success" size="small">Migrated</el-tag> Consistent with the current model,
            <el-tag type="danger" size="small">Expired</el-tag> Migrated but the model has changed.
          </div>
        </template>
      </el-alert>

      <div style="margin-bottom: 12px;">
        <el-button
          type="primary"
          :disabled="pendingMigrations.length === 0"
          :loading="migrationLoading"
          @click="migrateAllPending"
        >
          Migrate all with one click ({{ pendingMigrations.length }} (to be migrated)
        </el-button>
      </div>

      <el-table :data="allCollections" v-loading="migrationLoading" max-height="400px" size="small">
        <el-table-column prop="name" label="Collection" min-width="240" show-overflow-tooltip />
        <el-table-column label="Source" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.source === 'main' ? 'primary' : 'info'" size="small">
              {{ row.source === 'main' ? 'main storage' : 'mem0' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="data" width="90" align="center">
          <template #default="{ row }">
            {{ row.point_count }} Article
          </template>
        </el-table-column>
        <el-table-column prop="dimensions" label="Dimensions" width="70" align="center" />
        <el-table-column label="Migration status" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.migration_status === 'pending'" type="warning" size="small">To be migrated</el-tag>
            <el-tag v-else-if="row.migration_status === 'migrated'" type="success" size="small">Migrated</el-tag>
            <el-tag v-else-if="row.migration_status === 'outdated'" type="danger" size="small">Expired</el-tag>
            <span v-else style="color: #909399;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="Operation" width="120" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.point_count > 0 && row.migration_status !== 'migrated'"
              size="small"
              type="warning"
              :loading="migratingCollections[row.name]"
              @click="migrateOne(row)"
            >
              Migrate
            </el-button>
            <template v-else-if="row.point_count === 0">
              <span style="color: #909399; font-size: 12px;">empty data</span>
              <el-button
                size="small"
                type="danger"
                text
                :loading="migratingCollections[row.name]"
                @click="deleteCollection(row)"
              >
                Delete
              </el-button>
            </template>
            <el-tag v-else type="success" size="small">Completed</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="migrationResults.length > 0" style="margin-top: 16px;">
        <el-descriptions
          v-for="(r, i) in migrationResults"
          :key="i"
          :column="2"
          border
          size="small"
          style="margin-bottom: 8px;"
        >
          <el-descriptions-item label="Collection">{{ r.collection_name || r.source_collection }}</el-descriptions-item>
          <el-descriptions-item label="Status">
            <el-tag :type="r.success ? 'success' : 'danger'" size="small">
              {{ r.success ? 'success' : 'failed' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Process">{{ r.total_seen }}</el-descriptions-item>
          <el-descriptions-item label="Migrate">{{ r.migrated }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <template #footer>
        <el-button @click="migrationDialogVisible = false">close</el-button>
      </template>
    </el-dialog>
    -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isJdyunMode } from '@/utils/config'
import {
  Setting,
  Cpu,
  DataBoard,
  Coin,
  Tools,
  Download,
  Upload,
  Plus,
  Refresh,
  Key,
  OfficeBuilding,
  CircleCheck,
  Collection,
  Connection
} from '@element-plus/icons-vue'

import {
  configApi,
  type LLMProvider,
  type LLMConfig,
  type DataSourceConfig,
  type DatabaseConfig,
  type MarketCategory,
  type DataSourceGrouping,
  type SettingMeta,
  type GatewayConfig,
  type GatewayConfigRequest
} from '@/api/config'
import ConfigValidator from '@/components/ConfigValidator.vue'
import LLMConfigDialog from './components/LLMConfigDialog.vue'
import ProviderDialog from './components/ProviderDialog.vue'
import ModelCatalogManagement from './components/ModelCatalogManagement.vue'
import DataSourceConfigDialog from './components/DataSourceConfigDialog.vue'
import MarketCategoryManagement from './components/MarketCategoryManagement.vue'
import DataSourceGroupingDialog from './components/DataSourceGroupingDialog.vue'
import SortableDataSourceList from './components/SortableDataSourceList.vue'

// Responsive data
const router = useRouter()
const activeTab = ref('providers')
const providers = ref<LLMProvider[]>([])
const llmConfigs = ref<LLMConfig[]>([])
const llmConfigGroups = ref<any[]>([])
const dataSourceConfigs = ref<DataSourceConfig[]>([])
const databaseConfigs = ref<DatabaseConfig[]>([])
const systemSettings = ref<Record<string, any>>({})
const systemSettingsMeta = ref<Record<string, SettingMeta>>({})
const defaultLLM = ref<string>('')

// 🔥 New: Reminder for Embedding model switching
const originalEmbeddingModel = ref<string>('')

// Manufacturer information mapping
const providerInfoMap = ref<Record<string, any>>({})
const defaultDataSource = ref<string>('')

// New: Data source grouping related
const marketCategories = ref<MarketCategory[]>([])
const dataSourceGroupings = ref<DataSourceGrouping[]>([])
const dataSourceGroups = ref<any[]>([])
const ungroupedDataSources = ref<DataSourceConfig[]>([])

// Loading status
const providersLoading = ref(false)
const llmLoading = ref(false)
const dataSourceLoading = ref(false)
const databaseLoading = ref(false)
const systemLoading = ref(false)
const systemSaving = ref(false)
const exportLoading = ref(false)
const importLoading = ref(false)
const migrateLoading = ref(false)
const reloadLoading = ref(false)
const proxyTesting = ref(false)
const proxyTestResult = ref<{ success: boolean; message: string } | null>(null)

// dialog state
const providerDialogVisible = ref(false)
const currentProvider = ref<Partial<LLMProvider>>({})

// New: Data source related dialog box
const dataSourceDialogVisible = ref(false)
const currentDataSourceConfig = ref<DataSourceConfig | null>(null)
const marketCategoryManagementVisible = ref(false)
const dataSourceGroupingDialogVisible = ref(false)
const currentDataSourceName = ref<string>('')

// New: Database configuration dialog
const databaseDialogVisible = ref(false)
const databaseDialogMode = ref<'add' | 'edit'>('add')
const currentDatabaseConfig = ref<Partial<DatabaseConfig>>({
  name: '',
  type: 'mongodb',
  host: 'localhost',
  port: 27017,
  username: '',
  password: '',
  database: '',
  connection_params: {},
  pool_size: 10,
  max_overflow: 20,
  enabled: true,
  description: ''
})

// Gateway Configuration
const gatewayLoading = ref(false)
const gatewaySaving = ref(false)
const gatewayTesting = ref(false)
const gatewayQQConfig = ref<GatewayConfig>({
  platform: 'qq',
  app_id: '',
  app_secret: '',
  bot_secret: '',
  connection_mode: 'websocket',
  enabled: false,
  configured: false,
})
const gatewayFeishuConfig = ref<GatewayConfig>({
  platform: 'feishu',
  app_id: '',
  app_secret: '',
  bot_secret: '',
  connection_mode: 'webhook',
  enabled: false,
  configured: false,
  verification_token: '',
  encrypt_key: '',
})
const gatewayDingtalkConfig = ref<GatewayConfig>({
  platform: 'dingtalk',
  app_id: '',
  app_secret: '',
  bot_secret: '',
  connection_mode: 'webhook',
  enabled: false,
  configured: false,
  app_key: '',
  robot_code: '',
})

// test status
const testingProviders = ref<Record<string, boolean>>({})

// method
const handleMenuSelect = (index: string) => {
  activeTab.value = index
  loadTabData(index)
}

const loadTabData = async (tab: string) => {
  switch (tab) {
    case 'providers':
      await loadProviders()
      break
    case 'llm':
      await loadLLMConfigs()
      break
    case 'datasource':
      await loadDataSourceConfigs()
      break
    case 'database':
      await loadDatabaseConfigs()
      break
    case 'system':
      // System settings need to load the manufacturer and large model configuration, which is used in the model selection drop-down box.
      await loadProviders()
      await loadLLMConfigs()
      await loadSystemSettings()
      await loadEmbeddingProviders()  // 🔥 New: Load Embedding manufacturer list
      break
    case 'gateway':
      await Promise.all([
        fetchGatewayConfig('qq'),
        fetchGatewayConfig('feishu'),
        fetchGatewayConfig('dingtalk'),
      ])
      break
    case 'api-keys':
      await loadProviders()
      await loadLLMConfigs()
      break
  }
}

// 🔥 Computed properties: List of manufacturers sorted by enabled status (enabled at the top, disabled at the bottom)
const sortedProviders = computed(() => {
  return [...providers.value].sort((a, b) => {
    // Enabled ones come first (is_active=true Return -1)
    if (a.is_active && !b.is_active) return -1
    if (!a.is_active && b.is_active) return 1
    // If the status is the same, sort by name
    return (a.display_name || a.name).localeCompare(b.display_name || b.name)
  })
})

const allEnabledModels = computed(() => {
  return llmConfigs.value.filter(config => config.enabled)
})

const selectableEnabledModels = computed(() => {
  return allEnabledModels.value.filter(
    (config): config is LLMConfig & { config_id: string } => typeof config.config_id === 'string' && config.config_id.trim().length > 0
  )
})

const groupedAvailableModels = computed(() => {
  const groups = new Map<string, { provider: string; providerLabel: string; models: Array<LLMConfig & { config_id: string }> }>()

  for (const model of selectableEnabledModels.value) {
    const providerLabel = providerInfoMap.value[model.provider]?.display_name || model.provider_name || model.provider
    const existingGroup = groups.get(model.provider)

    if (existingGroup) {
      existingGroup.models.push(model)
      continue
    }

    groups.set(model.provider, {
      provider: model.provider,
      providerLabel,
      models: [model]
    })
  }

  return Array.from(groups.values()).map(group => ({
    ...group,
    models: [...group.models].sort((left, right) => {
      const leftName = left.model_display_name || left.model_name
      const rightName = right.model_display_name || right.model_name
      return leftName.localeCompare(rightName)
    })
  }))
})

const getProviderDisplayLabel = (providerName?: string, fallbackName?: string) => {
  const normalizedProvider = String(providerName || '').trim()
  if (!normalizedProvider) {
    return String(fallbackName || '').trim()
  }

  return providerInfoMap.value[normalizedProvider]?.display_name || fallbackName || normalizedProvider
}

const formatModelSelectionLabel = (model: Pick<LLMConfig, 'provider' | 'provider_name' | 'model_display_name' | 'model_name'>) => {
  const providerLabel = getProviderDisplayLabel(model.provider, model.provider_name)
  const modelLabel = model.model_display_name || model.model_name
  return providerLabel ? `${providerLabel} / ${modelLabel}` : modelLabel
}

const formatModelSelectionMeta = (model: Pick<LLMConfig, 'provider' | 'model_name'>) => {
  const providerName = String(model.provider || '').trim()
  return providerName ? `${providerName} / ${model.model_name}` : model.model_name
}

const formatEmbeddingSelectionLabel = (provider: { name: string; display_name: string }, model: string) => {
  const providerLabel = provider.display_name || provider.name
  return `${providerLabel} / ${model}`
}

const formatEmbeddingSelectionMeta = (provider: { name: string }, model: string) => {
  return `${provider.name}:${model}`
}

const modelSettingPairs = [
  { modelKey: 'quick_analysis_model', configIdKey: 'quick_analysis_model_config_id' },
  { modelKey: 'deep_analysis_model', configIdKey: 'deep_analysis_model_config_id' },
  { modelKey: 'deep_reasoning_model', configIdKey: 'deep_reasoning_model_config_id' },
  { modelKey: 'coding_model', configIdKey: 'coding_model_config_id' }
] as const

const findLLMConfigBySelection = (modelName?: string, configId?: string) => {
  const normalizedConfigId = String(configId || '').trim()
  if (normalizedConfigId) {
    const exactConfig = allEnabledModels.value.find(model => model.config_id === normalizedConfigId)
    if (exactConfig) {
      return exactConfig
    }
  }

  const normalizedModelName = String(modelName || '').trim()
  if (!normalizedModelName) {
    return null
  }

  const matchingConfigs = allEnabledModels.value.filter(model => model.model_name === normalizedModelName)
  if (!matchingConfigs.length) {
    return null
  }

  const preferredProvider = String(systemSettings.value.default_provider || '').trim().toLowerCase()
  if (preferredProvider) {
    const preferredConfig = matchingConfigs.find(model => String(model.provider || '').trim().toLowerCase() === preferredProvider)
    if (preferredConfig) {
      return preferredConfig
    }
  }

  return matchingConfigs[0]
}

const syncModelSelectionSettings = () => {
  for (const { modelKey, configIdKey } of modelSettingPairs) {
    const matchedConfig = findLLMConfigBySelection(
      systemSettings.value[modelKey],
      systemSettings.value[configIdKey]
    )

    systemSettings.value[configIdKey] = matchedConfig?.config_id || ''
    systemSettings.value[modelKey] = matchedConfig?.model_name || ''
  }
}

// 🔥 New: List of manufacturers and models that support embedding (obtained from the backend)
const embeddingProviders = ref<Array<{
  name: string
  display_name: string
  models: string[]
}>>([])

// 🔥 New: Load the list of manufacturers and models that support embedding
const loadEmbeddingProviders = async () => {
  try {
    const data = await configApi.getEmbeddingProviders()
    embeddingProviders.value = data
    console.log('✅ Loading Embedding manufacturer list successfully:', data)
  } catch (error) {
    console.error('❌ Failed to load Embedding manufacturer list:', error)
    ElMessage.error('Failed to load Embedding manufacturer list')
    // Use empty array on failure
    embeddingProviders.value = []
  }
}

// 🔥 New: Get the list of Embedding models from a specified manufacturer
const getEmbeddingModelsForProvider = (providerName: string) => {
  const provider = embeddingProviders.value.find(p => p.name === providerName)
  return provider ? provider.models : []
}

// Load manufacturer list
const loadProviders = async () => {
  providersLoading.value = true
  try {
    console.log('🔄 Start loading manufacturer list...')
    const providerList = await configApi.getLLMProviders()
    console.log('📊 Manufacturer list response:', providerList)
    providers.value = providerList
    console.log('✅ Manufacturer list loaded successfully, quantity:', providerList.length)
  } catch (error) {
    console.error('❌ Failed to load manufacturer list:', error)
    ElMessage.error('Failed to load manufacturer list')
  } finally {
    providersLoading.value = false
  }
}

const loadLLMConfigs = async () => {
  llmLoading.value = true
  try {
    console.log('🔄 Start loading large model configuration...')
    const configs = await configApi.getLLMConfigs()
    console.log('📊 Large model configuration response:', configs)
    llmConfigs.value = configs
    console.log('✅ Large model configuration loaded successfully, quantity:', configs.length)

    // Get default LLM
    const systemConfig = await configApi.getSystemConfig()
    console.log('📊 System configuration response:', systemConfig)
    defaultLLM.value = systemConfig.default_llm || ''

    // Build grouped data
    buildLLMConfigGroups()
  } catch (error) {
    console.error('❌ Failed to load large model configuration:', error)
    ElMessage.error('Failed to load large model configuration')
  } finally {
    llmLoading.value = false
  }
}

// Build large models to configure grouped data
const buildLLMConfigGroups = () => {
  // Group by manufacturer
  const providerGroups: Record<string, LLMConfig[]> = {}

  llmConfigs.value.forEach(config => {
    const provider = config.provider
    if (!providerGroups[provider]) {
      providerGroups[provider] = []
    }
    providerGroups[provider].push(config)
  })

  // Build grouped data
  const groups: any[] = []

  Object.entries(providerGroups).forEach(([provider, models]) => {
    // Get manufacturer information
    const providerInfo = providerInfoMap.value[provider] || {
      display_name: getProviderDisplayName(provider),
      description: `${getProviderDisplayName(provider)} Large model service`,
      is_active: true
    }

    // Create manufacturer group
    const group = {
      provider: provider,
      display_name: providerInfo.display_name,
      description: providerInfo.description,
      is_active: providerInfo.is_active,
      models: models.sort((a, b) => {
        // Default model comes first
        if (a.model_name === defaultLLM.value) return -1
        if (b.model_name === defaultLLM.value) return 1
        // Enabled models come first
        if (a.enabled && !b.enabled) return -1
        if (!a.enabled && b.enabled) return 1
        // Sort by name
        return a.model_name.localeCompare(b.model_name)
      })
    }

    groups.push(group)
  })

  // Sort by manufacturer name
  groups.sort((a, b) => a.display_name.localeCompare(b.display_name))

  llmConfigGroups.value = groups
}

const loadDataSourceConfigs = async () => {
  dataSourceLoading.value = true
  try {
    const configs = await configApi.getDataSourceConfigs()
    dataSourceConfigs.value = configs

    // Get the default data source
    const systemConfig = await configApi.getSystemConfig()
    defaultDataSource.value = systemConfig.default_data_source || ''

    // Load group related data
    await loadMarketCategories()
    await loadDataSourceGroupings()
    buildDataSourceGroups()
  } catch (error) {
    ElMessage.error('Failed to load data source configuration')
  } finally {
    dataSourceLoading.value = false
  }
}

// Load market categories
const loadMarketCategories = async () => {
  try {
    marketCategories.value = await configApi.getMarketCategories()
  } catch (error) {
    console.error('Failed to load market categories:', error)
  }
}

// Load data source grouping relationship
const loadDataSourceGroupings = async () => {
  try {
    dataSourceGroupings.value = await configApi.getDataSourceGroupings()
  } catch (error) {
    console.error('Failed to load data source grouping relationship:', error)
  }
}

// Build data source grouping
const buildDataSourceGroups = () => {
  const groups: any[] = []
  const ungrouped: DataSourceConfig[] = []

  // In JD Cloud mode: only tushare and akshare type data sources are displayed
  const filteredConfigs = isJdyunMode()
    ? dataSourceConfigs.value.filter(ds => ['tushare', 'akshare'].includes(ds.type?.toLowerCase() || ''))
    : dataSourceConfigs.value

  // Group by category
  marketCategories.value.forEach(category => {
    const categoryGroupings = dataSourceGroupings.value.filter(
      g => g.market_category_id === category.id
    )

    if (categoryGroupings.length > 0) {
      const dataSources = categoryGroupings
        .map(grouping => {
          const dataSource = filteredConfigs.find(
            ds => ds.name === grouping.data_source_name
          )
          if (dataSource) {
            return {
              ...dataSource,
              priority: grouping.priority,
              enabled: grouping.enabled
            }
          }
          return null
        })
        .filter((item): item is DataSourceConfig & { priority: number; enabled: boolean } => item !== null)
        .sort((a, b) => b.priority - a.priority) // Sort by priority in descending order

      groups.push({
        categoryId: category.id,
        categoryDisplayName: category.display_name,
        dataSources
      })
    }
  })

  // Find ungrouped data sources
  const groupedDataSourceNames = new Set(
    dataSourceGroupings.value.map(g => g.data_source_name)
  )

  filteredConfigs.forEach(dataSource => {
    if (!groupedDataSourceNames.has(dataSource.name)) {
      ungrouped.push(dataSource)
    }
  })

  dataSourceGroups.value = groups
  ungroupedDataSources.value = ungrouped
}

const loadDatabaseConfigs = async () => {
  databaseLoading.value = true
  try {
    databaseConfigs.value = await configApi.getDatabaseConfigs()
  } catch (error) {
    ElMessage.error('Failed to load database configuration')
  } finally {
    databaseLoading.value = false
  }
}

const loadSystemSettings = async () => {
  systemLoading.value = true
  try {
    const [settings, meta] = await Promise.all([
      configApi.getSystemSettings(),
      configApi.getSystemSettingsMeta()
    ])
    // Make sure there is a default value
    systemSettings.value = {
      quick_analysis_model: 'qwen-turbo',
      quick_analysis_model_config_id: '',
      deep_analysis_model: 'qwen-max',
      deep_analysis_model_config_id: '',
      deep_reasoning_model: '',
      deep_reasoning_model_config_id: '',
      coding_model: '',
      coding_model_config_id: '',
      default_embedding_model: '',  // 🔥 New: Default Embedding model
      default_analysis_timeout: 300,
      enable_cache: true,
      cache_ttl: 3600,
      log_level: 'INFO',
      enable_monitoring: true,
      // Queue and Worker Default
      worker_heartbeat_interval_seconds: 30,
      queue_poll_interval_seconds: 1.0,
      queue_cleanup_interval_seconds: 60.0,
      // SSE Default
      sse_poll_timeout_seconds: 1.0,
      sse_heartbeat_interval_seconds: 10,
      sse_task_max_idle_seconds: 300,
      sse_batch_poll_interval_seconds: 2.0,
      sse_batch_max_idle_seconds: 600,
      // TradingAgents (optional) default
      ta_use_app_cache: false,
      ta_hk_min_request_interval_seconds: 2.0,
      ta_hk_timeout_seconds: 60,
      ta_hk_max_retries: 3,
      ta_hk_rate_limit_wait_seconds: 60,
      ta_hk_cache_ttl_seconds: 86400,
      ta_china_min_api_interval_seconds: 0.5,
      ta_us_min_api_interval_seconds: 1.0,
      ta_google_news_sleep_min_seconds: 2.0,
      ta_google_news_sleep_max_seconds: 6.0,
      app_timezone: 'Asia/Shanghai',
      // Backtesting DSL generation verification
      dsl_validate_on_generate: true,
      dsl_run_execution_check: true,
      // Agent configuration
      proxy_enabled: false,  // Proxy is turned off by default
      http_proxy: '',
      https_proxy: '',
      no_proxy: 'localhost,127.0.0.1,eastmoney.com,push2.eastmoney.com,82.push2.eastmoney.com,82.push2delay.eastmoney.com,gtimg.cn,sinaimg.cn,api.tushare.pro,baostock.com',

      ...settings
    }
    // 🔥 Fix: The numerical field returned by the backend may be a string, el-input-number requires Number type
    const numericKeys = [
      'cost_alert_threshold', 'default_analysis_timeout', 'cache_ttl',
      'worker_heartbeat_interval_seconds', 'queue_poll_interval_seconds',
      'queue_cleanup_interval_seconds', 'sse_poll_timeout_seconds',
      'sse_heartbeat_interval_seconds', 'sse_task_max_idle_seconds',
      'sse_batch_poll_interval_seconds', 'sse_batch_max_idle_seconds',
      'ta_hk_min_request_interval_seconds', 'ta_hk_timeout_seconds',
      'ta_hk_max_retries', 'ta_hk_rate_limit_wait_seconds', 'ta_hk_cache_ttl_seconds',
      'ta_china_min_api_interval_seconds', 'ta_us_min_api_interval_seconds',
      'ta_google_news_sleep_min_seconds', 'ta_google_news_sleep_max_seconds',
      'max_usage_records',
    ]
    for (const k of numericKeys) {
      const v = systemSettings.value[k]
      if (v != null && typeof v !== 'number') {
        systemSettings.value[k] = Number(v)
      }
    }
    syncModelSelectionSettings()
    // 🔥 Save original Embedding model values (used for toggling reminders)
    originalEmbeddingModel.value = systemSettings.value.default_embedding_model || ''
    // The regular metadata is map
    const metaList = meta?.items || []
    systemSettingsMeta.value = Object.fromEntries(metaList.map((m: SettingMeta) => [m.key, m]))
    // Clear proxy test results
    proxyTestResult.value = null
  } catch (error) {
    ElMessage.error('Failed to load system settings')
  } finally {
    systemLoading.value = false
  }
}

// 🔥 New: Monitor Embedding model changes and be reminded when suppliers switch
watch(() => systemSettings.value.default_embedding_model, (newValue, oldValue) => {
  const getProvider = (val: string | undefined) => {
    if (!val) return ''
    const parts = val.split(':')
    return parts[0] || ''
  }
  const oldProvider = getProvider(oldValue)
  const newProvider = getProvider(newValue)
  if (oldProvider && newProvider && oldProvider !== newProvider) {
    ElMessageBox.alert(
      `<p>You are switching from <strong>${oldProvider}</strong> switch to <strong>${newProvider}</strong> As the default Embedding provider.</p>
       <p style="margin-top:10px; color:#f56c6c;"><strong>IMPORTANT NOTE:</strong>The semantic spaces of vectors generated by different embedding models are different. Even if the dimensions are the same, the similarity search results will be completely wrong.</p>
       <p style="margin-top:10px;">It is recommended to regenerate all vector data (such as memory functions, knowledge bases, etc.) to ensure accuracy.</p>`,
      'Switch Embedding Supplier Alerts',
      {
        confirmButtonText: 'I know',
        dangerouslyUseHTMLString: true,
        type: 'warning'
      }
    )
  }
})

// ========== Factory management operations ==========

// Display the Add Manufacturer dialog box
const showAddProviderDialog = () => {
  currentProvider.value = {}
  providerDialogVisible.value = true
}

// Edit manufacturer
const editProvider = (provider: LLMProvider) => {
  currentProvider.value = { ...provider }
  providerDialogVisible.value = true
}

// Switch manufacturer status
const toggleProvider = async (provider: LLMProvider) => {
  try {
    await configApi.toggleLLMProvider(provider.id, !provider.is_active)
    await loadProviders()
    ElMessage.success(`The manufacturer has${provider.is_active ? 'Disable' : 'enable'}`)
  } catch (error) {
    ElMessage.error('Failed to switch manufacturer status')
  }
}

// Delete manufacturer
const deleteProvider = async (provider: LLMProvider) => {
  try {
    await ElMessageBox.confirm(
      `Confirm to delete the manufacturer ${provider.display_name} ? After deletion, all model configurations under the manufacturer will also be deleted.`,
      'Confirm deletion',
      { type: 'warning' }
    )

    await configApi.deleteLLMProvider(provider.id)
    await loadProviders()
    ElMessage.success('Manufacturer deleted successfully')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Failed to delete manufacturer')
    }
  }
}

// Manufacturer operation successful callback
const handleProviderSuccess = () => {
  loadProviders()
  // Reload manufacturer information into the mapping table
  loadProviderInfoMap()
}

// Load manufacturer information into the mapping table
const loadProviderInfoMap = async () => {
  try {
    const providerList = await configApi.getLLMProviders()
    const map: Record<string, any> = {}

    providerList.forEach(provider => {
      map[provider.name] = {
        display_name: provider.display_name,
        description: provider.description,
        is_active: provider.is_active
      }
    })

    providerInfoMap.value = map
  } catch (error) {
    console.error('Failed to load manufacturer information mapping:', error)
  }
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

// Get manufacturer label type
const getProviderTagType = (provider: string): TagType => {
  const typeMap: Record<string, TagType> = {
    'openai': 'primary',
    'google': 'success',
    'anthropic': 'warning',
    'dashscope': 'info',
    'qwen': 'info',
    'zhipu': 'danger',
    'deepseek': 'primary',
    'qianfan': 'success'
  }
  return typeMap[provider.toLowerCase()] || 'info'
}

// 🆕 Get ability level text
const getCapabilityLevelText = (level: number) => {
  const levelMap: Record<number, string> = {
    1: '1 Level-Basic',
    2: '2 Level-Standard',
    3: '3 Level-Advanced',
    4: '4 Level-Professional',
    5: '5 level-flagship'
  }
  return levelMap[level] || `${level}level`
}

// 🆕 Get ability level label type
const getCapabilityLevelType = (level: number): TagType => {
  const typeMap: Record<number, TagType> = {
    1: 'info',
    2: 'primary',
    3: 'success',
    4: 'warning',
    5: 'danger'
  }
  return typeMap[level] || 'info'
}

// 🆕 Get character text
const getRoleText = (role: string) => {
  const roleMap: Record<string, string> = {
    'quick_analysis': 'Quick analysis',
    'deep_analysis': 'In-depth analysis',
    'both': 'all-rounder'
  }
  return roleMap[role] || role
}

// 🆕 Format price display (remove extra trailing zeros)
const formatPrice = (price: number | undefined | null) => {
  if (price === undefined || price === null) {
    return '0'
  }
  // Convert to string and remove extra trailing zeros
  return parseFloat(price.toFixed(6)).toString()
}

// Add model for manufacturer
const addModelToProvider = (providerRow: any) => {
  // Default manufacturer information
  currentLLMConfig.value = {
    provider: providerRow.provider,
    model_name: '',
    model_display_name: '',
    description: '',
    enabled: true,
    max_tokens: 4000,
    temperature: 0.2,  // Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
    timeout: 60,
    retry_times: 3,
    priority: 0,
    api_base: '',
    model_category: '',
    enable_memory: false,
    enable_debug: false
  }

  llmDialogVisible.value = true
  isEditingLLM.value = false
}

// Switch manufacturer status
const toggleProviderStatus = async (providerRow: any) => {
  try {
    const newStatus = !providerRow.is_active
    const action = newStatus ? 'enable' : 'Disable'

    // Get manufacturer ID
    const provider = providers.value.find(p => p.name === providerRow.provider)
    if (!provider) {
      ElMessage.error('Manufacturer information not found')
      return
    }

    // Call the backend API to switch manufacturer status
    await configApi.toggleLLMProvider(provider.id, newStatus)

    // Reload data
    await loadProviders()
    await loadLLMConfigs()

    // Reconstruct manufacturer information mapping and grouping data
    await loadProviderInfoMap()
    buildLLMConfigGroups()

    ElMessage.success(`The manufacturer has${action}`)
  } catch (error) {
    console.error('Failed to switch manufacturer status:', error)
    ElMessage.error('Failed to switch manufacturer status')
  }
}

// Test manufacturer API
const testProviderAPI = async (provider: LLMProvider) => {
  try {
    console.log('🔍 Test manufacturer API:', provider)
    console.log('📋 Manufacturer ID:', provider.id)
    console.log('📋 Manufacturer name:', provider.display_name)

    testingProviders.value[provider.id] = true

    // Call test API
    const result = await configApi.testProviderAPI(provider.id)

    if (result.success) {
      ElMessage.success(`${provider.display_name} API Test successful`)
    } else {
      ElMessage.error(`${provider.display_name} API test failed: ${result.message}`)
    }
  } catch (error) {
    console.error('API test failed:', error)
    ElMessage.error(`${provider.display_name} API test failed`)
  } finally {
    testingProviders.value[provider.id] = false
  }
}

// Get manufacturer display name
const getProviderDisplayName = (providerId: string) => {
  const provider = providers.value.find(p => p.name === providerId)
  return provider?.display_name || providerId
}

// API Key status related computed properties
const configuredProvidersCount = computed(() => {
  return providers.value.filter(p => p.extra_config?.has_api_key === true).length
})

const activeProvidersCount = computed(() => {
  return providers.value.filter(p => p.is_active).length
})

// Get key status type
const getKeyStatusType = (provider: LLMProvider) => {
  if (!provider.extra_config?.has_api_key) {
    return 'info'
  }
  return provider.is_active ? 'success' : 'warning'
}

// Get key status text
const getKeyStatusText = (provider: LLMProvider) => {
  if (!provider.extra_config?.has_api_key) {
    return 'Not configured'
  }
  if (!provider.is_active) {
    return 'configured(Disable)'
  }

  if (provider.extra_config?.source === 'environment') {
    return 'configured(environment variables)'
  }

  return 'configured'
}

// Migrate from environment variables
const migrateFromEnv = async () => {
  try {
    await ElMessageBox.confirm(
      'This operation will read the API key from the .env file and create the corresponding factory configuration. Existing factory configurations will not be overwritten.',
      'Confirm migration',
      { type: 'info' }
    )

    migrateLoading.value = true
    const result = await configApi.migrateEnvToProviders()

    ElMessage.success(result.message)

    // Reload manufacturer list
    await loadProviders()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('Migration failed:', error)
      ElMessage.error('Migration failed, please check the console for error messages')
    }
  } finally {
    migrateLoading.value = false
  }
}

// ========== Large model configuration operations ==========

// Large model configuration dialog
const llmDialogVisible = ref(false)
const currentLLMConfig = ref<LLMConfig | null>(null)
const isEditingLLM = ref(false)
const batchImporting = ref(false)
const batchImportDialogVisible = ref(false)
const selectedImportProviders = ref<string[]>([])
const importableProviders = ref<LLMProvider[]>([])

const handleBatchImport = async () => {
  // Load manufacturer list
  try {
    const providers = await configApi.getLLMProviders()
    importableProviders.value = providers.filter((p: LLMProvider) => p.is_active)
  } catch {
    ElMessage.error('Failed to load manufacturer list')
    return
  }
  selectedImportProviders.value = []
  batchImportDialogVisible.value = true
}

const confirmBatchImport = async () => {
  if (selectedImportProviders.value.length === 0) return

  batchImporting.value = true
  try {
    const result = await configApi.batchImportLLMConfigs(selectedImportProviders.value)
    if (result.success) {
      ElMessage.success(result.message)
      batchImportDialogVisible.value = false
      await loadLLMConfigs()
    } else {
      ElMessage.warning(result.message)
    }
  } catch (error) {
    console.error('Batch import failed:', error)
    ElMessage.error('Batch import failed')
  } finally {
    batchImporting.value = false
  }
}

const showAddLLMDialog = () => {
  currentLLMConfig.value = null
  isEditingLLM.value = false
  llmDialogVisible.value = true
}

const editLLMConfig = (config: LLMConfig) => {
  currentLLMConfig.value = config
  isEditingLLM.value = true
  llmDialogVisible.value = true
}

const handleLLMConfigSuccess = () => {
  loadLLMConfigs()
}

// Test LLM configuration
const testLLMConfig = async (config: LLMConfig) => {
  try {
    console.log('🧪 Test LLM configuration:', config)
    console.log('📋 Manufacturer:', config.provider)
    console.log('📋 Model name:', config.model_name)
    console.log('📋 display name:', config.model_display_name)
    console.log('📋 API Basics URL:', config.api_base)

    const result = await configApi.testConfig({
      config_type: 'llm',
      config_data: config
    })

    console.log('✅ Test results:', result)

    if (result.success) {
      ElMessage.success(`Test successful: ${result.message}`)
    } else {
      ElMessage.error(`test failed: ${result.message}`)
    }
  } catch (error: any) {
    console.error('❌ Test configuration failed:', error)
    console.error('❌ Error details:', error.response?.data)
    ElMessage.error(error.response?.data?.detail || error.message || 'Test configuration failed')
  }
}

// Switch LLM configuration enabled state
const toggleLLMConfig = async (config: LLMConfig) => {
  try {
    const newStatus = !config.enabled
    const action = newStatus ? 'enable' : 'Disable'

    // Update configuration
    const updateData = {
      ...config,
      enabled: newStatus
    }

    await configApi.updateLLMConfig(updateData)
    await loadLLMConfigs()
    ElMessage.success(`Model has${action}`)
  } catch (error) {
    ElMessage.error('Failed to switch model status')
  }
}

// Delete LLM configuration
const deleteLLMConfig = async (config: LLMConfig) => {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete the large model configuration? ${config.provider}/${config.model_name} ?`,
      'Confirm deletion',
      { type: 'warning' }
    )

    await configApi.deleteLLMConfig(config.provider, config.model_name)
    await loadLLMConfigs()
    ElMessage.success('Large model configuration deleted successfully')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Failed to delete large model configuration')
    }
  }
}





// Data source related operations
const showAddDataSourceDialog = () => {
  currentDataSourceConfig.value = null
  dataSourceDialogVisible.value = true
}

const editDataSourceConfig = (config: DataSourceConfig) => {
  currentDataSourceConfig.value = config
  dataSourceDialogVisible.value = true
}

// Show market category management
const showMarketCategoryManagement = () => {
  marketCategoryManagementVisible.value = true
}

// Display the data source grouping dialog box
const showDataSourceGroupingDialog = (dataSourceName: string) => {
  currentDataSourceName.value = dataSourceName
  dataSourceGroupingDialogVisible.value = true
}

// Handling data source sort updates
const handleUpdateDataSourceOrder = async (categoryId: string, orderedItems: Array<{name: string, priority: number}>) => {
  try {
    await configApi.updateCategoryDataSourceOrder(categoryId, orderedItems)
    ElMessage.success('Sorting update successful')
    // Reload data
    await loadDataSourceGroupings()
    buildDataSourceGroups()
  } catch (error) {
    console.error('Update sort failed:', error)
    ElMessage.error('Update sort failed')
  }
}

// Data source configuration success callback
const handleDataSourceConfigSuccess = async () => {
  await loadDataSourceConfigs()

  // 🔥 After the data source is successfully configured, guide the user to synchronize the data.
  try {
    await ElMessageBox.confirm(
      'The data source has been configured. It is recommended to synchronize the basic stock data immediately to start analysis.',
      'Data source configuration successful',
      {
        confirmButtonText: 'Sync data now',
        cancelButtonText: 'Talk to you later',
        type: 'success',
        showClose: true,
      }
    )
    // User clicks"Sync data now", Jump to synchronization page
    router.push('/settings/sync')
  } catch (action) {
    // User clicks"Talk to you later"or close and do nothing
  }
}

// Market classification management successfully called back
const handleMarketCategorySuccess = () => {
  loadMarketCategories()
  buildDataSourceGroups()
}

// Data source grouping success callback
const handleDataSourceGroupingSuccess = () => {
  loadDataSourceGroupings()
  buildDataSourceGroups()
}

const testDataSource = async (config: DataSourceConfig) => {
  try {
    const result = await configApi.testConfig({
      config_type: 'datasource',
      config_data: config
    })

    if (result.success) {
      ElMessage.success('Data source connection test successful')
    } else {
      ElMessage.error(`Data source connection test failed: ${result.message}`)
    }
  } catch (error) {
    ElMessage.error('Data source connection test failed')
  }
}

// Delete data source configuration
const deleteDataSourceConfig = async (config: DataSourceConfig) => {
  try {
    await ElMessageBox.confirm(
      `Confirm you want to delete the data source "${config.display_name || config.name}" ? This operation is irreversible.`,
      'Delete confirmation',
      {
        confirmButtonText: 'Confirm deletion',
        cancelButtonText: 'Cancel',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await configApi.deleteDataSourceConfig(config.name)
    ElMessage.success('Data source deleted successfully')
    await loadDataSourceConfigs()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete data source:', error)
      ElMessage.error(error.message || 'Failed to delete data source')
    }
  }
}

// Database related operations
const editDatabaseConfig = (config: DatabaseConfig) => {
  databaseDialogMode.value = 'edit'
  currentDatabaseConfig.value = { ...config }
  databaseDialogVisible.value = true
}

const saveDatabaseConfig = async () => {
  try {
    await configApi.updateDatabaseConfig(
      currentDatabaseConfig.value.name!,
      currentDatabaseConfig.value
    )
    ElMessage.success('Database configuration updated successfully')
    databaseDialogVisible.value = false
    await loadDatabaseConfigs()
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to save database configuration')
  }
}

const testDatabase = async (config: DatabaseConfig) => {
  try {
    console.log('🧪 Test database configuration:', config)
    console.log('📋 Configuration name:', config.name)
    console.log('📋 Configuration type:', config.type)
    console.log('📋 host address:', config.host)
    console.log('📋 port:', config.port)

    const result = await configApi.testDatabaseConfig(config.name)

    if (result.success) {
      ElMessage.success('Database connection test successful')
    } else {
      ElMessage.error(`Database connection test failed: ${result.message}`)
    }
  } catch (error: any) {
    console.error('❌ Database test failed:', error)
    console.error('❌ Error details:', error.response?.data)
    ElMessage.error(error.response?.data?.detail || error.message || 'Database connection test failed')
  }
}

// Configuration reload
// ========== Gateway Configuration related ==========

const fetchGatewayConfig = async (platform: string) => {
  try {
    gatewayLoading.value = true
    const data = await configApi.getGatewayConfig(platform)
    if (platform === 'qq') {
      gatewayQQConfig.value = data
    } else if (platform === 'feishu') {
      gatewayFeishuConfig.value = data
    } else if (platform === 'dingtalk') {
      gatewayDingtalkConfig.value = data
    }
  } catch (error: any) {
    console.error(`get Gateway ${platform} Configuration failed:`, error)
    ElMessage.error(`get Gateway ${platform} Configuration failed`)
  } finally {
    gatewayLoading.value = false
  }
}

const handleSaveGatewayConfig = async (platform: string) => {
  let req: GatewayConfigRequest

  if (platform === 'qq') {
    const cfg = gatewayQQConfig.value
    if (!cfg.app_id || !cfg.app_secret) {
      ElMessage.warning('AppID and AppSecret cannot be empty')
      return
    }
    req = {
      app_id: cfg.app_id,
      app_secret: cfg.app_secret,
      bot_secret: cfg.bot_secret || undefined,
      connection_mode: cfg.connection_mode || 'websocket',
      enabled: cfg.enabled,
    }
  } else if (platform === 'feishu') {
    const cfg = gatewayFeishuConfig.value
    if (!cfg.app_id || !cfg.app_secret) {
      ElMessage.warning('App ID and App Secret cannot be empty')
      return
    }
    req = {
      app_id: cfg.app_id,
      app_secret: cfg.app_secret,
      verification_token: cfg.verification_token || undefined,
      encrypt_key: cfg.encrypt_key || undefined,
      enabled: cfg.enabled,
    }
  } else if (platform === 'dingtalk') {
    const cfg = gatewayDingtalkConfig.value
    if (!cfg.app_key || !cfg.app_secret) {
      ElMessage.warning('AppKey and AppSecret cannot be empty')
      return
    }
    req = {
      app_key: cfg.app_key,
      app_secret: cfg.app_secret,
      robot_code: cfg.robot_code || undefined,
      enabled: cfg.enabled,
    }
  } else {
    return
  }

  try {
    gatewaySaving.value = true
    await configApi.updateGatewayConfig(platform, req)
    const labels: Record<string, string> = { qq: 'QQ', feishu: 'Feishu', dingtalk: 'DingTalk' }
    ElMessage.success(`${labels[platform] || platform} Gateway Configuration saved`)
    await fetchGatewayConfig(platform)
  } catch (error: any) {
    console.error(`save Gateway ${platform} Configuration failed:`, error)
    ElMessage.error(error.response?.data?.detail || `Save failed`)
  } finally {
    gatewaySaving.value = false
  }
}

const handleTestGatewayConnection = async (platform: string) => {
  try {
    gatewayTesting.value = true
    const res = await configApi.testGatewayConnection(platform)
    if (res.success) {
      ElMessage.success(res.message || `Gateway ${platform.toUpperCase()} Connection successful`)
    } else {
      ElMessage.error(res.message || `Gateway ${platform.toUpperCase()} Connection failed`)
    }
  } catch (error: any) {
    console.error(`test Gateway ${platform} Connection failed:`, error)
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || 'Test connection failed')
  } finally {
    gatewayTesting.value = false
  }
}

const handleReloadConfig = async () => {
  try {
    reloadLoading.value = true
    const response = await configApi.reloadConfig()

    if (response.success) {
      ElMessage.success({
        message: 'Configuration reload successful! The new configuration has taken effect',
        duration: 3000
      })
    } else {
      ElMessage.warning({
        message: response.message || 'Configuration reload failed',
        duration: 3000
      })
    }
  } catch (error: any) {
    console.error('Configuration reload failed:', error)
    ElMessage.error({
      message: error.response?.data?.detail || 'Configuration reload failed',
      duration: 3000
    })
  } finally {
    reloadLoading.value = false
  }
}

// System settings related operations
const isEditable = (key: string): boolean => {
  const meta = systemSettingsMeta.value[key]
  if (!meta) return true
  return !!meta.editable
}

const saveSystemSettings = async () => {
  systemSaving.value = true
  try {
    syncModelSelectionSettings()
    // Basic verification: these values need to > 0
    const positiveKeys: Array<{key: string; min: number}> = [
      { key: 'worker_heartbeat_interval_seconds', min: 1 },
      { key: 'queue_poll_interval_seconds', min: 0.000001 },
      { key: 'queue_cleanup_interval_seconds', min: 1 },
      { key: 'sse_poll_timeout_seconds', min: 0.000001 },
      { key: 'sse_heartbeat_interval_seconds', min: 1 },
      { key: 'sse_task_max_idle_seconds', min: 1 },
      { key: 'sse_batch_poll_interval_seconds', min: 0.000001 },
      { key: 'sse_batch_max_idle_seconds', min: 1 },
      // TradingAgents (optional)
      { key: 'ta_hk_min_request_interval_seconds', min: 0.000001 },
      { key: 'ta_hk_timeout_seconds', min: 1 },
      { key: 'ta_hk_max_retries', min: 0 },
      { key: 'ta_hk_rate_limit_wait_seconds', min: 1 },
      { key: 'ta_hk_cache_ttl_seconds', min: 1 },
      { key: 'ta_china_min_api_interval_seconds', min: 0.000001 },
      { key: 'ta_us_min_api_interval_seconds', min: 0.000001 },
      { key: 'ta_google_news_sleep_min_seconds', min: 0.000001 },
      { key: 'ta_google_news_sleep_max_seconds', min: 0.000001 },
    ]
    for (const { key, min } of positiveKeys) {
      const v = (systemSettings.value as any)[key]
      if (v !== undefined && v !== null && Number(v) <= min - Number.EPSILON && isEditable(key)) {
        ElMessage.error(`${key} must be greater than ${min}`)
        systemSaving.value = false
        return
      }
    }
    // Extra: Google News maximum delay should be greater than minimum delay
    const gMin = Number((systemSettings.value as any)['ta_google_news_sleep_min_seconds'])
    const gMax = Number((systemSettings.value as any)['ta_google_news_sleep_max_seconds'])
    if (!Number.isNaN(gMin) && !Number.isNaN(gMax) && isEditable('ta_google_news_sleep_max_seconds')) {
      if (gMax <= gMin) {
        ElMessage.error('ta_google_news_sleep_max_seconds must be greater than ta_google_news_sleep_min_seconds')
        systemSaving.value = false
        return
      }
    }

    // Submit only editable items
    const entries = Object.entries(systemSettings.value).filter(([k]) => isEditable(k))
    const payload = Object.fromEntries(entries)
    await configApi.updateSystemSettings(payload)
    ElMessage.success('System settings saved successfully')
    // If the proxy configuration is modified, the user is reminded to restart the service.
    if ('http_proxy' in payload || 'https_proxy' in payload || 'no_proxy' in payload) {
      ElMessage.warning('The proxy configuration has been saved. Please restart the backend service to make the configuration take effect.')
    }
  } catch (error) {
    ElMessage.error('System settings failed to save')
  } finally {
    systemSaving.value = false
  }
}

// Proxy connection test
const testProxyConnection = async () => {
  proxyTesting.value = true
  proxyTestResult.value = null

  try {
    const result = await configApi.testProxyConnection({
      http_proxy: systemSettings.value.http_proxy,
      https_proxy: systemSettings.value.https_proxy
    })

    const responseTime = result.data?.response_time
    proxyTestResult.value = {
      success: result.success,
      message: result.success
        ? `Connection successful (${responseTime?.toFixed(2)}s)`
        : (result.message || 'Connection failed')
    }
  } catch (error: unknown) {
    const errMsg = error instanceof Error ? error.message : 'test failed'
    proxyTestResult.value = {
      success: false,
      message: errMsg
    }
  } finally {
    proxyTesting.value = false
  }
}

// Import and export related operations
const exportConfig = async () => {
  exportLoading.value = true
  try {
    const result = await configApi.exportConfig()

    // Create download link
    const blob = new Blob([JSON.stringify(result.data, null, 2)], {
      type: 'application/json'
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `tradingagents-config-${new Date().toISOString().split('T')[0]}.json`
    link.click()
    URL.revokeObjectURL(url)

    ElMessage.success('Configuration export successful')
  } catch (error) {
    ElMessage.error('Configuration export failed')
  } finally {
    exportLoading.value = false
  }
}

const handleImportConfig = async (file: File) => {
  importLoading.value = true
  try {
    const text = await file.text()
    const configData = JSON.parse(text)

    await ElMessageBox.confirm(
      'Importing the configuration will overwrite the existing configuration. Are you sure you want to continue?',
      'Confirm import',
      { type: 'warning' }
    )

    await configApi.importConfig(configData)
    ElMessage.success('Configuration imported successfully')

    // Reload current tab data
    await loadTabData(activeTab.value)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Configuration import failed')
    }
  } finally {
    importLoading.value = false
  }

  return false // Block automatic uploads
}

const migrateLegacyConfig = async () => {
  migrateLoading.value = true
  try {
    await ElMessageBox.confirm(
      'Migrating legacy configurations may overwrite existing configurations. Are you sure you want to continue?',
      'Confirm migration',
      { type: 'warning' }
    )

    await configApi.migrateLegacyConfig()
    ElMessage.success('Traditional configuration migration successful')

    // Reload all data
    await loadTabData(activeTab.value)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Legacy configuration migration fails')
    }
  } finally {
    migrateLoading.value = false
  }
}

// Cleared only when the model itself is no longer available, default vendor changes should not limit model selection
watch(
  allEnabledModels,
  (availableModels) => {
    for (const { modelKey, configIdKey } of modelSettingPairs) {
      const configId = String(systemSettings.value[configIdKey] || '').trim()
      const modelName = String(systemSettings.value[modelKey] || '').trim()
      const matchedConfig = availableModels.find(model => {
        if (configId) {
          return model.config_id === configId
        }
        return model.model_name === modelName
      })

      if (!matchedConfig) {
        systemSettings.value[configIdKey] = ''
        systemSettings.value[modelKey] = ''
        continue
      }

      systemSettings.value[configIdKey] = matchedConfig.config_id || ''
      systemSettings.value[modelKey] = matchedConfig.model_name || ''
    }
  }
)

// life cycle
onMounted(async () => {
  // In JD Cloud mode: only the data source configuration tab page is displayed
  if (isJdyunMode()) {
    activeTab.value = 'datasource'
    await loadDataSourceConfigs()
    return
  }
  // Load manufacturer information first, then other data
  await loadProviders()
  await loadProviderInfoMap()
  loadTabData(activeTab.value)
})
</script>

<style lang="scss" scoped>
.config-management {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .header-left {
      flex: 1;

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
        margin: 0;
        color: var(--el-text-color-secondary);
        font-size: 14px;
      }
    }

    .header-right {
      display: flex;
      gap: 12px;
    }
  }

  .config-menu {
    .config-nav {
      border: none;
    }
  }

  .config-content {
    min-height: 500px;

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      h3 {
        margin: 0;
      }

      .header-actions {
        display: flex;
        gap: 8px;
      }
    }

    .datasource-content {
      .datasource-groups {
        margin-bottom: 24px;
      }

      .ungrouped-section {
        margin-bottom: 24px;

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;

          h4 {
            margin: 0;
            color: #303133;
            font-size: 14px;
          }
        }

        .ungrouped-list {
          .ungrouped-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #f0f0f0;

            &:last-child {
              border-bottom: none;
            }

            .item-info {
              flex: 1;
              display: flex;
              align-items: center;
              gap: 12px;

              .item-name {
                font-weight: 500;
                color: #303133;
              }

              .item-type {
                color: #909399;
                font-size: 12px;
              }
            }

            .item-actions {
              display: flex;
              gap: 8px;
            }
          }
        }
      }

      .empty-state {
        text-align: center;
        padding: 60px 20px;
      }
    }

    .setting-description {
      margin-left: 8px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }

    .import-export-content {
      h4 {
        margin: 0 0 8px 0;
        color: var(--el-text-color-primary);
      }

      p {
        margin: 0 0 16px 0;
        color: var(--el-text-color-regular);
        font-size: 14px;
      }

      .legacy-migration {
        margin-top: 24px;
      }
    }

    .api-keys-content {
      h4 {
        margin: 0 0 16px 0;
        color: var(--el-text-color-primary);
      }

      .api-key-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px;
        margin-bottom: 8px;
        border-radius: 6px;
        background: var(--el-fill-color-lighter);
        border: 1px solid var(--el-border-color-light);

        .key-name {
          flex: 1;
          font-size: 14px;
          font-weight: 500;
          color: var(--el-text-color-primary);
        }
      }

      .empty-state {
        text-align: center;
        padding: 40px 20px;
      }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
      }

      .stat-item {
        text-align: center;
        padding: 16px;
        background: var(--el-fill-color-lighter);
        border-radius: 8px;
        border: 1px solid var(--el-border-color-light);

        .stat-number {
          font-size: 24px;
          font-weight: bold;
          color: var(--el-color-primary);
          margin-bottom: 4px;
        }

        .stat-label {
          font-size: 12px;
          color: var(--el-text-color-regular);
        }
      }

      .api-key-help {
        margin-top: 24px;

        h4 {
          margin-bottom: 12px;
        }

        h5 {
          margin: 0 0 8px 0;
          color: var(--el-text-color-primary);
        }

        ol {
          margin: 0;
          padding-left: 20px;

          li {
            margin-bottom: 4px;
            color: var(--el-text-color-regular);
          }
        }

        .help-card {
          background: var(--el-fill-color-lighter);
        }
      }
    }

    .flex {
      display: flex;
    }

    .gap-1 {
      gap: 4px;
    }
  }

  // Manufacturer management style
  .provider-info {
    .provider-name {
      font-weight: 500;
      color: var(--el-text-color-primary);
    }

    .provider-id {
      font-size: 12px;
      color: var(--el-text-color-placeholder);
      margin-top: 2px;
    }
  }

  .features {
    .feature-tag {
      margin-right: 4px;
      margin-bottom: 4px;
    }
  }

  .status-column {
    display: flex;
    flex-direction: column;
    gap: 4px;

    .key-source-tag {
      font-size: 10px;
    }
  }

  .api-key-status {
    .key-preview {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
      margin-top: 2px;
      font-family: monospace;
    }
  }

  // Card layout style
  .empty-state {
    padding: 60px 20px;
    text-align: center;
  }

  .provider-groups {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .provider-group {
    border: 1px solid var(--el-border-color-light);
    border-radius: 8px;
    overflow: hidden;
    background: var(--el-bg-color);
  }

  .provider-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: var(--el-fill-color-lighter);
    border-bottom: 1px solid var(--el-border-color-light);

    .provider-info {
      display: flex;
      align-items: center;
      gap: 12px;

      .provider-tag {
        font-weight: 600;
      }

      .model-count {
        font-size: 14px;
        color: var(--el-text-color-regular);
      }

      .status-tag {
        margin-left: 8px;
      }
    }

    .provider-actions {
      display: flex;
      gap: 8px;
    }
  }

  // Table layout style
  .model-name-cell {
    .model-display-name {
      font-weight: 500;
      color: var(--el-text-color-primary);
      display: flex;
      align-items: center;
    }

    .model-code-text {
      font-size: 12px;
      color: var(--el-text-color-placeholder);
      font-family: 'Courier New', monospace;
      margin-top: 4px;
    }
  }

  .config-cell {
    font-size: 13px;
    color: var(--el-text-color-regular);
    line-height: 1.6;
  }

  .pricing-cell {
    font-size: 13px;
    color: var(--el-text-color-regular);
    line-height: 1.6;
  }

  .capability-cell {
    .capability-row-item {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;

      &:last-child {
        margin-bottom: 0;
      }

      .label {
        font-size: 12px;
        color: var(--el-text-color-secondary);
        min-width: 40px;
      }
    }
  }

  .text-muted {
    color: var(--el-text-color-placeholder);
  }

  // Keep the old card style (if still in use elsewhere)
  .model-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .model-title {
      display: flex;
      align-items: center;
      gap: 8px;

      .model-icon {
        color: var(--el-color-primary);
      }

      .model-name-wrapper {
        display: flex;
        flex-direction: column;
        gap: 2px;

        .model-name {
          font-weight: 600;
          font-size: 16px;
        }

        .model-code {
          font-size: 12px;
          color: #909399;
          font-family: 'Courier New', monospace;
        }
      }

      .default-tag {
        margin-left: 8px;
      }
    }
  }

  .model-config {
    margin-bottom: 12px;

    .config-row {
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
      font-size: 13px;

      .config-label {
        color: var(--el-text-color-regular);
      }

      .config-value {
        font-weight: 500;
        color: var(--el-text-color-primary);
      }
    }
  }

  .model-pricing {
    margin-bottom: 12px;
    padding: 8px;
    background: var(--el-fill-color-lighter);
    border-radius: 4px;

    .pricing-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
      font-size: 13px;
      color: var(--el-color-warning);
      font-weight: 600;
    }

    .pricing-details {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding-left: 20px;

      .pricing-item {
        display: flex;
        justify-content: space-between;
        font-size: 12px;

        .pricing-type {
          color: var(--el-text-color-regular);
        }

        .pricing-value {
          font-weight: 500;
          color: var(--el-color-warning);
        }
      }
    }
  }

  // 🆕 Model capability information style
  .model-capability {
    margin-bottom: 12px;
    padding: 8px;
    background: var(--el-fill-color-lighter);
    border-radius: 4px;

    .capability-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
      font-size: 13px;
      color: var(--el-color-primary);
      font-weight: 600;
    }

    .capability-details {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding-left: 20px;

      .capability-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;

        .capability-type {
          color: var(--el-text-color-regular);
          min-width: 60px;
        }
      }
    }
  }

  .model-features {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
    min-height: 20px;
  }

  .model-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;

    .el-button {
      flex: 1;
      min-width: 60px;
    }
  }

  // Agent test result style
  .proxy-test-result {
    font-size: 13px;
    padding: 4px 8px;
    border-radius: 4px;

    &.success {
      color: var(--el-color-success);
      background: var(--el-color-success-light-9);
    }

    &.error {
      color: var(--el-color-danger);
      background: var(--el-color-danger-light-9);
    }
  }

  .form-tip {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.4;
    margin-top: 4px;
  }
}
</style>
