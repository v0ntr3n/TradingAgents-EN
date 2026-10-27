# TradingAgents Project introduction

**Classification**: Source projects and papers
**difficulty**: Advanced
**reading time**: 15 minutes
**Update date**: 2025-11-15

---

## 📋 Introduction

TradingAgents-CN is based on**TradingAgents**Chinese localized version of project development. TradingAgents is an open source AI-driven multi-agent stock analysis platform developed by the Tauric Research team. This article will introduce the background, core concepts and technical architecture of the TradingAgents project.

---

## 🎯 Project background

### TradingAgents the birth of

TradingAgents The project originated from academic research and aims to explore how to use large language models (LLM) and multi-agent systems to improve the quality and efficiency of stock analysis.

**research team**: 
- Tauric Research team
- Several experts in AI and financial technology fields

**Publish a paper**: 
- 📄 Paper title:*"TradingAgents: TradingAgents: Multi-Agents LLM Financial Trading
Framework"*
- 📅 Publication date: 2024
- 🔗 Paper link:[arXiv](https://arxiv.org/pdf/2412.20138)

---

## 🏗️ core architecture

### 1. Multi-layer architecture design

TradingAgents Using a layered architecture, complex stock analysis tasks are decomposed into multiple levels:

```
┌─────────────────────────────────────────┐
│         Application Layer        │
│  Stock research analysis, position tracking, risk review, etc.          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Agent Layer            │
│  Multiple agents such as analysts, researchers, and research integrators          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Tool Layer               │
│  Data acquisition, technical analysis, fundamental analysis and other tools        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Data Layer               │
│  Market data, financial data, news data, etc.             │
└─────────────────────────────────────────┘
```

### 2. Multi-agent collaboration mechanism

TradingAgents The core innovation is**Multi-agent debate mechanism**: 

**agent role**: 
- 🔍 **Researcher**: Collect and organize information
- 📊 **Analyst**: Conduct in-depth analysis
- 💼 **Research Integrator**: Summary of research conclusions
- 🎯 **Risk Assessor**: Assess risks
- 👨‍💼 **Research Reviewer**: Comprehensive review of research conclusions

**Collaboration process**: 
1. Researchers collect data and information
2. Analysts analyze from different angles
3. Debate among agents
4. reach consensus or remain divided
5. Generate comprehensive analysis reports

---

## 🔬 core technology

### 1. LLM Integrate

TradingAgents Supports multiple large language models:

- **OpenAI Series**: GPT-3.5, GPT-4, GPT-4-Turbo
- **Open source model**: LLaMA, Mistral, Qwen Wait
- **API service**: Support customization LLM API

### 2. Tool system

TradingAgents Provides a wealth of stock analysis tools:

**data acquisition tool**: 
- Yahoo Finance API
- Alpha Vantage API
- Finnhub API
- Custom data source

**Analysis tools**: 
- Technical indicator calculation (MA, MACD, RSI, etc.)
- Fundamental analysis (PE, PB, ROE, etc.)
- Sentiment analysis (news, social media)
- Risk assessment (VaR, Sharpe ratio, etc.)

### 3. prompt word project

TradingAgents Use a well-designed prompt word template:

```python
# Analyst Prompt Word Examples
ANALYST_PROMPT = """
You are a senior stock analyst who is good at analyzing stocks from multiple dimensions.

Task: Analyze the investment value of the following stocks

Stock information:
{stock_info}

Market data:
{market_data}

Please analyze it from the following perspectives:
1. fundamental analysis
2. Technical analysis
3. Industry status
4. risk factors

Finally, the research conclusion tendency (optimistic/cautious/neutral) and reasons are given, and no trading instructions such as buy/sell are output. This system is positioned as a research aid, and all output is for research reference only and does not constitute investment advice.
"""
```

---

## 🌟 Core features

### 1. Open source and extensible

- ✅ Open source core components (Apache License 2.0)
- 🔒 Proprietary components follow the project root license instructions (see LICENSE and LICENSING.md)
- ✅ Modular design, easy to expand
- ✅ Support custom agents and tools
- ✅ Active community support

### 2. Multiple market support

- 🇺🇸 US stock market
- 🇨🇳 A Stock market (TradingAgents-CN enhanced)
- 🇭🇰 Hong Kong stock market

### 3. Flexible deployment methods

- 💻 local deployment
- ☁️ Cloud deployment
- 🐳 Docker Containerization
- 🌐 Web interface

---

## 📊 TradingAgents-CN improvements

TradingAgents-CN A large number of localization improvements have been made based on TradingAgents:

### 1. Chinese market adaptation

- ✅ Supports A-share and Hong Kong stock data sources
- ✅ Integrate domestic data interfaces such as Tushare and AKShare
- ✅ Adapt to Chinese market trading rules
- ✅ Chinese prompt word optimization

### 2. User experience optimization

- ✅ Modern web interface
- ✅ Real-time data synchronization
- ✅ Simulated trading function
- ✅ Stock Screening Tool

### 3. Deployment simplified

- ✅ One-click installation script
- ✅ Green version (Windows portable version)
- ✅ Docker mirror
- ✅ Detailed Chinese documentation

### 4. Function enhancement

- ✅ Multiple data sources support
- ✅ Scheduled tasks
- ✅ Cache optimization
- ✅ Log management
- ✅ User permission system

---

## 📖 academic papers

### Paper abstract

TradingAgents The paper proposes an open source AI agent platform for stock analysis and trading. The platform leverages the capabilities of large language models to achieve high-quality stock analysis through a multi-agent collaboration mechanism.

**Main contributions**: 

1. **multi-agent framework**: Proposed a role-based multi-agent collaboration framework
2. **Tool system**: Designed a scalable stock analysis tool system
3. **Experimental verification**: Experimentally proven effectiveness of multi-agent debate
4. **Open source platform**: Provides a complete open source implementation

### Paper download

- 📄 [English original PDF](/research-papers/TradingAgents_paper.pdf)
- 📄 [Chinese translation version](../../paper/TradingAgents_Chinese version of the paper.md)
- 📄 [arXiv Online version](https://arxiv.org/pdf/2412.20138)
- 📄 [Paper interpretation](./paper-guide.md)

---

## 🔗 Related resources

### official resources

- 🌐 [TradingAgents (source project)](https://github.com/TauricResearch/TradingAgents)
- 📚 [TradingAgents Documentation](https://github.com/TauricResearch/TradingAgents)

### TradingAgents-CN Resources

- 🌐 [GitHub warehouse](https://github.com/hsliuping/TradingAgents-CN)
- 📚 [Chinese documentation](../../README.md)
- 💬 [Problem feedback](https://github.com/hsliuping/TradingAgents-CN/issues)

### learning resources

- 📖 [Detailed explanation of multi-agent systems](../04-analysis-principles/multi-agent-system.md)

---

## 💡 Summary

TradingAgents It is an innovative open source stock analysis platform that provides new solutions for stock analysis through multi-agent collaboration and large language models. TradingAgents-CN has carried out in-depth localization on this basis, making it more suitable for the Chinese market and Chinese users.

**core value**: 
- 🎯 Combination of academic research and practical application
- 🎯 The power of open source communities
- 🎯 AI Innovative application of technology in stock analysis
- 🎯 Lower the threshold for stock analysis

---

## ❓ FAQ

**Q: TradingAgents What is the difference between it and TradingAgents-CN?**

A: TradingAgents-CN It is the Chinese localized version of TradingAgents, which adds support for the Chinese market, optimizes the user experience, and provides more complete Chinese documentation.

**Q: Can it be used commercially?**

A: Can. Both TradingAgents and TradingAgents-CN adopt open source licenses, allowing commercial use. But please pay attention to comply with relevant financial regulations.

**Q: How to contribute code?**

A: Contributions welcome! Please visit the GitHub repository and submit a Pull Request or Issue.

---

**Read next**: 
- 📖 [Chinese version of the paper](../../paper/TradingAgents_Chinese version of the paper.md)
- 📖 [multi-agent system](../04-analysis-principles/multi-agent-system.md)
- 📖 [quick start](../07-tutorials/getting-started.md)

