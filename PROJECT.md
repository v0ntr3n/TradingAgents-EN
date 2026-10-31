# Project: CARE-Agents Research Extensions for TradingAgents-EN

## Architecture
CARE-Agents integrates four synergistic research contributions into the TradingAgents-EN multi-agent financial trading framework:
1. **CBS-Gated Dynamic Coordination (C1)**: Structured 3-class analyst posteriors $(p_{\text{opt}}, p_{\text{neu}}, p_{\text{cau}})$ are extracted and normalized across all v2 specialist analysts. Inter-analyst Base-2 Jensen-Shannon Divergence ($D_{JS}$) and Coordination Breakeven Spread ($\text{CBS}$) determine whether to trigger multi-round Bull/Bear debate or route to single-pass fast-path synthesis (`RiskSelfDebateV2`), mitigating unneeded debate overhead and token latency.
2. **Online Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing (C2)**: Maintains independent analyst reliability weight vectors across market regimes (`bull`, `bear`, `sideways`), updated online via the Exponentially Weighted Forecaster (MWU) with multiclass Brier loss. Replaces heuristic price multipliers with Bayesian log-odds opinion pooling for calibrated target prices, ensemble confidence, and risk score.
3. **Regime-Filtered Episodic Memory & Counterfactual Credit Assignment (C3)**: Tags memories with `market_regime`, `volatility_quintile`, and `attribution_role`. Employs a regime circuit-breaker and drawdown circuit-breaker to prevent stale memory contamination during regime transitions. Uses 4-quadrant counterfactual reflection attribution to reward or penalize individual agents based on their marginal contribution rather than uniform portfolio returns.
4. **2026 Protocol Audit Evaluator & Factorial Ablation Benchmark (C4)**: Implements `ProtocolAuditEvaluator` auditing realistic China A-share asymmetric friction schedules (stamp duty, commission, slippage), annualized net metrics (Sharpe, Sortino, Calmar, MDD), calibration error (Brier, ECE), and coordination efficiency. A 4-way factorial ablation suite benchmark (`scripts/run_cph_ablation_benchmark.py`) compares Linear Pipeline, Vanilla TradingAgents, SelfDebate V2, and CARE-Agents across mock and live modes.

```
Market Data / State
        │
        ▼
[v2 Specialist Analysts] ──> Structured Posteriors (p_opt, p_neu, p_cau, move_bps, regime)
        │
        ├─────────────────────────────────────┐
        ▼                                     ▼
[CBS Gating: D_JS >= 0.12 & CBS > s_t]     [Online Regime MWU: w^(r) updated via Brier loss]
   ├── YES ──> Dynamic Bull/Bear Debate       │
   └── NO  ──> Fast-Path (RiskSelfDebateV2)   ▼
        │                              [Calibrated Signal Processing: Bayesian Log-Odds Target Price]
        ▼                                     │
[Trader / Risk Manager] <─────────────────────┘
        │
        ▼
[Episodic Memory: Regime Filtered + Drawdown Circuit-Breaker]
        │
        ▼
[Execution & Net-of-Cost Evaluation: ProtocolAuditEvaluator (A-Share Frictions)]
        │
        ▼
[Counterfactual Reflection Attribution: correct_driver, overridden_correct, false_driver, etc.]
```

---

## Feature Inventory

Every feature discovered during the Survey phase is mapped to an assigned milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Signal Block Extraction | Extracts JSON signal block from markdown report, stripping raw JSON from report text | M1 | `core/agents/analyst.py` |
| 2 | Posterior Normalization | Enforces probability simplex ($\sum p = 1.0$), parses percentage strings and bps moves | M1 | `core/agents/analyst.py` |
| 3 | Standalone Posterior API | Public function `extract_structured_posterior(report_text)` and static method alias | M1 | `plan.md` §1.1 |
| 4 | Regime State Propagation | `index_analyst_v2` outputs `market_regime` to top-level state | M1 | `plan.md` §1.2 |
| 5 | State Concurrency Reducer | `merge_dict` reducer handles concurrent parallel analyst writes to `state["analyst_posteriors"]` | M1 | `core/state/reducers.py` |
| 6 | Base-2 Shannon Entropy | Calculates $H_2(P) = -\sum p \log_2 p$ in pure Python without external dependencies | M1 | `tradingagents/graph/conditional_logic.py` |
| 7 | Base-2 JSD Disagreement | Computes weighted $D_{JS} = H_2(\bar{p}) - \sum w_i H_2(p_i) \in [0, 1]$ | M1 | `tradingagents/graph/conditional_logic.py` |
| 8 | CBS Gating & Calculation | Computes $\text{CBS} = \frac{D_{JS} \cdot \bar{m}}{2}$ and gates debate vs fast-path ($D_{JS} \ge 0.12 \land \text{CBS} > s_t$) | M1 | `tradingagents/graph/conditional_logic.py` |
| 9 | Dynamic Debate Rounds | Scales debate turns between 1 and $d_{\max}$ based on divergence intensity | M1 | `tradingagents/graph/conditional_logic.py` |
| 10 | Fast-Path Tripartite Synthesis | `RiskSelfDebateV2` synthesizes resilient, defensive, and base perspectives in 1 LLM pass | M1 | `core/agents/adapters/risk_self_debate_v2.py` |
| 11 | Regime-Partitioned Weights | Maintains independent weight tables `w[regime][analyst_id]` for Bull, Bear, Sideways | M2 | `core/agents/utils/weight_calculator.py` |
| 12 | Multiclass Brier Loss | Evaluates 3-class posterior against deadband outcome vector $y_{t+1}$ with $\frac{1}{3}$ scaling | M2 | `core/agents/utils/weight_calculator.py` |
| 13 | Online MWU Updates | Exponentially weighted forecaster update $\tilde{w} = w \exp(-\eta \ell)$ with weight floor $w_{\min}=0.03$ | M2 | `core/agents/utils/weight_calculator.py` |
| 14 | Logarithmic Opinion Pool | Aggregates analyst posteriors into consensus distribution via `aggregate_posteriors` | M2 | `plan.md` §2.2 |
| 15 | Bayesian Log-Odds Pricing | Derives calibrated price target using regime priors $L_0$ and analyst log-odds $\ell_i$ | M2 | `tradingagents/graph/signal_processing.py` |
| 16 | Process Calibrated Signal | Dedicated public function `process_calibrated_signal()` deriving confidence and risk score from posteriors | M2 | `tradingagents/graph/signal_processing.py` |
| 17 | Mandatory Metadata Schema | Enforces `market_regime`, `volatility_quintile`, `attribution_role`, `brier_calibration_error` | M3 | `core/memory/memory_manager.py` |
| 18 | Regime Circuit-Breaker | Suppresses cross-regime memory recall for decision agents when $\text{conf} \ge 0.5$ | M3 | `core/memory/memory_manager.py` |
| 19 | Regime-Matching Re-Ranking | Boosts same-regime similarity scores by 1.5x and excludes opposite regime | M3 | `plan.md` §3.2 |
| 20 | Drawdown Circuit-Breaker | Suspends memory retrieval during structural breaks / drawdowns $> 8\%$ | M3 | `plan.md` §3.2 |
| 21 | Counterfactual Credit Assignment | 4-Quadrant classification: `correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored` | M3 | `core/agents/reflection_helper.py` |
| 22 | Counterfactual Prompt Injection | Injects quadrant status and directive into reflection prompt for individual agents | M3 | `core/agents/reflection_helper.py` |
| 23 | China A-Share Friction Engine | Deducts 2.5 bps commission, 5.0 bps sell stamp duty, and configurable slippage | M4 | `core/backtest/result_evaluator.py` |
| 24 | Annualized Net Metrics | Computes Net Sharpe, Sortino, Calmar, MDD, CAGR over 252 trading days | M4 | `core/backtest/result_evaluator.py` |
| 25 | CBS & Latency Audit | Computes realized CBS hurdle, token cost, latency, and debate bypass rate | M4 | `core/backtest/result_evaluator.py` |
| 26 | Multi-Regime Breakdown | Slices performance across Bull, Bear, and Sideways windows | M4 | `core/backtest/result_evaluator.py` |
| 27 | Protocol Audit Evaluator Class | `ProtocolAuditEvaluator` class auditing all 5 credibility criteria & ECE calculation | M4 | `core/backtest/result_evaluator.py` |
| 28 | 4-Way Factorial Ablation | Runs comparative benchmark across M1, M2, M3, M4 under identical data & backbone | M4 | `scripts/run_cph_ablation_benchmark.py` |
| 29 | Automated Paper Table Export | Exports LaTeX (`.tex`) and CSV (`.csv`) ablation summary tables to `reports/` | M4 | `scripts/run_cph_ablation_benchmark.py` |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Structured Posteriors & CBS Gating | Features 1-10: Public `extract_structured_posterior()`, top-level `market_regime` propagation in `index_analyst_v2.py`, JSD and CBS gating aliases (`compute_jensen_shannon_divergence`, `compute_cbs_bps`, `should_gate_debate`) in `conditional_logic.py`, `tests/test_cbs_debate_gating.py` | none | DONE (132/132 tests passed; clean audit) |
| M2 | Online Regime Weights & Calibrated Signal | Features 11-16: `RegimeMultiplicativeWeightManager` alias, $w_{\min}=0.03$ floor, $\frac{1}{3}$ Brier loss scaling, `aggregate_posteriors()`, public `process_calibrated_signal()`, `tests/test_regime_weight_calculator.py` | M1 | PLANNED |
| M3 | Regime Memory & Counterfactual Attribution | Features 17-22: `attribution_role` metadata normalization, 1.5x same-regime re-ranking boost, drawdown circuit-breaker, role classification (`correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`), `compute_counterfactual_attribution()`, `tests/test_regime_memory_attribution.py` | none | PLANNED |
| M4 | Protocol Audit Evaluator & Factorial Ablation | Features 23-29: Class `ProtocolAuditEvaluator` with ECE & CBS surplus in `result_evaluator.py`, `scripts/run_cph_ablation_benchmark.py` with mock and live modes and LaTeX/CSV export, `tests/test_protocol_audit_evaluator.py` | M1, M2, M3 | PLANNED |
| M5 | Final Milestone: Full Verification & Ablation Pass | Phase 1: Pass 100% of Tiers 1-4 tests across all 4 acceptance test files. Phase 2: Adversarial coverage hardening (Tier 5). Validate ablation benchmark runner output across all 4 configurations | M1, M2, M3, M4, TEST_READY.md | PLANNED |
| E2E | E2E Testing Track | Independent opaque-box test infra and comprehensive test cases across Tiers 1-4 covering all 29 features; publishes `TEST_READY.md` | none | DONE (TEST_READY.md published; 74 tests passed) |

---

## Interface Contracts

### M1 ↔ M2 (Posteriors to Weight Management & Signal Processing)
- `state["analyst_posteriors"]`: `Dict[str, Dict[str, Any]]` where each value conforms to:
  ```python
  {
      "p_optimistic": float,  # [0.0, 1.0]
      "p_neutral": float,     # [0.0, 1.0]
      "p_cautious": float,    # [0.0, 1.0]
      "expected_move_bps": float,  # bps signed or unsigned
      "confidence": float,    # [0.0, 1.0]
      "market_regime": str,   # "bull" | "bear" | "sideways"
  }
  ```
  Sum of probabilities must equal $1.0 \pm 10^{-4}$.
- `state["market_regime"]`: Global regime string `"bull" | "bear" | "sideways"`.

### M2 ↔ M3 (Regimes and Calibration to Memory)
- Memory metadata must include:
  ```python
  {
      "market_regime": str,           # "bull" | "bear" | "sideways"
      "volatility_quintile": int,     # 1 to 5
      "attribution_role": str,        # "correct_driver" | "overridden_correct" | "false_driver" | "correct_dissent_ignored"
      "brier_calibration_error": float # >= 0.0
  }
  ```

### M1/M2/M3 ↔ M4 (Runtime State & Debates to Protocol Evaluator)
- `debate_records`: List of dicts with:
  ```python
  {
      "date": str,
      "debate_jsd": float,
      "cbs_bps": float,
      "dynamic_debate_rounds": int,
      "is_fast_path": bool,
      "token_cost": int,
      "latency_ms": float
  }
  ```
- `ProtocolAuditEvaluator`:
  ```python
  evaluator = ProtocolAuditEvaluator(friction_config=FrictionConfig())
  report = evaluator.evaluate(backtest_results)
  # returns dict with net_metrics, friction_metrics, coordination_metrics, calibration_metrics, regime_metrics
  ```

---

## Code Layout
```
TradingAgents-EN/
├── core/
│   ├── agents/
│   │   ├── analyst.py                       # v2 analysts, extract_structured_posterior
│   │   ├── reflection_helper.py             # counterfactual attribution, compute_counterfactual_attribution
│   │   ├── adapters/
│   │   │   ├── index_analyst_v2.py          # market_regime state propagation
│   │   │   └── risk_self_debate_v2.py       # fast-path synthesis
│   │   └── utils/
│   │       └── weight_calculator.py         # RegimeAdaptiveWeightCalculator, RegimeMultiplicativeWeightManager
│   ├── memory/
│   │   └── memory_manager.py                # Mem0AgentMemory, circuit_breaker_memory_filter
│   └── backtest/
│       └── result_evaluator.py              # FrictionConfig, ProtocolAuditEvaluator
├── tradingagents/
│   └── graph/
│       ├── conditional_logic.py             # compute_base2_jsd, calculate_cbs_routing, should_gate_debate
│       ├── signal_processing.py             # Bayesian log-odds pricing, process_calibrated_signal
│       └── reflection.py                    # graph reflection nodes
├── scripts/
│   └── run_cph_ablation_benchmark.py        # 4-way factorial ablation runner
└── tests/
    ├── test_cbs_debate_gating.py            # AC 1: CBS debate gating verification
    ├── test_regime_weight_calculator.py     # AC 2: Regime weight calibration verification
    ├── test_regime_memory_attribution.py    # AC 3: Regime memory & attribution verification
    └── test_protocol_audit_evaluator.py     # AC 4: Protocol audit evaluator verification
```
