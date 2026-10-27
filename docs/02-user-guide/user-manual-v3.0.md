# TradingAgents-CN v3.0 Complete user manual

> Version:v3.0 | Update date:2026-07-25 | Applicable objects: new users and advanced users
>
> TradingAgents-CN Pro It is a multi-agent investment research platform that connects the entire investment research process through natural language dialogue, programmable analysis workflows and scalable Agent/Skill workshops.

---

## Directory

- [v3.0 Panorama of analytical capabilities](#v30-Panorama of analytical capabilities)
- [Quick introduction (30 seconds to get started)](#Quickly learn how to get started in 30 seconds)
- [Learning path (from beginner to proficient)](#Learning path from beginner to proficient)
- [What the system can do for you](#What the system can do for you)
  - [v3.0 Governance capabilities (making AI no longer a black box)](#v30-Governance capabilities make -ai- no longer a black box)
- [Chapter 1 Installation and Deployment](#Chapter 1-Installation and Deployment)
  - [1.1 Windows Installation package deployment](#11-windows-Installation package deployment)
  - [1.2 Docker deploy](#12-docker-deploy)
  - [1.3 Deployment verification](#13-Deployment verification)
  - [1.4 JD Cloud cooperation version deployment (optional)](#14-JD Cloud cooperation version deployment is optional)
- [Chapter 2 First Configuration](#Chapter 2 - First time configuration)
  - [2.1 API Key configuration](#21-api-Key configuration)
  - [2.2 System initialization](#22-System initialization)
  - [2.4 User Guide](#24-User Guide-guide)
- [Chapter 3 Basic Functions](#Chapter 3-Basic Functions)
  - [3.1 Dashboard](#31-Dashboard-dashboard)
  - [3.2 single stock research](#32-single stock research-analysissingle)
  - [3.3 research report](#33-research report-reports)
  - [3.4 stock screen](#34-stock screen-screening)
  - [3.5 Stock Watchlist](#35-Stock Watchlist-favorites)
  - [3.6 mission center](#36-mission center-tasksunified)
  - [3.7 Stock details page](#37-Stock details page-stockscode)
- [Chapter 4 Trading Function](#Chapter 4 - Trading Functions)
  - [4.1 simulated trading](#41-simulated trading-paper)
  - [4.2 Position research](#42-Position research-portfolio)
  - [4.3 Operation review](#43-Operation review-review)
  - [4.4 trading plan](#44-trading plan-trading-system)
- [Chapter 5 Intelligent Assistant](#Chapter 5 - Intelligent Assistant)
  - [5.1 AI Conversation Assistant](#51-ai-Conversation Assistant-assistant)
  - [5.2 AI memory](#52-ai-memory-memory)
- [Chapter 6 Advanced Functions](#Chapter 6 - Advanced Functions)
  - [6.1 Analysis flow](#61-Analysis flow-workflow)
  - [6.1.1 process management](#611-process management)
  - [6.1.2 AI workflow architect](#612-ai-workflow architect)
  - [6.1.3 Tool configuration](#613-Tool configuration)
  - [6.1.4 Agent workshop](#614-agent-workshop)
  - [6.1.5 Skill Center](#615-skill-Center)
  - [6.1.6 MCP server](#616-mcp-server)
  - [6.2 Agent Workshop (independent entrance)](#62-agent-Independent entrance to the workshop)
  - [6.3 Skill Center (independent entrance)](#63-skill-Central independent entrance)
  - [6.4 Batch analysis](#64-Batch analysis-analysisbatch)
  - [6.5 timing analysis](#65-timing analysis)
    - [6.5.1 Timed analysis grouping](#651-Timed analysis grouping-settingswatchlist-groups)
    - [6.5.2 Timing analysis configuration](#652-Timing analysis configuration-settingsscheduled-analysis)
  - [6.6 General Research (/analysis/general)](#66-general studies analysisgeneral)
- [Chapter 7 Learning Center](#Chapter 7-Learning Center-learning)
- [Chapter 8 System Management](#Chapter 8 - System Management)
  - [8.1 Configuration management](#81-Configuration management)
  - [8.2 Database management](#82-Database management)
  - [8.3 Data synchronization](#83-Data synchronization)
  - [8.4 scheduled tasks](#84-scheduled tasks)
  - [8.5 Log management](#85-Log management)
  - [8.6 Competency Index](#86-Competency Index)
  - [8.7 Cache management](#87-Cache management)
  - [8.8 Data import management](#88-Data import management-settingsdata-import)
  - [8.9 Social media message management](#89-Social media message management-settingssocial-media)
  - [8.10 System update](#810-System update-settingsupdate)
  - [8.11 prompt word template](#811-prompt word template-settingstemplates)
  - [8.12 Injection strategy management](#812-Injection strategy management-settingsprompt-policies)
  - [8.13 Prompt design assistant](#813-prompt-design assistant-settingsprompt-design)
  - [8.14 Industry/Stock Allocation](#814-Industry stock allocation-settingsanalysis-profiles)
  - [8.15 usage statistics](#815-usage statistics-settingsusage)
- [Chapter 9 Personal Settings](#Chapter 9 - Personal Settings-settings)
- [Chapter 10 Frequently Asked Questions (FAQ)](#Chapter 10 - Frequently Asked Questions faq)
  - [Q13: What is the difference between the JD Cloud Cooperation Edition and the Standard Edition?](#q13 What is the difference between JD Cloud Cooperation Edition and Standard Edition?)
  - [Q14: JD Cloud Edition Analysis Task Report 429 Speed Limit Error What should I do?](#q14 Jingdong Cloud version analysis task report-429-speed limit error what to do)
- [Chapter 11 Best Practices](#Chapter 11 - Best Practices)
  - [11.1 From installation to first analysis](#111-From installation to first analysis)
  - [11.2 Daily research workflow](#112-Daily research workflow)
  - [11.3 cost control practices](#113-cost control practices)
  - [11.4 In-depth use: customized workflow, Agent and Skill](#114-In-depth use of custom workflow agents-and-skill)
  - [11.5 Data management practices](#115-Data management practices)
  - [11.6 safety practices](#116-safety practices)
  - [11.7 Version upgrade practice](#117-Version upgrade practice)
  - [11.8 Suggestions for using JD Cloud Cooperation Edition](#118-Suggestions for using JD Cloud Cooperation Edition)
- [Chapter 12 About (/about)](#Chapter 12 - About-about)
- [Common mistakes for newbies and how to avoid them](#Common mistakes for newbies and how to avoid them)
- [Appendix](#Appendix)

---

## About this manual

### Reading object

This manual is intended for users who are using TradingAgents-CN Pro v3.0 for the first time. Starting from installation and deployment, it will gradually introduce the use of all functional modules. Whether you are an ordinary investor or an advanced user, you can study in the order of chapters, or jump directly to the functions of interest through the table of contents.

### Advanced function identification

appearing in this manual ** (advanced features)** Identification, indicating that the function requires"Senior student"permission to use. Ordinary users can browse the relevant interfaces, but will be prompted with insufficient permissions when performing operations.

### v3.0 Release Notes

v3.0 It is a platform upgrade. The core changes include:

- Intelligent assistant from"Analysis trigger"upgraded to"Investment research collaborative portal", support 20+ Operational tools, multi-topic sessions.
- Added MCP Server open interface, which can be called by external clients such as Claude Desktop and Cursor.
- A new AI workflow architect is added to automatically plan workflows by describing requirements in natural language.
- A new Skill automatic generation system is added, and AI independently writes and verifies new tools.
- New capabilities include stock selection assistant, unified notification system (email/Feishu/DingTalk/enterprise WeChat multi-channel push), QQ Bot access and other capabilities.

---

## v3.0 Panorama of analytical capabilities

v3.0 Built-in **80+ analysis tools**, Cover **10 Category**, All things that traditionally require paid third-party tools are built into the platform. The table below is after you upgrade to v3.0**Can be used directly**Capability list (the numbers are approximate for each type of tool, see 8.6 Tool Capability Index for the complete list).

### One table to understand 80+ Analysis tools

| Category | Quantity | Typical abilities | what problem to solve |
|------|------|---------|-------------|
| **Fundamentals** | 20+ | PE/PB/ROE, Gross margin, revenue, cash flow, DCF valuation, WACC, DuPont analysis | Is this company profitable and valuable? |
| **technical aspect** | 9 | MA, RSI, KDJ, MACD, K Line patterns, chart patterns, Fibonacci, support pressure | Should you buy this stock and when? |
| **Risk detection** | 5 | Altman Z (Bankruptcy warning), Beneish M (financial report fraud), Piotroski F (financial health), Ohlson O (bankruptcy prediction), financial report fraud signal | Is this company at risk of thunderstorms? |
| **Market conditions** | 9 | Market, sector, chip distribution (profit ratio/average cost), individual stock prices, QMT access | What is the market environment now and which sectors are rising? |
| **Portfolio analysis** | 9 | Sharpe ratio, information ratio, maximum drawdown, return attribution, VaR, stress test | Is the risk of my position high and how does it contribute to the income? |
| **news sentiment** | 2 | News pull (title+Detailed dual-stage), snowball/stock bar emotions | What is the market talking about and whether the sentiment is bullish or bearish? |
| **Review analysis** | 4 | Transaction records, account information, market snapshots, attribution analysis | Why did you make/lose money last time and how to change it next time? |
| **stock selection valuation** | 5 | Multi-factor stock picking, value stock picking, PEG, Graham valuation, option pricing | Which stocks deserve further research |
| **Intelligent assistant operation** | 20+ | Trigger analysis, check reports, manage attention, manage timing, view token statistics, and view system status | No need to look for menus, just talk and operate |
| **self-build tools** | 2 | Agent Workshop, Skill Center | You can also create new analysts and tools yourself |

### 5 The most valuable ability to experience immediately

> Many of these five capabilities are practical tools already available in v2.x and enhanced in v3.0.**v3.0 The real upgrade lies in governance capabilities (traceable/verifiable/correctable)**, Analysis tools are just the foundation.

| Ability | Tool name | Usage | Applicable scenarios |
|------|--------|------|---------|
| **1. Financial report fraud detection** | `get_beneish_mscore` | Enter the stock code and get an 8-dimensional score in 5 minutes (> -1.78 Prompts possible fraud) | Must-check stocks with heavy holdings/targets of concern |
| **2. Bankruptcy Risk Assessment** | `get_altman_zscore` | 5 factor model,< 1.81 Tips on bankruptcy risk | ST Candidate/Financial Abnormal Stocks |
| **3. DCF discounted cash flow valuation** | `get_dcf_valuation` | forecast period + Perpetual period, automatically calculate how much the company is worth | Long-term value investment decisions |
| **4. K Line shape recognition** | `get_candlestick_patterns` | automatic recognition 25+ K-line patterns (hammer/engulfing/cross star/morning star/three soldiers) | Short-term timing and finding turning points |
| **5. Classic chart patterns** | `get_chart_patterns` | Head and shoulders top and bottom, double top and double bottom, triangle, flag, wedge | Judgment of medium and long-term trends |

### The data has a provenance, isn't it?"AI Guess"

The source of each data point can be found:

- **PE/PB/ROE** → Data from Tushare financial report
- **Market data** → From Tushare / QMT / AKShare real-time interface
- **News** → From the Tushare / AKShare open source news interface
- **emotions** → Prioritize analysis based on news content and user-submitted social media records
- **AI inference** → from LLM,**The system will mark which ones are AI inferences and which ones are real data.**

If it appears in the report"AI inference"Label, indicating that this conclusion is based on AI inference (not directly obtained data), please combine it with other information to judge.

### Full tool index

> 💡 **Tips**: This section is just**Capability Panorama**. How to use it specifically is explained by scenario in Chapter 5 Intelligent Assistant, Chapter 6 Analysis Flow, and 11.4 Best Practices.

If you want to know the detailed parameters and calculation methods of a specific tool:
- Valuation category (DCF/WACC/PEG/Graham)→ System management → Tool Capability Index (Section 8.6)
- Technical (MA/RSI/Pattern/Support Pressure)→ System management → Tool Capability Index (Section 8.6)
- Risk category (Altman/Beneish/Piotroski)→ System management → Tool Capability Index (Section 8.6)

---

## Quick introduction (30 seconds to get started)

**TradingAgents-CN Pro What is it?**

An AI-driven investment research platform uses multiple agents to work together to help you complete the entire research process from data collection, fundamental analysis, technical analysis to risk assessment.

**What can you do for me?**

| scene | Function | Time consuming |
|------|------|------|
| Learn about a stock quickly | Single Stock Research (Quick Analysis) | 5-10 minutes |
| In-depth research on position targets | Single Stock Research (In-depth Analysis) | 10-15 minutes |
| Analyze multiple stocks simultaneously | Batch analysis | 5-15 minutes each |
| Regularly track stock watchlists | timing analysis | Automatic execution |
| Natural language dialogue research | Smart Assistant | real time |
| Custom analysis process | Analyze Flow (Workflow Editor) | One-time configuration |
| Simulated trading verification strategy | simulated trading | real time |

**How do I start?**

1. Install and deploy the system according to Chapter 1
2. Follow Chapter 2 to complete the first configuration (API key + data source)
3. follow"User Guide" (Left navigation bar) Complete the boot configuration
4. in"single stock research"Enter the stock code in to start the first analysis

> 💡 **Tips**: Newbies are advised to use it first"3 Level-Standard Analysis"Depth, selected"market analyst"and"fundamental analyst"With two roles, you can get a complete research report in 4-8 minutes.

---

## Learning path (from beginner to proficient)

This manual is organized into 5 stages, with clear learning objectives and completion marks for each stage. It is recommended to study in order and step by step.

### Phase 1: Getting Started (Day 1)— Run through the first analysis

**target**: Complete system installation and configuration and generate the first analysis report.

| serial number | Learning content | Manual Chapter | Estimated time |
|------|---------|---------|---------|
| 1 | Install system | Chapter 1 Installation and Deployment | 30 minutes |
| 2 | Configure API keys and data sources | Chapter 2 First Configuration | 20 minutes |
| 4 | Follow the user guide to complete boot configuration | 2.4 User Guide | 15 minutes |
| 5 | Completed first single stock research | 3.2 single stock research | 10 minutes |

**✅ Done sign**: A complete analysis report is successfully generated, and you can see the comprehensive rating and analysis of each dimension.

**📋 Recommended exercises**: Choose a familiar stock (such as Kweichow Moutai 600519) and use"standard analysis"Depth, select all analysts and observe the report structure.

---

### Phase 2: Basics (Week 1)— Proficient in using core functions

**target**: Understand report content and become proficient in using core research functions.

| serial number | Learning content | Manual Chapter | Estimated time |
|------|---------|---------|---------|
| 1 | Understand dashboard layout | 3.1 Dashboard | 10 minutes |
| 2 | How to interpret study reports | 3.2 Analysis Report Interpretation Guide | 15 minutes |
| 3 | Management History Research Report | 3.3 research report | 10 minutes |
| 4 | Use stock screens to discover stocks | 3.4 stock screen | 15 minutes |
| 5 | Create a stock watchlist watchlist | 3.5 Stock Watchlist | 10 minutes |
| 6 | View task execution status | 3.6 mission center | 5 minutes |

**✅ Done sign**: Able to complete independently"Screen stocks → Join the following → single stock research → Interpret the report"The whole process.

**📋 Recommended exercises**: Use stock screening to find 3 targets in different industries, analyze them separately and then compare the report differences.

---

### Phase 3: Advancement (Weeks 2-4)— Trading features and advanced analytics

**target**: Use simulated trading to verify strategies and master batch analysis and scheduled analysis.

| serial number | Learning content | Manual Chapter | Estimated time |
|------|---------|---------|---------|
| 1 | Simulated trading operations | 4.1 simulated trading | 20 minutes |
| 2 | Position research and tracking | 4.2 Position research | 15 minutes |
| 3 | Operation review improvement strategy | 4.3 Operation review | 15 minutes |
| 4 | Develop a trading plan | 4.4 trading plan | 20 minutes |
| 5 | Conversation research using smart assistants | 5.1 AI Conversation Assistant | 15 minutes |
| 6 | Manage AI memory | 5.2 AI memory | 10 minutes |
| 7 | Analyze multiple stocks in batches | 6.4 Batch analysis | 15 minutes |
| 8 | Configure scheduled automatic analysis | 6.5 timing analysis | 20 minutes |

**✅ Done sign**: You can use simulated trading to verify strategies and configure scheduled analysis to automatically track stock watch lists.

**📋 Recommended exercises**: Establish a focus group of 5 stocks, configure daily after-hours timed analysis, and observe the report changes during the week.

---

### Phase 4: Advanced (Months 1-2)— Custom workflows and Agent

**target**: Create custom workflows, agents, and skills for personalized analysis.

| serial number | Learning content | Manual Chapter | Estimated time |
|------|---------|---------|---------|
| 1 | Understand workflow concepts | 6.1 Analysis flow | 20 minutes |
| 2 | Generate processes using AI Workflow Architect | 6.1.2 AI workflow architect | 30 minutes |
| 3 | Configuration tool capabilities | 6.1.3 Tool configuration | 15 minutes |
| 4 | Create customizations in the Agent Workshop Agent | 6.1.4 Agent workshop | 40 minutes |
| 5 | Create customizations in Skill Center Skill | 6.1.5 Skill Center | 40 minutes |
| 6 | Use general research to explore non-individual stock topics | 6.6 general studies | 20 minutes |
| 7 | Learning Center Advanced Courses | Chapter 7 Learning Center | continue |

**✅ Done sign**: You can use AI Workflow Architect to generate a custom process, or manually create a workflow that includes a custom Agent.

**📋 Recommended exercises**: Describe in natural language"I need an analytical process that focuses on ESG scoring", Let the AI ​​workflow architect generate and then use the process in single-strand research.

---

### Stage 5: Expert (ongoing)— System Optimization and Best Practices

**target**: Optimize system configuration, control costs, and ensure data quality.

| serial number | Learning content | Manual Chapter | Estimated time |
|------|---------|---------|---------|
| 1 | System configuration optimization | Chapter 8 System Management | on demand |
| 2 | Personal preferences | Chapter 9 Personal Settings | 15 minutes |
| 3 | cost control practices | 11.3 cost control practices | 15 minutes |
| 4 | Data management practices | 11.5 Data management practices | 15 minutes |
| 5 | safety practices | 11.6 safety practices | 10 minutes |
| 6 | Prompt word template optimization | 8.11 prompt word template | 30 minutes |
| 7 | MCP Server integration | 6.1.6 MCP server | on demand |
| 8 | Channel push configuration | 9.8 Channel push | 20 minutes |

**✅ Done sign**: Able to optimize system configuration according to own needs and establish stable and efficient research workflow.

**📋 Recommended exercises**: Configure Feishu/DingTalk channel push to automatically push scheduled analysis results to the work group.

---

### Learning path summary

| stage | duration | core competencies | key chapters |
|------|------|---------|---------|
| 🟢 Getting Started | Day 1 | Run through the first analysis | Chapter 1 and 2 + 3.2 |
| 🔵 Basics | Week 1 | Proficient in core functions | Chapter 3 + Report interpretation |
| 🟡 Advanced | Weeks 2-4 | transaction+Advanced analytics | Chapters 4, 5, and 6 (parts) |
| 🟠 Advanced | Month 1-2 | Custom workflow | 6.1-6.6 + Chapter 7 |
| 🔴 expert | continue | System optimization | Chapter 8 and 9 + Chapter 11 |

> 💡 **Tips**: It is not necessary to study in strict order of stages. If you have specific needs (for example, you only want to use timing analysis), you can jump directly to the corresponding chapter. However, it is recommended to complete at least Phase 1 and Phase 2 to ensure that you understand the basic concepts.

---

## What the system can do for you

This system is a**Investment research aids**, Through AI multi-agent collaboration, we help you organize information and provide multi-dimensional analysis references. The following is an objective description of the specific help each function can provide.

### Comparison of functions and practical help

| Function | What can I do for you? | What not to do |
|------|------------|-----------|
| **single stock research** | Organize a stock's technical, fundamental, news events, market sentiment and other multi-dimensional information and generate structured reports to help you save time in collecting and organizing information by yourself | It is impossible to predict the rise or fall of the stock price, and it cannot give a conclusion that it will definitely rise or fall, and the analysis results may be biased. |
| **Batch analysis** | Perform analysis on multiple individual stocks at the same time, saving you time on individual operations and eliminating horizontal comparisons between stocks. | It cannot replace manual judgment. The analysis results require you to verify key data one by one. |
| **timing analysis** | Automatically perform analysis at set times to help you track your stock watch list regularly, eliminating the need for manual operations every day | Automatic trading is not possible, and real-time intraday warnings are not available (timed execution is delayed) |
| **simulated trading** | Provide a virtual capital environment to help you verify strategic assumptions, record simulated operating points, and calculate profits and losses in learning and research | The simulation environment does not consider real market factors such as slippage and insufficient liquidity. The results are only for learning and research reference and do not constitute investment advice. |
| **Position research** | Conduct in-depth analysis of the stocks you already hold to help you sort out the reference basis for whether to continue tracking. | There is no guarantee that the analysis conclusion is correct, and investment decisions are your own responsibility. |
| **Operation review** | Review historical transaction records to help you summarize regular issues in the operating model | Past operating experience cannot guarantee future returns, and review conclusions are for reference only. |
| **Smart Assistant** | Quickly query stock information, trigger analysis tasks, and reduce operating steps through natural language | AI The answer may be wrong. For key data (such as financial figures), please refer to the official announcement. |
| **stock screen** | Screen stocks in batches based on price-to-earning ratio, price-to-book ratio, growth rate and other conditions to narrow the scope of research | The filtering conditions are rough, and the filtering results still need to be studied in depth one by one. |
| **Custom workflow** | Customize analysis dimensions according to your own concerns (such as focusing on ESG, cash flow, etc.) | A certain learning cost is required, and the analysis quality of the custom Agent depends on the prompt word design. |
| **Channel push** | After the analysis is completed, it will be automatically pushed to Feishu/DingTalk/email to help you get the results in time. | It is just a notification tool and does not change the analysis results themselves. |

### Actual usage scenarios

**Scenario 1: Before preparing to research a stock**

1. use"single stock research"Generate a standard analysis report to understand the fundamentals, technical aspects, and risk points of the stock
2. Important reading"risk scenario research"Part, understand prudent scenarios and avoid unilateral optimism
3. use"simulated trading"Record hypothetical positions and observe them for a period of time to verify research hypotheses

**Scenario 2: Tracking stocks you already own**

1. Add holding stocks to"watchlist"Group
2. Configuration"timing analysis", Automatic analysis once a week after the market opens
3. turn on"Channel push", After the analysis is completed, it will be automatically pushed to the mobile phone.
4. Check regularly"Position research", Track changes in fundamentals

**Scenario 3: Discover targets from the industry**

1. use"stock screen"By industry and financial indicators such as ROE>15%) Narrow down the scope
2. use"Batch analysis"Quickly analyze filter results
3. Reuse targets with potential"single stock research"Do in-depth analysis

### Important reminder

- **The system provides information collection and multi-dimensional analysis reference, and does not constitute investment advice.**
- AI The model may contain data deviations or logic errors. For key information, please refer to the announcements and regulatory disclosures of listed companies.
- The risk of investment decisions is borne by you, and the system cannot guarantee any investment returns.
- It is recommended to use system analysis as one of the research references and make independent judgments based on information from multiple parties.

### v3.0 Governance capabilities (making AI no longer a black box)

v3.0 in"Let AI run"On the basis of, the key points are solved"**Let AI errors be checked and corrected**": 

- **traceable**: Each conclusion in the report can be traced back to which Agent read what data, used what tools, and returned what results.
- **Verifiable**: Agent When the output does not conform to the format, the system will mark it instead of quietly letting it go.
- **Correctable**: The pitfalls you have stepped on will be remembered by the system, and similar errors will be automatically intercepted next time.
- **auditable**: All LLM calls are logged for easy review

For details on how to use it, see:
- **Execution trace view** → 3.6 mission center
- **Assertion Management (Advanced)** → 8.1 Configuration management

---

## Chapter 1 Installation and Deployment

TradingAgents-CN Pro v3.0 Two main deployment methods are provided:**Windows Installation package** (Suitable for ordinary users) and **Docker deploy** (Suitable for advanced users and server environments).

### v3.0 Environment port convention

| service | port | Description |
|------|------|------|
| MongoDB | 27019 | v3.0 Dedicated database port |
| Redis | 6381 | v3.0 Dedicated cache port |
| Backend services | 8002 | API service port |
| Front-end interface | 8082 | Web access port |
| Docker Project name | `ta-v3` | v3.0 Container orchestration project name |

> Note: v3.0, v2.1.0, and v2.0.1 use independent directories, independent ports, and independent data volumes, and can coexist on the same machine without interfering with each other.

### 1.1 Windows Installation package deployment

#### Function description

Windows The installation package is the simplest deployment method for ordinary users. There is no need to manually install the Python environment and dependencies. You can use it by double-clicking the installation. The installation includes an embedded Python runtime and does not pollute the system environment.

#### Operation steps

1. **Get the installation package**
   - Main channel: Baidu Netdisk + QQ Group download
   - Alternate channel: Alibaba Cloud OSS / Tencent Cloud COS accelerated download
   - Archive channel: GitHub Releases (historical version)

2. **System requirements**
   - Operating system: Windows 10 64-bit and above (Windows 11 recommended)
   - Memory: 8GB and above
   - Disk space: At least 5GB free space
   - Requires .NET Framework 4.7.2 and above to be installed (the system usually comes with it)

3. **Installation process**
   - Double click `TradingAgentsCN-Pro-v3.0-setup.exe` Start the installation wizard
   - Select the installation directory (it is recommended to use the default path and avoid Chinese characters and spaces)
   - Check"Create desktop shortcut"
   - Click"Installation"Wait for installation to complete
   - After installation is complete, you can choose"Start now"

4. **first start**
   - Double-click the desktop shortcut to start the service
   - The system will automatically start the back-end service (port 8002) and front-end service (port 8082)
   - Browser opens automatically `http://localhost:8082` You can enter the system

5. **Service management**
   - There is a TradingAgents icon in the system tray. Right-click to stop/restart the service.
   - Also available via"start menu → TradingAgentsCN Pro → Service management"Operation

#### Things to note

- The installation path must not contain Chinese characters, spaces, or special characters, otherwise the service may fail to start.
- If port 8002 or 8082 is occupied, the installer will prompt you to release the port in the firewall or service management.
- The first startup requires initializing the database, which may take 1-2 minutes, please be patient.
- Anti-virus software may report false positives, please add the installation directory to the whitelist.

### 1.2 Docker deploy

#### Function description

Docker The deployment is suitable for advanced users and server environments, providing advantages such as environment isolation, one-click start and stop, and easy upgrade and maintenance. v3.0 uses independent Docker project name `ta-v3`, Completely isolated from v2.x.

#### Operation steps

1. **Prerequisites**

   | components | Minimum version | Recommended version |
   |------|---------|----------|
   | Docker | 20.0+ | Latest version |
   | Docker Compose | 2.0+ | Latest version |
   | memory | 4GB | 8GB+ |
   | disk space | 10GB | 20GB+ |

2. **Installation Docker**
   - Windows: Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop), After starting, make sure the status is Running.
   - Linux: Reference [Docker Official installation guide](https://docs.docker.com/engine/install/). 

3. **Get project files**
   ```bash
   git clone https://github.com/hsliuping/TradingAgents-CN.git
   cd TradingAgents-CN
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` file and fill in your API key (see [Chapter 2 First Configuration](#Chapter 2 - First time configuration)) . 

5. **Launch using a pre-built image (recommended)**
   ```bash
   # Pull v3.0 image
   docker pull hsliuping/tradingagents-backend:3-latest
   docker pull hsliuping/tradingagents-frontend:3-latest

   # Start the service (use ta-v3 project name)
   docker-compose -p ta-v3 up -d
   ```

6. **Build the image locally (optional)**
   ```bash
   # AMD64 Architecture (Intel/AMD)
   ./scripts/build-amd64.sh

   # ARM64 Architecture (Apple Silicon / ARM Server)
   ./scripts/build-arm64.sh
   ```

7. **Access the app**
   - Browser opens:`http://localhost:8082`

8. **Commonly used Docker commands**
   ```bash
   # Check service status
   docker-compose -p ta-v3 ps

   # View log
   docker-compose -p ta-v3 logs -f backend
   docker-compose -p ta-v3 logs -f frontend

   # Stop service
   docker-compose -p ta-v3 down

   # Restart service
   docker-compose -p ta-v3 restart

   # Upgrade image
   docker-compose -p ta-v3 pull
   docker-compose -p ta-v3 up -d
   ```

#### Things to note

- Docker Mirror tag usage `3-latest` (rolling update) or precise version number (e.g. `3.0.0`, immutable). It is recommended to use precise version numbers in production environments.
- Data persistence is implemented through Docker Volume, and no data will be lost when upgrading the image.
- v3.0 Different from the Docker project name of v2.x (`ta-v3` vs `ta-v210` vs `ta-v201`) , Do not affect each other.
- When using Docker Desktop on Windows, make sure the WSL 2 backend is enabled.
- If you encounter MongoDB connection issues, please check whether port 27019 is occupied by other services.

### 1.3 Deployment verification

#### Function description

After the deployment is complete, use the following steps to verify that the system is functioning properly.

#### Operation steps

1. **Check service port**
   - Open browser to visit `http://localhost:8082`, You should see the login page.
   - visit `http://localhost:8002/docs`, You should see the backend API documentation (Swagger).

2. **Check database connection**
   - Log in to the system and enter"settings → System management → database", Check whether the connection status is"Connected". 

3. **Complete first configuration**
   - Follow the instructions to complete the API key configuration (see next chapter for details).

4. **Run test analysis**
   - in"single stock research"Enter a common stock symbol (such as `600519`) , Perform an analysis to confirm that the entire process is smooth.

#### Things to note

- If the front-end is accessible but the API reports an error, it is usually because the back-end service has not been fully started. Please wait 30 seconds and try again.
- When you run the analysis for the first time, you need to download the data dependencies. It is normal for it to take a long time.

### 1.4 JD Cloud cooperation version deployment (optional)

#### Function description

JD Cloud Cooperation Edition is a customized version of TradingAgents-CN Pro that cooperates with JD Cloud Model Service. Compared with the standard version, the JD Cloud version injects large models and data source configurations through environment variables. Users do not need to manually configure the interface and can be used out of the box.

**The core differences between JD Cloud Edition and Standard Edition:**

| Comparative item | Standard Edition | Jingdong cloud version |
|--------|--------|---------|
| Large model configuration | Users manually configure Provider and API Key | Through environment variable injection, the interface hides the configuration entry |
| Available models | Support multiple suppliers (Tongyi Qianwen, DeepSeek, Zhipu, etc.) | Only models provided by JD Cloud (GLM-5/GLM-5.1/GLM-5.2/DeepSeek-V4-Flash) |
| data source | support Tushare / AKShare / BaoStock | Tushare only (Token provided by JD Cloud) |
| Embedding | User selects Embedding model | Fixed use Qwen3-Embedding-8B |
| first start | Requires manual configuration of API key | Automatically initialize database from environment variables |
| LLM speed limit | No special restrictions | Built-in 429 retry + Concurrency reduction mechanism |

#### Environment variable configuration

Jingdong Cloud version drives all configurations through the following environment variables, which are deployed during deployment. `.env` Settings in the file:

| environment variables | Required | Description | Example value |
|---------|------|------|--------|
| `JDYUN_MODE` | Yes | Jingdong cloud mode switch, must be `true` | `true` |
| `OPENAI_API_BASE` | Yes | JD Cloud Model Service Address | `https://modelservice.jdcloud.com/v1` |
| `OPENAI_API_KEY` | Yes | Provided by JD Cloud API Key | `your_jdyun_api_key` |
| `OPENAI_MODEL` | Yes | Default dialogue model | `GLM-5` |
| `EMBEDDING_MODEL` | Yes | Embedding model | `Qwen3-Embedding-8B` |
| `TUSHARE_TOKEN` | Yes | Tushare data source Token | `your_tushare_token` |

**LLM Speed limit configuration (optional, the default value is optimized and usually does not need to be modified):**

| environment variables | Default value | Description |
|---------|--------|------|
| `JDYUN_LLM_MAX_RETRIES` | 8 | LLM The maximum number of retries when the call encounters the 429 rate limit (exponential backoff:1s→2s→4s→...→128s)  |
| `JDYUN_LLM_MAX_RPM` | 30 | LLM Maximum number of requests per minute |
| `JDYUN_BATCH_MAX_CONCURRENT` | 1 | Maximum number of concurrent batch analyzes (reduced to 1 to avoid speed limit) |
| `JDYUN_WORKER_MAX_CONCURRENT` | 1 | Worker Maximum number of concurrent tasks |
| `JDYUN_STOCK_INTERVAL_SECONDS` | 10 | The number of seconds between regular analysis of stocks |

#### Docker Deployment steps

1. **Prepare configuration file**
   - Copy `.env.jdyun.example` for `.env`, Fill in the credentials provided by JD Cloud:
     ```
     JDYUN_MODE=true
     OPENAI_API_BASE=https://modelservice.jdcloud.com/v1
     OPENAI_API_KEY=your_jdyun_api_key
     OPENAI_MODEL=GLM-5
     EMBEDDING_MODEL=Qwen3-Embedding-8B
     TUSHARE_TOKEN=your_tushare_token
     ```

2. **Start service**
   ```bash
   docker-compose -f docker-compose.jdyun.yml up -d
   ```
   - Service port: front end `8082`, backend `8002`, MongoDB `27019`, Redis `6381`

3. **access system**
   - Browser opens `http://your-server:8082`
   - The system automatically initializes the database from environment variables when starting for the first time (writing to JD Cloud Provider, model configuration, Tushare data source)
   - No need to manually configure API keys, just get started

#### Portable version deployment steps

1. **Package JD Cloud Version**
   ```powershell
   .\scripts\deployment\build_pro_package.ps1 -Edition jdyun
   ```
   - The packaging script will automatically use `--mode jdyun` Build the front end, inject `VITE_JDYUN_MODE=true`
   - generate `.env.jdyun.example` Configuration template

2. **Deploy to target machine**
   - Copy the packaged portable version directory to the target machine
   - Edit `.env` file, fill in the credentials provided by JD Cloud
   - Run startup script

#### Start the development environment

Used in development environment `start_dev.ps1` The script starts JD Cloud mode:

```powershell
.\start_dev.ps1 docker 3.0      # start MongoDB + Redis
.\start_dev.ps1 backend 3.0 -jdyun   # Start the backend in JD Cloud mode
.\start_dev.ps1 frontend 3.0 -jdyun  # Start the front end in JD Cloud mode
```

#### Things to note

- Jingdong cloud version**Hiding the configuration interface of large models and data sources**, Users cannot modify these configurations on the interface and can only adjust them through environment variables.
- Jingdong cloud version**Provider and data source additions, deletions, and modifications are disabled API**, Prevent accidental operations from overwriting environment variable configuration.
- Jingdong cloud version built-in **LLM speed limit response mechanism**: The concurrency number of batch analysis and scheduled analysis is automatically reduced to 1, the interval between tasks is 10 seconds, and exponential backoff retries up to 8 times when encountering the 429 speed limit.
- The available models are limited to 4 provided by JD Cloud:`GLM-5`, `GLM-5.1`, `GLM-5.2`, `DeepSeek-V4-Flash`, Users can switch during analysis.
- If LLM speed limit occurs frequently, you can increase the speed appropriately. `JDYUN_STOCK_INTERVAL_SECONDS` (such as 20 or 30 seconds).

---

## Chapter 2 First Configuration

### 2.1 API Key configuration

#### Function description

TradingAgents-CN Pro A Large Language Model (LLM) API key needs to be configured to drive intelligent analysis. The system supports multiple model providers, and you can choose one or a combination of them.

> **JD Cloud cooperative version users**: There is no need to perform this section. Jingdong Cloud version automatically configures large models and data sources through environment variables, and automatically initializes when it is first started. You can jump directly to [2.2 System initialization](#22-System initialization). 

#### Operation steps

1. **Enter the configuration page**
   - After logging in to the system, click on the left navigation bar"settings → System configuration", Or follow the guidance prompts to enter.

2. **Choose an LLM provider** (Recommended to choose one)

   **DeepSeek (Recommended, best value for money)**
   - Registered address:https://platform.deepseek.com/
   - Cost: approx. ¥1/10,000 tokens, new users have free quota
   - Configuration items:`DEEPSEEK_API_KEY`

   **Tongyi Qianwen / DashScope (domestic and stable)**
   - Registered address:https://dashscope.aliyun.com/
   - Cost: Pay by volume, with free quota
   - Configuration items:`DASHSCOPE_API_KEY`

   **OpenAI (powerful function)**
   - Registered address:https://platform.openai.com/
   - Cost: Billed based on usage, payable in U.S. dollars
   - Configuration items:`OPENAI_API_KEY`

   **Google AI / Gemini**
   - Registered address:https://aistudio.google.com/
   - Configuration items:`GOOGLE_API_KEY`

   **SiliconFlow (aggregation platform)**
   - Registered address:https://siliconflow.cn/
   - Configuration items:`SILICONFLOW_API_KEY`

3. **Configure data source API** (Optional but recommended)
   - **Tushare** (A Stock data recommendation):https://tushare.pro/ Register to obtain token and configure `TUSHARE_TOKEN`

4. **Configure in the interface**
   - "settings → System configuration"Find the corresponding configuration item and fill in the key.
   - Click"test connection"button to verify key validity.
   - Save configuration.

> **Note**: Modify directly `.env` The file is only compatible with the old version, v3.0 is recommended."settings → System configuration"The interface is configured.

5. **Set model priority**
   - in"settings → System configuration"Default model and analysis preferences can be set in .
   - Supports specifying different models for different analysts (such as fundamentals, news, risk) to balance cost and effectiveness.

#### Things to note

- API The key is stored in the database encrypted and will not be displayed in plain text.
- It is recommended to configure two LLM providers as active and backup at the same time, and automatically switch when the active model is unavailable.
- DeepSeek He Tongyi Qianwen has good support for the Chinese financial context and is recommended as the main model.
- Tushare There are different interface permissions according to the points level. New users with low points may not be able to obtain some data.
- After configuring the key, please click"test connection"Confirm that it is valid, otherwise the analysis task will be interrupted due to model call failure.

### 2.2 System initialization

#### Function description

After the first deployment, the system has automatically created a default administrator account and completed database initialization. Users only need to log in with the default account, complete basic data synchronization and data source configuration, and then start using it.

#### Operation steps

1. **Log in with default account**
   - The system has preset a default administrator account.
   - Username:`admin`
   - Password:`admin123`
   - After logging in for the first time, please immediately"settings → Personal center"Change the default password.

2. **Initialize database**
   - The system automatically creates the necessary collections and indexes.
   - Available at"settings → System management → database"Check the initialization status.

3. **Synchronize basic data**
   - enter"settings → System management → Data synchronization". 
   - Click"Initialize basic stock data", Synchronize the stock list of A shares.
   - This process may take 10-30 minutes, depending on network conditions.

4. **Configure data source**
   - in"settings → System configuration → data source"Select the main data source.
   - A We recommend Tushare, which can configure multiple data sources to back up each other.

5. **Check system status**
   - enter"Dashboard", Check whether the system status cards are all green.

#### Things to note

- The default password is only used for first login, please be sure to change it as soon as possible.
- Basic data synchronization is a prerequisite for the normal operation of subsequent analysis functions and must be completed.
- If synchronization fails, click"Try again"Or check network and API quotas.

### 2.4 User Guide (/guide)

#### Function description

The user guide is the system's built-in guided initial setup wizard, located on the left navigation bar"User Guide"menu. Help new users complete the entire process from API key configuration to completing their first AI research through step-by-step guidance, which is suitable for first-time users to follow.

#### Guided steps

The user guide adopts the form of step-by-step guide to complete the initial configuration step by step:

1. **Get the big model API key**
   - Explain how to obtain the API key of LLM such as DeepSeek / Tongyi Qianwen / OpenAI.
   - Provide registration links and precautions for each platform.
   - Click"Go to configuration"Jump to the system configuration page.

2. **Get data source API key**
   - Explain how to register a Tushare account and obtain Token.
   - Prompt the differences in permissions at different points levels.
   - Click"Go to configuration"Jump to data source configuration.

3. **Fill in the Token configuration**
   - The guide will populate the obtained API key into the system configuration.
   - After the configuration is completed, click"test connection"verify.

5. **Sync stock data**
   - Guide the initialization and synchronization of basic stock data.
   - Describe the synchronization scope and estimated time.
   - Click"Go to sync"Jump to the data synchronization page.

6. **Search and add stocks to watchlist**
   - Guide to add stocks of interest to your watchlist.
   - Provides search and grouping operation guidance.

7. **Complete your first study**
   - Navigate to single stock research, select analysis dimensions and start analysis.
   - View the research report when completed.

#### Operation steps

1. After logging in to the system, click on the left navigation bar"User Guide". 
2. Follow the steps in the order of the steps, and each step will be automatically marked as completed after completion.
3. Provided for each step"Go to operation"button to jump directly to the corresponding function page.
4. You can return to the user guide at any time to review your progress, and completed steps will remain marked.

#### Things to note

- The user guide is only a guide and does not affect the use of system functions and can be skipped at any time.
- Existing users who have completed the initial configuration no longer need to follow this guide.
- Step progress is stored locally in the browser and will be reset after clearing browser data.

---

## Chapter 3 Basic Functions

This chapter introduces the basic functional modules that are most frequently used in daily life, including dashboards, single stock research, research reports, stock screening, watch lists, and task centers.

### 3.1 Dashboard (/dashboard)

#### Function description

The dashboard is the default homepage after logging in. It provides system readiness guidance, quick function entry, recent analysis records and stock watch list overview, helping users quickly understand the system configuration status and enter commonly used functions with one click.

#### Interface composition

- **System readiness boot card**: Display the system configuration progress in the form of steps (configuration data source → Configure large model → Synchronize data), unfinished steps can be clicked"Go to settings"Jump to the corresponding configuration page.
- **Quick operation area**: Quick jump entrance to common functions such as single stock research, batch analysis, stock screening, task center, position research, review analysis, trading plan, etc.
- **Recent analysis area**: Display the latest analysis tasks in table form, including stock code, name, status, creation time, support"View"and"Download"operation.
- **Stock Watchlist Overview**: Display the stocks in the watch list, support"Add to study list"Quickly initiate analysis.

#### Operation steps

1. Automatically enter the dashboard after logging into the system.
2. When used for the first time, according to"System readiness boot card"Complete data source configuration, large model configuration and data synchronization.
3. Click"Quick operation area"The function card can jump directly to the corresponding function page.
4. in"recent analysis"Click in the form"View"button to view the full report; click"Download"Reports can be exported.
5. in"Stock Watchlist Overview"middle click"Add to study list", Single stock analysis can be quickly initiated.

#### Things to note

- The system readiness guide card displays the completion status after all configuration steps are completed.
- When using it for the first time, it is recommended to complete the basic configuration according to the guide card before conducting stock analysis.

### 3.2 Single Stock Research (/analysis/single)

#### Function description

Single stock research is the core function of the system. Enter a stock code, select the required analysis dimension and depth of analysis, and the system will call multiple AI analysts to collaboratively complete in-depth analysis and generate a structured research report.

#### supported markets

- **A stock market**: Shanghai and Shenzhen Main Board, GEM, Science and Technology Innovation Board, Beijing Stock Exchange (6-digit code, such as `000001`) 
- **ETF fund**: Such as `510050`, `159919` Wait

> Note: v3.0 does not currently support U.S. and Hong Kong stock market analysis. Related functions have been suspended and will be reopened in subsequent versions.

#### Operation steps

1. **Go to single stock research**
   - Left navigation bar"single stock research", Or dashboard quick access.

2. **Enter stock information**
   - in"Stock code"Enter the stock code directly into the input box (such as `000001`, `512400`) . 
   - in"market type"Select the corresponding market from the drop-down box: A-share market, ETF fund.
   - Each market code format prompt: A shares (6 digits), ETF (510050, 159919, etc.).

3. **Select analysis date (optional)**
   - The default is today, and you can manually select a historical date as the analysis base day.
   - Click"Data inspection"button to pre-verify the data integrity of that stock.

4. **Select analysis depth**
   - The system provides 5 levels of analysis depth:
     - **1 Level - Quick Analysis**: Basic data overview, quick decision-making (2-5 minutes)
     - **2 Level - Basic Analysis**: General investment decisions (3-6 minutes)
     - **3 Level - Standard Analysis**: technology + Fundamentals, Recommended (4-8 minutes)
     - **4 Level - In-Depth Analysis**: Multiple rounds of debate and in-depth research (6-11 minutes)
     - **5 Level - Comprehensive Analysis**: The most comprehensive analysis report (8-16 minutes)

5. **Choose an analyst team**
   - The system provides multiple analyst roles, displayed in the form of cards. Click the card to switch between selection/cancel:
     - **market analyst**: Analyze individual stock price trends and technical indicators (moving average/MACD/RSI/Bollinger Bands)
     - **fundamental analyst**: Analyze company financial condition, business model and competitive advantages
     - **news analyst**: Analyze the impact of relevant news, announcements and market events
     - **social media analyst**: Analyze social media sentiment, investor psychology and public opinion guidance
     - **Market Analyst**: Analyze market index trends, market environment and systemic risks (optional only for A shares)
     - **Sector Analyst**: Analyze industry trends, sector rotation and peer comparison (optional only for A shares)
     - **ETF analyst**: Analyze ETF net worth, tracking error, and position structure (optional for ETF market only)
   - Selected by default"market analyst"and"fundamental analyst". 
   - Analysts who do not correspond to the market will display"A shares only"Labels are not optional.

#### What dimensions does a complete report cover?

The table below is**The actual analysis dimensions that will be run for each analysis**, Let you know how each conclusion in the report comes from:

| Dimensions | Who is responsible | What data/tools were used? | What can you see in the report? |
|------|---------|----------------|------------------|
| **price trend** | market analyst | Historical K-line, real-time market | Current price, increase or decrease, trading volume, turnover rate |
| **Technical indicators** | market analyst | MA/RSI/KDJ/MACD, Bollinger Bands | Directional signals, overbought and oversold, trend direction |
| **K line pattern** | market analyst | 25+ Automatic shape recognition | Hammer line, engulfing, morning star/evening star, etc. |
| **chart pattern** | market analyst | Head and shoulders top and bottom, double top and double bottom, triangle | Judgment of medium and long-term trends |
| **support pressure** | market analyst | Pivot + Historical extreme value clustering | 3 3rd gear support position, 3rd gear pressure position |
| **financial table data** | fundamental analyst | Tushare Financial report data (balance sheet/income statement/cash flow statement/owner's equity statement) | Revenue, profit, gross profit margin, cash flow |
| **Earnings quality** | fundamental analyst | Accruals/Cash Flow/Earnings Sustainability | 5 Dimensions 0-100 points |
| **financial health** | fundamental analyst | Altman Z, Piotroski F | Whether there is bankruptcy risk and financial health |
| **Financial report fraud detection** | fundamental analyst | Beneish M (8 Dimensions) | Is there any suspicion of fraud (> -1.78 Tips) |
| **Valuation level** | fundamental analyst | PE/PB/PS/PEG | Is the relative valuation high or low? |
| **DCF Valuation** | fundamental analyst | discounted cash flow + WACC | How much is the company worth? |
| **Industry comparison** | Sector Analyst | Data of listed companies in the same industry | Position and market value ranking in the industry |
| **Market environment** | Market Analyst | Index + Number of stocks rising and falling | Bull market/bear market/shock market judgment |
| **news events** | news analyst | Oriental Fortune/Sina/Flush | Recent important news, catalysts, and risk events |
| **market sentiment** | social media analyst | Snowball/Stock Bar Discussion | Emotional tendencies, discussion enthusiasm |
| **Chip distribution** | Built-in tools | AkShare/Tushare | Profit ratio, average cost, 90%/70% concentration ratio |
| **multi-scenario research** | High Resilience/Defense/Baseline Scenario Analyst | Based on the above reports | Research observations of three scenario perspectives juxtaposed (does not constitute investment advice) |
| **Summary of research observations** | research integrator | All of the above | Balanced summary of observations from multi-scenario studies (non-directional conclusions) |

**Key points**: 
- The source of all data points in the report can be found (see v3.0 analysis capability panorama chapter for details)
- "AI inference"The label description is inferred by LLM, not the data obtained directly.
- Multi-scenario research is a new capability in v3.0, and Level 3 standard analysis will be automatically enabled
- 4 Level-in-depth analysis will add multiple rounds of debate sessions

6. **Start analysis**
   - Click"Start smart analysis"button.
   - The system enters the analysis progress page and displays the elapsed time, estimated remaining time, progress bar, and current task description in real time.
   - During analysis, the button appears as"Analysis in progress..." (Cannot be clicked repeatedly).

7. **View report**
   - After the analysis is complete, the button changes to"View results"and"Reanalyze". 
   - Click"View results"Expand the analysis report, including: comprehensive research observations, analysis of various dimensions, risk reminders, and follow-up observations.
   - Can be exported to PDF, Word, Markdown and other formats.

#### Things to note

- A single analysis will consume LLM Token, and in-depth analysis will consume a larger amount. Please make reasonable arrangements according to the authorization quota.
- Do not close the browser tab during the analysis, otherwise the task may be interrupted (the task can be found in"mission center"resume viewing).
- When analyzing a stock for the first time, the data download takes a long time; subsequent analysis will use cache and be faster.
- The analysis results are for reference only and do not constitute investment advice. Please make your own decisions based on your own judgment.
- Large-cap analysts and sector analysts only support the A-share market; the ETF market only displays ETF analysts, market analysts, and news analysts.

#### Analysis Report Interpretation Guide

After the analysis is completed, the report is displayed in the following structure to help you quickly obtain key information:

| Report Chapter | Content description | focus |
|---------|---------|---------|
| **Overall rating** | AI Overall research observations given (non-directional conclusions) | Certainty and Uncertainty Statement |
| **market analysis** | Interpretation of technical indicators (moving average, MACD, RSI, Bollinger Bands), price trend | Are you currently technically bullish or bearish? |
| **fundamental analysis** | Financial data, valuation level, industry status, competitive advantages | PE/PB Is it reasonable? Revenue and profit trends |
| **news analysis** | Impact of recent important news and announcements | Are there any major positive or negative events? |
| **social media analysis** | Social media sentiment and investor discussion | Is market sentiment optimistic or pessimistic? |
| **Market analysis** | Market index trends, market environment, systemic risks | Is the current market environment suitable for operation? |
| **Sector analysis** | Industry trends, sector rotation, peer comparison | Is the industry in which the stock belongs to a boom cycle? |
| **multi-scenario research** | Parallel research and observation of three situational perspectives | Main risk points and potential downside |
| **Summary of research observations** | Balanced multi-scenario research observations | Summary of research observations, no investment advice |

> 💡 **reading suggestions**: 
> - **When time is tight**: Just watch"Overall rating"and"Summary of research observations"Two sections.
> - **before decision**: Important reading"multi-scenario research", Understand research observations from different perspectives and avoid confirmation bias.
> - **Long term tracking**: Follow"fundamental analysis"trend changes to determine whether the company's operations have improved.

### 3.3 Research reports (/reports)

#### Function description

The research report module manages all historical analysis reports and supports searching by conditions, viewing details, and batch exporting.

#### Operation steps

1. **View report list**
   - "research report"This page displays all historical reports.
   - Each report displays: report title, type, format, status, analysis model, analysis depth, and creation time.
   - Supports searching by stock code/name, filtering by market (A shares/ETF), and filtering by date range.

2. **View report details**
   - Click in the report row"View"button to enter the report details page.
   - The details page includes: comprehensive research observations, detailed analysis by each analyst, data charts, risk warnings, and follow-up observations.
   - The report supports online reading and directory jump.

3. **Download report**
   - Click in the report row"Download"button to download a single report.
   - It also supports checking multiple reports and then clicking"Batch export", Choose format: Markdown/Word/PDF.

4. **Delete report**
   - Click in the report row"Delete"button to delete unnecessary reports.

5. **Token consumption view**
   - in"System management → usage statistics"The Token consumption of each function can be viewed on the page, including single stock research, batch analysis, Agent workshop, Skill generation, AI dialogue assistant, position analysis, operation review, etc.
   - You can also click on the research report page"Token statistics"button to enter the Token usage statistics page, filter by time range (today/7 days/30 days/90 days/all) and suppliers to view detailed Token usage and cost analysis, and support exporting statistical data.

#### Things to note

- If you encounter problems with Chinese fonts when exporting PDF, please ensure that the Chinese fonts are installed on the system (the Docker image is built-in).
- Word Format export requires system configuration pandoc (included by default with Docker deployments).

### 3.4 Stock Screening (/screening)

#### Function description

The stock screening module supports multi-condition combination screening for stocks, helping users quickly find targets that meet specific conditions from the entire market. v3.0 new"Stock Picking Assistant"mode to support natural language conversational filtering.

#### Operation steps

1. **Traditional filtering**
   - enter"stock screen"page.
   - Select the market scope: A-share market / CSI 300 / GEM / stock watch list, etc.
   - Add filter criteria:
     - Fundamentals: P/E ratio, P/B ratio, ROE, revenue growth rate, net profit growth rate
     - Technical aspect: rise and fall, turnover rate, volume ratio, moving average position
     - Scale: total market capitalization, circulating market capitalization
     - Industry: Filter by Shenwan industry classification
   - Set conditional logic (greater than/less than/between/equal to).
   - Click"Start filtering", View the list of results.

2. **Stock Picking Assistant (Conversational)** 
   - Click"Stock Picking Assistant"tab page.
   - Use natural language to describe screening requirements, for example:
     - "Help me find consumer stocks with ROE greater than 15% and P/E ratio less than 20"
     - "GEM stocks that have increased by more than 10% in the past week and have active turnover rates"
   - The system will go through three stages of processing:
     1. **Requirements confirmation**: AI Confirm screening intent with you.
     2. **strategic planning**: AI Plan how to use screening tools.
     3. **Perform filtering**: Call the tool to perform filtering and return the results.
   - The filter results support one-click addition to the stock watch list.

3. **Result operation**
   - Click on the stock name to enter details.
   - After selecting the stock, you can"Add to stock watchlist"or"Batch analysis". 
   - Supports exporting filter results to Excel.

#### Things to note

- The stock selection assistant is an advanced function and requires premium version authorization.
- Filter result data relies on underlying data synchronization, and if synchronization is not completed, the results may be incomplete.
- When the stock selection assistant times out or has no results, it will automatically fallback to historical successful results or a quick rough screening of the database to ensure that there are always candidate outputs.

### 3.5 Stock Watchlist (/favorites)

#### Function description

Watch list (stock watch list) is used to manage the stocks you follow, supporting group management, real-time market conditions, and quick analysis.

#### Operation steps

1. **Create group**
   - "Stock Watchlist"page, click"Create new group". 
   - Enter a group name (e.g."Liquor sector", "long term observation", "stop loss line") . 
   - Group color identification can be set.

2. **add stock**
   - Method 1: Click within the group"add stock", Join after searching for stocks.
   - Method 2: Click on the filter results and report details page"Add to stock watchlist". 
   - Method 3: Say it in the smart assistant"Add 600519 to my liquor section". 

3. **Management concern stocks**
   - Drag and drop stocks to adjust the order.
   - Supports cross-group movement.
   - Click on the stock code to enter**Stock details page** (See details [3.7 Stock details page](#37-Stock details page-stockscode)) , View real-time market conditions, K-line charts, core indicators, single stock analysis, positions and reviews, and use smart assistants for panoramic interpretation.
   - Operations supported by the stock details page: initiate AI research, position analysis, synchronize the latest data, clear cache, jump to simulated trading, and add/remove from the watch list.

4. **Batch operations**
   - Check multiple stocks to"Batch analysis" (Jump to batch analysis).
   - Yes"Batch export"for Excel.

#### Things to note

- It is recommended that each grouping should not exceed 50 stocks, as too many stocks will affect the page loading speed.
- The market data in the watch list is delayed market data and is not used as a basis for trading.
- The market data on the stock details page may be delayed. If you need the latest data, please click"sync"Button to pull manually.

### 3.6 Task Center (/tasks/unified)

#### Function description

The task center uniformly displays the status of all types of analysis tasks, including single-stock analysis, batch analysis, scheduled analysis, etc., making it easy to track task progress.

#### Operation steps

1. **View task list**
   - "mission center"The page presents a unified view of all tasks.
   - Each task displays: task type, target stock/analysis target, status, creation time, and time taken.
   - Status includes: Queuing, Running, Completed, Failed, Canceled.
   - The task objective for the generic research type appears as the analysis target text (instead of the stock symbol).

2. **Filter tasks**
   - Filter by task type.
   - Filter by status.
   - Filter by time range.

3. **Task operation**
   - **Running tasks**: You can check real-time progress and cancel tasks.
   - **Task completed**: Reports can be viewed, reanalyzed, and exported.
   - **Failed task**: You can view error logs and retry tasks.

4. **Mission details**
   - Click the task to enter the details page to view the execution steps and time-consuming of each analyst.

#### Execution trace (v3.0 core capabilities — Let AI check it wherever it goes)

**This is the most important traceability capability of v3.0.** Task details page"Execution trace"The tab page will analyze this**every step**With everything recorded, AI is no longer a black box.

**How to open** (Two ways):

- **Method 1 (recommended)— global switch**: "System settings → Advanced settings → Execution trace" → Enable. All new analysis tasks will be recorded when enabled.
- **Method 2 (single)— Task level switch**: Click on the upper right corner of the task details page"Turn on recording"button, only for the current task.

> 💡 Default**close** (avoid putting pressure on the database). It is recommended to turn it on when troubleshooting problems and turn it off during normal analysis.

**What can you see after opening it?**: 

| Field | meaning | Use when troubleshooting |
|------|------|----------------|
| **Agent list** | Which Agents (market, fundamentals, news) were run in this analysis…)  | Confirm whether each Agent has run |
| **Input for each Agent** | What it sees (upstream reporting, data) | troubleshooting"Why is this Agent conclusion so strange?" |
| **System prompt word + User prompt words** | LLM actually received prompt | troubleshooting"Is the prompt not transmitted correctly?" |
| **LLM original return** | LLM what was actually said | troubleshooting"Is it LLM? The answer is incorrect." |
| **Tool call record** | Which tools are called, what parameters are passed, and what is returned | troubleshooting"Did the tool get the wrong data?" |
| **Verification result** | Whether the output conforms to the format (passed/failed/warning) | troubleshooting"Why is the report format wrong this time?" |
| **Token Dosage** | How much does this analysis cost? Token | troubleshooting"Why did Token rise so much?" |
| **Time consuming** | How many seconds did each Agent take? | troubleshooting"why so slow" |

**A real investigation scenario**: 

> Question: Why does this news analysis say"The company has no major events recently"? 
>
> Answer: Open the execution trace → found"news analyst" → look at it"Tool call" → Found that it only adjusted"Title"Tool, not adjusted"Details"Tools → I know I chose the wrong tool

**How to use it most cost-effectively**: 

- ✅ Turn on when troubleshooting (incorrect analysis results, abnormal Token, strange report format)
- ✅ Turn on while learning (see how AI works)
- ❌ Daily analysis time (increased database storage)
- ❌ Batch analysis time is off (unless troubleshooting a specific stock)

> 💡 **Token influence**: Enable execution trace**Almost no impact on Token consumption** (Only records and does not add new calls), but will increase database storage. Archive after 7 days by default.

#### Things to note

- The number of concurrent tasks is limited by the authorization level. The standard version can run one task at the same time, and the advanced version supports concurrency.
- Queued tasks can be canceled at any time.
- When a failed task is retried, the Token will be consumed again.
- Enabling execution traces has almost no impact on token consumption (only logging does not add new LLM calls), but it will increase database storage.

---

### 3.7 Stock details page (/stocks/:code) 

#### Function description

The stock details page is a redesigned individual stock research workbench in v3.0, which integrates market conditions, research, positions, review, and intelligent assistants into one page, providing"Panoramic interpretation"experience. The page adopts a modular layout, divided into 8 areas from top to bottom, and is equipped with sticky research path navigation to help users quickly locate the required information.

#### Page layout

| area | module | Description |
|------|------|------|
| 1 | Stock overview + Operation entrance | Current price/up/down, today's opening/highest/lowest/trading volume, 6 shortcut operation buttons on the right |
| 2 | Smart assistant main entrance | A large card with purple gradient showing the status of loaded modules and providing 4 quick question buttons |
| 3 | Research Path (sticky) | 5 Step-by-step research path navigation, fixed on top when scrolling |
| 4 | K line graph + core indicators | K Line (including MA5/MA20/trading volume)+ Core Financial Indicators Card |
| 5 | Single stock analysis results | The latest AI analysis report, including one-sentence conclusion and re-analysis entry |
| 6 | Position holding and review | Switching tabs: position analysis and transaction review |
| 7 | Intelligent assistant dialogue area | Panoramic interpretation dialogue window, limited to the current stock theme |
| 8 | Fundamentals + financial details + News | Fundamental data, snapshots of financial details, recent news and announcements (supports ETF mode) |
| — | back to top button | Purple floating button in the lower right corner, appears when the scroll exceeds 600px |

The page as a whole adapts to the widescreen layout, and modules 4, 6, and 8 are arranged in a double-column grid; when the screen width is less than 1024px, it automatically switches to a single column.

#### Smart assistant main entrance

At the top of the page, immediately next to the stock overview, there is an eye-catching card with a purple gradient, which is the main entrance area of the smart assistant. The left side of the card displays:

- Assistant avatar and"Intelligent research assistant"Title
- The stock code and name currently being interpreted
- Loaded module status (displayed dynamically, e.g."K line loaded·single stock analysis·Position·Review·Fundamentals") 
- Description text:"I have integrated the stock's single stock analysis, position analysis, trading review, fundamentals and K-line trend, which can provide you with a panoramic interpretation"

There are 4 quick question buttons on the right side of the card (2×2 Grid), after clicking, it will automatically fill in the dialogue area below and send:

| shortcut button | Triggered issues |
|----------|-----------|
| 🔗 Panoramic interpretation | Help me analyze this stock in a panoramic manner. What do you think of the analysis results, positions, and review as a whole? |
| 📋 Analysis conclusion | What is the core conclusion of the latest single stock analysis? |
| 💼 Position perspective | Combining my positions and review, what should I focus on tracking next? |
| ⚠️ risk assessment | Do current valuations and fundamentals match? What are the risks? |

> The shortcut button will dynamically display the status according to the loaded module. If the data of a certain module is not loaded, the assistant will explain the missing data in the answer.

#### Intelligent Assistant Panoramic Interpretation (Core Functions)

The smart assistant and independent smart assistant module in the details page ([5.1 AI Conversation Assistant](#51-ai-Conversation Assistant-assistant)) Opened, but subject-limited, provided"Panoramic interpretation"Experience:

**1. One stock, one theme**

When entering the details page, the system will automatically create or obtain the research topic for the stock (titled"Equity research · {code} {Name}") . Repeatedly entering the page for the same stock will reuse the same topic, and historical conversations will be automatically loaded back without losing the context.

**2. Interpretation of three reports**

The intelligent assistant gets the summary of the single stock analysis report, position analysis report, and review report at the same time and interprets them together, without the need for the user to switch manually. For example, the user asked"Combining analysis and holdings, what should I focus on tracking next?", The assistant will make a judgment based on the three reports instead of just one.

**3. Topic Boundary Limitation**

The conversation is limited to the current stock range. The header of the chat area will display"The current topic is limited to: XX stocks"Tip bar. If the user asks about other stocks, the assistant will reply:

> Currently on the XX stock details page, you cannot switch to other stocks. If you need to inquire about other topics, please go to the "Intelligent Assistant" main page to create a new topic.

**4. Proactive reminder of overdue reports**

If the associated report has not been updated for more than 24 hours, the assistant:

- Actively push a reminder message when entering the page to list which reports have expired
- Refuse to draw conclusions based on old reports and ask if the analysis needs to be reinitiated
- After the user confirms, he can click on the corresponding module (single stock analysis, position, review)"Reanalyze"button to generate a new report

#### Research path navigation

There is a sticky navigation bar at the top of the page, showing the 5 steps and completion status of the research path:

| steps | Description | Completion conditions |
|------|------|----------|
| Market trend | K line + core indicators | Daily data available |
| single stock analysis | AI research report | There are completed single stock analysis tasks |
| Position holding and review | Position status + Transaction Review | Have position analysis or review records |
| Fundamentals | financial data + News | Have financial data |
| Intelligent Assistant Interpretation | Panorama covers all the above modules | always"To be used"Status |

Click on any step to quickly scroll to the corresponding area; the current area will be automatically highlighted when scrolling, and the shadow of the navigation bar will increase as you scroll.

#### K line graph

- Support daily K/week K/month K switching
- MA5 (5 Daily moving average, orange) and MA20 (20-day moving average, purple) are displayed in an overlay
- Volume histogram shown at the bottom with legend
- Supports data zoom (mouse wheel) and dragging to view historical intervals
- Data source:`stock_daily_quotes` collected `volume` Field

#### core indicators

The core indicator area is divided into 4 classification cards (2×2 Grid) displays the overall financial picture, and each card is equipped with a status label and progress bar to facilitate quick judgment:

**1. valuation card**
- Indicators:PE(TTM), PB, PS
- Status tag: Undervalued (PE < 15) / Neutral (PE 15~30) / On the high side (PE > 30) / Loss / No data
- PE Displayed when the data is real-time"real time"small label
- Progress bar color: blue (underestimated) / orange (neutral) / red (high)

**2. profitability card**
- Indicators: ROE, gross profit margin, net profit margin
- Status Label: Excellent (ROE ≥ 15%) / good (ROE 8~15%) / Weak (ROE < 8%) / Loss / No data

**3. Financial Wellness Card**
- Indicators: debt ratio, current ratio, dividend rate
- Status label: Health (debt ratio < 40%) / Neutral (40~60%) / On the high side (> 60%) / No data

**4. business scale card**
- Indicators: total market value, revenue, net profit
- The financial report announcement date is shown at the bottom.

**Factor prompt information**

Factor warnings and factor diagnostic labels may appear below the card (hover to view details):
- **factor warning label**: Displays the risk conditions triggered by the stock (e.g."High valuation risk") , hover View specific trigger conditions
- **Factor Diagnostic Tags**: Display factor status, reason, and missing input (for example, a factor cannot be calculated due to insufficient data)

> Data source priority: Financial indicators (ROE, debt ratio, etc.) are prioritized from `stock_financial_data` Collection acquisition, downgrade use `stock_basic_info`; Valuation data (PE/PB/PS) comes from `stock_basic_info`. When a field is missing, it appears as `-`. 

#### Single stock analysis results

Displays the latest single stock analysis report, marked next to the title"in-depth research"Badge. Different content is displayed according to the analysis status:

**Running status**
- When the analysis task is in progress, a progress bar (percentage) and prompt information (such as"Generating analysis report…") 

**Empty state**
- Displayed when there is no analysis record"No single stock analysis results yet", provide"Initiate single stock analysis"button

**Display when there are results**
- **Research conclusion**: Card with purple gradient background, showing one sentence conclusion (based on the research brief of the research integrator)
- **Analyze meta information**: Analysis time (full time + Relative time labels, such as"3 hours ago""2 days ago""1 months ago") , Report quantity
- **Data expiration reminder**: Displays orange if the report is older than 1 day"🔄 Data has expired, re-analyze"button
- **Report label preview**: Each sub-report is arranged in clickable tabs (e.g."market analysis""fundamental analysis""Risk assessment") , Click to jump directly to the corresponding report; there are also"View full report"button to open a multi-tab dialog box
- **Detailed report content (foldable)**: Click"Expand details"Finally, 6 types of sub-reports are displayed in a two-column grid:
  - 📈 market analysis,💰 fundamental analysis,📰 news analysis,⚠️ Risk assessment (red border),💬 social emotions,🎯 Research Integrator Research Briefing
- **History**: upper right corner"📜 History"button (with counting badge), click to jump to the task center to view all historical analysis of this stock
- **Compliance Disclaimer**: bottom mark"This analysis is generated by the AI multi-agent system based on public information. It is for research reference only and does not constitute any trading advice."

> Compliance instructions: This area does not display confidence and operation recommendation labels, and only retains research metadata.

#### Position holding and review

Switch between two modules via tabs, with status badges displayed on the tabs:

**Position analysis tab page** (Badge display"floating profit X%"/"floating loss X%"/"Analyzed") 

- **Position Snapshot Summary**: Cost price, current price, floating profit and loss (amount + percentage), holding days, position proportion
- **research observation**: Purple background card showing AI position research observations (maximum 3, for reference only)
- **Real offer/simulated position information**: Display the position quantity, cost price, current price, market value, and floating profit and loss respectively (real red label, simulated orange label)
- **Expiration reminder**: Shown when analysis is older than 1 day"🔄 Data has expired, re-analyze"button
- **Action button**: Reanalyze and view details (jump to task details page)
- **Position history**: upper right corner"📜 Position history"Button (with counting badge)

**Transaction review tab page** (Badge display"X times"/"Reviewed") 

- **Review summary**: Number of transactions, risk level, completion time (including relative time)
- **expired banner**: An orange banner is displayed when the review is more than 1 day old"⚠ This review is a long time ago, and the market environment may have changed."+ Resume button
- **Review conclusion**: Markdown Rendered conclusion text
- **research observation**: Original"Operation suggestions"Changed to research statement (compliance adjustment)
- **Action button**: Re-review and view details (jump to the review details dialog box)
- **Review history switch**: When there are multiple review records, the drop-down box in the upper right corner can switch to view different historical reviews;"📜 Review history"Button (with counting badge)

> Compliance instructions: Position analysis does not display operational suggestions and confidence. Transaction review"Operation suggestions"has been changed to"research observation"Expression. There is a disclaimer at the bottom of both tabs.

#### Operation entrance

There are 6 shortcut operation buttons in the upper right corner (3×2 Grid layout):

| button | Function |
|------|------|
| initiate research | Start AI multi-agent in-depth analysis (complete in minutes) |
| Position analysis | Initiate AI analysis on current positions |
| Sync data | Manually pull the latest market/financial data (optional data source and synchronization content) |
| simulated trading | Jump to the simulated trading page and pre-fill the current stock |
| Add/remove watchlist | Quickly manage attention status |
| clear cache | Clear the local cache of the stock and force a retrieval. |

#### Fundamental Data and News

Area 8 at the bottom of the page contains three cards (arranged in a double-column grid), which automatically switches the display content according to the stock/ETF type:

**1. Fundamental Data Card (Stock Mode)**

Show basic valuations and financial metrics:

| indicator | Description |
|------|------|
| Industry, sector | Industry and market sector (Main Board/GEM/Science and Technology Innovation Board, etc.) |
| Total market capitalization | to"billion"Display in units |
| PE(TTM) | Rolling P/E ratio, displayed with real-time data"real time"label |
| PB(price to book ratio), PS(TTM) | Price-to-book ratio, price-to-sales ratio |
| ROE | ROE |
| Debt ratio | Asset-liability ratio |
| dividend yield | annualized dividend rate |
| current ratio | Current assets/current liabilities |

**ETF Basic data card (ETF mode)**

When viewing an ETF, it automatically switches to ETF-specific fields: fund type, tracking index, fund size, fund shares, unit net value, cumulative net value, discount and premium rate, net value growth rate, manager, and custodian.

**2. Financial Details Snapshot Card (Stocks Only)**

Display detailed data from the latest financial report:

| indicator | Description |
|------|------|
| gross profit margin, net profit margin | profitability indicator |
| Revenue, net profit | Business scale (in"billion"as unit) |
| operating cash flow | cash flow from operating activities |
| total assets, total liabilities | Balance Sheet Summary |
| data source | Financial data source (e.g. tushare) |

- The card header shows the reporting period (e.g. `20250630`) 
- bottom display `raw_data` Grouping label, lists the original data groups and number of items that can be drilled down (such as"Income statement 12 items") , These groups have been exposed through the main stock interface and can be drilled down later.

**3. Recent news and announcements cards**

| Function | Description |
|------|------|
| Filter drop down box | support"All/News/Announcements"Three kinds of screening |
| News list | Display for each bar: type label (blue"News" / orange"Announcement") , Title (click to jump to the original text), relative time (such as"2 hours ago""3 days ago") , Source |
| Loading status | Display loading animation during data loading |
| Empty state | Show when there is no news"No news yet"Placeholder |

> News data sources (such as tushare / akshare) are shown in the source line of each news item.

#### Operation steps

1. **Enter the details page**
   - Click on a stock symbol from the stock watchlist
   - Click on a stock symbol from a research report
   - Click a stock link from a smart assistant conversation
   - direct access `/stocks/{Stock code}`

2. **Quick research process**
   - Check market trends and core indicators to understand fundamentals
   - Click"initiate research"Start AI multi-agent analysis (completes in minutes)
   - After the analysis is completed, ask in the intelligent assistant dialogue area"Give me an explanation based on analysis and positions"
   - The assistant will aggregate single stock analysis, positions, and review to give a comprehensive judgment.

3. **Data synchronization**
   - Click"Sync data"button
   - Check the synchronization content (real-time market / historical market / financial data / basic data)
   - Select data source (Tushare/AKShare/QMT)
   - The number of days of historical data can be specified (up to 3650 days, approximately 10 years)
   - After synchronization is completed, refresh the page to view the latest data.

#### Things to note

- The intelligent assistant dialogue in the details page is limited to the current stock topic and cannot be switched to other stocks; if you need to consult other subjects, please go to the independent intelligent assistant page (`/assistant`) 
- Reports that are more than 24 hours old will be marked as expired. The intelligent assistant will not draw conclusions based on expired reports and the analysis needs to be reinitiated.
- K Line charts and core indicators rely on synchronized data. If the data is empty, please click first."Sync data"
- The market data is delayed and not used as a basis for trading.
- The intelligent assistant's answers are generated based on loaded research data and are for research reference only and do not constitute investment advice.

---

## Chapter 4 Learning Research and Simulation Function

This chapter introduces the functional modules used for learning research and strategy verification, including simulated trading, position research, operation review and trading plan. These functions help you verify research hypotheses, review operating behaviors, and develop systematic tracking plans in a virtual environment, and do not constitute any investment advice.

### 4.1 Simulated trading (/paper)

#### Function description

The simulated trading system provides a virtual capital environment, supports simulated buying, simulated selling, and simulated position management, helping you learn market operation processes and verify research hypotheses without investing real funds. v3.0 supports A-share and ETF simulated trading. Simulated trading is only for learning and research and does not constitute any investment advice.

#### Operation steps

1. **Initialize demo account**
   - first time entry"simulated trading", The system will prompt you to create a demo account.
   - Set initial capital (default 1 million RMB).
   - Select account type: A-share account.

2. **Simulated buying (virtual position opening)**
   - Click"buy"button.
   - Enter the stock code, simulated buying price, and quantity.
   - optional"market price" (Transaction at the latest price) or"price limit" (Place an order at the specified price).
   - The system automatically calculates handling fees, stamp duty and other costs.
   - Submit after confirmation, and update positions and available funds after transaction.

3. **Simulated selling (virtual closing)**
   - Select the stock you want to sell in the position list.
   - Click"sell", Enter the simulated selling price and quantity.
   - The system automatically calculates profit and loss.

4. **Position view**
   - "Position"The tab displays all current positions.
   - Each stock displays: position quantity, cost price, current price, floating profit and loss, and profit and loss ratio.
   - Support sorting by profit and loss.

5. **transaction history**
   - "record"The tab displays all historical transaction details.
   - Supports filtering by time and stocks.

6. **Account statistics**
   - "statistics"The tab displays the account overview: total assets, total market value, available funds, total profit and loss, and rate of return.
   - Provide a revenue curve graph.

#### Things to note

- Simulated trading data does not affect real accounts and is only used for learning, research and strategy verification, and does not constitute investment advice.
- Simulated trading does not simulate price limits and trading suspensions, and is different from real trading.
- The handling fee is calculated based on the real rate (approximately 10,000 for A shares 2.5 + Stamp duty 1 per thousand), allowing for a true assessment of the strategy.
- Demo account funds can be reset, and all positions and records will be cleared after reset.

### 4.2 Portfolio Research (/portfolio)

#### Function description

The position research module performs an in-depth analysis of your current simulated positions to evaluate the risk exposure, industry concentration, correlation and optimization suggestions of the portfolio.

#### Operation steps

1. **Enter position research**
   - "Position research"The page automatically reads the position data in simulated trading.
   - Positions can also be imported manually (Excel template upload is supported).

2. **Portfolio overview**
   - Displays the total market value of the portfolio, industry distribution, and position distribution.
   - The pie chart shows the proportion of each industry and the proportion of each stock.

3. **risk assessment**
   - **Industry concentration**: Analyze whether there is excessive concentration in a certain industry.
   - **Concentration of individual stocks**: Analyze whether the proportion of a single stock is too high.
   - **correlation analysis**: Calculate the correlation coefficient between positions and evaluate the dispersion.
   - **Beta exposed**: Calculate the beta of a portfolio relative to the market.

4. **Optimization suggestions**
   - The system gives allocation references based on modern portfolio theory.
   - Mark excessively concentrated positions to indicate the risk of concentrated positions.
   - Recommend complementary industries or targets to improve diversification.

5. **One-click analysis**
   - Can be initiated for a single position"single stock research", Get in-depth analysis reports quickly.

#### Things to note

- Position research relies on simulated trading data. Please establish a position in simulated trading first.
- Correlation analysis requires historical data and may not be calculated for new stocks or stocks with insufficient data.
- Optimization observations are for reference only and do not constitute investment advice.

### 4.3 Operation review (/review)

#### Function description

The operation review module helps you review historical trading behaviors, analyze the reasons for profits and losses, summarize trading experience, and continuously improve trading strategies. v3.0 introduced **5 Special review Agent**, Take the review from"Write a summary based on your feelings"upgraded to"Structured attribution analysis". 

#### 5 Class review Agent

Each time a review is created,**5 Each Agent will take care of its own share.**, Help you analyze this transaction from different angles:

| Review Agent | What to focus on | what will you be asked |
|-----------|---------|----------|
| **Time to review** (timing)  | Trading time | Was it a good time? Is it chasing high? Did it fall? |
| **Position review** (position)  | Position size | Is the position too heavy? Is the pace of position adjustment reasonable? |
| **Emotional review** (emotion)  | decision-making mentality | Were you dominated by emotions at that time? Is there FOMO, fear, greed? |
| **Attribution review** (attribution)  | Source of profit and loss | This time the profit/loss comes from the industry β, individual stocks α, Or luck? |
| **Review manager** (review_manager)  | Comprehensive attribution | Based on the above 4 perspectives, the final conclusion is given |

#### Operation steps

1. **Create a review record**
   - "Operation review"page, click"Create a new review". 
   - Select the transaction to be reviewed (selected from simulated transaction records).
   - Or manually enter a transaction for review.

2. **5 Class review automatically triggered**
   - After selecting a transaction, the system automatically calls 5 Agents for parallel analysis
   - Each Agent generates reports independently (3-5 minutes)
   - The review manager gives the final conclusion based on 4 perspectives

3. **Review content**
   - **Transaction background**: Why did you make this deal? (Can be automatically brought in from the analysis report of the corresponding date)
   - **Decision basis**: Based on what information or signal?
   - **actual results**: Profit and loss situation, holding time.
   - **5 Agent-like reports**: Timing, position, sentiment, attribution, synthesis
   - **Experience summary**: What did you do right? What did you do wrong?
   - **Improvement points**: What should I do in a similar situation next time?

4. **Review classification**
   - You can label the review: trading with the trend, buying the bottom against the trend, stop loss, take profit, wrong operation, etc.
   - Supports statistics of winning rate and profit and loss by tag.

5. **Review statistics**
   - The statistics page displays: total number of transactions, winning rate, average profit and loss, and profit and loss ratio.
   - Analyze which types of transactions perform better by tag dimension.
   - Viewed by Agent dimension: your"timing judgment"Accuracy vs "Position control"Accuracy

6. **Correlation analysis report**
   - When reviewing, you can correlate the research reports at that time and compare them."Analysis conclusion"with"actual trend"deviation.

#### Reflection automatically settles

After each review is completed,**Review and reflection** (trade_lesson) will be automatically written into AI memory. The Agent will reference your previous lessons the next time it analyzes:

- Previous review found"I often chase the high on the day after the daily limit" → The Agent will proactively remind you during the next analysis
- Previous review found"I can't always hold on to liquor stocks." → Next time when analyzing liquor stocks, the Agent will mention this habit of yours.

#### Things to note

- Review is a key link to improve trading ability, and it is recommended to review every important transaction.
- The review records will be automatically linked to the AI memory system, and the intelligent assistant can refer to your trading preferences in subsequent analysis.
- 5 The similar review agent will run every time (cannot be closed separately), but you can only view"Review manager"comprehensive conclusion.

### 4.4 Trading plan (/trading-system)

#### Function description

The trading plan module helps you develop a systematic trading plan, including entry conditions, position management, stop-profit and stop-loss rules, and can automatically generate plans based on associated analysis reports.

#### Operation steps

1. **Create a trading plan**
   - "trading plan"page, click"New plan". 
   - Select target stocks.
   - optional"Generate from analysis report" (The system automatically populates the recommended parameters based on the latest reports).

2. **Set up plan elements**
   - **Entry conditions**: Price trigger conditions, technical indicator conditions, and fundamental conditions.
   - **Planned position**: Initial position, additional observation rules, maximum position.
   - **Revenue focus rules**: Revenue focuses on price, batch tracking, and mobile tracking.
   - **Risk focus rules**: Risks focus on price, risk ratio, and time observation.
   - **tracking period**: Short term (days) / Band (weeks) / Medium term (months) / Long term (years).

3. **plan template**
   - The system has built-in multiple research tracking plan templates (trend tracking, value investing, event-driven, etc.).
   - It can be quickly created based on templates and then adjusted according to actual conditions.
   - Supports saving custom templates.

4. **Plan execution tracking**
   - Enter after plan creation"To be executed"status.
   - The system sends a notification when the market price triggers an entry condition.
   - Can be marked manually"Already admitted", "The income concern level has been touched", "The risk concern level has been touched". 
   - The system automatically calculates the deviation between plan execution and planned targets.

5. **Linkage of planning and review**
   - After the plan is completed, it can be generated with one click"Operation review"Record and form a closed loop.

#### Things to note

- The trading plan will not automatically place orders. It is only used as a learning research and discipline restraint tool and does not constitute investment advice.
- The system will push notifications when profit/risk price conditions are triggered, but transactions will not be executed automatically.
- It is recommended to verify the plan assumptions in simulated trading before using it as a reference for personal decision-making.

---

## Chapter 5 Intelligent Assistant

### 5.1 AI Conversation Assistant (/assistant)

#### Function description

Intelligent assistant is the core upgrade module of v3.0, starting from"Analysis trigger"evolve into"Investment research collaborative portal". Supports natural language dialogue and can be called 20+ Operation tools, complete tasks across modules, and support multi-topic sessions.

#### core competencies

- **Analysis trigger**: Natural language initiated single stock/batch analysis.
- **Report query**: Search, view, and interpret historical reports.
- **task management**: Query task status and manage scheduled tasks.
- **Stock watch list management**: Add, delete, and query stocks of interest.
- **Position analysis**: Query positions and analyze portfolios.
- **Transaction review**: Query historical transactions and assist in review.
- **investment plan**: Create and query trading plans.
- **Price lower limit reminder**: Set price floor reminders.
- **Break down complex tasks**: Automatically break down complex requirements into multi-step execution.
- **RAG Financial knowledge search**: Built-in financial knowledge base to reduce illusions.

#### Operation steps

1. **Enter smart assistant**
   - Left navigation bar"Smart Assistant", or press `Ctrl+/` Shortcut keys.

2. **Create session**
   - Click"New session", Conversation topics can be selected (e.g."Kweichow Moutai Research", "Consumption sector tracking") . 
   - Each topic independently maintains message history and context.

3. **Dialogue interaction**
   - Type questions or instructions directly, for example:
     - "Help me analyze Kweichow Moutai's recent fundamentals"
     - "How are the stocks I've been following recently performing?"
     - "Help me screen out stocks with ROE greater than 20%"
     - "Check how much I earned from the CATL I bought last month."
     - "Explain what PEG valuation is"
   - The assistant understands the intent, calls tools, and returns structured results.

4. **Multiple rounds of dialogue**
   - The assistant will remember the context of the last 10 conversations and support follow-up questions.
   - For example, ask first"Analysis of Kweichow Moutai", Ask again"What are its risks?", Assistant understands"it"Refers to Kweichow Moutai.

5. **Session management**
   - Multiple conversation topics can be created and the context is independent when switching.
   - Support manual"Wrap up session"Generate structured summaries.
   - Sessions can be renamed, deleted, and archived.

6. **IM format adaptation**
   - When using the assistant through instant messaging channels such as QQ, the output is automatically converted to a condensed plain text format.

#### Things to note

- Tokens will be consumed when the assistant calls tools, and complex tasks consume a lot of money.
- Sliding window memory retains the last 10 conversations, older conversations do not enter context. For long-term memory, use"Wrap up session"Functionality or reliance on AI memory systems.
- The assistant will automatically inject user profile information (recent analysis, areas of concern) to provide more accurate answers.
- The assistant's answers are for reference only. For important decisions, please make independent judgments based on the research report.
- **Intelligent assistant in stock details page**: On the stock details page ([3.7 Stock details page](#37-Stock details page-stockscode)) When using the assistant, the conversation will be automatically limited to the topic of the stock, and the three reports of single stock analysis, position position, and review will be aggregated and interpreted. Questions beyond this stock will be directed to the independent smart assistant main page to continue.

### 5.2 AI Memory (/memory)

#### Function description

AI Memory is the stock object memory system of v3.0. The system will automatically memorize the key conclusions of each analysis, the user's trading preferences and focus, and inject them as context in subsequent analysis to achieve"The more I use it, the better I understand you.". 

#### memory type

v3.0 provide **7 memory type**, Covering all levels of conversations, users, Agent experience, Skill lessons, transaction models, etc.:

| memory type | range | What to remember | who can see |
|---------|------|---------|---------|
| **dialogue memory** (CONVERSATION)  | single session | Recent conversations between you and the smart assistant (default sliding window 10) | you |
| **User preferences** (USER_PREFERENCE)  | Across sessions | Investment style, risk preference, holding cycle, industry preference | you + system |
| **Analytical insights** (ANALYSIS_INSIGHT)  | span analysis | Conclusions, key judgments, and risk points of each analysis (by stock) | you + Next analysis of this stock |
| **Agent experience** (AGENT_EXPERIENCE)  | span analysis | Agent Lessons for self-reflection (reusable framework refined after debate) | you + all Agent |
| **Skills Lessons** (SKILL_LESSON)  | span generation | Skill Generate failed patterns (to avoid repeating the same mistake next time) | system + Skill workshop |
| **trading model** (TRADE_PATTERN)  | span transaction | Profile of your trading behavior (habits, preferences, common mistakes) | you + Smart Assistant |
| **Agent Build Lessons** (AGENT_BUILDER_LESSON)  | span build | Agent Pitfalls encountered when creating the workshop | system + Agent workshop |

**3 memories that mean the most to you**: 

1. **User preferences** (USER_PREFERENCE) : Tell the system"what do i care about". For example"I prefer low valuations and high dividends", The smart assistant will actively look for such stocks during the next analysis.
2. **Analytical insights** (ANALYSIS_INSIGHT) : Historical analysis of each stock is automatically accumulated. The next time the same stock is analyzed, the system will refer to the previous conclusion.
3. **trading model** (TRADE_PATTERN) : Categorized based on your historical transactions"Are you a left or right side trader?""Where is the usual stop loss?". The smart assistant will refer to it during review.

**The other 4 types are for"system itself"Used**, Ordinary users don't need to pay attention.

#### Operation steps

1. **View memory**
   - "AI memory"The page is divided into three tabs: stock memory, user portrait, and trading behavior.
   - Stock memories are organized by stock code. Click to view all historical memory entries for that stock.

2. **memory details**
   - Each memory displays: content summary, source (which analysis/conversation occurred), creation time, priority.
   - Supports editing memory content (correcting error messages).

3. **memory management**
   - **erase memory**: Expired or erroneous memories can be deleted.
   - **Adjust priority**: High-priority memories will be injected into the analysis context first.
   - **Add manually**: A memory can be entered manually (such as"The stock has a major shareholder plan to reduce its holdings") . 

4. **memory injection**
   - As the system performs analysis, relevant memories are automatically retrieved and injected into the analyst's context.
   - In the smart assistant conversation, user portrait memory is automatically injected so that the assistant understands you better.

#### Things to note

- The memory system is AI capable"amplifier", However, too many memory entries may increase Token consumption.
- It is recommended to regularly clean up expired memories (such as stock memories that have not been updated for more than half a year).
- The memory content will be encrypted and stored and will not be leaked to third parties.
- The memory system is an advanced function, and the upper limit of the number of memory entries is affected by the authorization level.

---

## Chapter 6 Advanced Functions

> **The functions in this chapter are all advanced functions and require advanced version permissions.** Standard Edition users can browse the interface, but will be prompted with insufficient permissions when performing operations.

### 6.1 Analysis flow (/workflow)

#### Function description

Analysis flow is the core advanced feature of v3.0, which provides a visual workflow editor and supports drag-and-drop arrangement of analysis processes. v3.0 adopts the v2.0 analysis engine, adds conditional branching, multi-round debate, parallel/merging, post-processor and other control nodes based on v1.0, and supports 6 process types and AI intelligent creation. Contains five major sub-modules: process management, tool configuration, Agent workshop, Skill center, and MCP server.

#### 6.1.1 process management

##### Function description

Process management supports the creation of customized analysis workflows, and arranges the analysis process by dragging nodes and connecting lines. Each node can be bound to different Agents and tool sets. v3.0 uses the v2.0 engine by default, providing richer node types and more flexible process orchestration capabilities.

##### v2.0 Analysis engine

v3.0 The analysis flow has been fully upgraded to the v2.0 engine, with improvements compared to v1.0:

| Features | v1.0 engine | v2.0 engine |
|------|-----------|-----------|
| analyst | fundamental analyst | Professional v2.0 analyst (market, sector, market, fundamentals, news, social media) |
| debate mechanism | Simple multi-scenario study | Multiple rounds of multi-scenario research + Three-party risk scenario research |
| conditional branch | Not supported | support |
| Parallel/Merge | Not supported | support |
| post processor | Not supported | Support (report generation, etc.) |
| risk assessment | single risk analysis | Highly resilient/defensive/baseline tri-party risk scenario study + Risk Assessor Review |
| research integration | research integrator | Research integrator (generates user version conclusions after risk review) |
| maintenance status | Maintenance has been stopped | Ongoing maintenance |

> Tip: When opening a v1.0 legacy process, the editor will display"The current workflow is a v1.0 legacy process and has been discontinued for maintenance."warning, it is recommended to migrate to v2.0 workflow.

##### Process type

When creating a workflow, you need to select a process type. Different types correspond to different analysis scenarios:

| Process type | Description | Applicable scenarios |
|----------|------|----------|
| Single stock research process | Complete single stock analysis process | Analyzing a single stock, the results are in"research report"View in |
| ETF Analysis process | ETF Dedicated analysis process | Analyze ETF funds (net value, size, tracking error) |
| Position analysis process | Position health analysis | Analyze the technical aspects, fundamentals and risks of stocks held |
| Operation review process | Transaction review process | Review timing, positions, sentiment and attribution |
| Portfolio health process | Combined holistic diagnosis | Assess portfolio dispersion and concentration |
| Common research process | Free to explore | The result is"process center"View |

##### Operation steps

1. **Create workflow**
   - "Analysis flow → process management", Click"Create a new analysis process". 
   - Select a process type (required) and a template (optional).
   - Enter a name and description.
   - Click"Create and edit". 

2. **Create from template**
   - The page displays the system's preset v2.0 templates, and each template displays a process preview and the number of nodes.
   - Click"Preview"View the detailed node structure and process description of the template.
   - Click"use this template", A copy is created after naming and can be modified on this basis.

3. **Available templates**

   | Template name | Description | Number of nodes |
   |----------|------|--------|
   | v2.0 Complete analysis flow | 6 analysts in parallel → multi-scenario research → research integrator → Risk multi-scenario research → risk assessor → research integrator | 16 |
   | v2.0 ETF Analysis flow | ETF analyst + market analyst + News Analyst, No Multiple Scenario Research | 8 |
   | Position research process v2.0 | technical aspect + Fundamental Parallelism → risk review → research integration | 7 |
   | Transaction review process v2.0 | Timing/position/sentiment/attribution parallel review → Review summary | 7 |
   | Blank process | Only start and end nodes, built from scratch | 2 |

4. **Edit workflow**
   - Drag nodes from the node panel on the left to the canvas.
   - Connect a node: Click the output port of the node, then click the input port of the target node.
   - Configure node: Click the node and set parameters in the right panel.

5. **Node type**

   The workflow editor provides two types of nodes:

   **agent node** (Grouped by category):
   - Analyst: market analyst, sector analyst, market analyst, fundamental analyst, news analyst, social media analyst
   - researcher: optimistic scenario researcher, cautious scenario researcher
   - Risk analysis (risk): high resilience scenario analyst, defensive scenario analyst, baseline scenario analyst
   - manager: research integrator, risk assessor
   - research integrator (trader): research integrator
   - Post-processor (post_processor): report generator, etc.

   **control node**: 
   - Start: Workflow entry
   - End (end): workflow exit
   - Conditional branch (condition): select different execution paths based on conditional expressions
   - Parallel start (parallel): multiple branches are executed simultaneously
   - Parallel merge: wait for all parallel branches to complete before continuing
   - Debate: multiple rounds of confrontational debate

6. **conditional branch**
   - Conditional branch nodes support dynamic selection of execution paths based on conditional expressions.
   - Edges starting from conditional branch nodes can be set with conditional labels (such as"true"/"false") . 
   - It is suitable for scenarios where the process is dynamically adjusted based on analysis depth, market type and other conditions.

7. **debate node**
   - Debate nodes are the core innovation of v2.0, supporting multi-round confrontational debates.
   - Configure debate participants (e.g. optimistic researchers vs cautious researchers, or tripartite risk analysts).
   - Debate rounds automatically adjust based on depth of analysis:
     - 1 Level Fast: Multiple Scenarios 1 round + Risk 1 round
     - 2 Level Basics: Multiple Scenarios 1 round + Risk 1 round
     - 3 Level Standard: Multiple Scenarios 1 round + Risk 2 rounds
     - 4 Level Depth: Multiple Scenarios 2 rounds + Risk 2 rounds
     - 5 Level Comprehensive: Multiple Scenarios 3 rounds + Risk 3 rounds

8. **Layer 3 configuration priority**
   - **Node level**: The configuration of a single node has the highest priority.
   - **Workflow level**: Workflow global configuration as node default.
   - **Agent level**: Agent Its own default configuration has the lowest priority.

9. **Toolbar operations**
   - **Edit/Preview**: Switch between edit mode and preview mode.
   - **Verify**: Check the structural integrity of the workflow (node ​​connections, required configuration, etc.).
   - **save**: Save the current workflow configuration.
   - **Set as default**: Set the current workflow as the default analysis process and use it automatically for subsequent analysis tasks.
   - **execute**: Only the single stock research process and the ETF analysis process support direct execution.

10. **Manage existing workflows**
    - in"My analysis flow"Area to view created workflows, grouped and displayed by process type.
    - Supported operations: edit, execute, copy, set as default, delete.
    - The process type can be modified: click on the editor toolbar"Modify"Switch process type.

##### Things to note

- Workflow editor supports undo/redo (Ctrl+Z / Ctrl+Y) . 
- For complex workflows, it is recommended to test run verification on a small range of stocks first.
- v1.0 The legacy process has been discontinued for maintenance and it is recommended to migrate to v2.0 workflow.
- Agent Custom Agents created in the Workshop are available in the Agent Nodes panel of the editor.
- The workflow set as the default will be automatically selected for single stock research, batch analysis, and scheduled analysis.
- The position analysis and operation review process does not currently support direct execution from the editor and needs to be triggered through the corresponding function entrance.

#### 6.1.2 AI workflow architect

##### Function description

AI Workflow Architect is v3.0's intelligent flow-building feature that automatically plans and generates customized workflows through natural language dialogue. The system will automatically identify missing Skills and create them, ultimately generating a publishable workflow.

##### Operation steps

1. **Enter AI Jianliu**
   - "Analysis flow → process management", Click"AI Smart creation". 
   - Or click on the analysis flow list page"AI Smart creation"button.

2. **Select process type** (Step 1)
   - Select the type of analysis process to create (Single Stock Research / ETF Analysis / Position Analysis / Operational Review / General Research).

3. **Requirements communication** (Step 2)
   - Use natural language to describe requirements, for example:"I need a process that specifically analyzes the prosperity of the liquor industry, focusing on pricing, inventory and sales data.". 
   - AI We will have multiple rounds of conversations with you to clarify the details of your needs.

4. **Plan confirmation** (Step 3)
   - AI Generate workflow planning solution, including node topology and Agent configuration.
   - After confirming the plan, proceed to the next step.

5. **Autocomplete** (Step 4)
   - The system automatically creates missing Skills and Agents.
   - Complete node configuration and binding toolset.
   - You can view the details of automatically created Skills.

6. **Complete publishing** (Step 5)
   - Check the generated workflow and publish it after confirmation.
   - AI Skills generated by stream building will be automatically registered to ToolRegistry and can be viewed in the Skill Center.

##### Things to note

- AI The flow building process consumes LLM Token. It is recommended that the requirements be clearly described to reduce the number of iterations.
- It is recommended that the generated Skill code be manually reviewed before use.
- If the conversation is interrupted, you can return to the list page to save your draft.

#### 6.1.3 Tool configuration

##### Function description

Tool configuration is used to manage the parameters of the analysis tool, including data sources, caching strategies, calling frequency, etc.

##### Operation steps

1. "Analysis flow → Tool configuration"View all registered tools.
2. Click Tools to enter the parameter configuration page.
3. Adjustable: timeout, number of retries, cache duration, concurrency limit.
4. The configuration takes effect immediately after saving.

#### 6.1.4 Agent workshop

##### Function description

Agent The workshop supports the creation of custom Agents. Select the Agent type (such as fundamental analyst, news analyst) and name through the drop-down menu, and configure the tool set and system prompt words it uses.

##### what tools can you use

When creating a custom Agent, you can start with **78 built-in tools**Select Binding. Common categories:

| The analysis you want to do | Bindable tools (examples) |
|------------|------------------|
| **Want to calculate how much the company is worth** | `get_dcf_valuation` (DCF valuation),`get_wacc_calculation` (WACC) , `get_peg_valuation` (PEG)  |
| **I want to see if there is any fraud** | `get_beneish_mscore` (Beneish M 8 dimension score),`get_financial_fraud_signals` (false signals) |
| **Wondering if it will go bankrupt?** | `get_altman_zscore` (Altman Z) , `get_ohlson_oscore` (Ohlson O)  |
| **Want to see if your finances are healthy?** | `get_piotroski_fscore` (Piotroski F 0-9 points),`get_earnings_quality_score` (Earnings quality 0-100) |
| **Want to see the technical form** | `get_candlestick_patterns` (K line 25+ form),`get_chart_patterns` (chart form),`get_fibonacci_retracement` (Fibonacci) |
| **Want to see support pressure** | `get_support_resistance_levels` (support pressure),`get_pivot_points` (pivot point) |
| **Want to see the valuation level** | `get_comparable_company_valuation` (Comparable companies),`get_industry_valuation_distribution` (Industry distribution) |
| **Want to see portfolio risk** | `get_var_calculation` (VaR) , `get_sharpe_ratio` (Sharp),`get_max_drawdown` (maximum drawdown) |
| **Want to choose stocks** | `get_multi_factor_screening` (multiple factors),`get_graham_screen` (Graham formula),`get_dividend_stock_screen` (bonus shares) |
| **Want to see market sentiment** | `get_stock_sentiment` (Snowball/stock bar),`get_stock_news_*` (News) |

> 💡 **Tips**: The complete list of 78 tools is described in detail in the v3.0 Analysis Capability Panorama chapter, which can be searched by keywords when binding.

##### Operation steps

1. **Create Agent**
   - "Analysis flow → Agent workshop", Click"New Agent". 
   - **Drop down to select the Agent type**: Choose from system preset types (Analyst, Data Processing, Decision, General, etc.).
   - **Pull down to select Agent name**: Name the Agent (e.g."Liquor industry expert", "Risk warning specialist") . 
   - Configure system prompt words (define the behavior and role of the Agent).
   - Select the bundled toolset.

2. **Configuration Agent**
   - Set the default LLM model.
   - Set parameters such as temperature (Temperature) and maximum Token.
   - Configure a tool whitelist (restricting the Agent to only call specified tools).

3. **test Agent**
   - You can test the Agent directly in the workshop, enter a message and view the response.
   - The workshop strictly exposes LLM errors without making any rules to make it easier to locate problems.

4. **publish Agent**
   - After the test passes and is published, the Agent can be referenced in the workflow.

##### Things to note

- Agent The type determines the range of available tools, please refer to the instructions when selecting.
- UniversalAgent As a safety net: Unregistered Agents will be `agent_configs` Automatically create UniversalAgent instances.
- Modifying a published Agent will affect all workflows that reference it, so please proceed with caution.
- It is recommended to bind 3-7 tools to an Agent. Too many tools will make LLM selection difficult and token consumption will be high.

#### 6.1.5 Skill Center

##### Function description

Skill The center supports the generation and management of Skills (analytics tools) through conversational interactions. The v3.0 Skill automatic generation system uses a 6-stage pipeline, and AI independently writes and verifies new tools.

##### Operation steps

1. **conversational generation Skill**
   - "Analysis flow → Skill Center", Click"generate new Skill". 
   - Describe requirements through dialogue, for example:"I need a tool that can capture northbound inflows and outflows". 
   - AI There will be multiple rounds of dialogue to clarify: input and output, boundary conditions, exception handling.

2. **6 stage pipeline** (Engineer's perspective)
   - **needs analysis** (RequirementAnalyzer) : Clarify Skill functional specifications.
   - **code generation** (CodeGenerator) : AI Write skill code.
   - **Static verification** (StaticValidator) : Grammar check, security check.
   - **sandbox run** (SandboxRunner) : Run tests in an isolated environment.
   - **Output evaluation** (OutputEvaluator) : Evaluate output quality.
   - **iterative optimization** (IterationController) : Iterative improvements based on evaluation results.

3. **View the generation process**
   - The results of each stage can be viewed, including AI-generated code, test output, and evaluation reports.
   - The reason for the failure phase will be marked and can be corrected through manual intervention.

4. **Register and store**
   - The generated Skill is automatically saved to `external_skills` collection.
   - Automatically registered to ToolRegistry and can be referenced in the Agent workshop.

5. **management Skill**
   - View all generated skills.
   - Skills can be disabled, edited, and deleted.
   - Support version management and retain historical versions.

##### The 4-step process you see

For ordinary users,**Generate a Skill in just 4 steps**: 

| steps | what do you do | what the system does |
|------|---------|----------|
| **1. Make demands** | speak in natural language"I want a tool that ______" | System multiple rounds of dialogue to confirm details (input and output formats, data sources) |
| **2. Automatically generated + test** | Wait (usually 5-15 minutes) | Complete needs analysis in-house → code generation → Static verification → sandbox run → Assessment → Iterate |
| **3. See the effect** | Look at the generated code + Test results will be released if satisfied | List all versions, test scores, whether they passed verification |
| **4. bind to Agent** | Choose an Agent and bind the Skill to it | Automatically registered in the tool table, the Agent can be called during the next analysis |

**When do you need to look at a 6-stage pipeline?**
- Skill When there is no run-through, positioning"Is it because the requirements are not clearly stated, or there is a problem with the code, or there is a problem with the test data?"
- When you want to optimize a Skill, look at which stage can be modified
- Ordinary user**No need to understand** 6 stage, just follow steps 4

##### Things to note

- Skill Generation will consume more Tokens, so it is recommended to describe the requirements clearly to reduce the number of iterations.
- Sandbox runs have timeout limits, and complex Skills may require multiple iterations.
- It is recommended that the generated Skill be manually reviewed before official use.
- The bound old Skill will not be overwritten by the new version, and the upgrade will not destroy the existing Agent.

#### 6.1.6 MCP server

##### Function description

MCP (Model Context Protocol) The server exposes the system's six standard tools through the MCP protocol and supports direct calls by external clients such as Claude Desktop and Cursor.

##### exposed tools

- `analyze_stock`: Trigger stock analysis (supports blocking/non-blocking mode)
- `get_report`: Get analysis report
- `chat_with_assistant`: Talk to smart assistant
- `list_workflows`: List available workflows
- `screen_stocks`: stock screen
- `get_market_overview`: Get a market overview

##### Operation steps

1. **Configuration MCP API Key**
   - "Analysis flow → MCP server", Click"generate API Key". 
   - The system is in `system_configs` Manage MCP API Key and support multi-Key distribution.

2. **Set daily quota**
   - Set a daily call quota for each API Key.
   - System press"User + Date"The number of calls is counted and calls that exceed the quota are automatically rejected.

3. **Access in Claude Desktop**
   - Add the MCP server address and API Key in the Claude Desktop configuration file.
   - The analytical capabilities of TradingAgents can be called directly from Claude Desktop.

4. **View call statistics**
   - MCP The server page displays the call volume, success rate, and error log of each API Key.

##### Things to note

- MCP The function is implemented based on the FastMCP framework and complies with the Anthropic MCP specification.
- API Key Please keep it properly and reset it immediately after leakage.
- The daily quota is reset at 0:00 Beijing time.

### 6.2 Agent Workshop (independent entrance)

> This section provides navigation instructions. A complete guide to using the Agent Workshop is available here [6.1.4 Agent workshop](#614-agent-workshop). 

Agent Workshop is a visual tool for creating and managing custom Agents. When the system's built-in analysts and researchers cannot meet your research needs, you can create an exclusive Agent in the workshop.

**Quick entry**: "Analysis flow → Agent workshop", Please refer to Section 6.1.4 for detailed operations.

### 6.3 Skill Center (independent entrance)

> This section provides navigation instructions. A complete guide to using the Skill Center is available here [6.1.5 Skill Center](#615-skill-Center). 

Skill The center manages Skills that can be called in the analysis flow, including system built-in Skills and custom Skills. When new data query or analysis capabilities need to be added to the Agent, they can be created in the Skill Center.

**Quick entry**: "Analysis flow → Skill Center", Please refer to Section 6.1.5 for detailed operations.

### 6.4 Batch analysis (/analysis/batch)

#### Function description

Batch analysis supports the analysis of multiple stocks at the same time, which is suitable for scenarios that require horizontal comparison or in-depth analysis after large-scale screening.

#### Operation steps

1. **Enter batch analysis**
   - "Batch analysis"page.

2. **add stock**
   - Method 1: Enter the stock codes one by one to add.
   - Method 2: Import from the watch list (select a group).
   - Method 3: Import from filter results.
   - Method 4: Paste stock codes in batches (one per line or separated by commas).

3. **Set analysis parameters**
   - Select analysis dimensions (consistent with single stock studies).
   - Select analysis depth (recommended for batch analysis"fast"or"Standard"depth).
   - Set the number of concurrencies (the advanced version supports concurrency, and the standard version executes serially).

4. **Start batch analysis**
   - Click"Start batch analysis". 
   - The system displays overall progress and subtask status for each stock.
   - Full progress can be viewed in the Mission Center.

5. **View batch results**
   - After completion, a batch analysis report summary table is generated.
   - The table displays the comprehensive rating, key indicators, and risk level of each stock.
   - Supports sorting by indicators to quickly find the optimal target.
   - Can be exported to Excel.

#### Things to note

- Batch analysis consumes a large amount of Tokens, and it is recommended not to exceed 20 stocks at a time.
- The number of concurrencies is subject to both authorization levels and API rate limits.
- Batch analysis can be canceled midway, and completed subtask reports will be retained.
- It is recommended to use stock screening to narrow the scope first, and then analyze the candidate stocks in batches, which is more efficient.

### 6.5 timing analysis

#### Function description

Scheduled analysis supports scheduled execution of analysis tasks based on CRON expressions, which is suitable for scenarios that require continuous tracking of certain stocks. divided into"Timed analysis grouping"and"Timing analysis configuration"Two submodules, both located in"settings → personal settings"Down.

#### 6.5.1 Regular analysis grouping (/settings/watchlist-groups)

##### Function description

Scheduled analysis grouping is used to prepare stock collections for scheduled analysis tasks. It supports creating/editing groups and configuring the grouping name, description, color identification, icon, and default analysis depth. Stocks can be imported from a stock list or tag.

##### Operation steps

1. **Create group**
   - "settings → personal settings → Timed analysis grouping", Click"Create new group". 
   - Fill in the group name (such as"daily morning paper", "Weekly review", "Liquor sector tracking") . 
   - Fill in the group description (optional).
   - Choose color identification (for quick identification in lists).
   - Select icon.
   - Set default analysis depth (Quick/Standard/Deep).

2. **Import stocks**
   - Method 1: Add one by one from the stock list.
   - Method 2: Batch import from existing tags.
   - Method 3: Import from watch list groups.

3. **Management grouping**
   - Edit grouping information or adjust stock lists.
   - Delete the group (the scheduled tasks under the group need to be migrated or deleted first).

##### Things to note

- Grouping is the basis for scheduled analysis configuration. Grouping must be prepared before creating a scheduled task.
- It is recommended that each group should not exceed 20 stocks to avoid a single scheduled execution taking too long.

#### 6.5.2 Scheduled analysis configuration (/settings/scheduled-analysis)

##### Function description

Scheduled analysis configuration is used to create and manage scheduled execution analysis tasks. It supports simple mode and advanced mode (Cron expression), and can configure execution time period, default grouping, analysis depth, email notification, etc.

##### Operation steps

1. **Create scheduled analysis configuration**
   - "settings → personal settings → Timing analysis configuration", Click"New configuration". 
   - Select the default analysis grouping (selected from the groupings created in 6.5.1).
   - Select analysis depth (Quick/Standard/Deep).
   - Configure email notifications (optional, you need to configure SMTP in notification settings first).

2. **Set execution time**
   - **Simple mode**: Choose daily/weekly/monthly + At execution time, the system automatically generates a CRON expression.
   - **Advanced mode**: Directly enter CRON expressions, suitable for complex scheduling requirements.
   - **fast Preset**: The system presets commonly used time templates (such as"After the market opens on each trading day", "Every Monday morning newspaper") , One click application.

3. **Execute tests**
   - After the configuration is completed, click"Execute tests"Run it once now to verify that the configuration is correct.
   - Test results are displayed in the execution history.

4. **View execution history**
   - After each scheduled execution, it is automatically recorded in the history list.
   - You can view the status, time taken, report link, and error information of each execution.

5. **Manage scheduled tasks**
   - The list page can enable/disable, edit, and delete scheduled configurations.
   - Support batch operations.

##### Things to note

- CRON The expression uses a 5-segment format (minute, hour, day, month, week), and the time zone is Asia/Shanghai.
- Scheduled analysis will also be executed on non-trading days. If you need to execute it only on trading days, please configure filtering logic in the workflow.
- If the scheduled task fails to execute, it will be automatically retried three times. If it still fails, a notification will be sent.
- Tokens consumed by regular analysis will be included in the account quota. Please pay attention to cost control.
- It is recommended to arrange scheduled analysis after the market opens (such as 16:00 Afterwards), make sure that the day's data is synchronized.

#### 6.5.3 Manage via smart assistant

You can say to the smart assistant:
- "Help me create a scheduled task to analyze Kweichow Moutai at 9 a.m. every day"
- "View all my scheduled analysis tasks"
- "Disable the daily morning report scheduled task"

### 6.6 General Research (/analysis/general)

#### Function description

Universal research is a flexible research workbench based on universal processes. Unlike single-stock research, it does not limit the analysis target to stock codes, but supports any customized analysis targets (such as industry trends, macro events, theme concepts, etc.), and cooperates with universal types of workflows to complete free exploratory research.

**Core differences from single-stock research:**

| Comparative item | single stock research | general studies |
|--------|---------|---------|
| Analyze goals | Stock code (e.g. 600519) | Arbitrary text (such as"New energy vehicle industry chain")  |
| Workflow type | Single stock research process/ETF analysis process | Common research process |
| form parameters | Fixed (stock code, analysis date, depth, etc.) | Dynamic (determined by the configuration of the selected process) |
| Results view location | Research report page | mission center |
| History | Research report page | general research page"historical results"tab page |

#### Operation steps

1. **Enter General Studies**
   - Left navigation bar"general studies", Go to the General Research page.
   - The page is divided into"new analysis"and"historical results"Two tabs.

2. **Select analysis process**
   - in"new analysis"tab page"Process selection"In the drop-down box, select a common research process.
   - The drop-down box only displays workflows of general type, with"Default"The labeled one is the system default process.
   - When selected, a process description will be displayed below.

3. **Configure execution parameters**
   - After selecting a process, the page dynamically displays the parameter form configured for the process.
   - The parameter form is based on the process `input_config` Automatically generated, parameters for different processes may be different.
   - Common parameter types:
     - **Text input**: Single or multiple lines of text (such as analysis objectives, research directions)
     - **digital input**: Numeric parameters (such as the number of days to look back)
     - **drop down selection**: Single or multiple selection (such as model selection, analyst selection)
     - **date selection**: date parameter
     - **switch**: Boolean parameters (such as whether to enable memory)
   - Required fields will be in red `*` logo.

4. **Start analysis**
   - Click"Start analysis"button.
   - The system creates an analysis task and enters the execution state. The page displays:
     - Task ID (can be copied)
     - Analyze goals
     - Start time and elapsed time
     - Real-time progress bar and current execution steps
   - During the analysis process, the button is displayed in the loading state and cannot be clicked repeatedly.

5. **View results**
   - After the analysis is completed, the page displays a success message.
   - Click"View results"Button jump to**mission center**View the full analysis report.
   - General research results**Will not appear on the research report page**, Only available in the Mission Center.
   - Click"Reanalyze"You can go back to the form and resubmit.

6. **View historical results**
   - switch to"historical results"tab page.
   - Supports filtering by the following conditions:
     - Process: Select a specific generic research process
     - Time range: Filter by date range
     - Keywords: Search analysis target or summary
     - Status: All/Success/Failed
   - Click the history record to view details, including: basic information, error information, analysis summary, complete workflow output, decision information, and raw data.

#### Things to note

- General research must select a general type of workflow. If there is no available process, please contact the administrator at"Analysis flow → process management"Created in .
- The analysis target of general research is determined by the process definition. Some processes may require the input of stock codes as analysis targets. Please refer to the process description.
- General research results can only be viewed in the task center and will not appear on the research report page.
- Timed analysis also supports common research workflows and is available at"Timing analysis configuration"Select a common process and configure parameters.
- A single analysis will consume LLM Token, please make reasonable arrangements according to the authorization quota.

---

## Chapter 7 Learning Center (/learning)

### Function description

The Learning Center provides a wealth of learning materials, including AI basics, prompt word engineering, model selection guides, analysis principles, risk tips, paper resources, and advanced courses. Help users understand the principles and methods of AI investment analysis from scratch.

### Content classification

1. **AI basic knowledge**: What is a large language model (LLM), the working principle, capabilities and limitations of LLM.
2. **prompt word project**: Prompt Basics, best practices, how to write effective analysis instructions.
3. **Model selection**: Comparison of features, applicable scenarios, and cost considerations of different LLMs.
4. **Analysis principle**: Multi-agent system principles and TradingAgents framework design ideas.
5. **Risks and Limitations**: AI Limitations of analysis, investment risk tips, and how to use AI recommendations rationally.
6. **Resources**: TradingAgents Interpretation of papers and related academic resources.
7. **Advanced courses**:  (Advanced functions) Systematic investment courses, covering strategy construction, risk control system, portfolio management, etc.

### Operation steps

1. **Browse study materials**
   - "Learning Center"The page displays all information by category.
   - Click on the article title to read.
   - Support search function.

2. **Advanced courses** (advanced features)
   - Advanced courses are paid content and require premium version authorization.
   - Courses are organized into chapters to support learning progress tracking.
   - Each chapter is equipped with exercises and cases.

3. **User Guide**
   - "User Guide" (/guide) It is a built-in quick start tutorial.
   - Suitable for first time browsing.

### Things to note

- The content of the learning center will be continuously updated, and it is recommended to browse it regularly.
- Advanced course content is for learning purposes only and does not constitute investment advice.

---

## Chapter 8 System Management

This chapter introduces system management-related functions, located in"settings → System management"Down. These features are primarily used by administrators.

### 8.1 Configuration management

#### Function description

Configuration management is the core configuration entrance of the system and manages all configuration items in a unified manner, including LLM keys, data sources, analysis parameters, notification settings, etc.

#### Operation steps

1. **Enter configuration management**
   - "settings → System configuration → Configuration management". 

2. **Configuration classification**
   - **LLM Configuration**: API Parameters such as key, model selection, model priority, temperature, etc.
   - **Data source configuration**: Tushare, FinnHub, Data source keys and priorities such as communication data.
   - **Analysis configuration**: Default analysis depth, cache strategy, and number of concurrencies.
   - **Notification configuration**: Email SMTP, Webhook address, QQ Bot configuration.
   - **System configuration**: Time zone, language, log level.

3. **QQ Bot Configuration**
   - QQ Bot Access allows interaction with the smart assistant through QQ instant messaging.
   - Configuration items: QQ Bot account, password, WebSocket connection address.
   - After configuration, you can directly chat with the intelligent assistant in QQ, and the output will be automatically converted into a simplified plain text format (adapted to IM scenarios).
   - See details [5.1 AI Conversation Assistant](#51-ai-Conversation Assistant-assistant) in"IM format adaptation". 

4. **Configuration import and export**
   - Supports exporting the current configuration as a JSON file (keys will be desensitized).
   - Supports importing configurations from JSON files (for easy migration or backup).

5. **Configuration verification**
   - After modifying the configuration, click"Verify"Check the validity of configuration items.
   - The system has a built-in configuration checker that will prompt unreasonable configuration combinations.

#### Things to note

- After the configuration is modified, some items need to be restarted to take effect, and the system will prompt you.
- Never modify core configurations such as database connections at will in the production environment.
- The configuration export file does not contain clear text keys and can be shared safely.

### 8.2 Database management

#### Function description

Database management provides MongoDB database status viewing, backup and recovery, and collection management functions.

#### Operation steps

1. **View database status**
   - "settings → System management → database". 
   - Displays the connection status, database size, each collection size, and index status.

2. **Data backup**
   - Click"Back up database", Select the export scope (all collections or specified collections).
   - The system generates a backup file (.archive format), which can be downloaded and saved.

3. **data recovery**
   - To upload the backup file, click"restore". 
   - The system will prompt for confirmation before restoring to avoid misoperation.

4. **Collection management**
   - View all collections (such as `analysis_reports`, `paper_trades`, `favorites`, `external_skills` etc.).
   - You can view the number of documents in the collection and the space occupied.
   - Supports clearing specified collections (dangerous operation, requires secondary confirmation).

5. **Index management**
   - View the index for each collection.
   - Indexes can be created and deleted.

#### Things to note

- Database backup is recommended to be performed regularly and can be automated with scheduled tasks.
- The restore operation will overwrite existing data, so please be careful.
- Cleared collections are irrecoverable, so be sure to back them up before operating.
- v3.0 Uses MongoDB port 27019, isolated from v2.x.

### 8.3 Synchronization of multiple data sources

#### Function description

Multi-data source synchronization is responsible for synchronizing basic stock data, market data, financial data, etc. from external data sources, which is the basis for the normal operation of the analysis function. Supports multi-data source status viewing, usage suggestions and synchronization control.

#### Operation steps

1. **View data source status**
   - "settings → System management → Synchronization of multiple data sources". 
   - The page displays the connection status and availability of each data source (Tushare, AKShare, etc.).

2. **Synchronous control**
   - Data synchronization can be triggered manually.
   - View sync history to understand sync progress and failure reasons.

3. **Data source usage recommendations**
   - The page provides usage suggestions for each data source to help choose the appropriate data source.

#### Things to note

- Data synchronization depends on the data source API quota, and different Tushare points levels have different calling restrictions.
- The first synchronization takes a long time (more than 30 minutes), so it is recommended to perform it during off-peak periods.
- When synchronization fails, you can check the log to locate the reason. Common reasons include API quota exhaustion and network timeout.

### 8.4 scheduled tasks

#### Function description

Scheduled tasks manage all background scheduling tasks of the system, including system-level tasks such as data synchronization, report cleaning, cache refresh, etc., as well as scheduled analysis tasks created by users.

#### Operation steps

1. **View scheduled task list**
   - "settings → System management → scheduled tasks". 
   - Displays the task name, CRON expression, last execution time, next execution time, and status.

2. **System built-in tasks**
   - Data synchronization task (daily after hours)
   - Notification of cleanup tasks (90 days overdue cleanup)
   - Cache refresh task

3. **Task operation**
   - Enable/disable tasks.
   - Manually trigger execution.
   - View execution history and logs.

#### Things to note

- Do not disable system built-in tasks at will, otherwise it may affect the normal operation of the system.
- The configuration entry for scheduled analysis tasks is at"settings → Timing analysis configuration", Not here.
- Scheduled tasks are implemented based on APScheduler, and the tasks will automatically resume after the service is restarted.

### 8.5 Operation log and system log

#### Function description

The system provides two independent log viewing pages:"Operation log"Record user business operations,"System log"Record system operation events to facilitate troubleshooting and auditing.

#### Operation steps

1. **View operation log**
   - "settings → System management → Operation log". 
   - Record the user's business operations (analysis tasks, transaction operations, configuration changes, etc.).
   - Supports filtering by time range and operation type.

2. **View system log**
   - "settings → System management → System log". 
   - Record system running events (service startup, configuration loading, scheduled tasks, error messages, etc.).
   - Supports filtering by level (DEBUG/INFO/WARNING/ERROR).
   - Supports search by keyword.

3. **Download log**
   - Log files can be downloaded by date.
   - Docker Deployment can be done via `docker-compose -p ta-v3 logs` View real-time logs.

#### Things to note

- Logs are saved for 30 days by default and can be adjusted in the configuration.
- DEBUG The level log volume is large, and it is recommended to use the INFO level in production environments.
- The logs do not contain sensitive information such as API keys (which have been desensitized).

### 8.6 Tool capability index

#### Function description

The tool capability index establishes a unified index for all Agents, Tools, and Skills in the system and supports semantic search, making it easy to quickly locate available capabilities in workflow orchestration and intelligent assistants.

#### Operation steps

1. **View capability index**
   - "settings → System management → Tool capability index". 
   - Displays a list of all registered Agents, Tools, and Skills.

2. **Semantic search**
   - Capabilities required to enter natural language descriptions, e.g."Get northbound funding data". 
   - The system returns a list of matching Tools/Skills.

3. **Index management**
   - The index can be rebuilt manually (rebuilding is recommended after adding Tool/Skill).
   - View index status and statistics.

#### Things to note

- The capability index is the basis for AI workflow architects and intelligent assistant call tools, and it is important to keep the index up to date.
- After a new Tool or Skill is added, the system will automatically update the index, but it is recommended to manually rebuild it regularly to ensure consistency.

### 8.7 Cache management

#### Function description

Cache management is used to view and manage Redis cache, including market data cache, analysis result cache, session cache, etc.

#### Operation steps

1. **View cache status**
   - "settings → System configuration → Cache management". 
   - Displays Redis connection status, memory usage, and hit rate of each cache category.

2. **Caching operations**
   - Clear cache of specified categories (quotes, analysis results, sessions).
   - Clear all caches (requires second confirmation).

3. **Cache policy configuration**
   - Market data cache duration (default 1 hour).
   - How long to cache analysis results (default 24 hours).

#### Things to note

- Clearing the cache will cause subsequent requests to re-fetch data and be temporarily slowed down.
- v3.0 Uses Redis port 6381, isolated from v2.x.

### 8.8 Data import management (/settings/data-import)

#### Function description

Data import management provides batch import portals for stock data and social media messages, and supports importing external data into the system database through API interfaces. This feature is an advanced feature and requires premium version authorization.

#### Operation steps

1. **Enter data import management**
   - "settings → System management → Data import management". 

2. **Stock data import**
   - Click"Stock data import", View supported import data types and API documentation.
   - Supports importing: market data, financial data, custom indicators, etc.
   - Provide JSON/CSV template download, prepare data according to the template format and then upload it through API.

3. **Social media message import**
   - Click"Social media message import", View the Social Media Message Import API Guide.
   - Supports bulk uploads in JSON and CSV formats.
   - Imported social media messages can be found in"Social media message management"View and use it.

4. **View the API guide**
   - The page provides detailed API access document links.
   - Contains authentication methods, request formats, field descriptions, and sample codes.

#### Things to note

- Data import requires Advanced Edition authorization. Standard Edition users can only view documents and cannot perform imports.
- Please confirm that the data format is correct before importing. Incorrect format will cause the import to fail.
- It is recommended to perform large batch imports in batches to avoid excessive timeout for a single request.

### 8.9 Social media message management (/settings/social-media)

#### Function description

Social media message management is used to view and manage imported social media public opinion data. It supports multi-dimensional filtering by stock code, market, platform, sentiment, etc., providing additional public opinion information sources for news analysts.

#### Operation steps

1. **Check social media news**
   - "settings → System management → Social media message management". 
   - The list displays all imported social media messages, including source platform, release time, content summary, and sentiment tags.

2. **Filter messages**
   - Filter by ticker: View sentiment related to a specific stock.
   - Filter by market: A-shares/ETFs.
   - Filter by platform: Oriental Fortune Stock Bar, Snowball, Weibo, etc.
   - Filter by sentiment: Positive / Negative / Neutral.

3. **View message details**
   - Click on the message to view the full content, original link, and associated stocks.
   - You can check which analysis reports this news is quoted by.

4. **Upload social media data**
   - Click"Upload data"button.
   - Select file format (JSON/CSV).
   - Required fields: stock code, platform, content, release time.
   - Select encoding (UTF-8/GBK).

5. **View the API guide**
   - Click"API Access Guide"View detailed API documentation.
   - Contains authentication method, request format, and field description.

#### Things to note

- Social media data is imported by users themselves and is not actively collected by the system.
- Emotion labels are specified when importing or automatically determined by the system.
- Social media messages are retained for 90 days and automatically cleared upon expiration.

### 8.10 System update (/settings/update)

#### Function description

System Update is used to check and install system version updates, providing different update methods according to the deployment method (Docker/Windows Portable Edition/Windows Installation Edition).

#### Operation steps

1. **View current version**
   - "settings → System management → System update". 
   - Displays the current version number, build number, and release date.

2. **Check for updates**
   - Click"Check for updates", The system connects to the update server to query the latest version.
   - If there is a new version, the version number, update content summary, and update package size are displayed.

3. **Docker Deploy updates**
   - Docker Deployments are not updated through this page.
   - Use the command line to pull the new image and restart:
     ```bash
     docker-compose -p ta-v3 pull
     docker-compose -p ta-v3 up -d
     ```

4. **Windows Portable/installed version updates**
   - Click"Download update package", Download the latest version installation package.
   - After the download is complete, click"Apply updates", The system automatically stops services, replaces files, and restarts.
   - Do not close the program or cut off power during the update process.

5. **View update history**
   - The page displays the installed version history.

#### Things to note

- It is recommended to back up configuration and data before updating.
- Docker Please update the deployment by pulling new images and do not use this page.
- If the update fails, you can check the log to locate the reason, which is usually a network problem or file occupation.
- Major version upgrades (such as v2.x → v3.0) Online updates are not supported and a new installation is required.

### 8.11 Prompt word template (/settings/templates)

#### Function description

Prompt word template management is used to manage the system prompt word templates of each Agent. It supports filtering by Agent type, Agent name, template name, preference, source, status, and provides operations such as viewing, cloning, editing, deleting, setting as current, and debugging. This feature is advanced.

#### Operation steps

1. **View template list**
   - "settings → Analysis configuration → prompt word template". 
   - Supports multi-dimensional filtering: Agent type, Agent name, template name, preference label, source (system built-in/customized), status (enabled/disabled).

2. **Edit template**
   - Click on the template to enter the editing page.
   - The editing area displays available variables (such as `{stock_name}`, `{industry}`, `{financial_data}` etc.).
   - Prompt word field descriptions help understand the purpose of each field.
   - The system will perform a basic syntax check when saving.

3. **Clone template**
   - Clone an existing template as a base, then modify it and save it as a new template.
   - Suitable for customization based on system built-in templates.

4. **Set as current template**
   - Each Agent can set one"Current template", Use this template when analyzing.
   - Switching the current template will take effect immediately.

5. **debug template**
   - Clickable on the edit page"Debugging", Render the template with test data.
   - View the complete prompt words actually injected into LLM to facilitate optimization.

6. **Prompt Real-time preview (/settings/prompt-preview)**
   - in"settings → Analysis configuration"middle click"Prompt Preview", Enter the Prompt real-time preview page.
   - Select the Agent type and Agent name to preview the final prompt after layered assembly.
   - Review the sources of each segment (system templates, custom templates, injection strategies, etc.) and capability gap analysis.
   - It is easy to understand the Prompt assembly process and troubleshoot prompt word problems.

#### Things to note

- The system's built-in templates cannot be deleted, but they can be cloned and modified.
- Modifying the template will affect all analysis tasks using the template. Please debug and verify it first.
- Variables used in the template must match the Agent context, otherwise they will be left empty when rendering.
- Prompt The preview is read-only. To modify Prompt, please go to prompt word template or injection policy management.

### 8.12 Inject policy management (/settings/prompt-policies)

#### Function description

Injection strategy management is used to press Agent + Scenario control context injection rules, finely manage the context information received by each Agent in different scenarios. This feature is advanced.

#### Configuration item description

1. **injection mode**: Control the overall strategy of context injection.
2. **Industry/stock portrait inheritance**: Whether to inject industry and stock portrait information into the Agent context.
3. **ability block injection**: Whether to inject descriptions of available tools/capabilities so that the Agent knows which tools can be called.
4. **External gap reminder**: Whether to remind the Agent to pay attention to data limitations when data is missing.
5. **Comparable company injection**: Whether to inject information about comparable companies in the same industry for Agent's reference.
6. **Injection location**: Control the position of the injected content in the prompt word (prefix/postfix/inline).

#### Operation steps

1. **Create an injection strategy**
   - "settings → Analysis configuration → Injection strategy management", Click"New strategy". 
   - Select the target agent and scenario.
   - Configure various injection rules.
   - Save and enable.

2. **management strategy**
   - Support enabling/disabling, editing, and deleting policies.
   - each Agent + Scenario combinations can be configured with independent strategies.

#### Things to note

- The injection strategy affects the Agent's analysis quality and Token consumption. The more detailed the configuration, the greater the Token consumption.
- It is recommended to use the default strategy first and only adjust it when the analysis effect is not satisfactory.
- After the policy is changed, the analysis needs to be re-executed to take effect.

### 8.13 Prompt Design Assistant (/settings/prompt-design)

#### Function description

Prompt The design assistant is a guided tool that helps users design high-quality analysis prompt words through a four-step process. It is suitable for users who are not familiar with prompt word engineering to get started quickly. This feature is advanced.

#### Design process (four steps)

1. **Select analysis target**
   - Select the core objective of this analysis (such as valuation analysis, risk assessment, industry comparison, etc.).

2. **Select stocks and industries**
   - Specify the target stock and industry.
   - The system will recommend relevant variables and data accordingly.

3. **Industry configuration**
   - Check whether the industry has been configured.
   - If there is an existing configuration, you can use it directly; if not, you can create a new industry configuration.
   - Industry configuration includes industry characteristics, key indicators, comparable companies, etc.

4. **Processes and nodes**
   - Select the analysis process (corresponding to the workflow).
   - Optimize the prompt words of each node.
   - The system automatically recommends optimization suggestions based on industry configurations.

#### Operation steps

1. "settings → Analysis configuration → Prompt design assistant". 
2. Follow the four-step process to configure.
3. After completion, you can preview the generated prompt words.
4. Save it as a prompt word template with one click, or apply it directly to the specified Agent.

#### Things to note

- Prompt The prompt words generated by the design assistant are recommended to be manually reviewed before application.
- Industry configuration is the basis of Prompt design. It is recommended to improve the industry configuration first.
- Different analysis goals are suitable for different prompt word structures, so do not generalize.

### 8.14 Industry/Stock Configuration (/settings/analysis-profiles)

#### Function description

Industry/stock configuration generates industry analysis drafts through chat-style collaboration, helping the system understand the characteristics of specific industries and individual stocks, thereby improving the quality of analysis. Configuration content includes industry characteristics, analysis dimensions, key indicators, comparable companies, etc. This function is an intelligent configuration function.

#### Operation steps

1. **Enter the configuration page**
   - "settings → Analysis configuration → Industry/Stock Allocation". 

2. **Select industry**
   - Select your target industry from a list of preset industries, or enter a custom industry name.

3. **Generate industry draft**
   - Click"Generate draft", AI The first version of the configuration draft will be generated based on industry information.
   - The draft includes: description of industry characteristics, recommended analysis dimensions, key indicators, and list of comparable companies.

4. **Manual finishing**
   - View the current draft in the right panel.
   - Each field can be manually edited to supplement or correct the AI-generated content.
   - The data coverage assessment shows the data completeness of the configuration.

5. **Save configuration**
   - Save the configuration after refinement is completed.
   - After the configuration takes effect, it will be automatically applied when analyzing stocks in this industry.

6. **Suggestions for next steps**
   - The system gives next-step optimization suggestions based on the current configuration (such as adding comparable companies, adding key indicators, etc.).

#### Things to note

- The more complete the industry configuration, the higher the analysis quality, but the longer the configuration time.
- For comparable companies, it is recommended to select 3-5 stocks in the same industry and similar market capitalization.
- The configuration can be modified at any time, and newly executed analyzes will use the latest configuration after modification.
- The system has preset configuration templates for some common industries, which can be used directly or modified on this basis.

### 8.15 Usage statistics (/settings/usage)

#### Function description

The usage statistics page displays the LLM call records and token consumption of each functional module of the system, helping users understand resource usage trends and cost estimates.

#### Description of statistical scope

Usage statistics cover LLM calls for the following functions:
- Single Stock Research (analysis_type: stock_analysis) 
- Batch analysis (analysis_type: stock_analysis) 
- Scheduled analysis (take the analysis service link)
- Agent Workshop (analysis_type: agent_workshop) 
- Skill generate(analysis_type: skill_generation) 
- Skill Parameter extraction/testing (analysis_type: skill_test) 
- AI Conversation Assistant (analysis_type: assistant) 
- Prompt Design Assistant (analysis_type: prompt_design) 
- Position analysis (analysis_type: portfolio) 
- Operation review (analysis_type: trade_review) 

#### Statistical overview

Four core indicators are displayed at the top of the page:

| indicator | Description |
|------|------|
| Total requests | Total number of LLM API requests for stock analysis during the statistical period |
| total input Token | The total amount of input tokens for stock analysis requests during the statistical period |
| total output Token | The total amount of output tokens for stock analysis requests during the statistical period |
| total cost | Estimated cost based on system configuration Token unit price (for reference only) |

#### About cost estimates

- The cost is based on the Token unit price of each model in the system configuration.**Estimate**derived, not the actual bill amount.
- Each LLM provider has different billing rules (such as subscription system, coding plan, monthly package, etc.), and there may be a large deviation between the estimated cost and the actual bill.
- It is recommended that this cost data be**Relative trend reference** (Observe consumption increase and decrease trends) rather than absolute cost basis.
- Please refer to the LLM supplier's official bill for actual charges.

#### chart area

1. **Statistics by supplier**: The pie chart shows the Token proportion of each LLM provider (DeepSeek, Tongyi Qianwen, OpenAI, etc.).
2. **Statistics by model**: The pie chart shows the Token proportion of each model (such as deepseek-chat, deepseek-reasoner, qwen-plus, etc.).
3. **daily cost trend**: The line chart shows the daily estimated cost change trend within the statistical period.

#### Usage records

The bottom table displays detailed usage records, including:
- Time: Request time.
- Supplier: LLM supplier name.
- Model: The name of the model to use.
- Input/output Token: Token consumption for this request.
- Cost: The estimated cost of this request.
- Function: the function module called (such as single stock analysis, batch analysis, etc.).

#### Operation steps

1. "settings → System management → usage statistics". 
2. Select a fiscal period (last 7 days / 30 days / 90 days).
3. View statistical overviews and charts.
4. For the latest data, click"Refresh"button.
5. Old records can be cleared to free up storage space.

#### Things to note

- Use statistics to cover LLM calls for the main functions of the system, including stock analysis, Agent workshop, Skill generation, AI dialogue assistant, position analysis, operation review, etc.
- Estimated costs are for reference only, actual charges are subject to LLM supplier bill.
- It is recommended to pay attention to Token consumption**relative trend**, rather than an absolute amount.
- If you find an abnormal sudden increase in Token consumption, you can check whether there are abnormal analysis tasks or key leaks.

---

## Chapter 9 Personal Settings (/settings)

The personal settings module manages the current user's personal preferences and account security configuration, located at"settings → personal settings"Down. Contains the following sub-modules: general settings, appearance settings, analysis preferences, notification settings, security settings, assistant settings, email notifications (advanced functions), channel push (advanced functions), scheduled analysis grouping, scheduled analysis configuration, and authorization management. For details on timing analysis grouping and timing analysis configuration, see [6.5 timing analysis](#65-timing analysis). 

### 9.1 General settings

#### Function description

Configure the user's basic information preferences.

#### Operation steps

- **Username**: Displays the current login user name (read-only, cannot be modified).
- **Email**: Set or modify your personal email address.
- **language**: Simplified Chinese / English.
- **time zone**: Beijing time (UTC+8) / new york time (UTC-5) / london time (UTC+0). 
- Click"Save settings"button takes effect.

### 9.2 Appearance settings

#### Function description

Configure interface display preferences.

#### Operation steps

- **theme mode**: Light theme / dark theme / follow system.
- **sidebar width**: Adjust sidebar width via slider (200-400px in 20px steps).
- Click"Save settings"button takes effect.

### 9.3 Analyze preferences

#### Function description

Configure the default behavior when analyzing single stocks to reduce repeated settings for each analysis.

#### Operation steps

- **Default market**: A Stock/ETF, affects the default market selection when entering individual stock research.
- **Default analysis depth**: 1 Level - Quick analysis / Level 2 - Basic analysis / Level 3 - Standard analysis (recommended) / Level 4 - In-depth analysis / Level 5 - Comprehensive analysis.
- **Default analyst**: Check the analysts selected by default for each analysis (market analysts, sector analysts, market analysts, fundamental analysts, news analysts, social media analysts).
- **risk appetite**: Defensive / Neutral / Highly Resilient (only affects the presentation style of the scenario research perspective and does not constitute investment advice).
- **Auto refresh**: Automatically refresh analysis results after turning on.
- **refresh interval**: Set the auto-refresh interval (10-300 seconds).
- Click"Save settings"button takes effect.

### 9.4 Notification settings

#### Function description

Configure how system notifications are received.

#### Operation steps

- **Desktop notifications**: Turn on/off browser desktop notifications.
- **Research completion notice**: Turn on/off notifications when analysis tasks are completed.
- **System maintenance notification**: Turn on/off system maintenance related notifications.
- Click"Save settings"button takes effect.

### 9.5 Security settings

#### Function description

Account security related configurations.

#### Operation steps

- **Change password**: Click"Change password"button to set a new password in the pop-up dialog box.

### 9.6 Assistant settings

#### Function description

Configure the smart assistant's behavior preferences and reply style.

#### Operation steps

- **Assistant name**: Set the name of the smart assistant (such as"small fortune", "Investment research assistant") , Can be addressed directly in conversation.
- **tone style**: Professional and rigorous / relaxed and friendly / concise and efficient.
- **Custom instructions**: Enter custom instructions (such as"Keep answers as short as possible, use tables, and bring data sources when replying.") , The assistant will use these instructions to adjust the answering style.
- Click"Save settings"button takes effect.

### 9.7 Email notification (/settings/email, advanced features)

#### Function description

Email notification is an independent advanced function page used to configure the SMTP email server and manage email notification rules for various analysis tasks. Unlike desktop notifications in 9.4 notification settings, email notifications support pushing analysis reports and execution results to designated mailboxes via email.

#### Operation steps

1. **Configure SMTP server**
   - "settings → personal settings → Email notification". 
   - Fill in the SMTP server address, port, sender email, SMTP username and password.
   - Select encryption method (SSL / TLS / No encryption).
   - Click"Send test email"Verify that the configuration is correct.

2. **Configure notification rules**
   - Select the event type that requires email notification:
     - **Single stock research completed**: A report summary is sent after the single stock analysis task is completed.
     - **Batch analysis completed**: The summary results are sent after all batch analyzes are completed.
     - **Timing analysis completed**: Send a report after the scheduled analysis task is completed.
     - **Analysis failure notification**: Send error notification when task fails.
   - Set the recipient email address (multiple are supported, separated by commas).

3. **View sending history**
   - The email sending history is displayed at the bottom of the page.
   - You can view the sending status, sending time, recipients, and subject of each email.
   - Emails that failed to be sent can be clicked"Resend". 

#### Things to note

- Email notification is an advanced feature and requires premium version authorization.
- SMTP Passwords are stored in encrypted form and will not be displayed in clear text.
- It is recommended to use a dedicated mailbox to send notifications to avoid being limited by the main mailbox.
- It is recommended to use the scheduled analysis email notification in conjunction with the 6.5 scheduled analysis configuration.

### 9.8 Channel push (/settings/channel-configs, advanced features)

#### Function description

Channel push is an independent advanced function page that supports pushing system events to multiple instant messaging channels (Feishu, DingTalk, Enterprise WeChat, and email) to achieve multi-channel message access. Unlike 9.7 email notifications, channel push supports multiple IM platforms and more flexible event subscriptions.

#### Supported push channels

| channel | Description | Configuration items |
|------|------|--------|
| **Feishu** | Push to Feishu group or individual | Webhook URL, Signing key |
| **DingTalk** | Push to DingTalk group | Webhook URL, Signing key |
| **Enterprise WeChat** | Push to corporate WeChat group | Webhook URL |
| **Mail** | Push to designated email | SMTP Configuration (shared with 9.7) |

#### Supported event subscriptions

| event | Description |
|------|------|
| **Analysis completed** | Push report summary after completion of single stock/batch/timed analysis |
| **Warning notification** | Pushed when price warning, take profit and stop loss are triggered |
| **tool gap** | AI Pushed when the workflow architect finds a skill gap |
| **System notification** | Push system events such as system updates and authorization expiration |

#### Operation steps

1. **Enter the channel push page**
   - "settings → personal settings → Channel push". 

2. **Add push channel**
   - Click"Add new channels". 
   - Select the channel type (Feishu / DingTalk / Business WeChat / Email).
   - Fill in the channel configuration (Webhook URL, keys, etc.).
   - Click"test connection"Verify channel availability.

3. **Configure event subscription**
   - Select the event type to subscribe to in the channel details.
   - Different event combinations can be subscribed to different channels.

4. **Management channels**
   - Supports enabling/disabling, editing, and deleting channels.
   - You can view the push history and success rate of each channel.

#### Things to note

- Channel push is an advanced feature and requires premium version authorization.
- Webhook URL and keys are stored encrypted.
- Each IM platform has limits on message frequency. It is recommended to only subscribe to important events.
- Please keep your Feishu and DingTalk signing keys properly and reset them immediately if they are leaked.

---

## Chapter 10 Frequently Asked Questions (FAQ)

### Q1: What should I do if it prompts that the port is occupied during installation?

**A: ** v3.0 By default, ports 8002 (backend) and 8082 (frontend) are used. If the port is occupied:

1. Windows Installation package: The installation program will prompt you to select another port or release the occupied port.
2. Docker Deployment:Modify `docker-compose.yml` port mapping in .
3. View port occupancy: Windows uses `netstat -ano | findstr :8002`, Linux Use `lsof -i:8002`. 

### Q2: API Does the analysis task report an error after key configuration?

**A: ** Please follow the following steps to troubleshoot:

1. in"settings → System configuration"middle click"test connection"Verify key validity.
2. Check if the key has sufficient balance/quota.
3. Check whether the corresponding API endpoint is accessible from the network (especially OpenAI requires a proxy).
4. View"Log management"Get details in the error log.
5. If using a proxy, set this in the configuration `HTTP_PROXY` / `HTTPS_PROXY`. 

### Q3: Analysis tasks are always queued and cannot be executed?

**A: ** Possible reasons:

1. The authorization level limits the number of concurrencies. The standard version can only run 1 task at the same time. Please wait for the current task to be completed.
2. Check if there is"zombie"Tasks occupy concurrency slots and can be canceled in the task center.
3. Insufficient system resources (CPU/memory), please check the service resource usage.

### Q4: Analysis reports show incomplete or empty data?

**A: ** Possible reasons:

1. The data source API quota is exhausted, please check the synchronization status on the data synchronization page.
2. The stock is a new or sub-new stock and there is insufficient historical data.
3. The stock code is entered incorrectly, please check the code format.
4. Basic data synchronization is not completed, please execute first"Initialize basic stock data". 

### Q5: How to reduce Token consumption?

**A: ** Suggestions:

1. Use low depth (level 1-2) for daily analysis, and high depth (level 3-4) for important targets.
2. Choose cost-effective models (such as DeepSeek) as your main workhorse.
3. Select analysts as needed, and do not check unnecessary analysis dimensions.
4. Make good use of cache, repeated analysis of the same stock will hit the cache.
5. in"System management → usage statistics"Check the Token consumption trend of each function and adjust the strategy in a timely manner (note that the estimated cost is for reference only, and the actual cost is subject to the supplier's bill).

### Q6: Docker How to upgrade the version after deployment?

**A: ** Upgrade steps:

```bash
# 1. Pull the new version image
docker-compose -p ta-v3 pull

# 2. Restart the service (data will not be lost)
docker-compose -p ta-v3 up -d

# 3. Check the log to confirm that the startup is normal
docker-compose -p ta-v3 logs -f backend
```

If you need to roll back, just change the image label to the previous precise version number.

### Q7: What should I do if my smart assistant always doesn't understand my questions?

**A: ** Suggestions:

1. Try to be clear about the stock symbol or name and avoid using pronouns (e.g."that stock") . 
2. Only ask one question at a time, and complex requirements can be described step by step.
3. Utilize multi-topic sessions, with each topic focusing on a research objective.
4. If the assistant calls the wrong tool, you can provide feedback"No, what I want is..."Make corrections.
5. Regularly clean up irrelevant session history to avoid contextual interference.

### Q9: v3.0 Can it be used with v2.x?

**A: ** Can. v3.0 and v2.1.0, v2.0.1 use completely independent ports and data volumes:

| version | MongoDB | Redis | Backend | front end | Docker Project name |
|------|---------|-------|---------|------|--------------|
| v3.0 | 27019 | 6381 | 8002 | 8082 | `ta-v3` |
| v2.1.0 | 27018 | 6380 | 8001 | 8081 | `ta-v210` |
| v2.0.1 | 27017 | 6379 | 8000 | 8080 | `ta-v201` |

The three can coexist on the same machine without interfering with each other.

### Q10: Are there security issues with the generated Skill code?

**A: ** Skill The automatic generation system takes the following security measures:

1. The static verification phase performs security checks to identify dangerous code patterns.
2. Sandboxes run in an isolated environment with restricted file system and network access.
3. It is recommended that the generated Skill be manually reviewed before official use.
4. Skill The permissions are restricted by the tool whitelist, and only authorized tools can be called.

### Q11: MCP How is the server called by Claude Desktop?

**A: ** Configuration steps:

1. in"Analysis flow → MCP server"Generate API Key.
2. In the Claude Desktop configuration file (`claude_desktop_config.json`) Add in:
   ```json
   {
     "mcpServers": {
       "tradingagents": {
         "command": "npx",
         "args": ["-y", "fastmcp-client"],
         "env": {
           "MCP_SERVER_URL": "http://localhost:8002/mcp",
           "MCP_API_KEY": "your-api-key"
         }
       }
     }
   }
   ```
3. Restart Claude Desktop to invoke the analytical capabilities of TradingAgents in a conversation.

### Q12: How to back up and migrate data?

**A：**

1. **backup**: in"settings → System management → database"Click"Back up database", Download the backup file.
2. **Migrate**: After deploying the system in the new environment, pass"restore"Function to upload backup files.
3. **Docker Data volume backup**: 
   ```bash
   # Back up MongoDB data volumes
   docker run --rm -v ta-v3_mongodb_data:/data -v $(pwd):/backup ubuntu tar czf /backup/mongodb-backup.tar.gz /data
   ```
4. It is recommended to automatically back up regularly, which can be implemented in conjunction with scheduled tasks.

### Q13: What is the difference between the JD Cloud Cooperation Edition and the Standard Edition?

**A: ** JD Cloud Cooperation Edition is a version specially customized for JD Cloud users. The main differences are:

1. **Configuration method**: The JD Cloud version injects large models and data source configurations through environment variables, eliminating the need for manual configuration on the interface; the Standard version requires configuration on the interface.
2. **Available models**: JD Cloud version only supports 4 models (GLM-5 / GLM-5.1 / GLM-5.2 / DeepSeek-V4-Flash) provided by JD Cloud; the standard version supports multiple vendors.
3. **data source**: JD Cloud version only supports Tushare; the standard version supports Tushare / AKShare / BaoStock.
4. **Interface differences**: JD Cloud version hides the large model and data source configuration interface, and disables related APIs.
5. **LLM speed limit**: Jingdong cloud version built-in 429 retry + Concurrency reduction mechanism ensures stable operation under JD Cloud API speed limit.

See details [1.4 JD Cloud Cooperation Edition Deployment](#14-JD Cloud cooperation version deployment is optional). 

### Q14: JD Cloud Edition Analysis Task Report 429 Speed Limit Error What should I do?

**A: ** JD.com Cloud version has built-in speed limit response mechanism, which usually does not require intervention. If errors still occur frequently:

1. **Increase task interval**: in `.env` Medium settings `JDYUN_STOCK_INTERVAL_SECONDS=30` (Default 10 seconds).
2. **avoid peak hours**: Schedule scheduled analysis during off-peak hours (such as early morning).
3. **Reduce the depth of analysis**: Use lower analysis depth to reduce the number of LLM calls.
4. **Check the number of concurrency**: ensure `JDYUN_BATCH_MAX_CONCURRENT=1` and `JDYUN_WORKER_MAX_CONCURRENT=1`. 
5. **View retry log**: The system will automatically retry up to 8 times with exponential backoff. Check the log to confirm whether the retry is effective.

---

## Chapter 11 Best Practices

This chapter is based on the actual usage scenario of a typical individual investor and connects the functional modules of the system to help you use the system efficiently.

**Typical scenario**: You are an individual investor looking to improve research efficiency through AI-assisted analysis. Here's the complete path from scratch to daily use.

### 11.1 From installation to first analysis

#### Step One: Installation and Basic Configuration

1. **Install system**: Windows Users run the installation package and follow the wizard to complete the installation; advanced users use Docker deployment.
2. **Log in to the system**: Use default account `admin / admin123` Log in, after logging in for the first time"personal settings → Security settings"Change password.
3. **Follow the user guide**: Click on the left"User Guide", Follow the instructions to complete the configuration:
   - Configure the LLM key and data source key, and fill in the Token configuration
   - Synchronize basic stock data
   - Search and add stocks to watchlist
   - Complete your first study
4. **Key configuration recommendations**: 
   - LLM Key: DeepSeek is recommended (high cost performance), arrive after configuration"personal settings → Analyze preferences"Set default analysis depth and analysts.
   - Data source key: Tushare is recommended, points are recommended 2000+ to unlock the full interface.
   - Change default password: to"personal settings → Security settings"Modify.

#### Step Two: First Analysis and Verification

1. enter"single stock research", Enter a familiar stock symbol (e.g. `000001` Ping An Bank).
2. Choose"3 Level - Standard Analysis"Depth (recommended for beginners, 4-8 minutes).
3. Selected by default"market analyst"and"fundamental analyst", Can be added as needed"news analyst". 
4. Click"Start smart analysis", Wait for the analysis to complete.
5. Check the report to confirm whether each analyst's output is in line with expectations.

**Pitfalls to avoid**: 
- Do not start analysis before basic data synchronization is completed, as this will result in incomplete data.
- Do not use Level 5 Full Analysis for your first analysis, first verify correct configuration with Level 3 Standard Analysis.

### 11.2 Daily research workflow

#### Create a watchlist

1. **Add a stock watchlist**: in"Stock Watchlist"Add stocks you are following and manage them by sector or strategy grouping.
2. **Group management**: Multiple groups can be created (e.g."Long term position", "Short term observation", "New bid") , Colors and icons can be set for each group to make them easier to distinguish.
3. **Quick analysis**: You can directly select stocks in the watch list to initiate single-stock research without having to repeatedly enter codes.

#### Timing analysis configuration

For stocks that need to be tracked regularly, use the scheduled analysis function to automate:

1. **Create analysis grouping**: Arrive"personal settings → Timed analysis grouping"Create groups (such as"daily morning report group") , Add stocks that require regular analysis.
2. **Create a scheduled configuration**: Arrive"personal settings → Timing analysis configuration"Create configuration:
   - Select a default analysis grouping and analysis depth (Level 3 standard analysis recommended).
   - Set execution time period (recommended 16:30 After the market opens, make sure the data for the day is synchronized).
   - Enable email notification to automatically receive a summary of the report after execution is completed.
3. **View execution history**: Click in the configuration list"history"View results and reports for each execution.

#### Batch analysis

Use batch analysis when you need to analyze multiple stocks at one time:

1. enter"Batch analysis", Add multiple stock symbols.
2. It is recommended to use level 2 basic analysis depth to balance time-consuming and token consumption.
3. After the analysis is completed, you can"research report"Compare and view.

### 11.3 cost control practices

#### Token Consumption management

1. **View Token Statistics**: Arrive"System management → usage statistics"Check the Token consumption trend of each function, including single stock research, Agent workshop, Skill generation, AI dialogue assistant, position analysis, etc. NOTE: Estimated costs are for reference only, actual charges are subject to LLM supplier bill.
2. **Select analysts on demand**: Only the necessary analysts are checked for each analysis, and each analyst consumes Token independently.
3. **Make good use of caching**: Repeated analysis of the same stock will hit the cache, and Tokens will not be consumed repeatedly within 24 hours. Available"System configuration → Cache management"View cache status.
4. **Deep selection strategy**: 
   - Daily rapid screening: Level 1 rapid analysis (2-5 minutes, low token consumption)
   - Routine studies: Level 3 standard analysis (4-8 minutes, recommended)
   - Important decision-making: Level 4 in-depth analysis (6-11 minutes, multiple rounds of debate)
   - Batch Analysis: Level 2 Basic Analysis (3-6 minutes, balanced cost)

#### About estimated costs

usage statistics"total cost"It is estimated based on the Token unit price configured in the system and is for reference only. Each LLM provider has different billing rules (such as subscription system, coding plan, monthly package, etc.), and there may be a large deviation between the estimated cost and the actual bill. It is recommended to pay attention to the relative trend of Token consumption rather than the absolute amount.

#### Cache management

1. Arrive"System configuration → Cache management"Check cache usage regularly.
2. You can clear expired caches to free up space, or clear all caches to force reanalysis.

### 11.4 In-depth use: customized workflow, Agent and Skill

When the default analysts don't meet specific needs, capabilities can be expanded through custom workflows, Agent Workshops, and Skill Centers.

#### Custom workflow

1. **Choose how to create**: 
   - **Create from template** (Recommended): in"Analysis flow"Select a system template (such as v2.0 complete analysis flow) on the page, create a copy and modify it.
   - **AI Smart creation**: Click"AI Smart creation", Let AI automatically plan workflows through natural language conversations.
   - **Blank process**: Choose"Blank process"Templates to build custom processes from scratch.

2. **orchestration process**: 
   - Use parallel nodes to allow multiple analysts to work simultaneously to improve efficiency.
   - Use debate nodes to implement multi-scenario confrontations and gain a more comprehensive analytical perspective.
   - Use conditional branches to dynamically adjust the process based on depth of analysis or market type.
   - Custom Agent needs to be"Agent workshop"Create and publish it in the editor before it can be used in the editor.

3. **Verify and publish**: 
   - Using the editor"Verify"Functionality checks workflow structural integrity.
   - Validate output quality by piloting it on 2-3 stocks before publishing.
   - Use"Set as default"Have subsequent analysis tasks automatically use this workflow.

#### Agent Workshop: Create a Custom Analyst

Agent The workshop creates custom Agents through a conversational process and does not support cloning system Agents.

1. **Enter Agent Workshop**: Arrive"Analysis flow → Agent workshop", Click"New Agent". 
2. **Describe requirements**: Use natural language to describe the Agent you want (e.g."I need an analyst who specializes in analyzing the prosperity of the liquor industry, focusing on pricing, inventory, and sales data.") . Available"Quick fill example"Reference format.
3. **Discuss requirements**: The system will talk to you to confirm the requirements details, and can add analysis dimensions, output format, etc.
4. **Confirm specifications**: After the discussion is completed, the system generates the Agent specification. Click after confirming that it is correct."Generate testable version". 
5. **Test verification**: Verify that the Agent output is as expected on the test page.
6. **iterative optimization**: If you are not satisfied, you can provide comments and continue the discussion, and the system will iteratively generate a new version (each iteration generates an independent version, which does not affect the bound Agent).
7. **Release for use**: After the test passes, it is published and the Agent can be referenced in workflow orchestration.

#### Skill Center: Creating Custom Tools

When the Agent needs to call tools not provided by the system, it is generated through the Skill Center:

1. **Enter Skill Center**: Arrive"Analysis flow → Skill Center". 
2. **Describe requirements**: Describe the required tool functionality (e.g."Get real-time transaction data of Hong Kong stocks") . 
3. **Generation and verification**: The system generates Skill code, which is available after static checking, sandbox execution, quality assessment, and edge testing.
4. **iterative optimization**: If you are not satisfied, it can be iterated. Each iteration generates an independent version (such as original_v2, original_v3), which does not affect the bound Agent.
5. **Manual review**: AI The generated code must be manually reviewed and used after confirming that there are no security risks.

#### Workflow orchestration best practices

1. Make good use of parallel nodes: Analysts usually do not depend on each other, and parallel execution can significantly shorten the analysis time.
2. Matching of debate rounds and depth: Use 1 round of debate for daily analysis, and 2-3 rounds for important decision-making.
3. Conditional branch use case: can be based on `analysis_depth` or `market_type` Conditions allow the same workflow to adapt to different scenarios.
4. Workflows and nodes use clear Chinese naming for easy maintenance.
5. Prompt word template supports binding `workflow_id`, Exclusive prompt words can be customized for different workflows (for details, see"System management → prompt word template") . 

### 11.5 Data management practices

#### Data synchronization

1. **First sync**: Arrive"System management → Synchronization of multiple data sources"To perform initialization, it is recommended to perform it during off-peak periods (such as at night).
2. **Daily synchronization**: The system automatically synchronizes after the market opens every day without manual intervention.
3. **Monitor sync status**: Check the sync page regularly, pay attention to failure records and try again.

#### Data import

Arrive"System management → Data import management"Can be imported in batches:
- **stock data**: Import your own basic stock data or historical quotes.
- **social media news**: Import social media public opinion data to enrich the information sources of news analysts and social media analysts.

#### Data backup

1. **Docker deploy**: Regularly back up MongoDB data volumes (`docker-compose -p ta-v3 exec mongodb mongodump`) . 
2. **Windows deploy**: Regular backup `data/` MongoDB data files in the directory.
3. **Configuration export**: System configuration can be exported (keys are automatically desensitized) to facilitate disaster recovery.

### 11.6 safety practices

#### Account security

1. **Change default password**: Immediately after logging in for the first time"personal settings → Security settings"Change the default password.
2. **Strong password**: Use a password of at least 12 characters, including uppercase and lowercase letters, numbers, and special characters.
3. **Regular replacement**: It is recommended to change your password every 90 days.

#### API Key security

1. **least privilege**: The data source API only provides necessary interface permissions.
2. **Key rotation**: It is recommended to rotate API keys every 6 months.
3. **Monitoring anomalies**: Follow"usage statistics"A sudden increase in Token consumption may be due to key leakage.
4. **Don't share keys**: Do not share configuration files (including plaintext keys) with others.
5. **Docker deploy**: `docker/.env` Use placeholders in the key and manually configure the real key through the system settings page after startup.

#### Skill code security

1. **Manual review**: AI The generated Skill code must be manually reviewed.
2. **Sandbox verification**: The generated Skill must be run through the sandbox for verification before use.
3. **Tool whitelist**: Limit the tools that a Skill can call through tool whitelisting.

### 11.7 Version upgrade practice

#### Before upgrading

1. **Back up data**: The MongoDB database must be backed up before upgrading.
2. **View release notes**: Learn about new version changes and breaking changes.
4. **Choose the moment**: Choose to upgrade during non-trading hours to avoid affecting use.

#### After upgrade

1. **Functional verification**: Perform a complete analysis to verify core functionality.
2. **Configuration check**: Check whether configuration items are missing or need to be adjusted.
3. **Monitor operation**: Pay close attention to the system operating status within 24 hours after the upgrade.
4. **Preserve rollback capabilities**: Keep the old version image/installation package before upgrading to facilitate rollback.

### 11.8 Suggestions for using JD Cloud Cooperation Edition

#### Deployment recommendations

1. **Environment variables take precedence**: All configurations passed `.env` File management, restart the service after modification to take effect.
2. **Credential security**: `.env` Files contain sensitive information, do not submit to version control or share with others.
3. **first start**: JD Cloud Edition will automatically initialize the database when it is started for the first time, please wait patiently for 1-2 minutes.

#### Analysis task optimization

1. **avoid peak hours**: JD Cloud LLM has speed limits, and it is recommended to schedule batch analysis and scheduled analysis during off-peak hours (such as 1-6 am).
2. **Set task intervals appropriately**: The default interval of 10 seconds is suitable for most scenarios. If the speed limit is frequent, it can be adjusted to 20-30 seconds.
3. **Perform batch analysis in batches**: No more than 10 stocks can be analyzed in a single batch to avoid occupying LLM resources for a long time.
4. **Prefer standard depth**: 3 Level-standard analysis provides the best balance between effectiveness and time consumption, and deep and comprehensive analysis significantly increases the number of LLM calls.

#### Regular analysis suggestions

1. **Off-peak execution**: Arrange scheduled analysis of different groups in different time periods to avoid triggering multiple analysis tasks at the same time.
2. **After-hours analysis**: It is recommended to 16:30 Then perform scheduled analysis to ensure that the data of the day is synchronized.
3. **Monitor execution status**: Check regularly"mission center"Timing analysis of execution records in the system enables timely detection of failures caused by speed limiting.

---

## Chapter 12 About (/about)

### Function description

The About page displays the system introduction, core functions, version information, technical architecture and contact information to help users quickly understand the system positioning and technology stack. This page can be accessed without logging in.

### Page content

#### 1. Hero District (system introduction)

- **Title**: TradingAgents-CN v3.0
- **subtitle**: AI Assisted stock analysis technology learning platform
- **Description**: A learning and verification platform focusing on AI-assisted analysis technology, helping the system learn stock analysis methods through optimized workflow engines and full-process analysis assistance.
- **Location badge**: Used to learn AI stock analysis technology / no trading guidance / practical learning methodology
- **Original project acknowledgments**: Developed based on TradingAgents project
- **Statistics cards**: Number of agents, number of data sources, monitoring duration, etc.
- **Quick entry**: "Start analysis" (Jump to single stock research),"View courses" (Jump to Learning Center)

#### 2. Learning center guidance banner

- Presenting an introduction to the systematic learning course
- "View courses"Button to jump to learning center

#### 3. Core functions

| Function | Description |
|------|------|
| Optimize analysis engine | v3.0 Workflow engine, visual process definition, Agent workshop, Skill center, MCP server |
| Full process analysis assistance | data collection→Indicator calculation→agent analysis→Report generation supports multiple analysis scenarios |
| Improve learning ability | AI Assisted learning of professional analysis methodology, transparent process, and skill improvement |
| Configurable architecture | Workflow, agents, tools, and prompt words can all be dynamically configured |

#### 4. Version information

- Version number: v3.0 (dynamically obtained from system API)
- Version status: dynamic judgment (beta version display"beta version"logo)
- Build time, build type
- Git commit hash
- API Version:v3.0
- Technical version: Vue 3.4.0, Element Plus 2.4.4, FastAPI 0.104.0,Python 3.11.9

#### 5. Technical architecture

| Category | technology stack |
|------|--------|
| front end | Vue 3, TypeScript, Element Plus, Pinia, Vite |
| backend | FastAPI, Python 3.11.9, Redis, MongoDB, Asynchronous processing |
| v3.0 core engine | Workflow engine, Agent workshop, Skill center, MCP server, capability index panel |

#### 6. Project source

- Based on TradingAgents (developed by Tauric Research team) open source project
- v3.0 Core improvements: Workflow engine, Agent workshop, Skill center, MCP server

#### 7. Contact information

| channel | information | Purpose |
|------|------|------|
| Email | hsliup@163.com | Technical support and business cooperation |
| QQ Communication group | 1079484482 | User communication and problem discussion |
| WeChat public account | TradingAgents-CN | Latest news and tutorials |

### Operation steps

1. Click on the left navigation bar"About"menu.
2. Browse each section for system information.
3. For technical support, check out"Contact information"Section to get contact information.

---

## Common mistakes for newbies and how to avoid them

| Common mistakes | Reason | Solution |
|---------|------|---------|
| **Analysis tasks are always queued and not executed.** | Worker Not started | Check whether the backend Worker process is running, refer to 8.4 Scheduled Tasks |
| **Report shows"Not enough data"** | Stock data not synced | First pull the basic data in 8.3 multi-data source synchronization |
| **LLM Call error 401** | API Key Invalid or in arrears | Check the API Key in 8.1 configuration management to confirm that the account balance is sufficient |
| **LLM Call error 429** | API rate limit exceeded | Reduce the number of concurrencies or upgrade the API package (JD Cloud version reference Q14) |
| **The analysis results are all"unknown"** | System variables are not injected | Check the data source configuration and confirm that the basic stock information has been synchronized |
| **Scheduled analysis is not performed** | Time period configuration error | Check whether the time period configured in 6.5.2 scheduled analysis is correct |
| **Export PDF Chinese garbled characters** | The system is missing Chinese fonts | Docker Deployment is built-in; Windows deployment requires Chinese fonts to be installed |
| **Batch analysis is slow** | The number of concurrency is too low or the network is slow | Increase the number of concurrency appropriately (JD Cloud version keeps the default 1) |
| **Simulated trading positions are not updated** | Market data is not synchronized | Click on the watch list or stock details page"sync"button |
| **Agent The Agent created by the workshop does not take effect** | Not published or added to process | Click on the Agent details page"publish", Then add in process management |

---

## Appendix

### A. Workflow Editor Canvas Actions

> v3.0 The workflow editor canvas supports the following mice + Keyboard operation (from [WorkflowCanvas.vue](file:///c:/TradingAgentsCN/frontend/src/views/Workflow/components/WorkflowCanvas.vue) of `canvas-help` Tips):

| Operation | Effect |
|------|------|
| **roller** | Zoom canvas |
| **space + Drag** | Pan the canvas |
| **Click on node** | Select node |
| **Drag node** | Adjust position |
| **Connections between nodes** | Drag the connection point of the node edge |

> 💡 **Tips**: v3.0 Current version**Not implemented**Global shortcut keys (such as `Ctrl+/` Open the assistant,`Ctrl+K` global search,`Ctrl+Z` cancellation, etc.). These features are planned to be provided in subsequent minor releases.

### B. Related documents

- [Quick start guide](getting-started/quick-start.md)
- [Installation and Deployment Guide](getting-started/installation.md)
- [Docker Deployment Guide](getting-started/docker-deployment-guide.md)
- [API Key management](configuration/api-key-management.md)
- [LLM Configuration Guide](configuration/llm-config.md)
- [Detailed explanation of simulated trading](features/paper-trading.md)
- [Timing Analysis Guide](features/scheduled-analysis-guide.md)
- [v2.1 vs v3.0 Contrast](../01-product/comparison/v2.1-vs-v3.0.md)
- [v3.0 Release Notes](../01-product/release-notes/v3.0.0-beta.1.md)

### C. Technical support

- **QQ group**: See the instructions in the installation package
- **GitHub Issues**：https://github.com/hsliuping/TradingAgents-CN/issues
- **Email**: See the official website for contact information

---

> **Disclaimer**: TradingAgents-CN Pro All analysis results, research observations, learning tools and simulated trading functions provided are for learning and research purposes only and do not constitute any investment advice. Investment is risky and decisions need to be made with caution. The system generates analysis based on AI models, which may contain biases or errors. Please make independent judgments based on information from multiple parties.
