Refactor the entire `TradingAgents-EN` (CARE-Agents) repository (`app/`, `core/`, `tradingagents/`, `cli/`, `frontend/`, and `tests/`) into a clean, modular, strongly typed, and test-verified codebase. Preserve 100% of existing external API contracts, LangGraph state transitions, CARE-Agents benchmark reproducibility (MR-1 through MR-7), and frontend user workflows without adding new features or altering external benchmark logic.

Working directory: /home/bramy/Downloads/TradingAgents-EN
Integrity mode: development

## Operating Rules & Constraints
- Do not change runtime behavior, external API contracts, LangGraph state transitions, CARE-Agents benchmark reproducibility (MR-1 through MR-7), or frontend user workflows.
- Execute only one atomic refactoring slice per commit following the Moving Invariant (`Introduce -> Redirect -> Remove`). Never change logic and file location in the same commit.
- Run baseline characterization tests before and after modifying any target module. If any test fails, revert the edit immediately (`git checkout -- .`) and diagnose the root cause before retrying.
- Keep every refactored Python function under 80 lines and cyclomatic complexity under 10 (`radon cc -min C`).
- Keep every refactored Python module under 600 lines and every Vue component under 400 lines.
- Automated verification runs offline with mock fixtures: live external market APIs and Playwright browser instances are not required. Record pre-existing test failures as a baseline before starting; introduce zero new regressions or broken imports.

## Requirements

### R1. Repository Hygiene, Dead Artifacts & Test Suite Reorganization
Verify canonical manuscript files in `paper/` (`care_agents_paper.tex`, `care_agents_paper.pdf`) and remove obsolete root duplicates, updating documentation references in `PROJECT.md`, `PEER_REVIEW_READINESS_REPORT.md`, and `REPRODUCIBILITY_R3.md`. Separate raw CSV/JSON benchmark outputs in `results/` from generated figures and tables in `reports/`, updating experiment script paths. Reorganize the flat test suite in `tests/` into structured directories (`tests/legacy_debug/` with `legacy_debug` added to `norecursedirs` in `pytest.ini`, `tests/unit/`, and `tests/integration/`) with zero broken imports.

### R2. Configuration Sprawl & Backend Service/Worker Consolidation
Consolidate the 26 disparate configuration modules into a single `pydantic-settings` hierarchy in `core/config/settings.py` with backward-compatible re-export shims. Decompose the 820-line `app/main.py:lifespan` into modular lifecycle hooks in `app/core/lifecycle/` and split monolithic config and analysis routers/services into modular subpackages. Unify redundant stock screening and analysis services under `app/services/screening/` and `app/services/analysis/`, routing analysis execution through `app/services/unified_analysis_engine.py`. Extract `BaseMarketSyncService` in `app/worker/base_market_sync.py` for market data sync workers.

### R3. Core Agent Runtime, Tool Decomposition & Exception Hardening
Decompose monolithic core agent builder and runtime modules—including `nanobot_agent_builder_tools.py`, workflow builders, iteration controllers, and agent tool execution loops—into modular subpackages under 600 lines each while preserving public interfaces via `__init__.py` re-exports. Eliminate all 56 bare `except:` blocks across `app/`, `core/`, `tradingagents/`, and `cli/`. Establish a typed domain exception hierarchy in `core/exceptions.py` and replace broad exception handling at boundaries with typed exceptions and structured contextual logging.

### R4. Agent Prompt & Tool Schema Disambiguation
Extract embedded prompt templates from services and memory modules into versioned external files under `prompts/`. Standardize all system prompts and tool docstrings in `core/tools/implementations/` using ASD-STE100 strict rules (active voice, maximum 20 words per instruction sentence, standardized terminology, zero synonym rotation).

### R5. Frontend Architecture Decomposition & UI Hardening
Decompose monolithic Vue views exceeding 2,000 lines into container views (<300 lines), child components (<400 lines), and composables. Eliminate all 795 TypeScript `any` usages with strict interfaces in `frontend/src/types/`, replace hardcoded hex colors with semantic CSS custom properties meeting WCAG AA contrast (`>=4.5:1`), replace console logging with a production-silent logger, and enforce `font-variant-numeric: tabular-nums` on financial data displays.

## Verification Resources
- Core CARE-Agents benchmark tests: `tests/test_cbs_debate_gating.py`, `tests/test_regime_weight_calculator.py`, `tests/test_regime_memory_attribution.py`, `tests/test_protocol_audit_evaluator.py`, `tests/test_ama_finben_integration.py`, `tests/test_phase5_prompt_seed_and_real_data.py`
- Reorganized unit tests: `tests/unit/`
- Static analysis & complexity tooling: `ruff`, `bandit`, `vulture`, `radon`
- Frontend build & type check: `npm run type-check`, `npm run build`

## Acceptance Criteria

### Code Quality & Architectural Boundaries
- [ ] Obsolete root manuscript files (`care_agents_paper.tex`, `care_agents_paper.pdf`) are removed and path references in documentation are updated to `paper/`.
- [ ] Raw benchmark outputs are written to `results/` and generated figures/tables to `reports/`.
- [ ] Root `tests/` directory is reorganized into structured directories (`tests/legacy_debug/`, `tests/unit/`, `tests/integration/`) with `legacy_debug` configured in `pytest.ini`.
- [ ] Disparate configuration modules are consolidated into `core/config/settings.py` with backward-compatible shims for legacy imports.
- [ ] `app/main.py:lifespan` is decomposed into modular lifecycle hooks in `app/core/lifecycle/`, reducing `app/main.py` under 250 lines.
- [ ] `core/tools/implementations/agent_builder/nanobot_agent_builder_tools.py` is decomposed into a modular package with public interfaces re-exported in `__init__.py`.
- [ ] All 56 bare `except:` blocks across `app/`, `core/`, `tradingagents/`, and `cli/` are eliminated.
- [ ] A typed domain exception hierarchy is created in `core/exceptions.py`.
- [ ] System prompts and tool docstrings in `core/tools/implementations/` comply with ASD-STE100 strict rules (active voice, <=20 words per instruction sentence).
- [ ] Monolithic Vue views (`SingleAnalysis.vue`, `ConfigManagement.vue`, `Screening/index.vue`, `Detail.vue`, `SkillGenerationCreate.vue`, `Assistant/index.vue`) are decomposed into views (<300 lines) and components (<400 lines).
- [ ] Zero TypeScript `any` usages remain in `frontend/src/`.
- [ ] Hardcoded hex color literals in frontend components are replaced with semantic CSS tokens meeting WCAG AA contrast (`>=4.5:1`).
- [ ] Numeric and financial data displays in the frontend enforce `font-variant-numeric: tabular-nums`.
- [ ] Every refactored Python function is under 80 lines with cyclomatic complexity under 10 (`radon cc -min C`).
- [ ] Every refactored Python module is under 600 lines and every Vue component is under 400 lines.

### Automated Verification Gates
- [ ] Pre-refactoring test baseline is recorded before modifying code.
- [ ] `ruff check app/ core/ tradingagents/ cli/` passes cleanly with zero errors on refactored code.
- [ ] `bandit -r app/ core/ tradingagents/ -ll -ii` reports zero high- or medium-severity issues.
- [ ] `radon cc app/ core/ tradingagents/ -s -n C` confirms zero functions with cyclomatic complexity >= C (11+).
- [ ] Core CARE-Agents reproducibility suite passes with zero regressions against baseline: `pytest tests/test_cbs_debate_gating.py tests/test_regime_weight_calculator.py tests/test_regime_memory_attribution.py tests/test_protocol_audit_evaluator.py tests/test_ama_finben_integration.py tests/test_phase5_prompt_seed_and_real_data.py -v`.
- [ ] Unit test suite passes without broken imports or regressions: `pytest tests/unit/ -v`.
- [ ] Frontend type check and build pass cleanly: `cd frontend && npm run type-check && npm run build`.
