# FAQ

**Classification**: FAQ  
**difficulty**: Getting Started  
**reading time**: 15 minutes  
**Update date**: 2025-11-14

---

## 📋 Directory

- [About TradingAgents-CN](#About tradingagents-cn)
- [Function related](#Function related)
- [Model selection](#Model selection)
- [Tips](#Tips)
- [Troubleshooting](#Troubleshooting)
- [Cost related](#Cost related)

---

## 🏢 About TradingAgents-CN

### Q1: TradingAgents-CN What is it?

**A**: TradingAgents-CN It is an AI stock analysis learning platform based on a large language model, using a multi-agent collaboration mechanism to help users learn and understand stock analysis methods.

**Core features**: 
- 🤖 Multi-agent collaborative analysis
- 🇨🇳 Specifically optimized for China's A-share market
- 📚 Learning tool, not investment advice
- 🔓 Open source project, self-deployable

### Q2: How is it different from other stock analysis tools?

**A**: 

| Features | TradingAgents-CN | Traditional analysis tools |
|------|-----------------|------------|
| Analysis method | AI Multi-agent collaboration | fixed algorithm |
| Flexibility | Customizable prompt words | fixed pattern |
| learning value | Show analysis process | Only give results |
| Applicable market | A stock optimization | Universal |
| Open source | Completely open source | Mostly closed source |

### Q3: Do you provide investment advice?

**A**: ⚠️ **No investment advice is provided**

TradingAgents-CN Yes**learning tools**, The analysis provided is for reference only and does not constitute investment advice.

```
✅ We provide: learning resources, analysis reference, tool support
❌ We do not provide: investment advice, income guarantee, professional consultation
```

### Q4: What is the data source?

**A**: 

**A Share data sources (by priority and responsibility)**: 
- 📊 Tushare (Main professional data, key required)
  - Stock list, daily/minute quotes,`daily_basic` (PE/PB/Market value, etc.), financial statements (profit/assets and liabilities/cash flow)
  - used within the frame"Dynamic PE/PB"with core sources of fundamental analysis (see `tradingagents/dataflows/realtime_metrics.py`) 
  - Downgrade chain preferred:MongoDB → Tushare → Others (see `stock_data_service.py`) 
- 📈 AKShare (Open source free supplement)
  - Historical/real-time market conditions and some financial data; Hong Kong stock data is given priority on AKShare (see `dataflows/providers/hk`) 
  - News interface: Oriental Fortune stock news `stock_news_em`, CCTV Market news (see `dataflows/akshare_utils.py`) 
- 🗃️ BaoStock (Free and stable historical data)
  - As a comprehensive supplement to the historical data of A shares (see `constants/data_sources.py` with `providers/china`) 


**data type**: 
- Real-time quotes
- financial statements
- Technical indicators
- market news

**International and news data sources**: 
- 🇺🇸 yfinance (Yahoo Finance, free)
  - US/Hong Kong stock market quotes and basic information; Hong Kong stocks are downgraded to yfinance when AKShare fails (see `dataflows/interface.py`) 
- 🇺🇸 Finnhub (Key required)
  - US stock/Hong Kong stock market conditions, fundamentals and news; back-end/front-end detection `FINNHUB_API_KEY` (see `web/modules/config_management.py`) 
- 🇺🇸 Alpha Vantage (Key required)
  - US stock fundamentals and selected news; as an alternative to the US market (see `providers/us/alpha_vantage_fundamentals.py`) 
- 📚 SimFin (data set)
  - US stock financial report data, providing balance sheet/income statement/cash flow (see `dataflows/interface.py`) 
- 📰 News aggregation (multiple sources)
  - Tushare News source: sina/eastmoney/10jqka/wallstreetcn/cls/First Financial/Financial Circle/Cloud Finance/Phoenix Finance (see `docs/features/news/NEWS_SYNC_FEATURE.md`) 
  - AKShare News source: Oriental Fortune, CCTV (see `dataflows/akshare_utils.py`) 
  - Build your own aggregators: Google News, Reddit (see `dataflows/interface.py` with `features/news/news-analysis-system.md`) 

**Environment variables and keys**: 
- `TUSHARE_TOKEN` (Required for Tushare)
- `FINNHUB_API_KEY` (Optional, enable Finnhub)
- `ALPHA_VANTAGE_API_KEY` (Optional, enable Alpha Vantage)
- `NEWSAPI_KEY` (Optional, enable some news aggregation)

**Data source selection and downgrade strategies (built-in)**: 
- A Shares:MongoDB → Tushare → AKShare → BaoStock (Automatically switch according to priority)
- Hong Kong stocks:AKShare → yfinance → Finnhub (Downgrade in case of failure)
- US stocks:Alpha Vantage → yfinance → Finnhub (Select and downgrade by scene)

---

## 🎯 Function related

### Q5: What stock markets are supported?

**A**: 

**Currently supported**: 
- ✅ China A shares (Shanghai, Shenzhen)
- ✅ Science and Technology Innovation Board
- ✅ GEM

**Current support (extended)**: 
- ✅ Hong Kong stocks (AKShare/yfinance/Finnhub)
- ✅ US stocks (yfinance / Finnhub / Alpha Vantage)

### Q6: What types of stocks can be analyzed?

**A**: 

**Supported stock types**: 
- ✅ Main board stocks
- ✅ Science and Technology Innovation Board Stocks
- ✅ GEM stocks
- ❌ delisted stocks
- ❌ Suspended stocks (data may be incomplete)

### Q7: How long does the analysis take?

**A**: 

| Analysis type | time | Applicable scenarios |
|---------|------|---------|
| Quick analysis | 30 seconds | Get to know quickly |
| standard analysis | 1-2 minutes | daily analysis |
| In-depth analysis | 2-3 minutes | important decisions |
| multi-agent debate | 5-8 minutes | major decisions |

**Influencing factors**: 
- Model selection (Qwen‑Max More stable but slightly slower; DeepSeek V3.1 is faster and cost-effective)
- Network status
- API Response speed

### Q8: Can I analyze multiple stocks at the same time?

**A**: 

**OK**, There are two ways:

**Method 1: Batch analysis**
```
1. enter"Batch analysis"Page
2. Enter multiple stock codes (separate by carriage return and line feed)
3. Select analysis dimensions
4. Click"Start analysis"
```


### Q9: Can analysis reports be saved?

**A**: 

**OK**, Supports multiple methods:

- 📄 **Export PDF**: Full report, suitable for printing
- 📊 **Export Excel**: Data table, suitable for further analysis
- 💾 **save to history**: View historical reports online


### Q10: How to use multi-agent debate?

**A**: 

**steps**: 
1. Select research depth (Level 1-5: Quick/Basic/Standard/Deep/Comprehensive)
2. Enter stock code
3. Click"Start analysis"
4. The system executes debate and risk discussion according to the selected level (different rounds)
5. View the debate process and comprehensive conclusion (Research Manager/Risk Adjudication)

**Debate Rounds and Risk Discussion Instructions**: 
- 1 Level Quick: 1 round of Debate; 1 round of Risk Discussion
- 2 Level Basic: 1 round of debate; 1 round of risk discussion
- 3 Level Standard: 1 round of debate; 2 rounds of risk discussion
- 4 Level Depth: 2 rounds of debate; 2 rounds of risk discussion
- 5 Level Full: 3 rounds of debate; 3 rounds of risk discussion

Tip: The actual time consumption is related to the selected level, model provider and tool call. The higher the level, the more rounds of debate and risk discussion, and the overall time will increase accordingly.

**Select recommendations by level**: 
- 1 Level Fast: daily monitoring, hotspot scanning, intraday quick reviews; lightweight scenarios that are sensitive to delays
- 2 Level Basics: regular single stock research, including the latest data; small position adjustments, short-term strategies
- 3 Level Standard (Recommended): Important investment decisions require risk control verification; covers most daily scenarios
- 4 Level Depth: major events/earnings season/high volatility; requires multiple rounds of debate and more stable conclusions
- 5 Level Comprehensive: High dollar or portfolio level decisions; produces complete research reports and compliance records

Tip: All levels are supported"multi-agent debate", It's just that the rounds of debate and risk discussion are different; choosing a higher level means a more comprehensive integration of views and longer time.

---

## 🤖 Model selection

### Q11: Which LLM model should be chosen?

**A**: 

**Choose based on budget (Focus DeepSeek + Qwen series)**: 

**Limited budget** (<¥100/month):
```
Main force: DeepSeek V3.1 (high cost performance, good Chinese performance)
Important analysis:Qwen3‑Plus (Long text/Chinese optimization)
```

**Moderate budget** (¥100‑500/month):
```
Main force:DeepSeek V3.1 + Qwen3‑Plus (division of labor and collaboration)
In-depth analysis:Qwen‑Max (Multiple rounds of debate/adjudication by management)
```

**Sufficient budget** (>¥500/month):
```
Analyst: DeepSeek V3.1 or Qwen3‑Plus (quick/long document)
Management:Qwen‑Max (In-depth reasoning and comprehensive ruling)
```

**Choose according to your needs**: 

| demand | Recommended model |
|------|---------|
| Quick analysis | DeepSeek V3.1 |
| In-depth analysis/adjudication | Qwen‑Max |
| Chinese optimization | Qwen3‑Plus |
| long text review | Qwen3‑Plus |
| Extremely cost-effective | DeepSeek V3.1 |

### Q12: Qwen‑Max and Qwen3‑Plus Is the difference big?

**A**: 

**Core differences**: 

| Dimensions | Qwen‑Max | Qwen3‑Plus |
|------|----------|------------|
| reasoning ability | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Analysis depth | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Context/Long Document | medium | longer |
| Tool call stability | ✅ high | ✅ high |
| speed | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| cost | 💰💰💰💰 | 💰💰 |
| Adaptation role | Management/In-Depth Verdict | Analyst/Long Document Review |

**Suggestions**: 
- Analyst single task, long text review: Select Qwen3‑Plus
- Management comprehensive, in-depth debate/adjudication: Select Qwen‑Max
- If the budget is sensitive: DeepSeek V3.1 is the main workhorse, and important links are switched to Qwen‑Max

### Q13: DeepSeek V3.1 What scenarios is it suitable for?

**A**: 

**DeepSeek V3.1 Features (the project has been deeply adapted)**: 
- 💰 Excellent cost: suitable as the main model for daily analysis
- 🇨🇳 Good understanding of Chinese: A good understanding of A-shares and Chinese information context
- 🔧 Function Calling Stable: tool chain calls and numerical calculations perform reliably
- ⚡ Fast response: suitable for intraday and batch tasks

**Suggestions**: 
- Daily and batch analysis: DeepSeek V3.1 is preferred (fast and low-cost)
- Long text/Chinese summary:Qwen3‑Plus More stable and longer context
- In-depth debate/final verdict:Qwen‑Max (Research Manager/Risk Manager)

### Q14: How to get API key?

**A**: 

**Domestic model (recommended)**: 
- **DeepSeek V3.1**: https://platform.deepseek.com (console → API Keys) 
- **DashScope**: https://dashscope.aliyun.com (console → API Keys) 
-  (Optional) A few words from Wen Xin:https://cloud.baidu.com; iFlytek Spark:https://xinghuo.xfyun.cn

**International model (optional)**: 
- OpenAI: https://platform.openai.com (If overseas network is required)

**Note**: 
- 🔒 Keep API keys safe
- 💰 Pay attention to API usage quota
- ⚠️ Don't share with others

---

## 💡 Tips

### Q15: How to improve the quality of analysis?

**A**: 

**5 tips**: 

1. **Choose a more suitable model**
  ```
  Qwen‑Max > Qwen3‑Plus > DeepSeek V3.1
   (in-depth ruling → long text review → Cost-effectiveness and speed)
  ```

2. **Provide more detailed data**
   ```
   Don't just enter a stock symbol
   Provide financial data, industry information, etc.
   ```

3. **Custom prompt words**
   ```
   Adjust prompt words according to analysis purpose
   Clarify the focus and angle of analysis
   ```

4. **Using multi-agent debate**
   ```
   Use debate mode for important decisions
   Listen to different perspectives
   ```

5. **Verify key data**
   ```
   AI something could go wrong
   Key data need to be cross-validated
   ```

### Q16: How to customize prompt words? (Not implemented, under development, will be provided in subsequent versions)

**A**: 

**steps**: 
1. enter"settings" → "Prompt word management"
2. Select the agent to modify
3. Edit Prompt Word Template
4. Save and test

**Example**: 

**Original prompt word**: 
```
You are a stock analyst, please analyze{stocks}investment value.
```

**Custom prompt words**: 
```
Are you someone who focuses on{Industry}senior analyst,
Have more than 10 years of investment experience.

Please analyze it from the perspective of value investment{stocks}, 
Focus on:
1. Valuation level (PE, PB)
2. Profitability (ROE, net profit margin)
3. Moat (competitive advantage)
4. management quality

Requirements:
- Use Buffett's investment philosophy
- Focus on long-term value
- conservative estimate
```

### Q17: How to manage a stock watchlist?

**A**: 

**Add to study list**: 
1. After analyzing a stock, click"Add to choice"
2. or in"Stock Watchlist"Pages added manually

**Stock watch list function**: 
- 📊 View a list of stocks to watch
- 📈 Batch analysis of stock watchlists
- 🔔 Set price alerts
- 📉 Check the ranking of gains and losses

**Group management**: 
```
Multiple groups can be created:
- Core positions
- watch list
- Industry sector
- Potential stocks
```

### Q18: How to set up price alerts? (Currently not implemented due to real-time data issues)

**A**: 

**steps**: 
1. Enter the stock details page
2. Click"Set reminder"
3. Select reminder type:
   - price arrived
   - Increase or decrease
   - Abnormal trading volume
4. Set reminder conditions
5. Select notification method (email/site message)

**Example**: 
```
Stock: Ping An Bank (000001)
Reminder Type: Price Arrival
Conditions:>= 14.50 Yuan
Notification method: email + Site message
```

---

## 🔧 Troubleshooting

### Q19: What should I do if the analysis fails?

**A**: 

**Common causes and solutions**: 

**1. API Key error**
```
Error message:Invalid API Key
Workaround: Check if the API key is correct
```

**2. API Insufficient quota**
```
Error message:Insufficient quota
Solution: Recharge API account
```

**3. network problems**
```
Error message:Network timeout
Solution: Check network connection and try again
```

**4. Stock code error**
```
Error message:Stock not found
Solution: Check if the stock symbol is correct
```

**5. Data source issues**
```
Error message:Data source error
Solution: Wait for the data source to be restored, or switch the data source
```

### Q20: What should I do if the analysis results are inaccurate?

**A**: 

**Possible reasons**: 

1. **AI hallucination**
   ```
   AI Made up data that doesn't exist
   Solution: Verify key data
   ```

2. **Data is out of date**
   ```
   Used old data
   Solution: Provide the latest data
   ```

3. **Inappropriate prompt word**
   ```
   The prompt word is not clear enough
   Solution: Optimize prompt words
   ```

4. **Insufficient model capabilities**
   ```
   Used a weaker model
   Solution: switch to Qwen‑Max Or increase the analysis depth level (level 4/5)
   ```

---

## 💰 Cost related

### Q21: Is there any fee to use TradingAgents-CN?

**A**: 

**software itself**: 
- ✅ completely free
- ✅ Open source projects
- ✅ Self-deployable

**Part that needs to be paid**: 
- 💰 LLM API Call charges (billed by usage)
- 💰 Data source API fee (some data sources)

### Q22: LLM API How much does it cost?

**A**: 

**Estimate (monthly)**: 

**light use** (Analyze 2-3 stocks every day):
```
Using DeepSeek V3.1: approx. ¥5-10/month
Use Qwen3‑Plus: approx. ¥10-30/month
Use Qwen‑Max: approx. ¥50-150/month
```

**Moderate use** (Analyze 5-10 stocks every day):
```
Using DeepSeek V3.1: approx. ¥20-40/month
Use Qwen3‑Plus: approx. ¥30-80/month
Use Qwen‑Max: approx. ¥150-400/month
```

**heavy use** (Analyze every day 20+only stocks):
```
Using DeepSeek V3.1: approx. ¥40-80/month
Use Qwen3‑Plus: approx. ¥80-200/month
Use Qwen‑Max: approx. ¥400-1200/month
```

**cost saving tips**: 
1. Daily/Batch: Priority DeepSeek V3.1 or Qwen3‑Plus
2. Depth Verdict: Use only in critical areas Qwen‑Max
3. Batch tasks: lowered `max_tokens` and analysis depth level
4. Enable caching and tool reuse to avoid repeated calls

### Q23: How to check API usage?

**A**: 

**In TradingAgents-CN**: 
1. enter"settings" → "usage statistics"
2. Check out:
   - total calls
   - Token Usage
   - Estimated cost

**On the official website of the API provider**: 
1. Log in to API provider account
2. View the Usage page
3. View detailed bill

---

## 📚 More resources

### Related documents

- 📖 [Quick Start Tutorial](../07-tutorials/getting-started.md)
- 📖 [prompt word project](../02-prompt-engineering/prompt-basics.md)
- 📖 [Model Selection Guide](../03-model-selection/model-comparison.md)
- 📖 [Risk warning](../05-risks-limitations/risk-warnings.md)

### Get help

- 💬 GitHub Issues
- 📧 Email support
- 👥 user community

---

**Have other questions?**

Feel free to ask questions in GitHub Issues, or view the full documentation.

