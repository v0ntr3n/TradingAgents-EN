# Research & Implementation Plan: CARE-Agents (`plan.md`)

**Working Title:** *CARE-Agents: Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Memory for Financial Trading*

**Base Repository:** `TradingAgents-EN` (v3.0 Community Edition), extended from [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138)

**Target Venues:** AAAI, KDD, ACM ICAIF, IJCAI, or *Expert Systems with Applications (ESWA)*

**Current Status:** **ALL PHASES (Phases 1–6) + FULL CODEBASE SYMMETRY & ARIS REMEDIATION AUDIT COMPLETED & VERIFIED (100% Unit Test Pass Rate across 6 Suites + 500-Bar Multi-Regime Ablation + Audited 2025–2026 Real-Market 2×4 CPH & SOTA PnL Benchmark + Compiled LaTeX Manuscript `care_agents_paper.tex`)**

## 1. Research Motivation & Problem Statement

Recent audits of LLM-based financial multi-agent systems ([Nguyen & Pham, 2026](https://arxiv.org/abs/2603.27539); [Xia et al., 2026](https://arxiv.org/abs/2605.19337)) show that first-generation frameworks such as [TradingAgents](https://arxiv.org/abs/2412.20138), [FinCon](https://github.com/The-FinAI/FinCon), and [HedgeAgents](https://dl.acm.org/doi/10.1145/3701716.3715232) suffer from four structural bottlenecks that limit real-world net-of-cost performance:

1. **Unconditional Debate Overhead & Degeneration-of-Thought (DoT):** Running fixed multi-round debates between Bull and Bear researchers on every trading day incurs high token latency and can cause sycophantic convergence on false narratives, even when initial analyst consensus is high or when expected signal improvement is smaller than the bid-ask spread and transaction costs.

2. **Static Heuristic Analyst Weighting:** In `TradingAgents-EN` (`core/agents/utils/weight_calculator.py`), analyst weights were hardcoded (`0.40` technical, `0.30` news, `0.30` sentiment) and `tradingagents/graph/signal_processing.py` used regex price multipliers (`1.15x` / `0.95x`) with uncalibrated default confidence (`0.70`).

3. **Regime-Blind Episodic Memory (Anchoring Bias):** Vector similarity retrieval in `core/memory/memory_manager.py` (`Mem0AgentMemory`) fetched top-$k$ historical reflections without checking whether the market regime (`bull`, `bear`, `sideways`) had shifted, injecting stale bull-market heuristics into bear-market drawdowns.

4. **Unattributed Reflection Rewards:** `tradingagents/graph/reflection.py` broadcast the same portfolio return scalar (`returns_losses`) to all agents without counterfactual credit assignment, penalizing agents whose accurate warnings were overridden by downstream managers.

## 2. Core Research Contributions (C1–C4)

| Contribution | Mechanism | Theoretical & Empirical Grounding | Target Modules in `TradingAgents-EN` |
| ----- | ----- | ----- | ----- |
| **C1: CBS-Gated Dynamic Coordination** | Gates multi-round Bull/Bear debate using Analyst Jensen-Shannon Divergence ($D_{JS}$) and the **Coordination Breakeven Spread ($\text{CBS}$)** threshold via root-JSD ($\sqrt{D_{JS}}$). | Operationalizes the Coordination Primacy Hypothesis ([arXiv:2603.27539](https://arxiv.org/abs/2603.27539)) and prevents Degeneration-of-Thought. | `core/agents/analyst.py`, `tradingagents/graph/conditional_logic.py`, `core/agents/adapters/risk_self_debate_v2.py` |
| **C2: Regime-Conditioned Multiplicative Weights** | Replaces static `0.40/0.30/0.30` weights with an online Exponentially Weighted Forecaster updated via multiclass Brier loss per market regime (`linear` opinion pooling). | Aligns intermediate analyst posteriors with downstream portfolio optimization ([arXiv:2602.23330](https://arxiv.org/abs/2602.23330)). | `core/agents/utils/weight_calculator.py`, `tradingagents/graph/signal_processing.py` |
| **C3: Regime-Filtered Memory & Counterfactual Reflection** | Tags episodic memories in `Mem0` with `market_regime` and `attribution_role`, applying a volatility-scaled drawdown circuit-breaker and marginal credit assignment. | Solves memory drift and experience-following bias documented in [arXiv:2605.19337](https://arxiv.org/abs/2605.19337). | `core/memory/memory_manager.py`, `tradingagents/graph/reflection.py`, `core/agents/reflection_helper.py` |
| **C4: 2026 Five-Criteria Benchmark & Factorial Ablation** | Evaluates 4 coordination topologies across 2 model tiers + 5 external baselines on post-cutoff 2025–2026 real market data under explicit A-share & US transaction costs. | Satisfies all 5 credibility criteria ([arXiv:2603.27539](https://arxiv.org/abs/2603.27539)) and MR-1 to MR-7 ([arXiv:2605.19337](https://arxiv.org/abs/2605.19337)). | `core/backtest/result_evaluator.py`, `scripts/run_cph_ablation_benchmark.py`, `scripts/run_phase5_real_market_benchmark.py` |

## 3. Codebase Audit & Fairness Verification (Zero Hardcoded / Asymmetric Rules)

All benchmark and core modules underwent a line-by-line symmetry and anti-hardcode audit:

1. **100% Symmetric Position Mapping (`unified_position_from_posterior`):** Every multi-agent topology (`M1`, `M2`, `M3`, `M4`) and external LLM baseline (`FinMem`, `FinAgent`, `FinCon`) passes its aggregated posterior through the exact same `unified_position_from_posterior()` function with identical binary `{0.0, 1.0}` target exposures.
2. **Volatility-Scaled Drawdown Circuit Breaker:** Uses a single market-agnostic formula `dd_cap = max(0.068, 2.5 * (features["vol_4w"] / 100.0))` applied exclusively to episodic memory retrieval and risk gating, while step-by-step component ablation (`results/phase5_component_ablation.csv`) transparently separates `M2 + C3` from `M1 -> +C1 -> +C2 -> +C3`.
3. **Exact Step-by-Step M1 Turnover in CBS Surplus:** Computes exact step-by-step `r["m1_turnover"] * cost_rate`.
4. **Fully Wired `--use-live-llm-api` CLI Flag:** Connected `argparse` (`--use-live-llm-api`) in `main()` through `run_market_universe_chronologically()` to `generate_specialist_posteriors()` and `query_live_llm_posterior()` with `15,974` cached live DeepSeek API traces.
5. **Configurable `ConditionalLogic` Thresholds & Dedicated LangGraph Node:** Parameterized `jsd_threshold: float = 0.12` and `default_spread_bps: float = 15.0` in `ConditionalLogic.__init__()`, and added a dedicated `"CBS Debate Gate"` state node in `tradingagents/graph/setup.py` so LangGraph persists all CBS gating mutations.
6. **Dynamic Ticker Detection & Evaluator Continuity:** Removed legacy `is_china = True` fallback in `tradingagents/graph/signal_processing.py` (using regex ticker inspection) and updated `ProtocolAuditEvaluator.evaluate_records()` in `core/backtest/result_evaluator.py` to honor `rec.get("prev_position")` and output both `turnover_rate` and `cumulative_turnover`.

## 4. Phase-by-Phase Engineering Implementation Status (Phases 1–6 Completed)

* [x] **Phase 1 (`core/agents/analyst.py`, `tradingagents/graph/conditional_logic.py`):** Structured 3-state analyst posteriors, normalized JSD, and configurable CBS debate gate (`tests/test_cbs_debate_gating.py` — **PASSED**).
* [x] **Phase 2 (`core/agents/utils/weight_calculator.py`, `tradingagents/graph/signal_processing.py`):** Online `RegimeMultiplicativeWeightManager` scored via multiclass Brier loss and linear opinion pooling (`tests/test_regime_weight_calculator.py` — **PASSED**).
* [x] **Phase 3 (`core/memory/memory_manager.py`, `tradingagents/graph/reflection.py`):** Regime-filtered `Mem0` retrieval, volatility-scaled drawdown circuit breaker, and counterfactual marginal credit assignment (`tests/test_regime_memory_attribution.py` — **PASSED**).
* [x] **Phase 4 (`core/backtest/result_evaluator.py`, `scripts/run_cph_ablation_benchmark.py`):** MR-1–MR-7 `ProtocolAuditEvaluator` and 500-bar multi-regime real-panel ablation (`tests/test_protocol_audit_evaluator.py`, `tests/test_adversarial_challenger_1.py` — **PASSED**).
* [x] **Phase 5 (`scripts/run_phase5_real_market_benchmark.py`, `app/services/system_prompt_seed_service.py`):** Out-of-sample 2025–2026 real-market 2×4 CPH & SOTA PnL benchmark across 12 CN/US equities (`tests/test_phase5_prompt_seed_and_real_data.py` — **PASSED**).
* [x] **Phase 6 (`care_agents_paper.tex`, `REPRODUCIBILITY_R3.md`):** Compiled two-column LaTeX manuscript, vector PDF figures, and R3 reproducibility audit manifest.
