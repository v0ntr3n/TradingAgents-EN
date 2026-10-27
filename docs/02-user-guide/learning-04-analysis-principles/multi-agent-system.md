# Detailed explanation of multi-agent systems

**Classification**: AI Analyze stock principles  
**difficulty**: Advanced  
**reading time**: 15 minutes  
**Update date**: 2025-11-14

---

## 📋 Introduction

TradingAgents-CN A multi-agent collaboration mechanism is used for stock analysis. What is a multi-agent system? Why use multiple AIs instead of one? This article will provide an in-depth analysis of the principles and advantages of multi-agent systems.

---

## 🤖 What is a multi-agent system?

### definition

**Multi-agent system (Multi-Agent System, MAS) **It is a system composed of multiple agents (Agents). Each agent is responsible for a specific task and completes complex goals through collaboration.

### Analogy understanding

Imagine a research team:

```
Traditional way (single agent):
One person does all the work
├── Collect data
├── technical analysis
├── fundamental analysis
├── risk assessment
└── make decisions

Multi-agent approach:
Collaboration between multiple experts
├── Researcher: Collect and organize information
├── Technical Analyst: Analyzing Price Movements
├── Fundamental Analyst: Analyze financial data
├── Risk Assessor: Assessing Risk
└── Research Integrator: Synthesize Research Conclusions
```

---

## 🏗️ TradingAgents-CN The agent architecture of

### agent role

#### 1. Researcher

**Responsibilities**: 
- Collect basic stock information
- Organize financial data
- Collect industry information
- Aggregate market news

**Output example**: 
```markdown
## Basic stock information
- Code:000001
- Name: Ping An Bank
- Industry: Banking
- Time on the market: 1991

## financial data
- P/E ratio:5.2
- Price to Book Ratio:0.6
- ROE：10.5%
- Asset-liability ratio:92.5%

## Latest news
- 2024Q3 Earnings Report: Revenue Growth 8.5%
- Recent News: Launch of Digital Transformation Strategy
```

#### 2. Technical Analyst

**Responsibilities**: 
- Analyze price trends
- Calculate technical indicators
- Identify support pressure levels
- Determine technical form signals

**Output example**: 
```markdown
## trend analysis
- Short-term trend: shock
- Medium-term trend: Up
- Long-term trend: Up

## Technical indicators
- MACD: golden cross signal
- RSI: 55 (neutral)
- Moving average: stand above the 60-day moving average

## key price
- Support level: 11.80 yuan
- Pressure level: 13.20 yuan

> Technical indicators and price levels are for research and observation only and do not constitute trading advice.
```

#### 3. Fundamental Analyst

**Responsibilities**: 
- Analyze financial metrics
- Assess profitability
- Research industry status
- Determine valuation level

**Output example**: 
```markdown
## Valuation analysis
- PE 5.2 vs Industry average 6.5: Undervalued
- PB 0.6: Net break, attractive valuation

## Profitability
- ROE 10.5%: medium level
- Net profit growth rate: 8.5%: Steady growth

## Industry status
- Market Share: Ex 10
- Competitive advantage: strong retail banking business
```

#### 4. Risk Assessor

**Responsibilities**: 
- Identify risk factors
- Assess risk level
- Provide risk warning
- Recommend risk control measures

**Output example**: 
```markdown
## Main risks
1. Credit risk: non-performing loan ratio 1.2%
2. Policy risk: Financial regulation becomes more stringent
3. Market risk: impact of interest rate fluctuations

## risk level
- Overall risk: Moderate
- Risk exposure tip: It is recommended to evaluate your own risk preference (users make their own judgment)
- Risk attention price: 10.50 yuan (users can track it by themselves, for research reference only)
```

#### 5. Research Integrator

**Responsibilities**: 
- Comprehensive opinions from all parties
- Weigh the pros and cons
- Summary of research conclusions
- Form a research brief

**Output example**: 
```markdown
## Comprehensive evaluation
Based on the above analysis, Ping An Bank:
- Valuation:★★★★☆ (underestimated)
- Growth:★★★☆☆ (Robust)
- Risks:★★★☆☆ (medium)

## research observation
- Research conclusion tendency: cautious
- Key verification interval: 14.00-15.00 yuan (observation area, non-target price)
- Tracking period: 6-12 months
- Follow-up observations: quarterly financial reports, changes in non-performing loan ratios
```

---

## 🔄 Collaboration process

### Standard analysis procedure

```mermaid
graph TD
    A[User enters stock code] --> B[Researchers collect information]
    B --> C[technical analyst analysis]
    B --> D[Fundamental analyst analysis]
    C --> E[Risk Assessor Review]
    D --> E
    E --> F[Summary of research integrators]
    F --> G[Generate research briefs]

> Note: This system is a research aid, and all analysis conclusions are for research reference only and do not constitute investment advice.
```

### Detailed steps

**Step 1: Information Collection**
```
Researcher:
"I have collected the basic information and financial data of Ping An Bank.
Now leave it to technical analysts and fundamental analysts to analyze."
```

**Step 2: Parallel Analysis**
```
Technical Analyst:
"From a technical perspective, the stock price is in an upward channel, MACD is golden cross..."

Fundamental Analyst:
"From a fundamental perspective, PE 5.2 is lower than the industry average and the valuation is attractive..."
```

**Step 3: Risk Review**
```
Risk Assessor:
"Comprehensive technical and fundamental aspects, the main risks include:
1. Non-performing loan ratio is high
2. Interest rate fluctuation risk
Follow-up needs to be followed: changes in non-performing ratio in quarterly financial reports."
```

**Step 4: Research Summary**
```
Research Integrator:
"Based on the opinions of experts:
- Technical: Positive Momentum Signals
- Fundamentals: Undervalued
- Risk: need attention
Research observation: The current trend is to be cautious, and it is necessary to continue to track quarterly financial reports and changes in non-performing ratios.
The above conclusions are for research reference only and do not constitute investment advice."
```

---

## 🎯 Advantages of multi-agent

### 1. Professional division of labor

**single agent**: 
```
One AI handles all tasks
→ May not be professional enough in some aspects
→ Difficult to analyze in depth
```

**multi-agent**: 
```
Each AI focuses on a specific area
→ More professional analysis
→ deeper insights
```

### 2. Multi-angle analysis

**single agent**: 
```
There may be limitations to a single perspective
```

**multi-agent**: 
```
technical aspect + Fundamentals + risk assessment
→ A more comprehensive analysis
→ Reduce blind spots
```

### 3. checks and balances

**Example**: 
```
Technical Analyst:"Technical picture shows positive momentum signal"
↓
Risk Assessor:"But the risk is higher, so you need to pay attention to the failure conditions."
↓
Research Integrator:"Based on the evidence from all parties, the current trend is to be cautious and requires continued follow-up."
```

### 4. Improve accuracy

**Research shows**: 
- Single agent accuracy:~70%
- Multi-agent collaboration accuracy:~85%
- Multi-agent debate accuracy:~90%

---

## 🗣️ debate mechanism

### What is a debate mechanism?

Let agents with different viewpoints debate and draw more reliable conclusions through the collision of ideas.

### debate process

**Scenario: Analyze the research value of Ping An Bank**

**Round 1: Initial Perspectives**
```
Optimists (fundamental analysts):
"PE 5.2 At historically low levels, valuations are attractive for research"

Prudential (Risk Assessor):
"The non-performing loan ratio of 1.2% is on the high side and requires continued observation."
```

**Round 2: Refutation and Argument**
```
Optimist:
"Although the non-performing loan ratio is 1.2%, it is at a medium level in the industry.
Moreover, the company's provision coverage ratio is 200%, and risks are controllable.
More importantly, the PE 5.2 is well below the historical average of 7.5,
There is room for research on valuation repair."

Prudential:
"There are reasons for the low valuation. The banking industry as a whole is facing the pressure of narrowing net interest margins.
Earnings growth slowed. Even if the PE is low, it does not mean that the research conclusion is necessarily optimistic.
It is recommended to wait for a clearer catalyst."
```

**Round 3: Research Summary**
```
Research Integrator (Integrated):
"There are valid points on both sides. All things considered:
1. Valuations do have research appeal (the optimists are right)
2. Risks need to be taken seriously (the prudent faction is correct)

Research observations:
- The current trend is to be cautious and needs to be followed up
- Key verification level: 10.50 yuan (observation area, non-target price)
- Pay attention to quarterly financial reports and dynamically adjust research and judgment
- The above conclusions are for research reference only and do not constitute investment advice."
```

---

## 💡 Implementation principle

### Prompt word design

**researcher prompts**: 
```
You are a professional stock researcher responsible for collecting and organizing stock information.

Mission: Collect{Stock code}basic information
Includes:
1. Basic information of the company
2. financial data
3. Industry information
4. Latest news

Requirements:
- Data is accurate
- Comprehensive information
- clear format
```

**Technical Analyst Tips**: 
```
You are an expert in technical analysis, focusing on price movements and technical indicators.

Based on the following data analysis{Stock code}: 
{price data}
{Technical indicators}

Please analyze:
1. Trend judgment
2. technical indicator signals
3. Support pressure level
4. Technical form signals (no buying and selling recommendations are output)
```

### information transfer

```python
# Pseudocode example
class MultiAgentSystem:
    def analyze(self, stock_code):
        # Step 1: Researcher Gathers Information
        info = researcher.collect(stock_code)
        
        # Step 2: Parallel Analysis
        technical = technical_analyst.analyze(info)
        fundamental = fundamental_analyst.analyze(info)
        
        # Step 3: Risk Assessment
        risk = risk_assessor.assess(technical, fundamental)
        
        # Step 4: Comprehensive summary
        research_conclusion = research_integrator.integrate(
            technical, fundamental, risk
        )
        
        return research_conclusion
```

---

## 📊 Effect comparison

### Test case: Analysis of Ping An Bank

**Single agent analysis**: 
```
Analysis depth:★★★☆☆
Analysis angle:★★☆☆☆
Risk warning:★★☆☆☆
Overall rating:6.5/10
```

**Multi-agent analysis**: 
```
Analysis depth:★★★★★
Analysis angle:★★★★★
Risk warning:★★★★☆
Overall rating:9.0/10
```

---

## 📚 Summary

### core points

1. **multi-agent system**Multiple professional AIs collaborate to complete tasks
2. **TradingAgents-CN**Contains 5 core agent roles
3. **Collaboration process**: collect→analysis→Assessment→Summary
4. **Main advantages**: Professional division of labor, multiple perspectives, mutual checks and balances
5. **debate mechanism**Improve the accuracy and reliability of your analysis

### Practical suggestions

1. **Understand the responsibilities of each agent**
2. **Focus on interactions between agents**
3. **Pay attention to the collision of different viewpoints**
4. **Taking into account the opinions of all parties**

---

## 🔗 Related resources

- 📖 [Detailed explanation of debate mechanism](./debate-mechanism.md)
- 📖 [Detailed explanation of analysis process](./analysis-workflow.md)
- 📖 [TradingAgents Project introduction](../06-resources/tradingagents-intro.md)
- 📖 [Practical tutorial](../07-tutorials/single-analysis.md)

