# TradingAgents-EN (Community Edition)

**English**: TradingAgents-CN Community Edition is a hybrid-licensed (Apache-2.0 core engine + proprietary source-available application layer) multi-agent stock research assistant for the Chinese A-share market. It orchestrates LLM-based analyst agents for debate-style research, natural-language stock screening, paper trading and study courses. For learning and research only — **not investment advice**.

[![License](https://img.shields.io/badge/License-Hybrid_(Apache--2.0_+_Proprietary)-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-brightgreen.svg)](https://vuejs.org/)

A multi-agent collaborative stock research assistant system for the Chinese A-share market. Multiple AI agents playing distinct roles (macro/sector/market/fundamental/news analysts, bullish/bearish researchers, etc.) collaborate throughout the research workflow to help you systematically learn multi-agent frameworks and the application of large language models in equity research.

> This project is a research assistance tool. All AI-generated content is for learning and reference only and **does not constitute investment advice**.

## Core Features

- **Single-Stock Research**: Multi-agent debate-style analysis (5 depth levels) with multi-scenario perspective presentation
- **General Research**: Ask questions in natural language to research any market topic
- **Stock Screening**: Natural language + conditional filtering to discover targets across 6,000+ stocks
- **Stock Selection Assistant**: Match candidate stock pools based on research requirement descriptions
- **Smart Assistant**: Web search + tool calling + fact memory
- **AI Memory**: Project-level memory and fact retention
- **Skill Center**: Create and manage custom data acquisition skills
- **Learning Center**: Free systematic courses (5 lessons in the Discovery Phase) + 8 study guides
- **Paper Trading**: Simulated trading and post-trade review

## Version Evolution

| Version | Positioning | Core Changes |
|------|------|---------|
| v1.0 | Multi-Agent Analysis Tool | Single-stock research + batch analysis; multiple analyst agents collaborating to complete the A-share research workflow |
| v2.0 | Integrating Analysis into a Research Loop | Unified analysis engine + visual workflow; added portfolio analysis, trade review, and periodic review |
| v2.1 | Research Assistance Compliance | Report phrasing, prompt templates, and UI copy fully aligned with the "research assistant" positioning; new model integrations and stability improvements |
| v3.0 | From Analysis Tool to AI Assistant | Unified AI assistant entry point, natural-language stock screening, autonomous Agent planning and analysis, Skill capability expansion; architecture upgraded to FastAPI + Vue 3 + MongoDB/Redis |

## Community Edition vs. Pro Edition

| Capability | Community Edition | Pro Edition |
|------|:------:|:------:|
| Single-Stock Research / General Research / Stock Screening | ✅ | ✅ |
| Learning Center (Free Courses) / Paper Trading / Skill Center | ✅ | ✅ |
| Agent Workshop (Create, publish, and manage custom Agents) | — | ✅ |
| Trading System (Strategy creation / optimization / template debugging) | — | ✅ |
| Scheduled Analysis / Batch Analysis | — | ✅ |
| Professional Report Export (Word / PDF multi-format) | — | ✅ |
| Advanced Courses (8 Advanced Phases) | — | ✅ |
| License | Hybrid License (Open-source core engine + Proprietary application layer) | Commercial License |

The Pro Edition is designed for users who require advanced research workflows. Visit the project homepage or contact the author for access.

## Quick Start

### Prerequisites

- Python 3.11
- Node.js 18+
- MongoDB 7.0+ (8.0 recommended) and Redis 6+ (7 recommended) — must be installed separately; see "Installing MongoDB / Redis" below

### Installing MongoDB / Redis

This project does not bundle databases. Please install and start MongoDB and Redis first (see version requirements above). Any installation method works as long as the **credentials and ports match the `.env` file in the next step**.

| OS | MongoDB | Redis |
|------|---------|-------|
| Windows | Official installer https://www.mongodb.com/try/download/community (starts automatically as a service after installation) | Run `redis-server` in WSL, or use a compatible implementation such as Memurai |
| macOS | `brew tap mongodb/brew && brew install mongodb-community && brew services start mongodb-community` | `brew install redis && brew services start redis` |
| Ubuntu / Debian | Refer to https://www.mongodb.com/docs/manual/installation/ | `sudo apt install redis-server && sudo systemctl enable --now redis-server` |

Alternatively, you can run just these two databases using Docker (requires Docker installed locally):

```bash
docker run -d --name ta-mongo -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=<your_password> mongo:8.0
docker run -d --name ta-redis -p 6379:6379 \
  redis:7-alpine redis-server --requirepass <your_password>
```

MongoDB requires authentication enabled (`authSource=admin`) and an administrator account created manually. Put the username/password, host, and port into `.env` in the next step (local defaults are `localhost:27017` / `localhost:6379`).

### Startup Steps

```bash
# 1. Clone the repository
git clone <repository_url>
cd TradingAgents-CN

# 2. Backend environment (Python 3.11)
python -m venv env
env\Scripts\activate            # Windows
source env/bin/activate         # Linux / macOS
pip install -r requirements.txt

# 3. Configuration (MongoDB / Redis / JWT_SECRET are required; see comments in .env.example for details)
copy .env.example .env          # Windows
cp .env.example .env            # Linux / macOS

# 4. Start your installed MongoDB / Redis (ensure credentials match .env)

# 5. Start the backend (defaults to port 8000, matching the frontend's default proxy)
uvicorn app.main:app

# 6. Start the frontend
cd frontend
npm install
npm run dev                     # Defaults to http://localhost:3000
```

### First Login

On its first startup, the backend automatically completes initialization (no need to run any import scripts manually):

1. Imports system-level configurations (model catalog, prompt templates, Agent configurations, workflows, etc.)
2. When the user table is empty, creates the administrator account `admin` using `ADMIN_DEFAULT_PASSWORD` from `.env`

| Account | Password |
|------|------|
| `admin` | `ADMIN_DEFAULT_PASSWORD` in `.env` |

After logging in, please configure your LLM API Keys (OpenAI / DeepSeek / Qwen, etc.) in System Settings first, and configure market data tokens as needed.

## Documentation

- User Manual: [docs/02-user-guide/user-manual-v3.0.md](docs/02-user-guide/user-manual-v3.0.md)
- Study Guides: [docs/02-user-guide/](docs/02-user-guide/) (learning-01 ~ 08)
- Free Courses: [docs/07-courses/v3.0/phase-01-discover/](docs/07-courses/v3.0/phase-01-discover/)

## Data Sources

Market and financial data are sourced from public APIs including [Tushare](https://tushare.pro/) / [AKShare](https://github.com/akfamily/akshare) / [BaoStock](https://www.baostock.com/). You will need to register and obtain tokens on your own where required.

## Contributing (Recruiting)

We are looking for **like-minded open-source contributors** to build TradingAgents-CN together.

**How to join**: Submit a Pull Request directly. No resumes, no interviews — **PRs are the only evaluation criterion**. We assess fit based on PR quality:

1. **Solve real problems**: Fix actual bugs or fill genuine gaps rather than making changes for the sake of changing
2. **Explain the rationale**: Clearly state "why the change was made", not just "what was changed"
3. **Respond to review feedback**: Actively address review comments and follow up with revisions

Contributors who consistently submit high-quality PRs will be invited to participate in release planning and core module development.

**Currently welcomed areas**:

- Data source adaptation: Integrating and maintaining public market/financial data APIs
- Frontend development: Vue 3 + TypeScript feature development and UX optimization
- Agent orchestration & prompt engineering: Analysis pipeline optimization
- Documentation & courses: User manuals and learning course development

**What you get**: Public attribution and visibility (shout-outs in release notes and official articles), hands-on engineering experience with multi-agent systems, and priority in future project commercialization. Project revenue does not yet cover basic infrastructure costs, so participation is currently voluntary; revenue-sharing principles once costs are covered (community contribution fund / consulting fees / profit-sharing paths) are documented upfront.

**How to contact**: For initial communication, please email hsliup@163.com; for specific technical issues, we recommend opening an Issue or PR for public discussion; after smooth collaboration, you will be invited to join the project WeChat group and knowledge community.

See [CONTRIBUTING.md](CONTRIBUTING.md) for submission workflows, revenue-sharing framework, and Contributor License Agreement (CLA).

## Disclaimer

- This system supports A-share market research only. Outputs are AI-generated research references and do not constitute investment advice
- Does not provide trading instructions such as target prices, stop-loss/take-profit levels, or buy/sell timing
- Investing involves risks; decisions require independent judgment

## License

This project uses a **hybrid license**. See [LICENSE](LICENSE) for details:

- **Apache-2.0 Open-Source Components**: `tradingagents/` (trading agents library), `cli/`, `docs/`, `tests/`, etc. — free to use, modify, and distribute
- **Proprietary Components (Source Available)**: `app/` (backend application), `frontend/` (frontend application), `core/` (core functional layer) — source code is viewable and permitted for personal use, evaluation, and educational purposes; **redistribution and commercial use are prohibited** (contact the author for a commercial license)

Submitting a contribution indicates your agreement to sign the [Contributor License Agreement (CLA)](CONTRIBUTING.md).

## Acknowledgments

- [Tauric Research / TradingAgents](https://github.com/TauricResearch/TradingAgents) — Original multi-agent trading framework project
- All contributors who have participated in building the project via PRs

For full acknowledgments (including licensing details and data source credits), see [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
