<template>
  <div class="skill-create-page">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          Return to list
        </el-button>
        <span class="header-divider">|</span>
        <h1 v-if="isIterateMode">🔄 iterative optimization Skill</h1>
        <h1 v-else>🛠️ create new Skill</h1>
      </div>
      <div class="header-right">
        <el-button v-if="wizardStep < 3 && sessionId" text size="small" @click="goBack">
          save draft
        </el-button>
      </div>
    </div>

    <!-- Iterative optimization tips -->
    <div v-if="isIterateMode && iterateSkillInfo" class="iterate-notice">
      <el-alert
        title="iterative optimization mode"
        type="info"
        :closable="false"
        show-icon
      >
        <template #default>
          <p>Skill is being iteratively optimized:<strong>{{ iterateSkillInfo.displayName }}</strong></p>
          <p>Current description:{{ iterateSkillInfo.description }}</p>
          <p v-if="iterateSkillInfo.toolId" class="tool-id">Original Tool ID:{{ iterateSkillInfo.toolId }}</p>
        </template>
      </el-alert>
    </div>

    <!-- step bar -->
    <div class="steps-bar">
      <el-steps :active="wizardStep" finish-status="success" align-center>
        <el-step title="Requirements communication" />
        <el-step title="Specification confirmation" />
        <el-step title="code generation" />
        <el-step title="Complete" />
      </el-steps>
    </div>

    <!-- Main content area: Make the most of the screen -->
    <div class="main-content">
      <!-- steps 0: Requirements communication -->
      <div v-if="wizardStep === 0" class="wizard-chat">
        <div v-if="handoffContext" class="handoff-card">
          <div class="handoff-title">Handover from upstream workshop</div>
          <div class="handoff-text">
            <span v-if="handoffContext.source === 'agent_workshop'">Currently, we are not creating a new Skill from scratch, but taking over the gaps in execution capabilities identified by the Agent Workshop.</span>
            <span v-else>The current session comes from the upstream process handover.</span>
          </div>
          <div class="handoff-meta">
            <span v-if="handoffContext.source_name">Upstream objects:{{ handoffContext.source_name }}</span>
            <span v-if="handoffContext.target_capability">Target abilities:{{ handoffContext.target_capability }}</span>
          </div>
          <div v-if="handoffContext.handoff_intent" class="handoff-note">{{ handoffContext.handoff_intent }}</div>
        </div>
        <div ref="chatContainer" class="chat-messages">
          <!-- Introductory message when entering for the first time -->
          <div v-if="chatMessages.length === 0 && !chatLoading" class="requirement-guide">
            <div class="guide-header">
              <el-icon class="guide-icon"><MagicStick /></el-icon>
              <h3 v-if="isIterateMode">🔄 Start iterative optimization Skill</h3>
              <h3 v-else>Tell me in one sentence what tool you want</h3>
              <p v-if="isIterateMode" class="guide-desc">You are iteratively optimizing an existing Skill. Tell me what you want to improve, such as: fix a bug, add new features, optimize performance, improve output format, etc.</p>
              <p v-else class="guide-desc">Don t think too carefully, just give a general idea. AI will help you refine your requirements through dialogue, and then automatically generate and verify code.</p>
            </div>

            <div class="guide-quick-examples" v-if="!isIterateMode">
              <div class="quick-label">For example, you can say:</div>
              <ul class="example-list">
                <li>Analyze the moat strength of a stock</li>
                <li>View cash flow quality trends for individual stocks</li>
                <li>Get the historical valuation quantile of a stock</li>
                <li>Calculate a stock s profitability stability indicator</li>
              </ul>
            </div>

            <div class="guide-quick-examples" v-else>
              <div class="quick-label">Iterative optimization can be said like this:</div>
              <ul class="example-list">
                <li>Fix the incorrect calculation of pledge ratio Bug</li>
                <li>Add quarterly statistics function</li>
                <li>Optimize the output format and add more visual information</li>
                <li>Improve data accuracy and increase data source fault tolerance processing</li>
              </ul>
            </div>

            <p class="guide-footer">Describe your needs in the input box below and press <kbd>Ctrl+Enter</kbd> Or click Send to get started</p>
          </div>
          <div v-for="(msg, idx) in chatMessages" :key="idx"
               :class="['chat-msg', msg.role === 'user' ? 'chat-user' : 'chat-ai']">
            <div class="msg-avatar">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else><MagicStick /></el-icon>
            </div>
            <div class="msg-bubble">
              <div class="msg-text" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>
          <div v-if="chatLoading" class="chat-msg chat-ai">
            <div class="msg-avatar"><el-icon><MagicStick /></el-icon></div>
            <div class="msg-bubble thinking">
              <span class="dot-animation">AI Analyzing<span>.</span><span>.</span><span>.</span></span>
            </div>
          </div>
        </div>

        <div v-if="boundaryWarning" class="boundary-alert boundary-collapsible">
          <div class="boundary-header" @click="boundaryExpanded = !boundaryExpanded">
            <el-icon class="boundary-icon"><WarningFilled /></el-icon>
            <span>Complexity reminder ({{ boundaryCheck?.complexity_score }}/5)</span>
            <el-icon class="boundary-chevron" :class="{ expanded: boundaryExpanded }"><ArrowDown /></el-icon>
          </div>
          <div v-show="boundaryExpanded" class="boundary-content">
            <div v-for="c in boundaryCheck?.concerns" :key="c">• {{ c }}</div>
            <div v-if="boundaryCheck?.decomposition_suggestions?.length" style="margin-top: 6px">
              <strong>It is recommended to split it into:</strong>
              <div v-for="s in boundaryCheck?.decomposition_suggestions" :key="s">→ {{ s }}</div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <el-input
            v-model="userInput"
            type="textarea"
            :rows="3"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :placeholder="chatMessages.length === 0 ? 'Describe the tools you need, for example: I need to get Oriental Fortune stock news...' : (canConfirm ? 'You can enter the plan choice (for example: I choose plan C) or supplementary explanation, and submit it when confirming.' : 'Reply to AI s question...')"
            :disabled="chatLoading"
            @keydown.enter.ctrl="handleChatSend"
          />
          <div class="chat-actions">
            <span class="tip">Ctrl+Enter send · No. {{ currentRound }}/{{ expectedRounds }} wheel</span>
            <div>
              <el-button type="primary" @click="handleChatSend" :loading="chatLoading" :disabled="!userInput.trim()">
                send
              </el-button>
              <el-button v-if="canConfirm" type="success" @click="handleViewSpec" :loading="chatLoading">
                📄 Next step·View specifications
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- steps 1: Specification confirmation -->
      <div v-if="wizardStep === 1" class="wizard-spec-confirm">
        <div class="spec-confirm-card">
          <h3>📄 Tool specification confirmation</h3>
          <div v-if="handoffContext" class="handoff-inline-note">
            The current specifications come from the upstream handover: first determine the existing reuse capabilities, and then decide whether to add a minimum implementation unit.
          </div>
          <el-descriptions v-if="specPreview" :column="1" border size="small">
            <el-descriptions-item label="Tools ID">{{ specPreview.tool_id }}</el-descriptions-item>
            <el-descriptions-item label="Name">{{ specPreview.display_name }}</el-descriptions-item>
            <el-descriptions-item label="Classification">{{ specPreview.category }}</el-descriptions-item>
            <el-descriptions-item label="data source">{{ specPreview.data_source }}</el-descriptions-item>
            <el-descriptions-item label="Description">{{ specPreview.description }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="upgradeChangePoints.length" class="upgrade-change-points">
            <el-alert type="success" :closable="false" show-icon title="Changes in this upgrade (all the rest inherit the verified specifications of the parent version)">
              <div v-for="(point, idx) in upgradeChangePoints" :key="`upgrade-point-${idx}`" class="catalog-note-item">
                {{ idx + 1 }}. {{ point }}
              </div>
            </el-alert>
          </div>
          <div v-if="previewFactReport" class="spec-catalog-card">
            <div class="spec-catalog-header">
              <div>
                <h4>Realize Facts and Reconnaissance Records</h4>
                <p>This step has completed the factual preparation before code generation. After confirming the specifications, you will go directly to code generation without running the same reconnaissance again.</p>
              </div>
            </div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="Recommended implementation strategies">{{ previewFactReport.recommended_strategy || '-' }}</el-descriptions-item>
              <el-descriptions-item label="recon confidence">{{ Math.round((previewFactReport.confidence || 0) * 100) }}%</el-descriptions-item>
              <el-descriptions-item v-if="previewFactReport.available_helpers?.length" label="Recommended helper">
                <div class="tag-wrap">
                  <el-tag v-for="entry in previewFactReport.available_helpers" :key="`${entry.module}.${entry.name}`" class="tag-item" type="success" effect="plain">
                    {{ entry.module }}.{{ entry.name }}
                  </el-tag>
                </div>
              </el-descriptions-item>
              <el-descriptions-item v-if="previewFactFieldSummaries.length" label="Sample field summary">
                <div v-for="[collection, fields] in previewFactFieldSummaries" :key="collection" class="catalog-note-item">
                  {{ collection }}: {{ fields.slice(0, 8).join(', ') }}
                </div>
              </el-descriptions-item>
              <el-descriptions-item v-if="previewFactReport.validation_checks?.length" label="Dynamic acceptance fields">
                {{ previewFactReport.validation_checks.map(item => item.field || item.name).join('、') }}
              </el-descriptions-item>
            </el-descriptions>
            <div v-if="previewToolTraces.length" class="catalog-notes" style="margin-top: 12px;">
              <div class="recommendation-label">Reconnaissance tool call record</div>
              <div v-for="(trace, idx) in previewToolTraces" :key="`${trace.tool_name}-${idx}`" class="tool-trace-card">
                <div class="tool-trace-header">
                  <strong>{{ idx + 1 }}. {{ trace.tool_name }}</strong>
                  <span>{{ trace.success ? 'success' : 'failed' }} · {{ trace.duration_ms }}ms</span>
                </div>
                <div class="tool-trace-body">parameters: {{ JSON.stringify(trace.arguments || {}) }}</div>
                <div v-if="trace.result_preview" class="tool-trace-body">summary of results: {{ trace.result_preview }}</div>
                <div v-if="trace.error" class="tool-trace-body tool-trace-error">Error: {{ trace.error }}</div>
              </div>
            </div>
          </div>
          <div v-if="specPreview?.parameters?.length" class="spec-params-section">
            <h4>input parameters</h4>
            <el-table :data="specPreview.parameters" size="small" border stripe>
              <el-table-column prop="name" label="parameters" width="120" />
              <el-table-column prop="type" label="Type" width="90" />
              <el-table-column prop="required" label="Required" width="70" align="center">
                <template #default="{ row }">{{ row.required ? 'Yes' : 'No' }}</template>
              </el-table-column>
              <el-table-column prop="description" label="Description" />
            </el-table>
          </div>
          <div v-if="boundaryWarning" class="spec-boundary-warn">
            <el-alert type="warning" :closable="false" show-icon>
              complexity {{ boundaryCheck?.complexity_score }}/5, Within the Skill scope
            </el-alert>
          </div>
          <div
            v-if="backendRecommendations && (backendRecommendations.stock_collections?.length || backendRecommendations.external_sources?.length)"
            ref="recommendationCardRef"
            :class="['spec-recommendation-card', { 'spec-recommendation-card-highlight': highlightRecommendationCard } ]"
          >
            <div class="spec-catalog-header">
              <div>
                <h4>System recommendations</h4>
                <p>This suggestion is generated by the back-end unified selector and will share the same set of hit logic with requirements analysis, specification confirmation, and code generation.</p>
              </div>
            </div>
            <div class="recommendation-grid">
              <div class="recommendation-block">
                <div class="recommendation-label">Recommended categories/main sources</div>
                <div class="recommendation-value">
                  {{ backendRecommendations.category_hint || '-' }}
                  <span v-if="backendRecommendations.data_source_hint"> · {{ backendRecommendations.data_source_hint }}</span>
                </div>
              </div>
              <div class="recommendation-block">
                <div class="recommendation-label">It is recommended to reuse local collections</div>
                <div class="tag-wrap" v-if="backendRecommendations.stock_collections?.length">
                  <el-tag v-for="entry in backendRecommendations.stock_collections" :key="`rec-stock-${entry}`" class="tag-item" type="success" effect="plain">{{ entry }}</el-tag>
                </div>
                <div v-else class="recommendation-empty">There are currently no local collections with obvious hits</div>
              </div>
              <div class="recommendation-block">
                <div class="recommendation-label">Recommend external sources</div>
                <div class="tag-wrap" v-if="backendRecommendations.external_sources?.length">
                  <el-tag v-for="entry in backendRecommendations.external_sources" :key="`rec-source-${entry}`" class="tag-item" type="warning" effect="plain">{{ entry }}</el-tag>
                </div>
                <div v-else class="recommendation-empty">Currently, local priority is sufficient, external sources are not required.</div>
              </div>
              <div v-if="!isExternalApiMode && (matchedStockCollections.length || matchedExternalSources.length)" class="recommendation-block">
                <div class="recommendation-label">Quick positioning</div>
                <div class="recommendation-actions">
                  <el-button v-if="matchedStockCollections.length" size="small" type="success" plain @click="focusFirstMatchedStockCard">Locate local hits</el-button>
                  <el-button v-if="matchedExternalSources.length" size="small" type="warning" plain @click="focusFirstMatchedExternalCard">locate external hits</el-button>
                </div>
              </div>
            </div>
          </div>
          <div v-if="isExternalApiMode" class="spec-catalog-card">
            <div class="spec-catalog-header">
              <div>
                <h4>External data source integration mode</h4>
                <p>The data source for this requirement {{ externalApiSourceName }}] Not within the system catalog, evaluation of local stock assets and external sources within the catalog has been skipped. Please ensure that the requirements include interface specifications: URL, request method, parameters, authentication method, return fields; if missing, the generator will ask for clarification and will not invent interface details and field names.</p>
              </div>
            </div>
            <div v-if="interfaceSpecConstraints.length" class="interface-spec-list">
              <div class="recommendation-label">Identified interface specifications (code generation will be used verbatim, rewriting the path is strictly prohibited)</div>
              <div v-for="(entry, idx) in interfaceSpecConstraints" :key="`iface-spec-${idx}`" class="interface-spec-item">{{ entry }}</div>
            </div>
            <el-alert
              v-else
              type="warning"
              :closable="false"
              show-icon
              title="Interface not recognized in current specification URL"
              description="The interface address is the only source of truth for external integration. It is recommended to replenish the complete interface specifications (URL, request method, parameters, request headers) in the requirements and then reconfirm to avoid the generator asking for clarification or fabricated interfaces."
              style="margin-top: 10px;"
            />
            <div v-if="interfacePreflight" class="interface-preflight-block">
              <el-alert
                :type="interfacePreflight.status === 'verified' ? 'success' : (interfacePreflight.status === 'warning' ? 'warning' : 'error')"
                :closable="false"
                show-icon
                :title="interfacePreflight.status === 'verified'
                  ? `Interface connectivity verified (HTTP ${interfacePreflight.http_status || 200}, Return ${interfacePreflight.data_items || 0} data)`
                  : (interfacePreflight.status === 'warning' ? 'The interface is reachable, but the data is questionable' : 'Interface preflight failed')"
                :description="interfacePreflight.message"
              />
              <div v-if="interfacePreflight.sample_fields?.length" class="catalog-notes" style="margin-top: 6px;">
                <div class="catalog-note-item">Return sample fields:{{ interfacePreflight.sample_fields.join(', ') }}</div>
                <div v-if="interfacePreflight.ignored_params?.length" class="catalog-note-item" style="color: #e6a23c;">
                  Measured parameters ignored by the interface (the generated code will pull all the parameters and then filter them locally):{{ interfacePreflight.ignored_params.join(', ') }}
                </div>
              </div>
            </div>
            <div v-if="otherSpecConstraints.length" class="catalog-notes" style="margin-top: 10px;">
              <div class="recommendation-label">behavioral constraints</div>
              <div v-for="(entry, idx) in otherSpecConstraints" :key="`spec-constraint-${idx}`" class="catalog-note-item">{{ entry }}</div>
            </div>
          </div>
          <div v-if="!isExternalApiMode" class="spec-catalog-card">
            <div class="spec-catalog-header">
              <div>
                <h4>Local stock data directory</h4>
                <p>Here the stock core collection and key fields referenced by the current Skill Generator are displayed. When confirming the specifications, you can directly check whether to prioritize reusing existing data in the database.</p>
              </div>
              <el-button text @click="loadStockDataCatalog" :loading="stockCatalogLoading">refresh directory</el-button>
            </div>
            <div v-if="stockCatalogDoc" class="catalog-summary">
              Currently sorted {{ stockCatalogCollections.length }} It is a core collection. It is recommended to reuse encapsulated functions first and do not directly make up field names.
            </div>
            <div v-if="matchedStockCollections.length" class="catalog-match-summary">
              This specification hit set:{{ matchedStockCollections.map(item => item.collection).join(', ') }}
            </div>
            <el-collapse v-model="stockCatalogExpanded">
              <el-collapse-item name="stock-data-catalog" title="View the collection and field catalog">
                <div v-if="stockCatalogCollections.length" class="catalog-collection-list">
                  <div
                    v-for="item in stockCatalogCollections"
                    :key="item.collection"
                    :ref="(el) => setStockCardRef(item.collection, el)"
                    :class="['catalog-collection-card', { 'catalog-collection-card-recommended': isStockCollectionMatched(item) } ]"
                  >
                    <div class="catalog-collection-topbar">
                      <div>
                        <div class="catalog-collection-title">{{ item.collection }}</div>
                        <div v-if="isStockCollectionMatched(item)" class="catalog-match-label">This hit</div>
                      </div>
                      <div class="catalog-collection-actions">
                        <el-button size="small" text @click="insertCatalogIntoRequirement(item)">Insert into requirement</el-button>
                        <el-button size="small" text @click="copyCatalogCollectionName(item.collection)">Copy collection name</el-button>
                        <el-button size="small" text @click="copyCatalogQueryKeys(item)">Copy query key</el-button>
                        <el-button size="small" text @click="copyCatalogPreferredAccess(item)">copy access function</el-button>
                        <el-button size="small" text @click="copyCatalogFieldNames(item)">Copy field name</el-button>
                        <el-button size="small" text @click="copyCatalogFieldDescriptions(item)">Copy field description</el-button>
                      </div>
                    </div>
                    <div class="catalog-collection-purpose">{{ item.purpose }}</div>
                    <div class="tag-wrap" v-if="item.preferred_access?.length">
                      <el-tag v-for="entry in item.preferred_access" :key="`${item.collection}-access-${entry}`" class="tag-item" type="success" effect="plain">{{ entry }}</el-tag>
                    </div>
                    <div class="tag-wrap" v-if="item.query_keys?.length" style="margin-top: 8px;">
                      <el-tag v-for="entry in item.query_keys" :key="`${item.collection}-query-${entry}`" class="tag-item" type="info" effect="plain">{{ entry }}</el-tag>
                    </div>
                    <el-table :data="item.fields" size="small" border stripe class="catalog-field-table">
                      <el-table-column prop="name" label="Field" width="180" />
                      <el-table-column prop="type" label="Type" width="140" />
                      <el-table-column prop="description" label="Description" min-width="320" />
                    </el-table>
                    <div v-if="item.notes?.length" class="catalog-notes">
                      <div v-for="entry in item.notes" :key="`${item.collection}-note-${entry}`" class="catalog-note-item">{{ entry }}</div>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="It is not currently loaded into the stock data directory." />
              </el-collapse-item>
            </el-collapse>
          </div>
          <div v-if="!isExternalApiMode" class="spec-catalog-card">
            <div class="spec-catalog-header">
              <div>
                <h4>External interface and data source directory</h4>
                <p>Only the external sources supported by the current system are shown here. When online complement is required, you should first select the most matching one or two sources, and do not stuff all APIs together into requirements.</p>
              </div>
              <el-button text @click="loadExternalDataSourceCatalog" :loading="externalSourceCatalogLoading">refresh directory</el-button>
            </div>
            <div v-if="externalSourceCatalogDoc" class="catalog-summary">
              Currently sorted {{ externalSourceCatalogSources.length }} As a core external source, it is recommended to accurately select according to needs and retain the strategy of local priority and external degradation.
            </div>
            <div v-if="matchedExternalSources.length" class="catalog-match-summary">
              The source of this specification hit:{{ matchedExternalSources.map(item => item.display_name).join(', ') }}
            </div>
            <el-collapse v-model="externalSourceCatalogExpanded">
              <el-collapse-item name="external-data-source-catalog" title="View external source directory">
                <div v-if="externalSourceCatalogSources.length" class="catalog-collection-list">
                  <div
                    v-for="item in externalSourceCatalogSources"
                    :key="item.source_id"
                    :ref="(el) => setExternalSourceCardRef(item.source_id, el)"
                    :class="['catalog-collection-card', { 'catalog-collection-card-recommended': isExternalSourceMatched(item) } ]"
                  >
                    <div class="catalog-collection-topbar">
                      <div>
                        <div class="catalog-collection-title">{{ item.display_name }}</div>
                        <div class="catalog-collection-purpose">{{ item.source_id }} · {{ item.source_type }}</div>
                        <div v-if="isExternalSourceMatched(item)" class="catalog-match-label">This hit</div>
                      </div>
                      <div class="catalog-collection-actions">
                        <el-button size="small" text @click="insertExternalSourceIntoRequirement(item)">Insert into requirement</el-button>
                        <el-button size="small" text @click="copyExternalSourceName(item)">Copy source name</el-button>
                        <el-button size="small" text @click="copyExternalSourceInterfaces(item)">Copy interface</el-button>
                        <el-button size="small" text @click="copyExternalSourcePreferredFor(item)">Copy applicable scenarios</el-button>
                        <el-button size="small" text @click="copyExternalSourceConstraints(item)">Copy constraints</el-button>
                      </div>
                    </div>
                    <div class="tag-wrap" v-if="item.markets?.length" style="margin-top: 10px;">
                      <el-tag v-for="entry in item.markets" :key="`${item.source_id}-market-${entry}`" class="tag-item" type="warning" effect="plain">{{ entry }}</el-tag>
                    </div>
                    <div class="tag-wrap" v-if="item.categories?.length" style="margin-top: 8px;">
                      <el-tag v-for="entry in item.categories" :key="`${item.source_id}-category-${entry}`" class="tag-item" type="info" effect="plain">{{ entry }}</el-tag>
                    </div>
                    <div v-if="item.preferred_for?.length" class="catalog-notes">
                      <div v-for="entry in item.preferred_for" :key="`${item.source_id}-preferred-${entry}`" class="catalog-note-item">Recommended scenario:{{ entry }}</div>
                    </div>
                    <div v-if="item.interfaces?.length" class="catalog-notes">
                      <div v-for="entry in item.interfaces" :key="`${item.source_id}-interface-${entry}`" class="catalog-note-item">Recommended interface:{{ entry }}</div>
                    </div>
                    <div v-if="item.constraints?.length" class="catalog-notes">
                      <div v-for="entry in item.constraints" :key="`${item.source_id}-constraint-${entry}`" class="catalog-note-item">Constraints:{{ entry }}</div>
                    </div>
                    <div v-if="item.notes?.length" class="catalog-notes">
                      <div v-for="entry in item.notes" :key="`${item.source_id}-note-${entry}`" class="catalog-note-item">Description:{{ entry }}</div>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="It has not been loaded into the external interface and data source directory yet." />
              </el-collapse-item>
            </el-collapse>
          </div>
          <div v-if="specPreview" class="spec-preflight-card">
            <div class="spec-catalog-header">
              <div>
                <h4>Check before building</h4>
                <p>The current generation will be executed according to the following reuse strategy first. After confirmation, enter the code generation and verification process.</p>
              </div>
            </div>
            <div class="preflight-grid">
              <div v-if="preflightAvailableHelpers.length" class="recommendation-block">
                <div class="recommendation-label">Helper function hit (datasource overridden)</div>
                <div class="tag-wrap">
                  <el-tag v-for="entry in preflightAvailableHelpers" :key="`preflight-helper-${entry.module}.${entry.name}`" class="tag-item" :type="entry.data_source_handling === 'self_contained' || !entry.data_source_handling ? 'success' : 'warning'" effect="plain">
                    {{ entry.module.split('.').pop() }}.{{ entry.name }}
                  </el-tag>
                </div>
                <div class="catalog-note-item" style="margin-top: 6px; color: #67c23a;">
                  total {{ preflightAvailableHelpers.length }} of which {{ preflightSelfContainedHelpers.length }} A self-contained data source (just call it directly)
                </div>
              </div>
              <div class="recommendation-block">
                <div class="recommendation-label">Prioritize reuse of local collections</div>
                <div v-if="preflightLocalCollections.length" class="tag-wrap">
                  <el-tag v-for="entry in preflightLocalCollections" :key="`preflight-local-${entry}`" class="tag-item" type="success" effect="plain">{{ entry }}</el-tag>
                </div>
                <div v-else-if="isExternalApiMode" class="recommendation-empty">External data source integration mode: Local stock assets are not evaluated.</div>
                <div v-else-if="preflightSelfContainedHelpers.length" class="recommendation-empty">The data source is already covered by the helper function, no additional hits to local collections are required.</div>
                <div v-else class="recommendation-empty">There is currently no explicit local collection hit, and the generation will rely more on the requirement description and directory context.</div>
              </div>
              <div class="recommendation-block">
                <div class="recommendation-label">Candidate external sources</div>
                <div v-if="preflightExternalSources.length" class="tag-wrap">
                  <el-tag v-for="entry in preflightExternalSources" :key="`preflight-source-${entry}`" class="tag-item" type="warning" effect="plain">{{ entry }}</el-tag>
                </div>
                <div v-else-if="isExternalApiMode" class="recommendation-empty">Requirements specify external data sources ({{ externalApiSourceName }}) If it is not in the system directory, the interface specifications provided by the user shall prevail.</div>
                <div v-else-if="preflightSelfContainedHelpers.length" class="recommendation-empty">The data source is covered by the helper function, external sources are not required.</div>
                <div v-else class="recommendation-empty">Currently, local data is given priority and external sources are not required.</div>
              </div>
              <div class="recommendation-block">
                <div class="recommendation-label">Generate reminder</div>
                <div class="preflight-notes">
                  <div v-for="entry in preflightNotes" :key="entry" class="catalog-note-item">{{ entry }}</div>
                </div>
              </div>
            </div>
          </div>
          <div ref="confirmActionsRef" :class="['spec-confirm-actions', { 'spec-confirm-actions-highlight': highlightConfirmActions } ]">
            <el-button @click="wizardStep = 0">✏️ Return to modification</el-button>
            <el-button type="primary" @click="handleConfirmAndGenerate" :loading="specConfirmLoading">
              ✅ Confirm and generate
            </el-button>
          </div>
        </div>
      </div>

      <!-- steps 2: Build progress -->
      <div v-if="wizardStep === 2" class="wizard-generating">
        <div class="gen-status">
          <el-icon class="gen-spinner" :size="40"><Loading /></el-icon>
          <h3>Generating Skill...</h3>
          <p class="gen-desc">{{ pipelineMessage || 'AI Generating code, validating syntax, sandboxing execution and quality assessment' }}</p>
        </div>
        <el-progress :percentage="Math.round(genProgress * 100) / 100" :stroke-width="14" style="margin: 24px 0; max-width: 500px; margin-left: auto; margin-right: auto;" />
        <div class="gen-steps">
          <div v-for="(s, i) in genSteps" :key="i" :class="['gen-step', s.status]">
            <el-icon v-if="s.status === 'done'"><CircleCheck /></el-icon>
            <el-icon v-else-if="s.status === 'running'" class="is-loading"><Loading /></el-icon>
            <el-icon v-else><MoreFilled /></el-icon>
            <span>{{ s.label }}</span>
          </div>
        </div>
        <div v-if="pipelineThinking" class="thinking-panel">
          <div class="thinking-header" @click="thinkingExpanded = !thinkingExpanded">
            <span>AI Thought process (real time)</span>
            <el-icon :class="['thinking-arrow', { collapsed: !thinkingExpanded }]"><ArrowDown /></el-icon>
          </div>
          <pre v-show="thinkingExpanded" ref="thinkingBodyRef" class="thinking-body">{{ pipelineThinking }}</pre>
        </div>
        <div v-if="pipelineEvalResult" class="eval-result-panel">
          <div class="eval-result-header">
            <span>Quality assessment results</span>
            <span :class="['eval-total', pipelineEvalResult.passed ? 'pass' : 'fail']">
              {{ pipelineEvalResult.total }}/10 ({{ pipelineEvalResult.passed ? 'Meet the standard' : 'Not up to standard' }}) 
            </span>
          </div>
          <div class="eval-dimensions">
            <div v-for="dim in evalDimensions" :key="dim.key" class="eval-dim">
              <span class="eval-dim-label">{{ dim.label }}</span>
              <el-progress
                :percentage="Math.min(100, (pipelineEvalResult[dim.key] / 10) * 100)"
                :stroke-width="8"
                :show-text="false"
                :color="evalScoreColor(pipelineEvalResult[dim.key])"
                class="eval-dim-bar"
              />
              <span class="eval-dim-score">{{ pipelineEvalResult[dim.key] }}</span>
            </div>
          </div>
          <div v-if="pipelineEvalResult.expert_comment" class="eval-comment">
            {{ pipelineEvalResult.expert_comment }}
          </div>
          <div v-if="pipelineEvalResult.business_passed === false" class="eval-business-fail">
            Business acceptance failed
          </div>
        </div>
      </div>

      <!-- steps 3: Complete -->
      <div v-if="wizardStep === 3" class="wizard-done">
        <el-result
          :icon="genResult?.success ? 'success' : 'error'"
          :title="genResult?.success ? '🎉 Skill Created successfully!' : '❌ Build failed'"
          :sub-title="genResult?.success
            ? `Tools ID: ${genResult.skill_id} · Time consuming ${genResult.total_time}s · Rating ${genResult.final_score ?? '-'}/10`
            : genResult?.error || 'Please add correction suggestions based on the failure information below, and then regenerate'"
        >
          <template #extra>
            <el-button v-if="genResult?.success" type="primary" @click="goBack">
              View Skill List
            </el-button>
            <el-button v-else @click="wizardStep = 1">Return to specification confirmation</el-button>
            <el-button @click="goBack">Return to list</el-button>
          </template>
        </el-result>
        <div v-if="!genResult?.success" class="repair-card">
          <div class="spec-catalog-header">
            <div>
              <h4>Let the AI explain the correction plan first, and then decide whether to rerun</h4>
              <p>Failure information for static verification, sandbox execution, and evaluation phases will be automatically included here. You first add what you think is wrong, and AI will first reply with the problems it understands and a correction plan; after confirming that there are no deviations, it will continue to generate according to this plan.</p>
            </div>
          </div>
          <div v-if="pipelineFailureSummary.length" class="repair-summary-list">
            <div v-for="entry in pipelineFailureSummary" :key="entry" class="catalog-note-item">{{ entry }}</div>
          </div>
          <div class="repair-timeout-row">
            <span class="repair-timeout-label">Code generation timeout (seconds)</span>
            <el-input-number
              v-model="codegenTimeout"
              :min="60"
              :max="1800"
              :step="60"
              controls-position="right"
              style="width: 160px"
            />
            <span class="repair-timeout-hint">The longest wait allowed for a single code generation call; if it fails due to timeout, increase it and regenerate it.</span>
          </div>
          <el-input
            v-model="repairFeedback"
            type="textarea"
            :rows="4"
            resize="vertical"
            placeholder="For example: the current price is silently set to 0 and the valuation continues, which is wrong; please give priority to using local real-time market prices to get the price. If you cannot get the effective current price, you will directly return an error."
          />
          <div v-if="repairPlan" class="repair-plan-card">
            <div class="repair-plan-header">
              <h5>AI Understanding issues and correction plans</h5>
              <span v-if="repairPlanStale" class="repair-plan-stale">You have modified your comments, please regenerate the plan</span>
            </div>
            <div class="markdown-body repair-plan-markdown" v-html="renderMarkdown(repairPlan)" />
          </div>
          <div class="repair-actions">
            <el-button @click="wizardStep = 1">Return to specification confirmation</el-button>
            <el-button :loading="repairPlanning" :disabled="!repairFeedback.trim() || !sessionId" @click="handlePreviewRepairPlan">
              {{ repairPlan ? 'Regenerate correction plan' : 'Let AI make correction plans first' }}
            </el-button>
            <el-button type="primary" :loading="repairing" :disabled="!canConfirmRepair" @click="handleRepairAndRegenerate">
              Confirm to run again according to this plan
            </el-button>
          </div>
        </div>
        <div v-if="genResult?.success" class="test-run-card">
          <div class="spec-catalog-header">
            <div>
              <h4>Test this now Skill</h4>
              <p>Here, the test interface will be called directly to run the newly generated Skill, and the default test_input in the current specifications will be used to verify whether it can be executed and whether the data is actually obtained.</p>
            </div>
          </div>
          <div v-if="generatedTestParams.length" class="test-run-form">
            <el-form label-width="120px" size="default">
              <el-form-item v-for="p in generatedTestParams" :key="p.name" :label="p.name" :required="p.required">
                <el-input
                  v-if="p.type === 'string' || !p.type"
                  v-model="generatedTestArgs[p.name]"
                  :placeholder="p.description || `Please enter ${p.name}`"
                  clearable
                />
                <el-input-number
                  v-else-if="p.type === 'integer' || p.type === 'int'"
                  v-model="generatedTestArgs[p.name]"
                  :placeholder="p.description"
                  controls-position="right"
                  style="width: 100%"
                />
                <el-input-number
                  v-else-if="p.type === 'float' || p.type === 'number'"
                  v-model="generatedTestArgs[p.name]"
                  :placeholder="p.description"
                  :precision="2"
                  controls-position="right"
                  style="width: 100%"
                />
                <el-switch v-else-if="p.type === 'boolean' || p.type === 'bool'" v-model="generatedTestArgs[p.name]" />
                <el-input
                  v-else
                  v-model="generatedTestArgs[p.name]"
                  :placeholder="p.description || `Please enter ${p.name}`"
                  clearable
                />
              </el-form-item>
            </el-form>
          </div>
          <div v-else class="test-params-empty">The current specification has no explicit parameters and will be executed directly using the default test input.</div>
          <div class="test-run-actions">
            <el-button @click="resetGeneratedTestArgs">Restore default parameters</el-button>
            <el-button type="primary" :loading="generatedTestLoading" :disabled="!generatedSkillId" @click="runGeneratedSkillTest">
              Run tests
            </el-button>
          </div>
          <div v-if="generatedTestResult" class="test-run-result">
            <div class="test-run-summary">
              <el-tag :type="generatedTestResult.success ? 'success' : 'danger'">{{ generatedTestResult.success ? 'Executed successfully' : 'Execution failed' }}</el-tag>
              <el-tag :type="generatedTestDataState.type" effect="plain">{{ generatedTestDataState.label }}</el-tag>
            </div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="Execution time">{{ generatedTestResult.execution_time }}s</el-descriptions-item>
              <el-descriptions-item label="Result explanation">{{ generatedTestDataState.description }}</el-descriptions-item>
              <el-descriptions-item v-if="generatedTestResult.error" label="Error">
                <span class="test-run-error">{{ generatedTestResult.error }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="output">
                <pre class="test-run-pre">{{ generatedTestResultText }}</pre>
              </el-descriptions-item>
              <el-descriptions-item v-if="generatedTestResult.stdout" label="stdout">
                <pre class="test-run-pre">{{ generatedTestResult.stdout }}</pre>
              </el-descriptions-item>
              <el-descriptions-item v-if="generatedTestResult.stderr" label="stderr">
                <pre class="test-run-pre">{{ generatedTestResult.stderr }}</pre>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
        <div v-if="genResult?.success && (preflightLocalCollections.length || preflightExternalSources.length)" class="done-context-card">
          <div class="spec-catalog-header">
            <div>
              <h4>The reuse strategy used in this generation</h4>
              <p>The following content comes from the pre-generation unified selector, which is used to explain which local collections and external sources are prioritized for this code generation.</p>
            </div>
          </div>
          <div class="preflight-grid">
            <div class="recommendation-block">
              <div class="recommendation-label">local collection</div>
              <div v-if="preflightLocalCollections.length" class="tag-wrap">
                <el-tag v-for="entry in preflightLocalCollections" :key="`done-local-${entry}`" class="tag-item" type="success" effect="plain">{{ entry }}</el-tag>
              </div>
              <div v-else class="recommendation-empty">The local collection is not explicitly locked this time.</div>
            </div>
            <div class="recommendation-block">
              <div class="recommendation-label">external sources</div>
              <div v-if="preflightExternalSources.length" class="tag-wrap">
                <el-tag v-for="entry in preflightExternalSources" :key="`done-source-${entry}`" class="tag-item" type="warning" effect="plain">{{ entry }}</el-tag>
              </div>
              <div v-else class="recommendation-empty">This strategy favors local priority and external sources are not required.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, computed, watch, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, User, MagicStick, Loading, CircleCheck, MoreFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'
import { skillGenerationApi } from '@/api/skillGeneration'
import type {
  BoundaryCheck,
  ConfirmResult,
  ExternalDataSourceCatalogItem,
  ImplementationFactReportView,
  InterfacePreflightResult,
  PipelineResultDetail,
  PipelineEvalResult,
  ReconToolTrace,
  SessionDetail,
  SkillHandoffContext,
  SkillGenerationRecommendations,
  StockDataCatalogCollection,
  TestResult,
} from '@/api/skillGeneration'

// marked The configuration has been @/utils/markdown Unified management
const renderMarkdown = (content: string): string => {
  if (!content?.trim()) return ''
  try { return safeMarkdown(content) } catch { return content }
}

const route = useRoute()
const router = useRouter()

// ==================== Status ====================

const wizardStep = ref(0)

interface ChatMsg { role: 'user' | 'ai'; content: string }
const chatMessages = ref<ChatMsg[]>([])
const chatLoading = ref(false)
const userInput = ref('')
const chatContainer = ref<HTMLElement | null>(null)

const recommendationCardRef = ref<HTMLElement | null>(null)
const confirmActionsRef = ref<HTMLElement | null>(null)
const stockCardRefs = ref<Record<string, HTMLElement | null>>({})
const externalSourceCardRefs = ref<Record<string, HTMLElement | null>>({})
const sessionId = ref('')
const currentRound = ref(0)
const expectedRounds = ref(3)
const boundaryCheck = ref<BoundaryCheck | null>(null)
const boundaryExpanded = ref(false)
const boundaryWarning = computed(() => boundaryCheck.value && !boundaryCheck.value.within_boundary)

watch(boundaryCheck, () => { boundaryExpanded.value = false })
const canConfirm = computed(() => chatMessages.value.length >= 2)

const specPreview = ref<Record<string, any> | null>(null)
const previewFactReport = ref<ImplementationFactReportView | null>(null)
const interfacePreflight = ref<InterfacePreflightResult | null>(null)
// List of change points in upgrade patch mode (diff-style display on iteration session confirmation page)
const upgradeChangePoints = ref<string[]>([])
const specConfirmLoading = ref(false)
const pipelineMessage = ref('')
const pipelineDetails = ref<Array<{ stage: string; message: string; iteration: number; progress: number; timestamp?: string }>>([])
const pipelineThinking = ref('')
const pipelineEvalResult = ref<PipelineEvalResult | null>(null)
const thinkingExpanded = ref(true)
const thinkingBodyRef = ref<HTMLElement | null>(null)

/** Quality assessment dimension configuration (the order is the display order) */
const evalDimensions = [
  { key: 'executability', label: 'Enforceability' },
  { key: 'authenticity', label: 'authenticity' },
  { key: 'completeness', label: 'integrity' },
  { key: 'relevance', label: 'Relevance' },
  { key: 'format_quality', label: 'Format quality' },
] as const

/** Dimension score color matching:<7 Red prompts insufficient, 7-8 orange,≥8 green */
const evalScoreColor = (score: number): string => {
  if (score < 7) return '#f56c6c'
  if (score < 8) return '#e6a23c'
  return '#67c23a'
}

watch(pipelineThinking, () => {
  nextTick(() => {
    if (thinkingBodyRef.value) thinkingBodyRef.value.scrollTop = thinkingBodyRef.value.scrollHeight
  })
})
const stockCatalogLoading = ref(false)
const stockCatalogDoc = ref('')
const stockCatalogCollections = ref<StockDataCatalogCollection[]>([])
const stockCatalogExpanded = ref<string[]>(['stock-data-catalog'])
const externalSourceCatalogLoading = ref(false)
const externalSourceCatalogDoc = ref('')
const externalSourceCatalogSources = ref<ExternalDataSourceCatalogItem[]>([])
const externalSourceCatalogExpanded = ref<string[]>(['external-data-source-catalog'])
const backendRecommendations = ref<SkillGenerationRecommendations | null>(null)
const handoffContext = ref<SkillHandoffContext | null>(null)
const highlightRecommendationCard = ref(false)
const highlightConfirmActions = ref(false)

// Iterative optimization mode related
const isIterateMode = ref(false)
interface IterateSkillInfo {
  toolId: string
  displayName: string
  description: string
  category: string
}
const iterateSkillInfo = ref<IterateSkillInfo | null>(null)

// Initialize iterative optimization mode from routing parameters
const initIterateMode = () => {
  const mode = route.query.mode
  if (mode === 'iterate') {
    isIterateMode.value = true
    iterateSkillInfo.value = {
      toolId: String(route.query.toolId || ''),
      displayName: String(route.query.displayName || ''),
      description: String(route.query.description || ''),
      category: String(route.query.category || '')
    }
    // If there is a description, prepopulate it into the chat
    if (iterateSkillInfo.value.description) {
      userInput.value = `I want to iteratively optimize this Skill:${iterateSkillInfo.value.displayName}\n\n${iterateSkillInfo.value.description}\n\n Please help me regenerate a better version or tell me where I can improve it.`
    }
  }
}

const getRouteHandoffContext = (): SkillHandoffContext | null => {
  const sourceSpecId = typeof route.query.from_agent_workshop === 'string' ? route.query.from_agent_workshop.trim() : ''
  const targetCapability = typeof route.query.target_capability === 'string'
    ? route.query.target_capability.trim()
    : (typeof route.query.skill_name === 'string' ? route.query.skill_name.trim() : '')
  const sourceName = typeof route.query.source_name === 'string' ? route.query.source_name.trim() : ''
  const handoffIntent = typeof route.query.handoff_intent === 'string' ? route.query.handoff_intent.trim() : ''
  if (!sourceSpecId && !targetCapability) return null

  return {
    source: sourceSpecId ? 'agent_workshop' : '',
    source_spec_id: sourceSpecId,
    source_name: sourceName,
    target_capability: targetCapability,
    handoff_intent: handoffIntent || 'Currently, the ability gap is filled from the Agent creation process, not ordinary Skill brainstorming. Priority must be given to retaining the upstream target capabilities; if it needs to be split into Skills, it can only be defined as the minimum deterministic sub-capability within the Agent s capabilities.',
  }
}

const preflightLocalCollections = computed(() => backendRecommendations.value?.stock_collections || [])
const preflightExternalSources = computed(() => backendRecommendations.value?.external_sources || [])
// Hit helper function (from recon layer fact_report.available_helpers)
const preflightAvailableHelpers = computed(() => previewFactReport.value?.available_helpers || [])
// Among them, the helper of the self-contained data source (self_contained means that the data source call has been encapsulated inside the helper)
const preflightSelfContainedHelpers = computed(() =>
  preflightAvailableHelpers.value.filter(h => !h.data_source_handling || h.data_source_handling === 'self_contained')
)
// External API integration mode: data source requirements outside the directory, do not display/do not evaluate local stock assets and internal and external sources in the directory
const isExternalApiMode = computed(() => backendRecommendations.value?.requirement_mode === 'external_api')
const externalApiSourceName = computed(
  () => backendRecommendations.value?.unknown_data_source
    || String(specPreview.value?.data_source || '').trim()
    || 'Out-of-directory data sources'
)
// Interface specification constraints: constraints with URL (the core contract of the external interface integration pattern, used verbatim for code generation)
const interfaceSpecConstraints = computed(() =>
  (specPreview.value?.constraints || []).filter((entry: string) => /https?:\/\//.test(String(entry)))
)
// Remaining behavioral constraints (excluding URL)
const otherSpecConstraints = computed(() =>
  (specPreview.value?.constraints || []).filter((entry: string) => !/https?:\/\//.test(String(entry)))
)
const preflightNotes = computed(() => {
  const notes: string[] = []
  // External interface integration mode: The data source is outside the system directory, and the generated reminder will no longer output local priority words.
  if (isExternalApiMode.value) {
    notes.push(
      `External interface integration mode: data source ${externalApiSourceName.value}] If it is not in the system directory, it will be implemented directly according to the interface specifications (URL, request headers, parameters) provided by the user.`
    )
    notes.push('Will not reuse local stock collections or external sources within the directory; the generator will ask for clarification when interface specifications are not provided and will not invent interface details.')
    notes.push('This time it will still go through code generation, static verification, sandbox execution and quality assessment, and verification will not be skipped.')
    return notes
  }
  // Prioritize display of hit helper functions (this is the core signal of data source capabilities, more accurate than local collections)
  if (preflightSelfContainedHelpers.value.length) {
    const helperNames = preflightSelfContainedHelpers.value.map(h => `${h.module.split('.').pop()}.${h.name}`)
    notes.push(`Hit ${preflightSelfContainedHelpers.value.length} Helper functions for self-contained data sources:${helperNames.join(', ')} (Just call it directly, no additional data sources are needed)`)
  } else if (preflightAvailableHelpers.value.length) {
    notes.push(`Hit ${preflightAvailableHelpers.value.length} A helper function (some may require additional data sources)`)
  }

  if (preflightLocalCollections.value.length) {
    notes.push(`Prioritize reuse of local collections:${preflightLocalCollections.value.join(', ')}`)
  } else if (preflightSelfContainedHelpers.value.length) {
    // There is already a self-contained helper, local collections are no longer required
    notes.push('The data source is already covered by the helper function, no additional hits to local collections are required.')
  } else {
    notes.push('There is currently no local collection that is explicitly hit. The generator will decide whether to directly connect to external sources based on the requirement description and directory information.')
  }

  if (preflightExternalSources.value.length) {
    notes.push(`If local data is insufficient, priority will be given to these external sources:${preflightExternalSources.value.join(', ')}`)
  } else if (preflightSelfContainedHelpers.value.length) {
    notes.push('The data source is covered by the helper function, external sources are not required.')
  } else {
    notes.push('The current recommendation strategy favors local priority, with more external sources as optional supplements.')
  }

  notes.push('This time it will still go through code generation, static verification, sandbox execution and quality assessment, and verification will not be skipped.')
  return notes
})

const normalizeSpecText = (spec: Record<string, any> | null) => {
  if (!spec) return ''
  const parts = [
    spec.category,
    spec.description,
    spec.data_source,
    ...(Array.isArray(spec.constraints) ? spec.constraints : []),
    ...((spec.parameters || []).map((item: any) => item?.name).filter(Boolean)),
    ...((spec.expected_output?.fields || []).filter(Boolean)),
  ]
  return parts.join('\n').toLowerCase()
}

const specPreviewText = computed(() => normalizeSpecText(specPreview.value))
const recommendedStockCollectionSet = computed(() => new Set((backendRecommendations.value?.stock_collections || []).map(item => item.toLowerCase())))
const recommendedExternalSourceSet = computed(() => new Set((backendRecommendations.value?.external_sources || []).map(item => item.toLowerCase())))

const isStockCollectionMatched = (item: StockDataCatalogCollection) => {
  if (recommendedStockCollectionSet.value.has(item.collection.toLowerCase())) return true

  const spec = specPreview.value
  const text = specPreviewText.value
  if (!spec || !text) return false

  if (text.includes(item.collection.toLowerCase())) return true
  if ((item.preferred_access || []).some(entry => text.includes(entry.toLowerCase()))) return true
  if ((item.query_keys || []).some(entry => text.includes(entry.toLowerCase()) && !['symbol', 'code'].includes(entry.toLowerCase()))) return true

  const category = String(spec.category || '').toLowerCase()
  const purpose = String(item.purpose || '').toLowerCase()
  if (category && purpose.includes(category)) return true

  if (item.collection === 'stock_news' && (category === 'news' || text.includes('News') || text.includes('publish_time'))) return true
  if (item.collection === 'stock_financial_data' && (category === 'fundamentals' || text.includes('Finance') || text.includes('report_period'))) return true
  if (item.collection === 'stock_daily_quotes' && (category === 'technical' || text.includes('daily line') || text.includes('trade_date'))) return true
  if (item.collection === 'market_quotes' && (category === 'market' || text.includes('real time') || text.includes('snapshot'))) return true
  if (item.collection === 'stock_basic_info' && ['fundamentals', 'market', 'technical', 'news'].includes(category)) return true

  return false
}

const isExternalSourceMatched = (item: ExternalDataSourceCatalogItem) => {
  if (recommendedExternalSourceSet.value.has(item.source_id.toLowerCase())) return true

  const spec = specPreview.value
  const text = specPreviewText.value
  if (!spec || !text) return false

  if (text.includes(item.source_id.toLowerCase()) || text.includes(item.display_name.toLowerCase())) return true
  if ((item.categories || []).some(entry => text.includes(entry.toLowerCase()))) return true
  if ((item.interfaces || []).some(entry => text.includes(entry.toLowerCase()))) return true

  const category = String(spec.category || '').toLowerCase()
  if (item.source_id === 'tushare' && (category === 'fundamentals' || text.includes('dividend') || text.includes('report_period'))) return true
  if (item.source_id === 'akshare' && ((category === 'technical' || category === 'market') || text.includes('free'))) return true
  if (item.source_id === 'eastmoney_via_akshare' && (text.includes('Oriental Fortune') || text.includes('Dongcai'))) return true

  return false
}

const matchedStockCollections = computed(() => stockCatalogCollections.value.filter(item => isStockCollectionMatched(item)))
const matchedExternalSources = computed(() => externalSourceCatalogSources.value.filter(item => isExternalSourceMatched(item)))

const genProgress = ref(0)
const genSteps = ref([
  { label: 'Generate code', status: 'pending' },
  { label: 'Grammar check', status: 'pending' },
  { label: 'sandbox execution', status: 'pending' },
  { label: 'quality assessment', status: 'pending' },
])
const genResult = ref<ConfirmResult | null>(null)
const repairing = ref(false)
const repairPlanning = ref(false)
const repairFeedback = ref('')
const repairPlan = ref('')
const repairPlanFeedback = ref('')
// Code generation single LLM call timeout (seconds): default 480; after the timeout fails, it can be increased and resubmitted.
const codegenTimeout = ref(480)
const generatedTestLoading = ref(false)
const generatedTestArgs = ref<Record<string, any>>({})
const generatedTestResult = ref<TestResult | null>(null)

const sessionPipelineResult = ref<PipelineResultDetail | null>(null)

const repairPlanStale = computed(() => {
  const feedback = repairFeedback.value.trim()
  return !!repairPlan.value.trim() && !!feedback && repairPlanFeedback.value !== feedback
})

const canConfirmRepair = computed(() => {
  return !!sessionId.value && !!repairPlan.value.trim() && !repairPlanStale.value
})

const generatedSkillSpec = computed(() => genResult.value?.spec || specPreview.value || null)
const generatedSkillId = computed(() => genResult.value?.skill_id || '')
const generatedTestParams = computed(() => {
  const spec = generatedSkillSpec.value
  return Array.isArray(spec?.parameters) ? spec.parameters : []
})
const generatedTestDefaults = computed(() => {
  const spec = generatedSkillSpec.value
  return spec?.test_input && typeof spec.test_input === 'object' ? spec.test_input : {}
})
const generatedTestResultText = computed(() => {
  if (!generatedTestResult.value) return ''
  return JSON.stringify(generatedTestResult.value.output, null, 2)
})

const previewToolTraces = computed<ReconToolTrace[]>(() => previewFactReport.value?.tool_traces || [])

const previewFactFieldSummaries = computed(() => {
  return Object.entries(previewFactReport.value?.sample_fields || {}).slice(0, 4)
})
const generatedTestDataState = computed(() => {
  const result = generatedTestResult.value
  if (!result) {
    return {
      label: 'Not tested yet',
      type: 'info' as const,
      description: 'After running a test, this will tell you whether you actually got valid data.',
    }
  }

  if (!result.success) {
    return {
      label: 'Data not obtained',
      type: 'danger' as const,
      description: result.error || 'The test execution failed and it is currently impossible to confirm whether the data can be obtained normally.',
    }
  }

  const output = result.output
  const hasData = (
    output !== null &&
    output !== undefined &&
    (!(Array.isArray(output)) || output.length > 0) &&
    (typeof output !== 'object' || Array.isArray(output) || Object.keys(output).length > 0) &&
    (typeof output !== 'string' || output.trim().length > 0)
  )

  return hasData
    ? {
        label: 'Data has been obtained',
        type: 'success' as const,
        description: 'The test has passed and the returned results contain valid output.',
      }
    : {
        label: 'Execution successful but no data',
        type: 'warning' as const,
        description: 'The code has been executed successfully, but the current output is empty. You need to continue to confirm whether the query parameters or data sources are correct.',
      }
})

const pipelineFailureSummary = computed(() => {
  const result = sessionPipelineResult.value
  if (!result) return []

  const lines: string[] = []
  if (result.error) {
    lines.push(`Final error:${result.error}`)
  }

  for (const iteration of result.iterations || []) {
    const prefix = `No.${iteration.round_number}wheel`
    if (iteration.validation?.errors?.length) {
      for (const error of iteration.validation.errors.slice(0, 5)) {
        lines.push(`${prefix} Static verification:${error}`)
      }
    }
    if (iteration.sandbox && iteration.sandbox.success === false && iteration.sandbox.error) {
      lines.push(`${prefix} Sandbox execution:${iteration.sandbox.error}`)
    }
    if (iteration.eval_score && typeof iteration.eval_score.total === 'number') {
      lines.push(
        `${prefix} Insufficient assessment points:total=${iteration.eval_score.total}, ` +
        `executability=${iteration.eval_score.executability ?? '-'}，` +
        `authenticity=${iteration.eval_score.authenticity ?? '-'}，` +
        `completeness=${iteration.eval_score.completeness ?? '-'}，` +
        `relevance=${iteration.eval_score.relevance ?? '-'}，` +
        `format_quality=${iteration.eval_score.format_quality ?? '-'}`
      )
    }
    if (iteration.feedback) {
      lines.push(`${prefix} System feedback:${iteration.feedback}`)
    }
  }

  return Array.from(new Set(lines))
})

const buildGeneratedTestArgs = () => {
  const defaults = generatedTestDefaults.value || {}
  const init: Record<string, any> = {}
  for (const p of generatedTestParams.value) {
    init[p.name] = defaults[p.name] ?? p.default ?? (p.type === 'boolean' || p.type === 'bool' ? false : '')
  }
  for (const [key, value] of Object.entries(defaults)) {
    if (!(key in init)) init[key] = value
  }
  return init
}

const resetGeneratedTestArgs = () => {
  generatedTestArgs.value = buildGeneratedTestArgs()
}

const prepareGeneratedTestPanel = () => {
  generatedTestResult.value = null
  generatedTestLoading.value = false
  resetGeneratedTestArgs()
}

const normalizePipelineProgress = (progress?: number | null) => {
  if (typeof progress !== 'number' || Number.isNaN(progress)) return 0
  const normalized = progress <= 1 ? progress * 100 : progress
  return Math.max(0, Math.min(100, normalized))
}

const updateGenerationProgressUI = (stage?: string, message?: string, progress?: number | null) => {
  const stageToStep: Record<string, number> = {
    reconnaissance: 0,
    code_generation: 0,
    static_validation: 1,
    sandbox_execution: 2,
    output_evaluation: 3,
    edge_testing: 3,
    reflection: 3,
    error: 3,
  }

  pipelineMessage.value = message || stage || ''

  const normalizedProgress = normalizePipelineProgress(progress)
  if (normalizedProgress > 0 || progress === 0) {
    genProgress.value = Math.round(normalizedProgress * 100) / 100
  }

  if (!stage || stageToStep[stage] === undefined) return

  const idx = stageToStep[stage]
  genSteps.value.forEach((s, i) => {
    s.status = i < idx ? 'done' : i === idx ? 'running' : 'pending'
  })
}

// ==================== method ====================

const scrollChat = () => {
  nextTick(() => {
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  })
}

const goBack = () => {
  router.push('/skills')
}

const copyText = async (text: string, successMessage: string) => {
  const normalized = text.trim()
  if (!normalized) return

  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = normalized
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success(successMessage)
  } catch (e: any) {
    ElMessage.error(e?.message || 'Copy failed')
  }
}

const copyCatalogCollectionName = async (collectionName: string) => {
  await copyText(collectionName, `Collection name copied:${collectionName}`)
}

const copyCatalogFieldNames = async (item: StockDataCatalogCollection) => {
  const fieldNames = (item.fields || []).map(field => field.name).filter(Boolean)
  await copyText(fieldNames.join(', '), `Copied ${item.collection} field name`)
}

const copyCatalogQueryKeys = async (item: StockDataCatalogCollection) => {
  const queryKeys = (item.query_keys || []).filter(Boolean)
  await copyText(queryKeys.join(', '), `Copied ${item.collection} query key`)
}

const copyCatalogPreferredAccess = async (item: StockDataCatalogCollection) => {
  const preferredAccess = (item.preferred_access || []).filter(Boolean)
  await copyText(preferredAccess.join(', '), `Copied ${item.collection} Recommended access functions`)
}

const copyCatalogFieldDescriptions = async (item: StockDataCatalogCollection) => {
  const fieldDescriptions = (item.fields || [])
    .filter(field => field?.name)
    .map(field => `${field.name} (${field.type}): ${field.description}`)
  await copyText(fieldDescriptions.join('\n'), `Copied ${item.collection} field description`)
}

const copyExternalSourceName = async (item: ExternalDataSourceCatalogItem) => {
  await copyText(item.display_name, `Source name copied:${item.display_name}`)
}

const copyExternalSourceInterfaces = async (item: ExternalDataSourceCatalogItem) => {
  await copyText((item.interfaces || []).join('\n'), `Copied ${item.display_name} Recommended interface`)
}

const copyExternalSourcePreferredFor = async (item: ExternalDataSourceCatalogItem) => {
  await copyText((item.preferred_for || []).join('\n'), `Copied ${item.display_name} Applicable scenarios`)
}

const copyExternalSourceConstraints = async (item: ExternalDataSourceCatalogItem) => {
  await copyText((item.constraints || []).join('\n'), `Copied ${item.display_name} Constraint description`)
}

const buildCatalogRequirementSnippet = (item: StockDataCatalogCollection) => {
  const queryKeys = (item.query_keys || []).filter(Boolean)
  const preferredAccess = (item.preferred_access || []).filter(Boolean)
  const fieldDescriptions = (item.fields || [])
    .filter(field => field?.name)
    .map(field => `- ${field.name} (${field.type}): ${field.description}`)

  return [
    `Please give priority to reusing local stock data collections ${item.collection}. `,
    preferredAccess.length ? `Recommended access functions:${preferredAccess.join(', ')}. ` : '',
    queryKeys.length ? `Common query keys:${queryKeys.join(', ')}. ` : '',
    fieldDescriptions.length ? `Key fields:\n${fieldDescriptions.join('\n')}` : '',
  ].filter(Boolean).join('\n')
}

const insertCatalogIntoRequirement = async (item: StockDataCatalogCollection) => {
  const snippet = buildCatalogRequirementSnippet(item)
  if (!snippet.trim()) return

  userInput.value = userInput.value.trim()
    ? `${userInput.value.trim()}\n\n${snippet}`
    : snippet

  if (wizardStep.value !== 0) {
    wizardStep.value = 0
    await nextTick()
  }

  ElMessage.success(`Already ${item.collection} The directory information is inserted into the requirements input box.`)
}

const buildExternalSourceRequirementSnippet = (item: ExternalDataSourceCatalogItem) => {
  const markets = (item.markets || []).filter(Boolean)
  const categories = (item.categories || []).filter(Boolean)
  const preferredFor = (item.preferred_for || []).filter(Boolean)
  const interfaces = (item.interfaces || []).filter(Boolean)
  const constraints = (item.constraints || []).filter(Boolean)

  return [
    `If you need external online data, please use it first ${item.display_name} (${item.source_id}) . `,
    markets.length ? `Market coverage:${markets.join(', ')}. ` : '',
    categories.length ? `Applicable categories:${categories.join(', ')}. ` : '',
    preferredFor.length ? `Recommended scenario:${preferredFor.join('; ')}. ` : '',
    interfaces.length ? `Priority interface:${interfaces.join('; ')}. ` : '',
    constraints.length ? `Use constraints:${constraints.join('; ')}. ` : '',
  ].filter(Boolean).join('\n')
}

const insertExternalSourceIntoRequirement = async (item: ExternalDataSourceCatalogItem) => {
  const snippet = buildExternalSourceRequirementSnippet(item)
  if (!snippet.trim()) return

  userInput.value = userInput.value.trim()
    ? `${userInput.value.trim()}\n\n${snippet}`
    : snippet

  if (wizardStep.value !== 0) {
    wizardStep.value = 0
    await nextTick()
  }

  ElMessage.success(`Already ${item.display_name} The directory information is inserted into the requirements input box.`)
}

const loadStockDataCatalog = async () => {
  stockCatalogLoading.value = true
  try {
    const res = await skillGenerationApi.getStockDataCatalog()
    stockCatalogCollections.value = res.collections || []
    stockCatalogDoc.value = res.doc || ''
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to load stock data directory')
  } finally {
    stockCatalogLoading.value = false
  }
}

const loadExternalDataSourceCatalog = async () => {
  externalSourceCatalogLoading.value = true
  try {
    const res = await skillGenerationApi.getExternalDataSourceCatalog()
    externalSourceCatalogSources.value = res.sources || []
    externalSourceCatalogDoc.value = res.doc || ''
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to load external interface and data source directory')
  } finally {
    externalSourceCatalogLoading.value = false
  }
}

const getPrefillDescription = () => {
  const raw = route.query.description
  if (typeof raw === 'string') return raw.trim()
  return ''
}

const shouldFocusRecommendations = () => route.query.focus === 'recommendations'
const shouldFocusConfirmActions = () => route.query.focus === 'confirm'

const setStockCardRef = (collection: string, el: Element | ComponentPublicInstance | null) => {
  const htmlEl = el instanceof HTMLElement ? el : (el as any)?.$el instanceof HTMLElement ? (el as any).$el : null
  stockCardRefs.value[collection] = htmlEl
}

const setExternalSourceCardRef = (sourceId: string, el: Element | ComponentPublicInstance | null) => {
  const htmlEl = el instanceof HTMLElement ? el : (el as any)?.$el instanceof HTMLElement ? (el as any).$el : null
  externalSourceCardRefs.value[sourceId] = htmlEl
}

const scrollElementIntoView = async (element: HTMLElement | null) => {
  await nextTick()
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const focusFirstMatchedStockCard = async () => {
  if (!matchedStockCollections.value.length) return
  stockCatalogExpanded.value = ['stock-data-catalog']
  await nextTick()
  const firstMatch = matchedStockCollections.value[0]
  await scrollElementIntoView(stockCardRefs.value[firstMatch.collection] || null)
}

const focusFirstMatchedExternalCard = async () => {
  if (!matchedExternalSources.value.length) return
  externalSourceCatalogExpanded.value = ['external-data-source-catalog']
  await nextTick()
  const firstMatch = matchedExternalSources.value[0]
  await scrollElementIntoView(externalSourceCardRefs.value[firstMatch.source_id] || null)
}

const focusRecommendationCard = async () => {
  if (!shouldFocusRecommendations()) return
  await nextTick()
  if (!recommendationCardRef.value) return

  recommendationCardRef.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
  highlightRecommendationCard.value = true
  window.setTimeout(() => {
    highlightRecommendationCard.value = false
  }, 2200)
}

const focusConfirmActions = async () => {
  if (!shouldFocusConfirmActions()) return
  await nextTick()
  if (!confirmActionsRef.value) return

  confirmActionsRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
  highlightConfirmActions.value = true
  window.setTimeout(() => {
    highlightConfirmActions.value = false
  }, 2200)
}

const focusRecommendationFlow = async () => {
  if (!shouldFocusRecommendations()) return
  stockCatalogExpanded.value = ['stock-data-catalog']
  externalSourceCatalogExpanded.value = ['external-data-source-catalog']
  await focusRecommendationCard()
  if (matchedStockCollections.value.length) {
    window.setTimeout(() => {
      void focusFirstMatchedStockCard()
    }, 450)
    return
  }
  if (matchedExternalSources.value.length) {
    window.setTimeout(() => {
      void focusFirstMatchedExternalCard()
    }, 450)
  }
}

const focusConfirmFlow = async () => {
  if (!shouldFocusConfirmActions()) return
  await focusConfirmActions()
}

const buildGenResultFromSession = (session: SessionDetail): ConfirmResult | null => {
  const pr = (session.pipeline_result || null) as PipelineResultDetail | null
  if (!pr && session.status !== 'completed' && session.status !== 'failed') {
    return null
  }

  const lastIter = pr?.iterations?.[pr.iterations.length - 1]
  const es = lastIter?.eval_score
  const finalScore = es ? Math.round(
    (es.executability || 0) * 0.25 +
    (es.authenticity || 0) * 0.25 +
    (es.completeness || 0) * 0.2 +
    (es.relevance || 0) * 0.2 +
    (es.format_quality || 0) * 0.1
  ) : null

  return {
    status: session.status,
    session_id: session.session_id,
    skill_id: pr?.tool_id ?? null,
    spec: session.spec ?? null,
    success: session.status === 'completed',
    total_rounds: pr?.total_rounds ?? 0,
    total_time: pr?.total_time ?? 0,
    final_score: finalScore,
    error: pr?.error ?? session.pipeline_message ?? null,
  }
}

/** Initialization: Create a new or restore draft */
const initFromRoute = async () => {
  const sid = route.query.sessionId as string
  if (sid) {
    try {
      const session = await skillGenerationApi.getSession(sid)
      sessionId.value = session.session_id
      currentRound.value = session.current_round
      expectedRounds.value = Math.max(3, session.rounds?.length || 0)
      boundaryCheck.value = session.boundary_check || null
      handoffContext.value = session.handoff_context || getRouteHandoffContext()

      chatMessages.value = []
      for (const round of (session.rounds || [])) {
        chatMessages.value.push({ role: 'user', content: round.user_message })
        chatMessages.value.push({ role: 'ai', content: round.ai_message })
      }

      genResult.value = null
      genProgress.value = 0
      genSteps.value.forEach(s => s.status = 'pending')
      userInput.value = ''

      specPreview.value = session.spec || null
      backendRecommendations.value = session.recommendations || null
      previewFactReport.value = session.fact_report || null
      sessionPipelineResult.value = (session.pipeline_result || null) as PipelineResultDetail | null
      pipelineDetails.value = Array.isArray(session.pipeline_details) ? session.pipeline_details : []
      pipelineThinking.value = session.pipeline_thinking || ''
      pipelineEvalResult.value = session.pipeline_eval_result || null

      if (session.status === 'generating') {
        wizardStep.value = 2
        updateGenerationProgressUI(
          session.pipeline_stage,
          session.pipeline_message,
          session.pipeline_progress ?? 0,
        )
      } else if (session.status === 'completed' || session.status === 'failed') {
        genResult.value = buildGenResultFromSession(session)
        if (session.status === 'completed') prepareGeneratedTestPanel()
        pipelineMessage.value = session.pipeline_message || genResult.value?.error || ''
        wizardStep.value = 3
      } else if (session.status === 'confirmed') {
        wizardStep.value = 1
        if (shouldFocusConfirmActions()) {
          await focusConfirmFlow()
        } else {
          await focusRecommendationFlow()
        }
      } else {
        wizardStep.value = 0
      }
      scrollChat()
      ElMessage.success('Draft restored')
    } catch (e: any) {
      ElMessage.error('Restoring draft failed: ' + (e?.message || ''))
      wizardStep.value = 0
    }
  } else {
    wizardStep.value = 0
    handoffContext.value = getRouteHandoffContext()
    const prefillDescription = getPrefillDescription()
    if (prefillDescription) {
      userInput.value = prefillDescription
      await nextTick()
      await handleChatSend()
    }
  }
}

const handleChatSend = async () => {
  const text = userInput.value?.trim()
  if (!text || chatLoading.value) return

  chatMessages.value.push({ role: 'user', content: text })
  userInput.value = ''
  scrollChat()
  chatLoading.value = true

  try {
    if (!sessionId.value) {
      const res = await skillGenerationApi.startSession({
        description: text,
        handoff_context: handoffContext.value || undefined,
        iterate_skill_id: isIterateMode.value ? iterateSkillInfo.value?.toolId : undefined,
      })
      sessionId.value = res.session_id
      currentRound.value = res.current_round
      expectedRounds.value = res.expected_rounds
      boundaryCheck.value = res.boundary_check
      chatMessages.value.push({ role: 'ai', content: res.ai_message })
    } else {
      const res = await skillGenerationApi.respondToSession(sessionId.value, text)
      currentRound.value = res.current_round
      expectedRounds.value = res.expected_rounds
      if (res.boundary_check != null) boundaryCheck.value = res.boundary_check
      chatMessages.value.push({ role: 'ai', content: res.ai_message })
    }
    scrollChat()
  } catch (e: any) {
    const msg = e?.message || e?.response?.data?.message || 'Request failed'
    ElMessage.error(msg)
    chatMessages.value.push({ role: 'ai', content: `❌ Something went wrong:${msg}` })
    scrollChat()
  } finally {
    chatLoading.value = false
  }
}

/** View specifications: After generating specifications and reconnaissance reports, enter specification confirmation */
const handleViewSpec = async () => {
  if (!sessionId.value) return
  const confirmMessage = userInput.value?.trim() || 'Confirm'
  if (userInput.value?.trim()) {
    chatMessages.value.push({ role: 'user', content: userInput.value.trim() })
    userInput.value = ''
    scrollChat()
  }
  chatLoading.value = true
  try {
    const res = await skillGenerationApi.previewSpec(sessionId.value, confirmMessage)
    specPreview.value = res.spec
    backendRecommendations.value = res.recommendations || null
    previewFactReport.value = res.fact_report || null
    interfacePreflight.value = res.interface_preflight || null
    upgradeChangePoints.value = res.upgrade_change_points || []
    wizardStep.value = 1
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to get specifications')
    wizardStep.value = 0
  } finally {
    chatLoading.value = false
  }
}

/** Confirm and generate: call confirmSpec, if generating is returned, poll */
const handleConfirmAndGenerate = async () => {
  if (!sessionId.value) return
  // Generate more accurate confirmation text based on the hit helper function and local collection conditions
  const helperCount = preflightSelfContainedHelpers.value.length
  const helperHint = helperCount > 0
    ? `Hit ${helperCount} Helper function for a self-contained data source that has been overridden.`
    : (preflightAvailableHelpers.value.length > 0
        ? `Hit ${preflightAvailableHelpers.value.length} A helper function (some may need to supplement the data source).`
        : '')
  const localHint = preflightLocalCollections.value.length
    ? `Prioritize reuse of local collections:${preflightLocalCollections.value.join(', ')}`
    : (helperCount > 0
        ? 'The data source is already covered by the helper function, no additional hits to local collections are required.'
        : 'There is currently no local collection explicitly hit.')
  const externalHint = preflightExternalSources.value.length
    ? `Candidate external sources:${preflightExternalSources.value.join(', ')}`
    : (helperCount > 0
        ? 'External sources are not required.'
        : 'Local data is currently preferred, external sources are not required.')
  const confirmationText = [
    helperHint,
    localHint,
    externalHint,
    'After confirmation, code generation, static verification, sandbox execution and quality assessment will begin.',
  ].filter(Boolean).join('\n')

  try {
    await ElMessageBox.confirm(confirmationText, 'Confirm before generating', {
      confirmButtonText: 'Continue to generate',
      cancelButtonText: 'Return to check',
      type: 'warning',
    })
  } catch {
    return
  }

  specConfirmLoading.value = true
  wizardStep.value = 2
  repairFeedback.value = ''
  genResult.value = null
  sessionPipelineResult.value = null
  genSteps.value.forEach(s => s.status = 'pending')
  genProgress.value = 0
  pipelineMessage.value = 'Confirming specifications and starting build task...'
  pipelineDetails.value = []
  pipelineThinking.value = ''
  pipelineEvalResult.value = null

  try {
    const res = await skillGenerationApi.confirmSpec(sessionId.value, 'Confirm', codegenTimeout.value)
    if (res.status === 'generating') {
      const pollInterval = 1500
      const poll = async () => {
        const session = await skillGenerationApi.getSession(sessionId.value)
        sessionPipelineResult.value = (session.pipeline_result || null) as PipelineResultDetail | null
        pipelineDetails.value = Array.isArray(session.pipeline_details) ? session.pipeline_details : []
        pipelineThinking.value = session.pipeline_thinking || ''
      pipelineEvalResult.value = session.pipeline_eval_result || null
        const stage = session.pipeline_stage
        const msg = session.pipeline_message
        const prog = session.pipeline_progress ?? 0
        updateGenerationProgressUI(stage, msg, prog)
        if (session.status === 'completed' || session.status === 'failed') {
          const pr = session.pipeline_result
          const lastIter = pr?.iterations?.[pr.iterations.length - 1]
          const es = lastIter?.eval_score
          const finalScore = es ? Math.round(
            (es.executability || 0) * 0.25 + (es.authenticity || 0) * 0.25 +
            (es.completeness || 0) * 0.2 + (es.relevance || 0) * 0.2 +
            (es.format_quality || 0) * 0.1
          ) : null
          if (session.status === 'completed') {
            genProgress.value = 100
            genSteps.value.forEach(s => s.status = 'done')
          } else {
            pipelineMessage.value = pr?.error || msg || stage || 'Build failed'
          }
          genResult.value = {
            status: session.status,
            session_id: sessionId.value,
            skill_id: pr?.tool_id ?? null,
            spec: session.spec ?? null,
            success: session.status === 'completed',
            total_rounds: pr?.total_rounds ?? 0,
            total_time: pr?.total_time ?? 0,
            final_score: finalScore,
            error: pr?.error ?? null,
          }
          if (session.status === 'completed') prepareGeneratedTestPanel()
          wizardStep.value = 3
          return
        }
        setTimeout(poll, pollInterval)
      }
      setTimeout(poll, pollInterval)
    } else if (res.status === 'failed' && res.interface_preflight) {
      // External interface preflight interception: Stay on the confirmation page to correct the interface specifications without entering the generation process
      interfacePreflight.value = res.interface_preflight
      wizardStep.value = 1
      ElMessage.error(res.message || 'External interface preflight failed, code generation has been blocked')
    } else {
      genProgress.value = 100
      genSteps.value.forEach(s => s.status = 'done')
      genResult.value = res
      if (res.success) prepareGeneratedTestPanel()
      wizardStep.value = 3
    }
  } catch (e: any) {
    genResult.value = {
      status: 'failed', session_id: sessionId.value, skill_id: null,
      spec: null, success: false, total_rounds: 0, total_time: 0,
      final_score: null, error: e?.message || 'Build failed'
    }
    wizardStep.value = 3
  } finally {
    specConfirmLoading.value = false
  }
}

const handleRepairAndRegenerate = async () => {
  if (!sessionId.value || !repairFeedback.value.trim() || !canConfirmRepair.value) return
  repairing.value = true
  try {
    await skillGenerationApi.repairSession(
      sessionId.value,
      repairFeedback.value.trim(),
      repairPlan.value.trim(),
      codegenTimeout.value,
    )
    wizardStep.value = 2
    genProgress.value = 0
    pipelineMessage.value = 'Correction plan confirmed and being regenerated...'
    genResult.value = null
    genSteps.value.forEach(s => s.status = 'pending')
    pipelineDetails.value = []
    pipelineThinking.value = ''
    pipelineEvalResult.value = null
    sessionPipelineResult.value = null
    repairPlan.value = ''
    repairPlanFeedback.value = ''

    const pollInterval = 1500
    const poll = async () => {
      const session = await skillGenerationApi.getSession(sessionId.value)
      sessionPipelineResult.value = (session.pipeline_result || null) as PipelineResultDetail | null
      pipelineDetails.value = Array.isArray(session.pipeline_details) ? session.pipeline_details : []
      pipelineThinking.value = session.pipeline_thinking || ''
      pipelineEvalResult.value = session.pipeline_eval_result || null
      const stage = session.pipeline_stage
      const msg = session.pipeline_message
      const prog = session.pipeline_progress ?? 0
      updateGenerationProgressUI(stage, msg, prog)

      if (session.status === 'completed' || session.status === 'failed') {
        const pr = session.pipeline_result as PipelineResultDetail | null
        const lastIter = pr?.iterations?.[pr.iterations.length - 1]
        const score = lastIter?.eval_score
        const finalScore = typeof score?.total === 'number' ? score.total : null
        if (session.status === 'completed') {
          genProgress.value = 100
          genSteps.value.forEach(s => s.status = 'done')
        } else {
          pipelineMessage.value = pr?.error || msg || stage || 'Build failed'
        }
        genResult.value = {
          status: session.status,
          session_id: sessionId.value,
          skill_id: pr?.tool_id ?? null,
          spec: session.spec ?? null,
          success: session.status === 'completed',
          total_rounds: pr?.total_rounds ?? 0,
          total_time: pr?.total_time ?? 0,
          final_score: finalScore,
          error: pr?.error ?? null,
        }
        if (session.status === 'completed') prepareGeneratedTestPanel()
        wizardStep.value = 3
        return
      }
      setTimeout(poll, pollInterval)
    }

    setTimeout(poll, 1500)
  } catch (e: any) {
    ElMessage.error(e?.message || 'Regeneration failed')
  } finally {
    repairing.value = false
  }
}

const runGeneratedSkillTest = async () => {
  if (!generatedSkillId.value) return
  generatedTestLoading.value = true
  generatedTestResult.value = null
  try {
    const args: Record<string, any> = {}
    for (const p of generatedTestParams.value) {
      let value = generatedTestArgs.value[p.name]
      if (value === '' || value === undefined) value = p.default
      if (p.type === 'integer' || p.type === 'int') args[p.name] = value != null ? Number(value) : undefined
      else if (p.type === 'float' || p.type === 'number') args[p.name] = value != null ? Number(value) : undefined
      else if (p.type === 'boolean' || p.type === 'bool') args[p.name] = !!value
      else args[p.name] = value
    }
    for (const [key, value] of Object.entries(generatedTestDefaults.value || {})) {
      if (!(key in args) || args[key] === undefined || args[key] === '') args[key] = value
    }
    generatedTestResult.value = await skillGenerationApi.testSkill(generatedSkillId.value, args)
  } catch (e: any) {
    generatedTestResult.value = {
      success: false,
      output: null,
      stdout: '',
      stderr: '',
      execution_time: 0,
      error: e?.message || 'Test request failed',
    }
  } finally {
    generatedTestLoading.value = false
  }
}

const handlePreviewRepairPlan = async () => {
  if (!sessionId.value || !repairFeedback.value.trim()) return
  repairPlanning.value = true
  try {
    const res = await skillGenerationApi.previewRepairSession(sessionId.value, repairFeedback.value.trim())
    repairPlan.value = res.ai_message || ''
    repairPlanFeedback.value = repairFeedback.value.trim()
  } catch (e: any) {
    ElMessage.error(e?.message || 'Failed to generate remediation plan')
  } finally {
    repairPlanning.value = false
  }
}

onMounted(async () => {
  await loadStockDataCatalog()
  await loadExternalDataSourceCatalog()
  initIterateMode()
  initFromRoute()
})
</script>

<style lang="scss" scoped>
.skill-create-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  min-height: 500px;
  padding: 16px 24px;
  background: var(--el-bg-color-page);
}

.iterate-notice {
  margin-bottom: 16px;

  p {
    margin: 4px 0;
    font-size: 14px;
  }

  .tool-id {
    color: var(--el-text-color-secondary);
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
  }
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  margin-bottom: 16px;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;

    .header-divider {
      color: var(--el-border-color);
      font-size: 14px;
    }

    h1 {
      font-size: 18px;
      margin: 0;
      font-weight: 600;
    }
  }
}

.steps-bar {
  flex-shrink: 0;
  margin-bottom: 20px;
  padding: 12px 24px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  padding: 20px;
  overflow: hidden;
}

/* ========== Requirements communication (full screen use) ========== */
.wizard-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  margin-bottom: 12px;
}

.handoff-card {
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid #d7e3f7;
  background: linear-gradient(135deg, #f7fbff 0%, #eef5ff 100%);
}

.handoff-title {
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #1f3b63;
}

.handoff-text {
  font-size: 14px;
  color: #30445f;
  line-height: 1.7;
}

.handoff-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  font-size: 13px;
  color: #58708f;
}

.handoff-note {
  margin-top: 8px;
  font-size: 13px;
  color: #405a7d;
  line-height: 1.6;
}

/* Instructions for submitting requirements */
.requirement-guide {
  padding: 24px 20px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.7;

  .guide-header {
    text-align: center;
    margin-bottom: 24px;

    .guide-icon {
      font-size: 48px;
      color: var(--el-color-primary);
      margin-bottom: 12px;
    }

    h3 {
      font-size: 18px;
      margin: 0 0 8px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    .guide-desc {
      margin: 0;
      color: var(--el-text-color-secondary);
      font-size: 14px;
    }
  }

  .guide-quick-examples {
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 20px;

    .quick-label {
      font-weight: 500;
      margin-bottom: 8px;
      color: var(--el-text-color-primary);
    }

    .example-list {
      margin: 0;
      padding-left: 20px;
      color: var(--el-text-color-secondary);

      li {
        margin-bottom: 4px;
        font-style: italic;
      }
    }
  }

  .guide-footer {
    text-align: center;
    margin: 0;
    font-size: 13px;
    color: var(--el-text-color-placeholder);

    kbd {
      display: inline-block;
      padding: 2px 6px;
      font-size: 12px;
      background: var(--el-fill-color);
      border: 1px solid var(--el-border-color);
      border-radius: 4px;
      font-family: inherit;
    }
  }
}

.chat-msg {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;

  &.chat-user { flex-direction: row-reverse; }

  .msg-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: var(--el-color-primary-light-8);
    color: var(--el-color-primary);
    font-size: 18px;
  }

  &.chat-user .msg-avatar {
    background: var(--el-color-success-light-8);
    color: var(--el-color-success);
  }

  .msg-bubble {
    max-width: 75%;
    padding: 12px 16px;
    border-radius: 12px;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-lighter);
    line-height: 1.7;
    font-size: 14px;

    &.thinking {
      color: var(--el-text-color-secondary);
      font-style: italic;
    }
  }

  &.chat-user .msg-bubble {
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-7);
  }
}

.msg-text {
  :deep(p) { margin: 0 0 6px; }
  :deep(ul), :deep(ol) { margin: 6px 0; padding-left: 24px; }
  :deep(table) {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
    th, td { border: 1px solid var(--el-border-color); padding: 8px 12px; }
    th { background: var(--el-fill-color-light); }
  }
}

.dot-animation span {
  animation: blink 1.4s infinite both;
  &:nth-child(2) { animation-delay: 0.2s; }
  &:nth-child(3) { animation-delay: 0.4s; }
}
@keyframes blink { 0%, 80%, 100% { opacity: 0; } 40% { opacity: 1; } }

.boundary-alert {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.boundary-collapsible {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
  overflow: hidden;
}

.boundary-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 14px;
  color: var(--el-color-warning-dark-2);
  &:hover { background: var(--el-color-warning-light-8); }

  .boundary-icon { font-size: 18px; color: var(--el-color-warning); }
  .boundary-chevron {
    margin-left: auto;
    transition: transform 0.2s;
    &.expanded { transform: rotate(180deg); }
  }
}

.boundary-content {
  padding: 0 12px 12px 36px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.chat-input-area {
  flex-shrink: 0;
}

.chat-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;

  .tip { color: var(--el-text-color-placeholder); font-size: 12px; }
}

/* ========== Specification confirmation ========== */
.wizard-spec-confirm {
  flex: 1;
  min-height: 0;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow-y: auto;
  padding: 24px;
}
.spec-confirm-card {
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
  padding: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.spec-confirm-card h3 {
  margin: 0 0 16px;
  font-size: 16px;
}

.handoff-inline-note {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f6f8fc;
  color: #52627a;
  font-size: 13px;
  line-height: 1.6;
}

.spec-params-section {
  margin-top: 16px;
}
.spec-params-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.spec-boundary-warn {
  margin-top: 16px;
}

.spec-catalog-card {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
}

.spec-recommendation-card {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-color-primary-light-9), var(--el-bg-color));
}

.spec-recommendation-card-highlight {
  box-shadow: 0 0 0 2px var(--el-color-warning-light-5), 0 10px 24px rgba(0, 0, 0, 0.08);
  transition: box-shadow 0.3s ease;
}

.recommendation-grid {
  display: grid;
  gap: 14px;
  margin-top: 12px;
}

.recommendation-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.recommendation-block {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.recommendation-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.recommendation-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.recommendation-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

.spec-catalog-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;

  h4 {
    margin: 0;
    font-size: 15px;
  }

  p {
    margin: 6px 0 0;
    color: var(--el-text-color-secondary);
    line-height: 1.6;
    font-size: 13px;
  }
}

.catalog-summary {
  margin: 12px 0 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.catalog-match-summary {
  margin-top: 10px;
  font-size: 13px;
  color: var(--el-color-primary);
  font-weight: 500;
}

.catalog-collection-list {
  display: grid;
  gap: 16px;
}

.catalog-collection-card {
  padding: 16px;
  border-radius: 10px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
}

.catalog-collection-card-recommended {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-8) inset;
}

.catalog-collection-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.catalog-collection-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  flex-shrink: 0;
  justify-content: flex-end;
}

.catalog-collection-title {
  font-size: 15px;
  font-weight: 600;
}

.catalog-match-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 500;
}

.catalog-collection-purpose {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.catalog-field-table {
  margin-top: 12px;
}

.catalog-notes {
  margin-top: 12px;
  display: grid;
  gap: 8px;
}

.catalog-note-item {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.tool-trace-card {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
}

.tool-trace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.tool-trace-body {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  word-break: break-word;
}

.tool-trace-error {
  color: var(--el-color-danger);
}

.interface-spec-list {
  margin-top: 10px;
}

.interface-spec-item {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  background: var(--el-color-success-light-9, #f0f9eb);
  border-left: 3px solid var(--el-color-success);
  padding: 8px 10px;
  border-radius: 4px;
  margin-top: 6px;
  word-break: break-all;
  color: var(--el-text-color-primary);
}

.spec-confirm-actions {
  margin-top: 20px;
  padding-bottom: 8px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.spec-confirm-actions-highlight {
  padding: 12px;
  border-radius: 10px;
  background: var(--el-color-success-light-9);
  box-shadow: 0 0 0 2px var(--el-color-success-light-5);
  transition: box-shadow 0.3s ease, background 0.3s ease;
}

.spec-preflight-card {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-color-warning-light-9), var(--el-bg-color));
}

.preflight-grid {
  display: grid;
  gap: 14px;
  margin-top: 12px;
}

.preflight-notes {
  display: grid;
  gap: 8px;
}

.done-context-card {
  margin: 20px auto 0;
  max-width: 760px;
  padding: 18px;
  border: 1px solid var(--el-color-success-light-5);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-color-success-light-9), var(--el-bg-color));
}

/* ========== Build progress ========== */
.wizard-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;

  .gen-status {
    text-align: center;
    h3 { margin: 16px 0 8px; font-size: 18px; }
    .gen-desc { color: var(--el-text-color-secondary); font-size: 14px; }
  }
}

  .gen-detail-panel {
    margin: 24px auto 0;
    max-width: 760px;
    text-align: left;
    background: #f6f8fb;
    border: 1px solid #d9e2f2;
    border-radius: 14px;
    padding: 16px 18px;
  }

  .gen-detail-title {
    font-size: 14px;
    font-weight: 700;
    color: #244a7c;
    margin-bottom: 10px;
  }

  .gen-detail-item {
    color: var(--el-text-color-regular);
    font-size: 13px;
    line-height: 1.7;
  }

.gen-spinner { animation: spin 1.5s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.gen-steps {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 24px;
  margin-top: 24px;
}

.thinking-panel {
  max-width: 680px;
  margin: 20px auto 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
  overflow: hidden;
  text-align: left;
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  user-select: none;
}

.thinking-arrow {
  transition: transform 0.2s ease;
}

.thinking-arrow.collapsed {
  transform: rotate(-90deg);
}

.thinking-body {
  margin: 0;
  max-height: 260px;
  overflow-y: auto;
  padding: 10px 14px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.eval-result-panel {
  max-width: 680px;
  margin: 12px auto 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 12px 16px;
  text-align: left;
}

.eval-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 10px;
}

.eval-total.pass {
  color: var(--el-color-success);
}

.eval-total.fail {
  color: var(--el-color-danger);
}

.eval-dimensions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.eval-dim {
  display: flex;
  align-items: center;
  gap: 10px;
}

.eval-dim-label {
  width: 60px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.eval-dim-bar {
  flex: 1;
}

.eval-dim-score {
  width: 32px;
  text-align: right;
  font-size: 12px;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}

.eval-comment {
  margin-top: 10px;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.eval-business-fail {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-color-danger);
}

.gen-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--el-text-color-secondary);

  &.done { color: var(--el-color-success); }
  &.running { color: var(--el-color-primary); font-weight: 500; }
}

/* ========== Complete ========== */
.wizard-done {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  padding: 40px;
  overflow-y: auto;
  overflow-x: hidden;
}

.test-run-card {
  margin: 20px auto 0;
  max-width: 760px;
  width: 100%;
  padding: 18px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-color-primary-light-9), var(--el-bg-color));
}

.test-run-form {
  margin-top: 12px;
}

.test-run-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.test-run-result {
  margin-top: 18px;
}

.test-run-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.test-run-pre {
  margin: 0;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.6;
}

.test-run-error {
  color: var(--el-color-danger);
}

.test-params-empty {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.repair-card {
  margin: 20px auto 0;
  max-width: 760px;
  padding: 18px;
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-color-danger-light-9), var(--el-bg-color));
}

.repair-summary-list {
  display: grid;
  gap: 8px;
  margin: 14px 0;
}

.repair-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.repair-timeout-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0;
}

.repair-timeout-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.repair-timeout-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.repair-plan-card {
  margin-top: 16px;
  padding: 16px 18px;
  border-radius: 14px;
  border: 1px solid rgba(36, 99, 235, 0.18);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.92) 0%, rgba(248, 250, 252, 0.98) 100%);
}

.repair-plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.repair-plan-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e3a8a;
}

.repair-plan-stale {
  font-size: 12px;
  color: #b45309;
}

.repair-plan-markdown {
  color: #1f2937;
}
</style>
