# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [3.0.0] - 2026-09-22

v3.0 It is a platform upgrade: multi-agent research engine reconstruction, intelligent assistant and Skill ecosystem, multi-data source synchronization system,
And for the first time, a free and open source community version was released (see below for the functional boundaries with the Pro version).

### Breaking changes (common to Community Edition and Pro)

- **Multi-agent research engine v2**: The analysis process is executed in stages (data collection → analyst → research debate → risk assessment → trading decisions), contractual data model, analysts can combine it on demand
- **Smart Assistant**: from"Analysis trigger"Upgraded to an investment research collaborative portal to support 20+ Action tools, multi-topic sessions, and streaming responses
- **Skill ecology**: Skill Center (browse/search/install), Skill generation (create from scratch or inherit Agent workshop output), capability index and quality assessment
- **Synchronization of multiple data sources**: Tushare / AKShare / BaoStock Unified management, basic data/historical market conditions/financial data are synchronized step by step, and data verification is purely local and read-only.
- **Simulated trading and operation review**: Virtual fund practice trading, AI review and analysis of operation records, and execution of consistency checks
- **Portfolio analysis**: Risk-return analysis of position portfolios (VaR, stress testing, Brinson attribution, etc. 20+ tools)
- **unified mission center**: Analyze task unified scheduling, progress tracking, and historical records
- **Learning Center**: 24 AI Stock Analysis System Course + Advanced Trading Course
- **Notification center**: In-site notifications, WebSocket real-time push, SSE event streaming
- **Analyze configuration files**: Save commonly used analysis configurations (depth/team/parameters) and reuse them with one click
- **Car Sales Data Tool**: by brand + Query the sales volume of Chedi models by month (multi-agent tool chain)
- **Basic tool chain expansion**: Valuation (12 categories such as DCF/DDM/EVA), financial quality (Altman-Z/Beneish-M/Piotroski-F), macro and industry, technical aspects (form/divergence/support pressure), etc. 200+ research tools

### Community Edition (free and open source) includes

All common features above, plus:

- Complete Single Stock Research / Research Reports / Stock Screeners / Watch Lists / Stock Details
- Simulated trading, operation review, portfolio analysis, learning center, intelligent assistant, Skill center and generation
- Multi-data source synchronization, data verification, database management, system configuration, version update check
- Advanced functions (batch analysis, report export, email notification, prompt word template, etc.) passed"Senior student"Points system unlocked

### Pro Edition exclusive

- **Agent workshop**: Visually build exclusive Agent (AgentSpec contract, gap filling GapJob, assertion and execution trace)
- **trading system**: Trading plan management and execution evaluation
- **backtest**: Strategy historical backtesting
- **prompt word project**: Prompt word template/design/preview/injection strategy management
- **Multi-channel notifications**: Email notification, channel push configuration, watch list grouping
- **Report export**, **Historical data management**, **Social media sentiment analysis**, **MCP Integrate**
- **License Authorization system**: Online/offline activation, function level management

### Fixes and improvements (since 3.0.0-beta series)

- Data inspection is changed to purely local read-only, external data is no longer pulled on-site, and interface blocking during inspection is fixed.
- Historical data query full table scan optimization ($or Dual field detection, 3.56 million documents 3s → 0.03s) 
- Notification center click jump 404 repair (stock notification link batch refresh)
- User Guide (/guide)License Activation Steps Community Edition is automatically hidden
- User Manual Strips License Activation Chapter (community:remove Marking mechanism)
- Community version GapJob broken link brush WARNING repair (when the module is missing, it will be silently disabled after a one-time prompt)
- Dashboard Icon markRaw fix (eliminates console component responsive warnings)
- start_dev.ps1 Versioned startup injection MongoDB authentication (fix requires authentication)
- Development environment version isolation: v3.0 / v2.1 / v2.0 / JD Cloud version independent port and data volume
- Community version release pipeline: publish_community full snapshot + Leak scan + mark stripping + Integrity self-check
