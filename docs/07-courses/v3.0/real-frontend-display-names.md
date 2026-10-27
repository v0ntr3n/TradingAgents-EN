# v3.0 Course field name/term verification reference

> **purpose**:Record in the front-end code**true**Field display name/term for,Serve as a reference for course revision.
> **Source**:Actual front-end code(`frontend/src/views/Reports/ReportDetail.vue` Wait)
> **Maintenance principles**:The content of this document must**Found from the code**,**No relying on memory/guessing**Write.

## 1. Batch analysis page"Analysis depth"drop down item

Source: [BatchAnalysis.vue:139-158](file:///c:/TradingAgentsCN/frontend/src/views/Analysis/BatchAnalysis.vue#L139-L158)

| gear | Page drop-down display name(What users see) |
|------|------------------|
| 1 | ⚡ **1 Level - Quick Analysis**(2-4 minutes/only) |
| 2 | 📈 **2 Level - Basic Analysis**(4-6 minutes/only) |
| 3 | 🎯 **3 Level - Standard Analysis**(6-10 minutes/only)⭐ |
| 4 | 🔍 **4 Level - In-Depth Analysis**(10-15 minutes/only) |
| 5 | 🏆 **5 Level - Comprehensive Analysis**(15-25 minutes/only) |

## 2. Batch analysis page"Analyst Team"Checkable roles(only 7)

Source: [analysts.ts:13-59](file:///c:/TradingAgentsCN/frontend/src/constants/analysts.ts#L13-L59)

| Page display name | actual ID | Description |
|---------|---------|------|
| 📈 market analyst | `market` | Analyze individual stock price trends and technical indicators(Moving Average/MACD/RSI/Bollinger Bands) |
| 💰 fundamental analyst | `fundamentals` | Analyze company financial condition, business model and competitive advantages |
| 📰 news analyst | `news` | Analyze the impact of relevant news, announcements and market events |
| 💬 social media analyst | `social` | Analyze social media sentiment, investor psychology and public opinion guidance |
| 📊 Market Analyst | `index_analyst` | Analyze market index trends, market environment and systemic risks |
| 🏭 Sector Analyst | `sector_analyst` | Analyze industry trends, sector rotations and peer comparisons |
| ETF analyst | `etf` | Optional only for ETF market,Analyze ETF net worth, tracking error, and position structure |

**System checked by default**:["market analyst", "fundamental analyst"](see [analysts.ts:65](file:///c:/TradingAgentsCN/frontend/src/constants/analysts.ts#L65))

## 3. Report module page tab name(in the report"Detailed research report"card)

Source: [ReportDetail.vue:286-312](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L286-L312)

| backend key | Page Tab display name(with icon) |
|---------|------------------|
| `index_report` | 📊 Market Analyst |
| `sector_report` | 🏭 Sector Analyst |
| `market_report` | 📈 market analyst |
| `sentiment_report` | 💬 social media analyst |
| `news_report` | 📰 news analyst |
| `fundamentals_report` | 💰 fundamental analyst |
| `bull_researcher` | 🐂 Optimistic Scenario Researcher |
| `bull_report` | 🐂 Optimistic Scenario Study |
| `bear_researcher` | 🐻 Prudential Scenario Researcher |
| `bear_report` | 🐻 Prudential Scenario Study |
| `research_team_decision` | 🔬 research integrator |
| `trader_investment_plan` | 🧩 research integrator |
| `risky_analyst` | ⚡ Highly Resilient Scenario Analyst |
| `risky_opinion` | ⚡ Highly elastic scenario research observations |
| `safe_analyst` | 🛡️ Defense Scenario Analyst |
| `safe_opinion` | 🛡️ Defense Scenario Research Observations |
| `neutral_analyst` | ⚖️ Baseline Scenario Analyst |
| `neutral_opinion` | ⚖️ Baseline Scenario Research Observations |
| `risk_management_decision` | 👔 risk assessor |
| `risk_assessment` | ⚠️ risk review |
| `investment_plan` | 🧾 research brief |
| `final_trade_decision` | 🧾 Comprehensive research conclusion |
| `investment_debate_state` | 🔬 Research team analysis(old) |
| `risk_debate_state` | ⚖️ Risk team analysis(old) |
| `detailed_analysis` | 📄 Detailed analysis |

## 4. Agent top analyst list display name in the report

Source: [ReportDetail.vue:235-284](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L235-L284)

| backend key | Page display name(Top Analyst List) |
|---------|----------------------|
| `index_analyst` / `index_analyst_v2` | Market Analyst |
| `sector_analyst` / `sector_analyst_v2` | Sector Analyst |
| `market_analyst` / `market_analyst_v2` / `market` / `technical` | market analyst |
| `fundamentals_analyst` / `fundamentals_analyst_v2` / `fundamentals` | fundamental analyst |
| `etf_analyst` / `etf_analyst_v2` / `etf` | ETF analyst |
| `news_analyst` / `news_analyst_v2` / `news` | news analyst |
| `social_analyst` / `social_analyst_v2` / `social` / `sentiment` | social media analyst |
| `bull_researcher` / `bull_researcher_v2` / `multi-investigator` | Optimistic Scenario Researcher |
| `bear_researcher` / `bear_researcher_v2` / `short researcher` | Prudential Scenario Researcher |
| `research_manager` / `research_manager_v2` | research manager |
| `trader` / `trader_v2` | research integrator |
| `risky_analyst` / `risky_analyst_v2` / `activist analyst` | Highly Resilient Scenario Analyst |
| `safe_analyst` / `safe_analyst_v2` / `conservative analyst` | Defense Scenario Analyst |
| `neutral_analyst` / `neutral_analyst_v2` / `neutral analyst` | Baseline Scenario Analyst |
| `risk_manager` / `risk_manager_v2` | risk assessor |

**Note**:
- Report top analyst list(No icon) ≠ Report Tab List(with icon). Same one Agent,The label at the top is"market analyst",Tab tag is"📈 market analyst". 
- "Optimistic Scenario Researcher"and"🐂 Optimistic Scenario Researcher"Yes**Unified display name of the same Agent in different locations**(top and Tab). 

## 5. Risk assessment JSON fields(in the report"risk review" Tab rendering)

Source: [ReportDetail.vue:707-745](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L707-L745)

| backend key | Page display label(What users see) |
|---------|----------|
| `risk_level` | **risk level** |
| `risk_score` | **risk score** |
| `reasoning` / `conclusion` / `summary` / `assessment` | **Assessment conclusion** |
| `key_risks` (array) | **core risk**(to `-` List rendering) |
| `risk_control` / `control` / `suggestions` | **Risk control suggestions** |
| `investment_adjustment` / `adjustment` | **Investment adjustment suggestions** |

## 6. in position analysis"action tag"mapping

Source: [PositionAnalysisDetailDialog.vue:235-244](file:///c:/TradingAgentsCN/frontend/src/views/Portfolio/components/PositionAnalysisDetailDialog.vue#L235-L244)

| Backend return value | Page display(What users see) |
|---------|---------|
| `optimistic` | optimistic |
| `Prudence` | Prudence |
| `Neutral` | Neutral |
v3.0 Position studies use the same 3 decision tags as single stock studies(Optimistic/cautious/neutral), no more"Long/short/to be verified"Wait for additional tags.

## 7. Stock screening page(Screening/index.vue)Field

### 7.1 Smart filtering Tab

- Page title:"stock screen"
- Page description:"By default, it guides you through intelligent dialogue to complete stock selection.;Only if granular manual configuration is required,Enter advanced mode again"
- two Tab:**Smart filtering** / **Advanced mode**(The default is"Smart filtering")
- Left panel title:"Filter history"(subtitle:"View previous smart filter records by session"),bring"New"button
- Smart filtering confirmation action button:"Filter by original requirements" / "Filter after taking suggestions" / "Execute screening plan" / "Re-describe requirements"

### 7.2 Advanced mode Tab ——"Common conditions"District(8 are displayed by default)

Source: [Screening/index.vue:267-403](file:///c:/TradingAgentsCN/frontend/src/views/Screening/index.vue#L267-L403)

| Field labels(What users see) | actual field | Type |
|---------|---------|------|
| **Stock code/name** | `keyword` | Text input |
| **Industry classification** | `industry` | Multiple selection drop-down |
| **market type** | `market` | drop down(Fixed as A shares,disabled) |
| **market capitalization range** | `total_mv` | drop down(Small Cap/Mid Cap/Large Cap) |
| **P/E ratio (PE)** | `pe` | range input(min-max) |
| **price to book ratio (PB)** | `pb` | range input |
| **Increase or decrease** | `pct_chg` | range input |
| **Volume** | `amount` | drop down(active/normal/light) |

### 7.3 Advanced mode Tab ——"Advanced fields"District(Need to be added manually)

Source: [Screening/index.vue:406-547](file:///c:/TradingAgentsCN/frontend/src/views/Screening/index.vue#L406-L547)

- area title:"Advanced fields",subtitle:"Uncommonly used fields are not expanded by default;Actively add it to the filter conditions when needed"
- upper right label:"Optional N items"
- Add field dropdown placeholder:"Select advanced fields to append"
- Prompt text:"Only show fields you actively added;Removing a field will clear the corresponding conditions at the same time"
- Empty status prompt:"No advanced fields have been added yet. When more detailed conditions are needed,Then select the fields you want to add from above"

### 7.4 Filter results table columns

Source: [Screening/index.vue:619-720](file:///c:/TradingAgentsCN/frontend/src/views/Screening/index.vue#L619-L720)

| Table columns(What users see) | Show content |
|---------|----------|
| Checkbox column | Select to join the batch analysis list |
| **Stock code** | Clickable links,Jump stock details |
| **Stock name** | - |
| **Industry** | Industry classification |
| **current price** | Format:¥XX.XX |
| **Increase or decrease** | with plus or minus sign,Such as +1.23% / -0.85% |
| **Market value** | Format:XX billion / XX trillion |

### 7.5 button

- top:**Start filtering** / **reset condition**
- results area:**Batch analysis(N)** / **Export results** / **Re-filter**
- placeholder:"No matching stocks found"

## 8. Batch analysis page(BatchAnalysis.vue)Other fields

Source: [BatchAnalysis.vue](file:///c:/TradingAgentsCN/frontend/src/views/Analysis/BatchAnalysis.vue)

- Page title:"Batch analysis",upper right"Advanced"label
- Risk warning:"⚠️ Important tips:This analysis is only used for learning, research and public information compilation,No individual stock trading guidance is provided."
- Description:"AI Driven batch research workbench,Efficiently organize research leads on multiple stocks"
- "stock list"card(upper right label:`N only stocks`)
  - Market drop down options:"🇨🇳 A stock market(6 digits)" / "📈 ETF fund(510050, 159919 Wait)"
  - Input box placeholder(A shares):"Please enter stock code,one per line\n Supported formats:\n000001\n000002.SZ\n600036.SH"
  - Input box placeholder(ETF):"Please enter ETF code,one per line\n Supported formats:\n510050\n510300.SH\n159919.SZ"
  - button:"Parsing stock symbols" / "Clear"
  - Stock Preview Title:"Stock preview"
  - Invalid code prompt:"The following stock symbols may be formatted incorrectly,please check:"
- "Analysis configuration"card(upper right"Batch settings"label)
  - "Analysis depth"drop down(See section 1)
  - "Analysis process"drop down:Column `workflow_type === 'stock_analysis'` workflow,Selected by default `is_default=true` of
  - "Analyst Team"(See section 2)
  - submit button:"Start batch analysis(N only)"
- "Advanced configuration"card:Contains ModelConfig component,Field"Quickly analyze models"and"Deep analysis model"

## 9. General Research Analysis Page(GeneralAnalysis.vue)

Source: [GeneralAnalysis.vue](file:///c:/TradingAgentsCN/frontend/src/views/Analysis/GeneralAnalysis.vue)

- Page title:"General Research Analysis",icon Document
- Risk warning:"⚠️ Important tips:All conclusions of this analysis are used to learn and verify AI securities analysis technology,It is not intended as a guide for real trading operations."
- Description:"Flexible research workbench based on common processes,Support custom analysis goals and parameters"
- Tab:**new analysis** / **historical results**
- form fields:
  - **Process selection**:"Please select a general analysis process"
  - Displayed after selecting the process"Execution parameters"divider,fields from `selectedWorkflowFull.input_config.fields` Dynamically generated
  - Field type support:string / textarea / number / boolean / date / select / multiselect
  - Field label usage `field.label || field.name`(priority label,Useless name)
  - The field description is displayed below the input box:`field.description`
- button:"Start analysis" / "View results" / "Reanalyze"

## 10. Agent Name displayed in Chinese(Used for Agent workshop drop-down, etc.)

Source: [agentLabels.ts](file:///c:/TradingAgentsCN/frontend/src/constants/agentLabels.ts)

| backend key | Page display name(drop down) |
|---------|---------|
| `analysts_v2` | independent analyst v2.0 |
| `researchers_v2` | Optimistic/cautious scenario researcher v2.0 |
| `debators_v2` | Risk multi-scenario research v2.0 |
| `managers_v2` | Research/Risk Assessor v2.0 |
| `trader_v2` | research integrator v2.0 |
| `reviewers_v2` | Review analysis v2.0 |
| `position_analysis_v2` | Position analysis v2.0 |
| `post_processors_v2` | post processor v2.0 |
| `universal` | Customize Agent |

## 11. Display order of report modules(The order that users see on the Tab)

Source: [ReportDetail.vue:601-635](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L601-L635)

```
first stage:macro analysis(2 a)
  - index_report → 📊 Market Analyst
  - sector_report → 🏭 Sector Analyst

second stage:Analyst Team(4 a)
  - market_report → 📈 market analyst
  - fundamentals_report → 💰 fundamental analyst
  - sentiment_report → 💬 social media analyst
  - news_report → 📰 news analyst

The third stage:research team(multi-scenario research + Preliminary research observations)
  - bull_researcher → 🐂 Optimistic Scenario Researcher
  - bull_report → 🐂 Optimistic Scenario Study
  - bear_researcher → 🐻 Prudential Scenario Researcher
  - bear_report → 🐻 Prudential Scenario Study
  - research_team_decision → 🔬 research integrator
  - investment_plan (Hide when duplicated with research_team_decision)

Stage 4:trading team
  - trader_investment_plan → 🧩 research integrator

The fifth stage:risk management team(risk debate)
  - risky_analyst → ⚡ Highly Resilient Scenario Analyst
  - risky_opinion → ⚡ Highly elastic scenario research observations
  - safe_analyst → 🛡️ Defense Scenario Analyst
  - safe_opinion → 🛡️ Defense Scenario Research Observations
  - neutral_analyst → ⚖️ Baseline Scenario Analyst
  - neutral_opinion → ⚖️ Baseline Scenario Research Observations
  - risk_management_decision → 👔 risk assessor
  - risk_assessment → ⚠️ risk review

Stage six:final research conclusion
  - final_trade_decision → 🧾 Comprehensive research conclusion

Compatible with old fields
  - investment_debate_state → 🔬 Research team analysis(old)
  - risk_debate_state → ⚖️ Risk team analysis(old)
  - detailed_analysis → 📄 Detailed analysis
```

## 12. What users see on the report page"Risk warning"

Source: [ReportDetail.vue:83-93](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L83-L93)

```
⚠️ Important Risk Warnings and Disclaimers

- Platform nature:This platform is an AI-assisted analysis technology learning platform,Focus on the application verification and technical learning of AI technology in the fields of securities and ETF analysis.
- Analysis purpose:All analysis conclusions are only used to learn and verify AI-assisted analysis technology,It is not intended to be used as real trading guidance or investment basis.
- Not investment advice:All analysis results, scores, and suggestions are for technical verification reference only.,It does not constitute any buying and selling advice or the basis for investment decisions.
- Data limitations:Analysis is based on historical data and publicly available information,MAY BE DELAYED, INCOMPLETE OR INACCURATE,It is impossible to predict future market trends.
- investment risk:Both stock and ETF investments are subject to various risks such as market risk, liquidity risk, policy risk, etc.,May result in loss of principal.
- independent decision-making:Investors should make investment decisions independently based on their own risk tolerance, investment objectives and financial status.
- Responsibility statement:Any investment decisions and consequences arising from the use of this platform are the sole responsibility of the user.,This platform does not assume any responsibility.
```

## 13. In the report page"research brief"card

Source: [ReportDetail.vue:108-119](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L108-L119)

- card title:**research brief**
- subtitle icon:InfoFilled
- content: Markdown rendered `summaryDisplayContent`

## 14. In the report page"Detailed research report"card

Source: [ReportDetail.vue:121-145](file:///c:/TradingAgentsCN/frontend/src/views/Reports/ReportDetail.vue#L121-L145)

- card title:**Detailed research report**
- subtitle icon:Files
- Tab Type:`type="border-card"`
- Tab label:by `getModuleDisplayName(moduleName)` Dynamically generated(Refer to Section 3)

## 15. Report center list(Reports/index.vue)Field

Source: [Reports/index.vue](file:///c:/TradingAgentsCN/frontend/src/views/Reports/index.vue)

| Table columns | Page display name |
|--------|----------|
| Report title | `Stock code - stock name` |
| report type | "analysis report" / "Batch report" |
| Format | "MARKDOWN" / "DOCX" / "PDF" / "JSON" |
| Status | "Completed" / "Analyzing" / "failed" |
| Analytical model | LLM Model name(Such as "qwen-flash / qwen-max") |
| Analysis depth | "Depth: 5" / "Depth: 3" |
| creation time | YYYY-MM-DD HH:mm |

## 16. Report Center filters

- Search box placeholder:**"Search for a stock symbol or name"**
- Market filter placeholder:**"Market screening"**,Options:only **A shares**
- date range placeholder:**"start date"** / **"end date"**

## 17. Description text at the top of the report center

```
View and manage stock analysis reports,Supports export in multiple formats(Batch export up to 10 items)
```

## 📋 Matters still to be verified

The following functions were not found in the frontend code,Need further verification:

- [ ] `/portfolio` Field display on the position page
- [ ] `/paper` Field display for simulated trading
- [ ] `/review` Review field display
- [ ] `/assistant` AI Assistant field display
- [ ] `/position` Field display of position management
- [ ] `/settings/*` Field display on various settings pages
- [ ] `report_manifest` Specific display differences in different workflows

## ⚠️ Things to note when revising courses

1. **Priority is given to"Chinese labels that users see on the page"Subject to**,instead of the backend field name
2. **The display of the same thing in different locations has been unified**(Such as"Optimistic Scenario Researcher"Both at the top and Tab are the same)
3. **Don't use code key**(Such as `bull_researcher`, `risk_level`)Show it to users,to write"🐂 Optimistic Scenario Researcher", "risk level"
4. **When writing code references**use `[BatchAnalysis.vue:139-158](file:///...)` This format with line numbers,Easy to check
