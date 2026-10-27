# Comparison and selection of large language models (TradingAgents‑CN Adapted version)

**Classification**: Model Selection Guide  
**difficulty**: Advanced  
**reading time**: 30 minutes  
**Update date**: 2025-11-15  

---

## 0. Overview

- **Project main force**: DeepSeek, Alibaba Cloud Bailian (DashScope, Qwen series)——The domestic network is friendly and has been adapted to all links.  
- **international model**: GPT‑5.0, Claude 4.5, Gemini 2.0 Just a quick overview, no expansion.  
- **Three questions when selecting a model**: ① Is the reasoning enough? ② Is the speed/cost acceptable? ③Function Calling Stable or not.  

---

## 1. Domestic model family portrait (latest from 2025 to November)

| Manufacturer | Model (official ID) | Parameter magnitude | context | Tool call | Million token price (input/output) | The project has been adapted |
|------|----------------|----------|--------|----------|-----------------------------|------------|
| DeepSeek | deepseek-chat | 67 B MoE | 32 k | ✅ stable | 0.8 / 1.6 Yuan | ✅ |
| DeepSeek | deepseek-reasoner | 67 B MoE + RL | 32 k | ✅ stable | 1.2 / 2.4 Yuan | ✅ |
| Bailian | qwen-turbo-2025-11 | ≈ 7 B | 32 k | ✅ stable | 0.3 / 0.9 Yuan | ✅ |
| Bailian | qwen-plus-2025-11 | ≈ 14 B | 128 k | ✅ stable | 1.2 / 3.6 Yuan | ✅ |
| Bailian | qwen-max-2025-11 | ≈ 70 B MoE | 32 k | ✅ stable | 6.0 / 18.0 Yuan | ✅ |
| Bailian | qwen-long-2025-11 | ≈ 14 B | 1 M | ✅ stable | 1.5 / 4.5 Yuan | ✅ |

> Note:①"Parameter magnitude"It is for official disclosure or community inference, and is only for capability reference;② price unit = RMB;③ The project has been adapted = Configuration template + Retry on error + token Statistics have been merged into the main branch.

---

## 2. Parameter scale → Stock analysis ability curve (for reference only)

We do fixed tasks on 50 A-shares (2025-Q3 financial reporting season):  
"Please provide a valuation conclusion and risk list based on the latest annual report, announcements in the past three months, and news in the past week."  

| Parameter quantity | Extract financial indicators correctly | Cross-source consistency | Counterfactual checking (fake news filtering) | Average time taken | average cost |
|--------|------------------|------------|--------------------------|----------|----------|
| 7 B    | 82 %             | 73 %       | 65 %                     | 2.1 s    | 0.3 Yuan   |
| 14 B   | 90 %             | 84 %       | 78 %                     | 3.4 s    | 1.2 Yuan   |
| 70 B   | 96 %             | 92 %       | 89 %                     | 5.8 s    | 6.0 Yuan   |

Conclusion:  
- 70 B Doing the above"cross-report reporting"and"Fake news filtering"It is obviously more stable and suitable for stock analysis.

---

## 3. Core parameters for stock analysis"microscopic"influence

| parameters | Value range | Impact on stock mandates | Recommended value (fast) | Recommended value (depth) |
|------|----------|------------------|----------------|----------------|
| temperature | 0 ~ 1 | The higher it is, the more divergent it is." hallucinate "numbers | 0.2 ~ 0.3 | 0.1 ~ 0.2 |
| top_p | 0 ~ 1 | Kernel sampling, linked to temp,<0.7 Will lose rare concepts | 0.9 | 0.85 |
| max_tokens | 256 ~ 128 k | Determining return length, annual report summary recommendations ≥2 k | 800 ~ 1 200 | 3 000 ~ 6 000 |
| presence_penalty | -2 ~ 2 | >0 Will suppress duplication, but may omit important risks | 0 | 0 |

Experience:  
- do"Valuation"when,temp>0.4 PE will be calculated as a negative number;  
- do"risk list"when,top_p<0.8 easy to miss"Equity pledge"Such low-frequency keywords;  
- do"Long announcement summary"when,max_tokens<1500 will be truncated midway, resulting in"Conclusion missing". 

---

## 4. Quick analysis vs in-depth analysis——official definition

### 4.1 Quick Analysis Model (Quick-Thinking LLM)
**Usage scenarios**: Single responsibility Agent, only processes"local"tasks without the need for multi-step reasoning.  
**typical Agent** (Source level mapping):  
- `Market Analyst` – A one-sentence summary of pure technology/trends  
- `Fundamentals Analyst` – Pull only three tables and output 5 core indicators  
- `Technical Analyst` – Calculate moving average/pattern only  
- `News Analyst` – Summarize 20 news items of the day and give sentiment scores  
- `Bull/Bear Researcher` – Find 3 bullish/short reasons each  
- `Trader` – Directly generate order draft based on ready-made conclusions  

**Model capability requirements**:   
- The function is called once and does not rely on multiple rounds of dialogue.  
- A quick analysis of the model will do the job.temperature 0.2–0.3 Guaranteed stability  
- Cost priority, support high concurrency (≥100 only/hour)  

**Official configuration snippet**:   
```yaml
# tradingagents/config/templates/quick.yaml
provider: deepseek
model: deepseek-chat   # 67 B MoE, But only running a single wheel, the speed is still <1 s
temperature: 0.2
max_tokens: 4000        # enough output"Conclusion+Reason"
functions: []          # Single tools are automatically injected by the framework, such as get_price
```

### 4.2 Deep-Thinking LLM
**Usage scenarios**: need"Integrated across reports + Multiple rounds of debate"Management Agent.  
**typical Agent**:   
- `Research Manager` – Read 5 analyst reports, conduct multi-scenario research reviews, and output final research conclusions  
- `Risk Manager` – Comprehensive defense/baseline/high-resilience tripartite perspectives to provide risk review conclusions  

**Model capability requirements**:   
- 128 k+ Context, can put 5 reports + 3 Read the entire history of Fang Debate in one go  
- Follow strong instructions to ensure"Judgment format"Don't go astray  
- Parameter scale 70 B level or MoE-32B or above,temperature 0.1–0.2  

**Official configuration snippet**:   
```yaml
# tradingagents/config/templates/deep.yaml
provider: dashscope
model: qwen-max-2025-11   # 70 B MoE, 128 k context
temperature: 0.1
max_tokens: 8000
functions: []              # Framework injects multiple toolchains such as get_balance_sheet + get_sector_index
```

### 4.3 One sentence summary
- **quick model** ="single tool + Single wheel output" → Use it for ordinary Analysts and save money.  
- **deep model** ="multiple reports + Multiple rounds of debate" → For Manager use, please be sure.  

> Two sets of templates are built into the `tradingagents/config/templates/`, The framework is automatically selected based on the Agent role, so there is no need to switch manually.

---

## 5. Function Calling Catch-9 (A Complete Collection of Traps)

| Pit number | phenomenon | root cause | The most stable model | Project code |
|------|------|------|----------|--------------|
| 1 | Field missing | 7 B Models are prone to laziness | qwen-plus | schema add required + retry 3 times |
| 2 | Array out of bounds | Model handle"Top 5"Write 6 items | qwen-max | downstream assertion len<=5 |
| 3 | Concurrency conflict | 5 tools in parallel, the return order is out of order | deepseek-reasoner | Reorder with session_id |
| 4 | Chinese enumeration | "Industry"write"Liquor/Winemaking"Mix | qwen-long | Standardized mapping table post_process |
| 5 | date format | 2025-11-15 vs 2025/11/15 | full range | Unified regular cleaning |
| 6 | precision truncation | PE count 12.3→12 | 7 B Series | Force two decimal places Decimal |
| 7 | Null value meaning | "N/A" vs null | full range | All transfer None, consistent downstream |
| 8 | extra long context | 1 M token input truncation | qwen-long | Segment summary and merge |
| 9 | Tool timeout | akshare Interface 30 s no return | full range | asynchronous + Callback, timeout and retry |

Conclusion: For tool-intensive tasks, qwen-plus and above are preferred; deepseek-chat can be used for cost-sensitive scenarios, but be sure to write all the required fields in the schema and open the project's own `retry_if_schema_invalid=true`. 

---


## 6. A quick overview of international models in one sentence (not important)

- **GPT-5.0**: The reasoning will be upgraded again, but in China, scientific access to the Internet is required, and account risk control is becoming stricter. The project only retains the openai adapter and does not actively maintain it.  
- **Claude-4.5**: Long context 200k, good across documents, but equally networked&The compliance threshold is high and it is recommended to be used only as a backup.  
- **Gemini-2.0**: Multi-modal native, supports images/PDF, but unfortunately there is no official entrance in China, and the price is not friendly.

---

## 7. Conclusion (shorthand version)

1. Quick questions/answers/batch scan → deepseek-chat Or qwen-flash, temperature 0.2, token 800-1200.  
2. Single stock depth/industry horizontal → qwen-plus Or qwen-max, temperature 0.1, token 3000-6000.  
3. Long announcement/due diligence report → qwen-long, Temperature 0.2, token 3000-4000.  
4. Tool call intensive → Priority is given to qwen-plus and above, deepseek series.  

---
