# Progress Report - Explorer Survey 2

Last visited: 2026-11-02T05:21:00Z
Status: In progress

## Tasks
- [ ] 1. Configuration sprawl (R2)
  - [ ] Locate and list all 26 configuration modules across `app/`, `core/`, `tradingagents/`, `cli/`.
  - [ ] Analyze how they can be consolidated into a single `pydantic-settings` hierarchy in `core/config/settings.py` with backward-compatible re-export shims.
- [ ] 2. Lifespan, routers, services, workers (R2)
  - [ ] Analyze `app/main.py:lifespan` (820 lines) and map modular lifecycle hooks into `app/core/lifecycle/`.
  - [ ] Analyze monolithic config and analysis routers/services and how to split them into modular subpackages.
  - [ ] Analyze stock screening and analysis services under `app/services/screening/` and `app/services/analysis/`, and how execution is routed through `app/services/unified_analysis_engine.py`.
  - [ ] Analyze market data sync workers and how `BaseMarketSyncService` in `app/worker/base_market_sync.py` should be structured.
- [ ] 3. Core Agent Runtime & Tool Decomposition (R3)
  - [ ] Identify monolithic core agent builder and runtime modules (`nanobot_agent_builder_tools.py`, workflow builders, iteration controllers, agent tool execution loops) that exceed 600 lines or need decomposition.
  - [ ] Map modular subpackages under 600 lines each while preserving public interfaces via `__init__.py` re-exports.
- [ ] 4. Exception Hardening (R3)
  - [ ] Locate all 56 bare `except:` blocks across `app/`, `core/`, `tradingagents/`, and `cli/` (exact file and line numbers).
  - [ ] Design the typed domain exception hierarchy in `core/exceptions.py`.
- [ ] 5. Agent Prompt & Tool Schema Disambiguation (R4)
  - [ ] Locate embedded prompt templates in services and memory modules to extract to `prompts/`.
  - [ ] Identify system prompts and tool docstrings in `core/tools/implementations/` requiring ASD-STE100 strict rules.
- [ ] 6. Handoff Report Synthesis & Delivery
