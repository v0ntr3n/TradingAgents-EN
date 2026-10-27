# TradingAgents-CN v3.0 Real feature list

> **Verify time**: 2026-07-31
> **Verification method**: Read the code directly + Check MongoDB samples + Check front-end routing + Check the sidebar menu
> **purpose**: for [v3.0 courses](../README.md) Adapted to provide"comparison table",Make sure every feature description is well documented

## ⚠️ Important statement

There may be differences between this document and project memory.**Subject to code**. 

For example:Project memory mentioned"v3.0 Hong Kong and US stocks have been suspended",The front-end entry has actually been removed(§9),But the backend code has not been cleaned up yet(Historical baggage,Students are not visible). Curriculum rewriting should**Clearly tell users that the platform only supports A shares and ETF**. 

---

## §1 Front-end 25 top-level routes

Source: [frontend/src/router/index.ts](../../../frontend/src/router/index.ts)

| # | path | Name | Description |
|---|------|------|------|
| 1 | `/dashboard` | Dashboard | Dashboard(System home page) |
| 2 | `/guide` | Guide | Platform guidance(Getting Started) |
| 3 | `/learning` | Learning | Learning Center(Show 3 subpages) |
| 4 | `/analysis/single` | SingleAnalysis | single stock research |
| 5 | `/analysis/batch` | BatchAnalysis | Batch research |
| 6 | `/analysis/general` | GeneralAnalysis | general studies(No clear stocks) |
| 7 | `/screening` | StockScreening | stock screen |
| 8 | `/favorites` | Favorites | watchlist |
| 9 | `/assistant` | Assistant | AI Smart Assistant(Conversational) |
| 10 | `/memory` | Memory | AI memory management(Multi-topic conversation) |
| 11 | `/reports` | Reports | reporting center(Report viewing, details, Token statistics) |
| 12 | `/workflow` | Workflow | Workflow(5 submenu,see §2) |
| 13 | `/tasks/unified` | UnifiedTaskCenter | mission center(Unified version) |
| 14 | `/paper` | Paper | simulated trading |
| 15 | `/portfolio` | Portfolio | **Position**(Note:Don't bark position) |
| 16 | `/review` | Review | Review(actual call trade_review) |
| 17 | `/trading-system` | TradingSystem | trading system(Strategy) |
| 18 | `/stocks/:code` | StockDetail | Stock details page |
| 19 | `/backtest` | Backtest | backtest(The front-end entrance is offline) |
| 20 | `/settings` | Settings | settings(6 submenu,see §3) |
| 21 | `/debug/embedded-nanobot` | EmbeddedNanobotDebug | Debug page(Developers) |
| 22 | `/about` | About | About |
| 23 | `/login` | Login | Login |
| 24 | `/paper/:name.md` | PaperMdRedirect | Paper jump |
| 25 | `/:pathMatch(.*)*` | - | 404 Keep everything in mind |

## §2 Workflow submenu(5 a)

Source: [SidebarMenu.vue](../../../frontend/src/components/Layout/SidebarMenu.vue)

| path | Name | Description |
|------|------|------|
| `/workflow` | Workflow Home Page | Visual orchestration workflow |
| `/workflow/tools` | Tool management | Tool addition, deletion and modification |
| `/workflow/agent-workshop` | Agent workshop | Create custom Agent |
| `/workflow/skills` | Skill Center | Create/Manage Skill |
| `/workflow/mcp-servers` | MCP server | external tool server |

## §3 Settings submenu(11 a)

| path | Name | Description |
|------|------|------|
| `/settings` | General settings | Basic configuration |
| `/settings?tab=appearance` | Appearance settings | Theme/Layout |
| `/settings?tab=analysis` | Analyze preferences | Personal analysis default parameters |
| `/settings?tab=notifications` | Notification settings | Notification method |
| `/settings?tab=security` | Security settings | Password/2FA |
| `/settings?tab=assistant` | Assistant settings | AI Assistant configuration |
| `/settings/email` | Email configuration | SMTP settings |
| `/settings/channel-configs` | Channel push | Feishu/DingTalk/Email/Webhook |
| `/settings/watchlist-groups` | Follow group | Watch list group management |
| `/settings/scheduled-analysis` | timing analysis | Scheduled task configuration |
| `/settings/license` | Authorize(Standard Edition) | License activate(Jingdong cloud version hidden) |
| `/settings/jdyun-config` | JD Cloud configuration | Exclusively for JD Cloud Edition |
| `/settings/config` | Configuration management(Standard Edition) | LLM/Data source/system settings |
| `/settings/cache` | Cache management | Cache cleaning |
| `/settings/templates` | report template | Template management |
| `/settings/prompt-policies` | cue word strategy | Anti-injection |
| `/settings/prompt-design` | Prompt word design | Custom prompt words |
| `/settings/analysis-profiles` | Analyze portrait | Industry/stock portrait |
| `/settings/database` | Database management | MongoDB management |
| `/settings/logs` | Operation log | User operation log |
| `/settings/system-logs` | System log | System level logs |
| `/settings/sync` | Synchronization of multiple data sources | Tushare/AKShare/BaoStock sync |
| `/settings/capability-index` | Tool capability index | Tool metadata |
| `/settings/scheduler` | scheduled tasks | System-level scheduled tasks |
| `/settings/social-media` | Social media message management | Feishu/DingTalk message template |
| `/settings/data-import` | Data import | Historical data import |
| `/settings/usage` | usage statistics | Token Dosage |
| `/settings/update` | System update | System upgrade |

## §4 Backend 78 APIRouter routing modules

Source: [app/routers/](../../../app/routers/)

Classified by function(Incomplete enumeration):

| prefix | module | key endpoint |
|------|------|---------|
| `/api/agent-workshop` | agent_workshop.py | sessions/start, sessions/respond, build-version, versions/publish, prompt |
| `/api/akshare-init` | akshare_init.py | status, start-full, start-basic-sync |
| `/api/analysis-profiles` | analysis_profiles.py | industries, stocks |
| (None prefix) | analysis.py | single, batch, general, tasks, history, queue-status, cancel, retry |
| `/api/backtest` | backtest.py | analyze, generate, run, results, sessions, optimize, evaluate |
| `/api/baostock-init` | baostock_init.py | status, start-full, start-basic |
| `/api/cache` | cache.py | stats, cleanup, clear |
| `/api/channel-configs` | channel_configs.py | Add, delete, modify and check + test + event-types |
| `/config` | config.py | jdyun/status, gateway, llm/providers, datasource, system, settings |
| `/database` | database.py | MongoDB management |
| `/api/embedded-nanobot` | embedded_nanobot.py | Embedded nanorobots |
| `/favorites` | favorites.py | Add, delete, modify and check the watch list |
| `/api/financial-data` | financial_data.py | Financial data query |
| `/api/gateway` | gateway.py | Gateway configuration |
| `/api/historical-data` | historical_data.py | Historical market inquiry |
| `/api/assistant` | intelligent_assistant.py | Smart assistant conversation |
| `/api/screening/intelligent` | intelligent_screening.py | **Natural language filtering conversations** |
| `/api/internal-messages` | internal_messages.py | inside information |
| `/api/knowledge` | knowledge.py | knowledge base |
| `/api/license` | license.py | Authorization management |
| `/system-logs` | logs.py | System log |
| `/api/mcp` | mcp.py | MCP server |
| `/api/memory` | memory.py | AI memory |
| `/api/model-capabilities` | model_capabilities.py | Model capability management |
| `/markets` | multi_market_stocks.py | multi-market stocks(backend reserved,The front end is not visible) |
| `/api/multi-period-sync` | multi_period_sync.py | Multi-cycle data synchronization |
| `/api/sync/multi-source` | multi_source_sync.py | Synchronization of multiple data sources |
| `/api/news-data` | news_data.py | news data |
| `/logs` | operation_logs.py | Operation log |
| `/paper` | paper.py | simulated trading(A stock account;The backend code supports three markets,The front end is offline) |
| `/api/v1/prompt-design` | prompt_design.py | Prompt word design |
| `/api/v1/prompt-policies` | prompt_injection_policies.py | Prompt word anti-injection |
| `/api/v1/prompt-preview` | prompt_preview.py | Prompt word preview |
| `/api/quality-metrics` | quality_metrics.py | quality index |
| `/report-templates` | report_templates.py | report template |
| `/api/reports` | reports.py | Report management |
| `/api/scheduler` | scheduler.py | System level timing |
| (None prefix) | scheduled_analysis.py | User-level timing analysis |
| `/api/screening` | screening.py | Conditional filtering(Old version) |
| `/api/skill-center` | skill_center.py | Skill Management Center |
| `/api/skill-gaps` | skill_gaps.py | Skill gap analysis |
| `/api/skill-generation` | skill_generation.py | Skill Automatically generated |
| `/api/skills` | skills.py | Skills CRUD |
| `/api/social-media` | social_media.py | social media push |
| `/api/stock-data` | stock_data.py | stock data |
| `/api/stock-sync` | stock_sync.py | Stock data synchronization |
| `/stocks` | stocks.py | Basic stock information(The backend code supports three markets,The front end is offline) |
| `/api/sync` | sync.py | Sync tasks |
| (None prefix) | system_config.py | System configuration |
| `/tags` | tags.py | tag management |
| `/api/tushare-init` | tushare_init.py | Tushare initialization |
| `/api/v2/tasks` | unified_tasks.py | unified mission center |
| `/api/system/update` | update.py | System update |
| `/api/usage` | usage_statistics.py | Token usage statistics |
| (None prefix) | user_template_configs.py | User template configuration |
| (None prefix) | watchlist_groups.py | Follow group |
| `/api/v1/workflow` | workflow_api.py | Workflow API |
| `/api/workflow-generation` | workflow_generation.py | Workflow generation |
| `/api/workflow-growth` | workflow_growth.py | Workflow iteration |

## §5 Actual Structure of Single Stock Research Reports

Source: MongoDB `analysis_reports` collection(sample:CATL 300750 / Industrial and Commercial Bank of China 601398)

### Top level fields(28 a)

| Field | Type | Description |
|------|------|------|
| `_id` | ObjectId | primary key |
| `analysis_id` | str | business ID(Format `<code>_<date>_<time>`) |
| `stock_symbol` | str | Stock code(Such as 300750) |
| `stock_code` | str | Stock code(Same stock_symbol) |
| `stock_name` | str | Stock name(Such as Ningde era) |
| `market_type` | str | market type(A shares/ETF;The data table retains the Hong Kong and US stock fields,The frontend is no longer available) |
| `model_info` | str | Model used(Such as `qwen-flash/qwen-plus`) |
| `analysis_date` | date | Analysis date |
| `timestamp` | datetime | creation time |
| `status` | str | Status(`completed`/`failed`/`running`) |
| `source` | str | Source(`api`/`manual` Wait) |
| `engine` | str | Engine version(`v2`) |
| `research_depth` | str | Research depth(**string**,Such as `Standard`/`Depth`/`fast`) |
| `summary` | str(long text) | Investment summary(final trading decision) |
| `analysts` | list[str] | 7 analysts used ID(see §6) |
| `reports` | dict | 12 subreport(see §7) |
| `decision` | dict | decision-making structure(see §8) |
| `recommendation` | str(long text) | investment advice(Detailed version) |
| `confidence_score` | float | Confidence(0-1,Such as 0.76) |
| `risk_level` | str | risk level(`low`/`in`/`high`/`medium`) |
| `risk_score` | float | risk score(0-1,Such as 0.5) |
| `key_points` | list[str] | Key takeaways(array) |
| `execution_time` | float | Execution time(seconds,Such as 525.32) |
| `tokens_used` | int | Token Dosage |
| `performance_metrics` | dict | Performance indicators |
| `user_id` | str | User ID |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | Update time |
| `task_id` | str | Associated tasks ID |

## §6 7 built-in analyst role

Source: MongoDB `agent_configs` collection(filter `is_builtin=True`)

actual report `analysts` The field contains 7 ID:

| # | ID | role | Type |
|---|----|------|------|
| 1 | `market_analyst` | market analyst | analyst |
| 2 | `fundamentals_analyst` | fundamental analyst | analyst |
| 3 | `bull_researcher` | bullish researcher | researcher |
| 4 | `bear_researcher` | bearish researcher | researcher |
| 5 | `risky_analyst` | activist risk analyst | risk |
| 6 | `safe_analyst` | conservative risk analyst | risk |
| 7 | `neutral_analyst` | Neutral Risk Analyst | risk |

## §7 reports Dictionary 12 subreports

| Key | Description |
|-----|------|
| `market_report` | Market/technical analysis(MA/MACD/RSI/BOLL) |
| `fundamentals_report` | fundamental analysis(Valuation/Finance/Industry) |
| `investment_plan` | investment plan |
| `trader_investment_plan` | Trader's practical framework |
| `final_trade_decision` | final trading decision |
| `bull_researcher` | Bullish Researcher Report |
| `bear_researcher` | Bearish Researcher Report |
| `research_team_decision` | Research team decisions |
| `risky_analyst` | Aggressive Risk Analysis |
| `safe_analyst` | conservative risk analysis |
| `neutral_analyst` | neutral risk analysis |
| `risk_management_decision` | risk management decisions |

## §8 decision Field(decision-making structure,Already compliant)

> ⚠️ This table shows the structure after compliance(2026-08 update). old `target_price` / `stop_loss` / "Buy/Sell/Hold" etc fields have been removed.
> Source: [core/agents/adapters/risk_manager_v2.py](file:///c:/TradingAgentsCN/core/agents/adapters/risk_manager_v2.py) of `FinalTradeDecision` / `RiskAssessmentOutput` schema. 

| Key | Type | Description |
|-----|------|------|
| `action` | str | Decision label,**can only be `optimistic` / `Prudence` / `Neutral`**(non-trading orders) |
| `confidence` | float | Confidence(0-1) |
| `price_analysis_range` | str(Optional) | price analysis range(replace old `target_price`,**non-target price**) |
| `risk_reference_price` | str(Optional) | Risk control reference price(replace old `stop_loss`,**non-stop price**) |
| `risk_exposure_ratio` | str(Optional) | Risk exposure analysis |
| `reasoning` | str | reasoning process |
| `summary` | str | Analysis summary |
| `risk_warning` | str | Risk warning |

risk review(`risk_assessment`)Also:`risk_level`(low/medium/high), `risk_score`(0-1), `key_risks`(array), `risk_control`, `investment_adjustment`(Optimistic/cautious/neutral). 

## §9 ⚠️ Function status of Hong Kong and US stocks:The front end is offline,backend reserved

**business decisions**(2026-07-31 User confirmation):
- **All front-end entrances to Hong Kong and US stocks have been removed**,Users cannot see or use it from the UI
- **The backend code is temporarily reserved**(`foreign_stock_service.py` 2402 OK and so on),Possible reuse in the future
- **Courses should be"Hong Kong and US stocks are not available"Process**,Not introduced to students

### Front-end portal to verify status(2026-07-31)

| entrance | Hong Kong and US stock options? | Description |
|------|---------|------|
| `/analysis/single` single stock research | ❌ None | `MarketType = 'A shares' \| 'ETF'`,The front end does not include Hong Kong and US stock options |
| `/analysis/batch` Batch research | ❌ None | Same as above,`market: 'A shares' as 'A shares' \| 'ETF'` |
| `/screening` Filter | ❌ None | `<el-select v-model="basicFilters.market" disabled>`,Show only A shares |
| `/favorites` watchlist | ❌ Cleaned | Only A shares optional |
| `/paper` simulated trading | ❌ Cleaned | A-share account only |
| Sidebar menu | ❌ No relevant entrance | see §1 routing table |
| Dashboard card | ❌ No relevant entrance | Only A-share entrance |

### Backend code retained(The course does not need to cover)

- ⚠️ `multi_market_stocks.py` API The endpoint is still(CN/HK/US Three market searches)
- ⚠️ `foreign_stock_service.py` 2402 OK
- ⚠️ `paper.py` Simulated trading routing supports three market accounts
- ⚠️ `hk_sync_service.py` Hong Kong stock data synchronization
- ⚠️ `market_categories` collection `us_stocks` / `hk_stocks` Still `enabled=True`

**These backend codes are not visible to students,Courses should not cover**. If you need to clean up the backend code in the future,That's another engineering task.

### Impact of curriculum rewriting

- ❌ **lesson-10 simulated trading**:Do not write Hong Kong and US stock accounts(In the original course, I misjudged that I should keep Hong Kong and US stocks.)
- ❌ **lesson-04 Multiple scenarios**:Delete"5 kind of situation",explain instead"2 role debate(Optimistic/cautious)+ 1 integrator"
- ❌ **lesson-03 single stock research**:Example stock uses A share code(Such as 600519/601919)
- ✅ **Courses should clearly tell users**:"The platform only supports A-share and ETF fund analysis"

## §10 Complete list of built-in Agents(20+)

Source: MongoDB `agent_configs` collection

### analyst Category(15 a)
- Market Analyst/Market Analyst v2
- fundamental analyst
- news analyst
- social media analyst
- Industry/sector analyst
- Market/Index Analyst
- timing analyst
- Position Analyst
- sentiment analyst
- attribution analyst
- Review summary expert
- Position Technical Analyst
- Fundamental Analyst
- Position risk assessor
- technical analyst v2.0
- risk assessor v2.0

### researcher Category(4 a)
- bullish researcher / bullish researcher v2.0
- bearish researcher / bearish researcher v2.0

### trader Category(3 a)
- trader / trader v2.0
- Position Analyst

### risk Category(6 a)
- Activist Risk Analyst / Activist Risk Analyst v2.0
- Conservative Risk Analyst / Conservative Risk Analyst v2.0
- Neutral Risk Analyst / Neutral Risk Analyst v2.0

### manager Category(5 a)
- risk manager
- research manager
- Position operation advisor
- Operational advisor v2.0

### post_processor Category(3 a)
- report saver
- Email Notifier
- System Notifier

## §11 Data collection list(48 a)

Source: MongoDB `db.list_collection_names()`

| collection | Number of documents | Description |
|------|--------|------|
| `users` | 1 | User table |
| `user_sessions` | 0 | session table |
| `user_favorites` | 3 | User watchlist |
| `user_tags` | 2 | User tag |
| `user_template_configs` | 48 | User template configuration |
| `watchlist_groups` | 1 | Follow group |
| `analysis_reports` | 2 | analysis report |
| `analysis_tasks` | 1 | Analysis tasks(Old version) |
| `unified_analysis_tasks` | 1 | unified mission(new version) |
| `scheduled_analysis_configs` | 1 | Timing analysis configuration |
| `paper_accounts` | 5 | Demo account |
| `paper_market_rules` | 3 | Simulate market rules |
| `real_accounts` | 1 | real account |
| `trading_systems` | 2 | trading system strategy |
| `workflows` | 1 | Workflow definition |
| `workflow_history` | 0 | Workflow execution history |
| `agent_configs` | 47 | Agent Configuration |
| `tool_agent_bindings` | 38 | Tool-Agent Binding |
| `tool_configs` | 1 | Tool configuration |
| `model_catalog` | 12 | Model catalog |
| `llm_providers` | 11 | LLM supplier |
| `platform_configs` | 4 | Platform configuration |
| `system_configs` | 38 | System configuration(plural) |
| `system_config` | 1 | System configuration(singular) |
| `prompt_templates` | 146 | prompt word template |
| `stock_basic_info` | 16578 | Basic stock information |
| `stock_screening_view` | 16578 | Stock Screener View |
| `stock_daily_quotes` | 484 | Daily market price |
| `stock_news` | 60 | stock news |
| `stock_financial_data` | 2 | financial data |
| `market_quotes` | 5548 | Real-time quotes(A shares) |
| `market_categories` | 3 | Market classification(A/HK/US) |
| `sync_status` | 1 | Sync status |
| `quotes_ingestion_status` | 1 | Market storage status |
| `token_usage` | 15 | Token Usage record |
| `notifications` | 1 | Notification |
| `operation_logs` | 102 | Operation log |
| `capital_transactions` | 1 | Capital flow |
| `datasource_groupings` | 11 | Data source grouping |
| `smtp_config` | 1 | SMTP Email configuration |
| `license_cache` | 1 | License cache |
| `scheduler_metadata` | 1 | Scheduling metadata |
| `system.views` | 1 | MongoDB View metadata |

## §12 Trading system collection structure

Source: MongoDB `trading_systems` collection(sample:Short-term trend tracking system / mid-term value growth system)

| Field | Type | Description |
|------|------|------|
| `name` | str | System name |
| `description` | str | Description |
| `style` | str | **style**(`short_term` / `medium_term` / `long_term`) |
| `risk_profile` | str | risk profiling(`aggressive` / `balanced` / `conservative`) |
| `stock_selection` | dict(2) | Stock picking method |
| `timing` | dict(1) | timing judgment |
| `position` | dict(3) | Position management |
| `holding` | dict(3) | Position management |
| `risk_management` | dict(2) | risk management |
| `review` | dict(2) | Review |
| `discipline` | dict(2) | discipline |
| `version` | str | version number |
| `is_active` | bool | Whether to activate |

**Impact on the curriculum**:
- ✅ in course"Short/medium and long term"The distinction is supported by real data(`style` Field)
- There are actually 3 styles: `short_term` / `medium_term` / `long_term`(Not just 2 types)

## §13 focus:All new v3.0 features that users can find

Route via frontend + backend API + MongoDB collection,New v3.0 features recognized by the system(Contrast v2.x):

| # | Function | path/module | v3.0 New? |
|---|------|----------|------------|
| 1 | **Natural language stock picking** | `/api/screening/intelligent/chat` | ✅ |
| 2 | **AI Smart Assistant(Conversational)** | `/assistant` | ✅ |
| 3 | **AI memory(Multi-topic conversation)** | `/memory` | ✅ |
| 4 | **general studies(No clear stocks)** | `/analysis/general` | ✅ |
| 5 | **MCP server** | `/api/mcp` | ✅ |
| 6 | **Agent workshop** | `/workflow/agent-workshop` | ✅ |
| 7 | **Skill Center** | `/api/skill-center` | ✅ |
| 8 | **Skill Automatically generated** | `/api/skill-generation` | ✅ |
| 9 | **AI workflow architect** | `/api/workflow-generation` | ✅ |
| 10 | **Synchronization of multiple data sources** | `/api/sync/multi-source` | ✅ |
| 11 | **Multi-cycle synchronization** | `/api/multi-period-sync` | ✅ |
| 12 | **Analyze portrait** | `/api/analysis-profiles` | ✅ |
| 13 | **report template** | `/report-templates` | ✅ |
| 14 | **Prompt word design** | `/api/v1/prompt-design` | ✅ |
| 15 | **Prompt word anti-injection strategy** | `/api/v1/prompt-policies` | ✅ |
| 16 | **unified mission center** | `/tasks/unified` | ✅ |
| 17 | **unified reporting center** | `/reports` | ✅ |
| 18 | **Token statistics** | `/reports/token` | ✅ |
| 19 | **Channel push(Feishu/DingTalk/Email/Webhook)** | `/api/channel-configs` | ✅ |
| 20 | **Take Profit Alert** | `/api/stop-gain-alerts`(To be confirmed) | ✅ |
| 21 | **backtest** | `/backtest` | ❌ The front-end entrance is offline |
| 22 | **Embedded nanorobots** | `/api/embedded-nanobot` | ✅ |
| 23 | **Tool capability index** | `/api/capability-index` | ✅ |
| 24 | **System update** | `/api/system/update` | ✅ |
| 25 | **Use the Q&A Assistant** | (Floating window in lower right corner) | ✅ |

## §14 Things that need to be checked when rewriting the course"Easy to make mistakes"

1. **Multiple scenario analysis**: ❌ No"Optimistic/Baseline/Crudent/Highly Resilient/Defensive"5 scene. Actually **2 role debate(Optimistic/cautious)+ 1 integrator** + **3 risk perspective(High resiliency/defense/baseline)**,Finally, the risk assessor comprehensively outputs decision(`action` ∈ {Optimistic/cautious/neutral})
2. **Confidence**: ✅ exist correctly `confidence_score` Field(0-1)
3. **AI Rating**: ❌ No"AI Overall rating 0-100". Actually `confidence_score` (0-1) and `risk_score` (0-1)
4. **risk level**: ✅ Yes `risk_level` Field(string:"low"/"in"/"high"/"medium")
5. **Target Price/Stop Loss**: ❌ Removed for compliance. decision no more `target_price`/`stop_loss`,Change to optional `price_analysis_range`(price analysis range) and `risk_reference_price`(Risk reference price),and clear"It is prohibited to give a specific target price or stop loss price"
6. **Position analysis**: ✅ There are 4 dedicated Agent(Position technical aspects/fundamentals/risk assessment/operation suggestions)
7. **Review**: ✅ Yes `/review` routing,backend `trade_review_service.py` 3618 OK
8. **backtest**: ⚠️ The backend has `/backtest` routing and `/api/backtest` API Residue,But the front-end entrance is offline,Product not provided
9. **Watchlist grouping**: ✅ Yes `watchlist_groups` collection,Available at `/settings/watchlist-groups` management
10. **timing analysis**: ✅ Yes `scheduled_analysis_configs` collection
11. **Natural language filtering**: ✅ Yes `/api/screening/intelligent/chat` API,There is an entry in Dashboard

## §15 Mapping of course stages and real functions

| course stage | The real function that should be used |
|---------|-----------------|
| **stage 1:discover** | Natural language filtering(`/api/screening/intelligent/chat`) + Conditional filtering(`/screening`) + Batch analysis(`/analysis/batch`) + single stock research(`/analysis/single`) |
| **stage 2:Track** | general studies(`/analysis/general`) + timing analysis(`/settings/scheduled-analysis`) + watchlist(`/favorites`) + Follow group(`/settings/watchlist-groups`) + Channel push(`/settings/channel-configs`) |
| **stage 3:Position** | simulated trading(`/paper`) + Position(`/portfolio`) + 4 positions Agent(Technical/Fundamentals/Risk/Operation Suggestions) |
| **stage 4:Review** | Review(`/review`) + Case library(`trade_review_service.py`) + attribution analyst |
| **stage 5:short term** | trading system `/trading-system` of `short_term` style |
| **stage 6:Medium and long term** | trading system `/trading-system` of `medium_term` / `long_term` style |
| **stage 7:Platform extension** | AI workflow architect(`/api/workflow-generation`) + Agent workshop(`/workflow/agent-workshop`) + Skill Center(`/workflow/skills`) + Skill Automatically generated(`/api/skill-generation`) |
| **stage 8:personal plan** | trading system(`/trading-system`) + AI Assistant(`/assistant`) + AI memory(`/memory`) |

---

> **last updated**: 2026-07-31
> **Supporting documents**: [v3.0 courses README](../README.md) | [Course Deviation Checklist](../../06-knowledge/course-v3-deviation-list-2026-07-31.md)
