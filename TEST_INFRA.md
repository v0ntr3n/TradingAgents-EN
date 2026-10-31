# E2E Test Infrastructure: CARE-Agents Quantitative Framework

## 1. Test Philosophy & Architecture
The CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Memory for Financial Trading) test infrastructure is structured as an **opaque-box, requirement-driven, deterministic, offline-capable** verification system.

All tests execute in pure Python with zero external network calls, zero external database requirements, and sub-second deterministic execution using mockable fixtures and synthetic market series.

### Multi-Tier Testing Hierarchy
```
┌────────────────────────────────────────────────────────────────────────┐
│                   Tier 4: Real-World Market Scenarios                  │
│       Bull-to-Bear Shift, Consensus Bull, Sideways Churn,              │
│       Miscalibration Adaptation, 4-Way Factorial Ablation Suite        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                Tier 3: Pairwise Cross-Feature Interactions             │
│    JSD/CBS x MWU Weights, Log-Odds x Dynamic Debate, Circuit-Breaker x │
│    Attribution, Net Costs x Latency, Concurrency Reducer Merging       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│             Tier 2: Boundary Value Analysis & Numerical Extremes       │
│    D_JS in {0, 1}, JSD=0.12, CBS=15 bps, Extreme Brier Loss [0, 2],    │
│    Weight Floor w_min=0.03, Metadata Clamping, Zero-Division Guards    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                 Tier 1: Feature Coverage (Category-Partition)          │
│    Features 1 to 29 across Milestones M1, M2, M3, M4 Contracts         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Canonical Acceptance Test Suites & Feature Mapping

The CARE-Agents verification suite organizes all 29 features from `PROJECT.md` into four canonical acceptance criteria test files:

| Suite Path | Milestone | Scope & Acceptance Criteria |
|------------|:---------:|-----------------------------|
| `tests/test_cbs_debate_gating.py` | M1 | CBS debate gating, boundary conditions ($D_{JS}=0, D_{JS}=1$), disagreement threshold ($D_{JS} \ge 0.12$), CBS spread hurdle ($\text{CBS} > s_t$), dynamic routing switches between multi-round debate and fast-path synthesis (`RiskSelfDebateV2`), dynamic rounds scaling, state concurrency reducer (`merge_dict`). |
| `tests/test_regime_weight_calculator.py` | M2 | Regime-partitioned weights (`w[regime][analyst_id]`), multiclass Brier loss calculation ($\frac{1}{3}$ or Euclidean in $[0, 2]$), weight convergence across synthetic bull/bear/sideways sequences, weight floor $w_{\min} \ge 0.03$, Bayesian log-odds opinion pooling, calibrated price targets, ensemble confidence and risk score. |
| `tests/test_regime_memory_attribution.py` | M3 | Mandatory metadata schema (`market_regime`, `volatility_quintile`, `attribution_role`, `brier_calibration_error`), regime filtering with circuit-breaker ($\text{conf} \ge 0.5$ active, $< 0.5$ bypassed), drawdown circuit-breaker ($> 8\%$), 4-quadrant counterfactual credit assignment (`correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`), prompt injection. |
| `tests/test_protocol_audit_evaluator.py` | M4 | `ProtocolAuditEvaluator` class, realistic China A-share asymmetric frictions (2.5 bps commission, 5.0 bps sell stamp duty, 5.0 bps slippage), annualized net metrics (Net Sharpe, Sortino, Calmar, MDD, CAGR), calibration metrics (Brier, ECE), CBS surplus, token/latency tracking, multi-regime breakdown, 4-way factorial ablation benchmark verification. |

In addition, `tests/test_care_agents_ablation.py` provides cross-tier ablation benchmark execution, while milestone unit test files (`tests/test_analyst_posteriors_cbs.py`, `tests/test_regime_weights_signal.py`, `tests/test_regime_memory_reflection.py`, `tests/test_result_evaluator_care.py`) provide exhaustive modular coverage.

---

## 3. Complete 29-Feature Inventory

| # | Feature | Milestone | Canonical Test Suite | Verification Method |
|---|---------|:---------:|----------------------|---------------------|
| 1 | Signal Block Extraction | M1 | `test_cbs_debate_gating.py` | Regex JSON extraction from markdown without leaking to content |
| 2 | Posterior Normalization | M1 | `test_cbs_debate_gating.py` | Simplex enforcement $\sum p = 1.0 \pm 10^{-4}$, percentage string parsing |
| 3 | Standalone Posterior API | M1 | `test_cbs_debate_gating.py` | Public `extract_structured_posterior` function and static alias |
| 4 | Regime State Propagation | M1 | `test_cbs_debate_gating.py` | `index_analyst_v2` outputs `market_regime` to top-level state |
| 5 | State Concurrency Reducer | M1 | `test_cbs_debate_gating.py` | `merge_dict` reducer handling parallel analyst posterior writes |
| 6 | Base-2 Shannon Entropy | M1 | `test_cbs_debate_gating.py` | Pure Python $H_2(P) = -\sum p \log_2 p$, boundary $H_2([1,0,0])=0, H_2([0.5,0.5])=1$ |
| 7 | Base-2 JSD Disagreement | M1 | `test_cbs_debate_gating.py` | Weighted $D_{JS} \in [0, 1]$, boundary $D_{JS}=0$ (identical) and $D_{JS}=1$ (orthogonal) |
| 8 | CBS Gating & Calculation | M1 | `test_cbs_debate_gating.py` | $\text{CBS} = \frac{D_{JS} \cdot \bar{m}}{2}$, gating $D_{JS} \ge 0.12 \land \text{CBS} > s_t$ |
| 9 | Dynamic Debate Rounds | M1 | `test_cbs_debate_gating.py` | Rounds scaled 1 to $d_{\max}$ based on $(D_{JS}-0.12)/(1-0.12)$ |
| 10 | Fast-Path Tripartite Synthesis | M1 | `test_cbs_debate_gating.py` | `RiskSelfDebateV2` 1-pass synthesis of resilient, defensive, and base views |
| 11 | Regime-Partitioned Weights | M2 | `test_regime_weight_calculator.py` | Independent weight tables `w[regime][analyst_id]` for bull, bear, sideways |
| 12 | Multiclass Brier Loss | M2 | `test_regime_weight_calculator.py` | 3-class prediction vs deadband outcome, scaling in $[0, 2]$ |
| 13 | Online MWU Updates | M2 | `test_regime_weight_calculator.py` | $\tilde{w} = w \exp(-\eta \ell)$, normalization, weight floor $w_{\min}=0.03$ |
| 14 | Logarithmic Opinion Pool | M2 | `test_regime_weight_calculator.py` | Posterior aggregation into consensus distribution via `aggregate_posteriors` |
| 15 | Bayesian Log-Odds Pricing | M2 | `test_regime_weight_calculator.py` | Calibrated target price using prior $L_0$ and analyst log-odds $\ell_i$ |
| 16 | Process Calibrated Signal | M2 | `test_regime_weight_calculator.py` | Ensemble confidence and risk score derived from calibrated posteriors |
| 17 | Mandatory Metadata Schema | M3 | `test_regime_memory_attribution.py` | `market_regime`, `volatility_quintile` [1,5], `attribution_role`, `brier_calibration_error` |
| 18 | Regime Circuit-Breaker | M3 | `test_regime_memory_attribution.py` | Suppresses cross-regime memory recall for decision agents when $\text{conf} \ge 0.5$ |
| 19 | Regime-Matching Re-Ranking | M3 | `test_regime_memory_attribution.py` | 1.5x boost for same-regime memories, exclusion of opposite regime |
| 20 | Drawdown Circuit-Breaker | M3 | `test_regime_memory_attribution.py` | Memory retrieval suspended during structural breaks / drawdowns $> 8\%$ |
| 21 | Counterfactual Credit Assignment | M3 | `test_regime_memory_attribution.py` | 4-quadrant roles: `correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored` |
| 22 | Counterfactual Prompt Injection | M3 | `test_regime_memory_attribution.py` | Injects quadrant status and directive into reflection user prompt |
| 23 | China A-Share Friction Engine | M4 | `test_protocol_audit_evaluator.py` | 2.5 bps commission (buy/sell), 5.0 bps sell stamp duty, 5.0 bps slippage |
| 24 | Annualized Net Metrics | M4 | `test_protocol_audit_evaluator.py` | Net Sharpe, Sortino, Calmar, MDD, CAGR computed over 252 trading days |
| 25 | CBS & Latency Audit | M4 | `test_protocol_audit_evaluator.py` | Realized CBS hurdle, token cost, latency ms, debate bypass rate |
| 26 | Multi-Regime Breakdown | M4 | `test_protocol_audit_evaluator.py` | Performance sliced across Bull, Bear, and Sideways windows |
| 27 | Protocol Audit Evaluator Class | M4 | `test_protocol_audit_evaluator.py` | Class `ProtocolAuditEvaluator` auditing all credibility criteria & ECE |
| 28 | 4-Way Factorial Ablation | M4 | `test_protocol_audit_evaluator.py` | Benchmark comparison across Linear, Vanilla, SelfDebate, and CARE-Agents |
| 29 | Automated Paper Table Export | M4 | `test_protocol_audit_evaluator.py` | LaTeX (`.tex`) and CSV (`.csv`) table export format validation |

---

## 4. Test Execution & Verification

### Running the Canonical Acceptance Test Suites
```bash
# Run all 4 canonical acceptance criteria test suites
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest \
  tests/test_cbs_debate_gating.py \
  tests/test_regime_weight_calculator.py \
  tests/test_regime_memory_attribution.py \
  tests/test_protocol_audit_evaluator.py -v

# Run individual canonical test suites
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_cbs_debate_gating.py -v
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py -v
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_attribution.py -v
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_protocol_audit_evaluator.py -v

# Run the full 4-tier ablation suite
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_care_agents_ablation.py -v
```

### Coverage Thresholds & Quality Gates
- **Pass Rate**: 100% (0 failures, 0 errors).
- **Execution Speed**: Sub-second execution for core suites, zero hanging processes.
- **Offline Integrity**: 100% offline-verifiable, zero external network dependency.
- **Precision**: Exact floating-point assertions ($10^{-4}$ to $10^{-6}$) and numerical invariant checks.
