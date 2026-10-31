# Milestone 2 Test Suite Analysis: Regime Weight Calculator & Signal Calibration

**Agent**: Explorer 3 (`teamwork_explorer`)  
**Milestone**: M2 / Phase 2 (Online Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing)  
**Date**: 2026-10-30  
**Target Suites**:  
- `tests/test_regime_weight_calculator.py` (Canonical Acceptance Criteria Suite)  
- `tests/test_regime_weights_signal.py` (Exhaustive Unit & Regression Test Suite)  

---

## 1. Executive Summary

Milestone 2 establishes online regime-adaptive weighting via an Exponentially Weighted Forecaster (Multiplicative Weights Update / MWU) paired with Bayesian log-odds opinion pooling to eliminate heuristic price multipliers and static weights.

The test suite consists of two primary test files totaling **49 test cases**:
1. `tests/test_regime_weight_calculator.py`: 17 canonical acceptance tests validating Brier loss, weight convergence across synthetic 20-day sequences, strict regime isolation, and calibrated signal processing outputs.
2. `tests/test_regime_weights_signal.py`: 32 regression and unit tests providing granular verification of initialization, active analyst subselection, MWU mathematical compounding, legacy report weight fallbacks, and `SignalProcessor` integration.

Currently, **all 49 tests pass (49/49, 100%)** when executed with `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest`. However, `tests/test_regime_weight_calculator.py` currently relies on fallback mock imports (lines 31–62) for `RegimeMultiplicativeWeightManager` and `process_calibrated_signal` because these symbols are not yet explicitly exported in `core/agents/utils/weight_calculator.py` and `tradingagents/graph/signal_processing.py`.

---

## 2. Enumeration of Test Cases in `tests/test_regime_weight_calculator.py`

The canonical test file `tests/test_regime_weight_calculator.py` defines 17 test cases across 4 test classes:

### 2.1 Multiclass Brier Loss Unit Tests (`TestMulticlassBrierLoss`)

Multiclass Brier loss evaluates an analyst's 3-class posterior distribution $\mathbf{p} = [p_{\text{opt}}, p_{\text{neu}}, p_{\text{caut}}]$ against a discrete market outcome deadband vector $\mathbf{y} \in \{[1,0,0], [0,1,0], [0,0,1]\}$:
$$\text{BrierLoss}(\mathbf{p}, \mathbf{y}) = \sum_{k=1}^3 (p_k - y_k)^2 \in [0.0, 2.0]$$

| Test Method | Realized Return | Target Outcome $\mathbf{y}$ | Forecast $\mathbf{p}$ | Expected Loss | Verification Focus |
|-------------|:---------------:|:---------------------------:|:---------------------:|:-------------:|-------------------|
| `test_brier_loss_bull_outcome` | $+0.02$ (> +50 bps) | $[1, 0, 0]$ (optimistic) | $[1.0, 0.0, 0.0]$<br>$[0.0, 0.0, 1.0]$<br>$[0.0, 1.0, 0.0]$<br>$[1/3, 1/3, 1/3]$ | $0.0$<br>$2.0$<br>$2.0$<br>$2/3$ | Verifies zero loss for perfect forecast, maximum penalty (2.0) for orthogonal forecasts, and baseline uninformative loss ($2/3 \approx 0.6667$). |
| `test_brier_loss_bear_outcome` | $-0.015$ (< -50 bps) | $[0, 0, 1]$ (cautious) | $[0.0, 0.0, 1.0]$<br>$[1.0, 0.0, 0.0]$ | $0.0$<br>$2.0$ | Verifies bear outcome rewards cautious predictions and penalizes optimistic predictions. |
| `test_brier_loss_sideways_neutral_outcome` | $+0.001$ (within $\pm 50$ bps) | $[0, 1, 0]$ (neutral) | $[0.0, 1.0, 0.0]$<br>$[0.8, 0.1, 0.1]$ | $0.0$<br>$1.46$ | Verifies deadband behavior: return within $[-0.005, +0.005]$ targets neutral. Loss for $[0.8, 0.1, 0.1]$ is $0.8^2 + (0.1-1)^2 + 0.1^2 = 1.46$. |
| `test_brier_loss_unnormalized_probabilities_automatically_normalized` | $+0.01$ | $[1, 0, 0]$ | $[2.0, 0.0, 0.0]$ | $0.0$ | Verifies that unnormalized posteriors are safely projected onto the probability simplex before loss calculation. |
| `test_brier_loss_strictly_bounded_in_zero_to_two` | $[-0.03 \dots +0.04]$ | Dynamic | Varied | $[0.0, 2.0]$ | Strict boundary guard verifying $0.0 \le \text{loss} \le 2.0$ across a combinatorial grid of returns and distributions. |

### 2.2 Weight Convergence & Regime Partitioning (`TestRegimeWeightConvergence`)

Verifies Multiplicative Weights Update rule:
$$\tilde{w}_i^{(t+1)} = w_i^{(t)} \cdot \exp(-\eta \cdot \ell_i^{(t)}), \quad w_i^{(t+1)} = \frac{\tilde{w}_i^{(t+1)}}{\sum_j \tilde{w}_j^{(t+1)}}$$
with learning rate $\eta = 0.25$ over 20-day synthetic sequences.

| Test Method | Scenario Description | Analyst Posteriors | Sequence | Acceptance Assertions |
|-------------|----------------------|--------------------|:--------:|-----------------------|
| `test_synthetic_bull_sequence_convergence` | 20-day synthetic bull rally (+1.5% daily) | `bull_spec`: $[0.85, 0.10, 0.05]$<br>`bear_spec`: $[0.05, 0.10, 0.85]$<br>`neutral_spec`: $[0.20, 0.60, 0.20]$ | 20 rounds, $r_t = +0.015$ | 1. $w_{\text{bull\_spec}} > 0.65$<br>2. $w_{\text{bear\_spec}} < 0.10$<br>3. $\sum w_i = 1.0 \pm 10^{-5}$ |
| `test_synthetic_bear_sequence_convergence` | 20-day synthetic bear decline (-1.5% daily) | Same 3 specialists | 20 rounds, $r_t = -0.015$ | 1. $w_{\text{bear\_spec}} > 0.65$<br>2. $w_{\text{bull\_spec}} < 0.10$<br>3. $\sum w_i = 1.0 \pm 10^{-5}$ |
| `test_synthetic_sideways_sequence_convergence` | 20-day mean-reverting churn (+0.01% daily) | `neutral_spec`: $[0.10, 0.80, 0.10]$<br>`bull_spec`, `bear_spec` | 20 rounds, $r_t = +0.0001$ | 1. $w_{\text{neutral\_spec}} > 0.65$<br>2. $w_{\text{bull\_spec}} < 0.20$<br>3. $w_{\text{bear\_spec}} < 0.20$<br>4. $\sum w_i = 1.0 \pm 10^{-5}$ |
| `test_regime_isolation_property` | 10 rounds of updates strictly in `"bull"` regime ($r_t = +0.02$) | `bull_spec`, `bear_spec` | 10 rounds in `"bull"` | 1. $w_{\text{bull}}[\text{bull\_spec}] > w_{\text{bull}}[\text{bear\_spec}]$<br>2. $w_{\text{bear}}$ and $w_{\text{sideways}}$ remain exactly equal to initial uniform weights ($1/3$) across all registered analysts |
| `test_manager_alias_instantiation` | Verifies specification alias `RegimeMultiplicativeWeightManager` | N/A | Instantiation | 1. `set(mgr.weights.keys()) == {"bull", "bear", "sideways"}`<br>2. `len(mgr.analyst_ids) == 7` |

### 2.3 Calibrated Signal Processing Outputs (`TestCalibratedSignalProcessingOutputs`)

Verifies Bayesian log-odds opinion pooling:
$$L_0(\text{regime}) = \begin{cases} \ln(0.60 / 0.40) \approx +0.405465 & \text{bull} \\ 0.0 & \text{sideways} \\ \ln(0.40 / 0.60) \approx -0.405465 & \text{bear} \end{cases}$$
$$\ell_i = \ln\left(\frac{p_{\text{opt}, i}}{p_{\text{caut}, i}}\right), \quad L_{\text{agg}} = L_0 + \sum_{i} w_i \ell_i, \quad P_{\text{agg}} = \sigma(L_{\text{agg}})$$
$$\Delta_{\text{cal}} = (2 P_{\text{agg}} - 1) \cdot \frac{|\bar{m}_{\text{bps}}|}{10000}$$

| Test Method | Action | Regime | Current Price | Posteriors / Input | Assertions |
|-------------|:------:|:------:|:-------------:|-------------------|------------|
| `test_bayesian_log_odds_bull_regime_elevation` | `buy` | `bull` | 100.0 | $a_1: [0.70, 0.10, 150 \text{ bps}]$, $a_2: [0.65, 0.15, 120 \text{ bps}]$ | 1. $\text{target} > 100.0$<br>2. $\text{target} \ne 115.00$ (eliminates static 1.15 multiplier) |
| `test_bayesian_log_odds_bear_regime_reduction` | `sell` | `bear` | 50.0 | $a_1: [0.10, 0.75, -200 \text{ bps}]$, $a_2: [0.15, 0.70, -180 \text{ bps}]$ | 1. $\text{target} < 50.0$<br>2. $\text{target} \ne 47.50$ (eliminates static 0.95 multiplier) |
| `test_bayesian_log_odds_hold_action` | `hold` | `sideways` | 75.50 | Neutral posteriors | $\text{target} == 75.50$ (preserves current price) |
| `test_process_calibrated_signal_contract` | `buy` | `bull` | 10.0 | `index_analyst_v2`, `market_analyst_v2` posteriors | 1. Keys present: `target_price`, `calibrated_prob`, `calibrated_return`<br>2. $\text{target} > 10.0$<br>3. $0.5 < \text{calibrated\_prob} < 1.0$ |
| `test_fallback_when_posteriors_missing` | `buy`, `sell` | `bull` | 100.0 | `{}` (empty posteriors) | 1. Buy target: $100.0 \times 1.15 = 115.00$<br>2. Sell target: $100.0 \times 0.95 = 95.00$ |

### 2.4 Backward Compatibility & Formatting (`TestWeightCalculatorBackwardCompatibility`)

| Test Method | Input | Assertions |
|-------------|-------|------------|
| `test_calculate_report_weights_style_inference` | `{"fundamentals_report": "...", "market_report": "..."}` | 1. Inferred style is `"long"`<br>2. Keys in weights<br>3. $\sum w = 1.0 \pm 10^{-5}$ |
| `test_format_weighted_reports_prompt` | `{"market_report": "..."}`, $w=1.0$ | Prompt contains `"[Important report]"` and `"Bull flag breakout."` |

---

## 3. Fallback Mock Imports in `tests/test_regime_weight_calculator.py`

### 3.1 Direct Code Inspection (Lines 31–62)

In `tests/test_regime_weight_calculator.py`, lines 31–62 contain fallback mock shims:

```python
# Specification aliases & compatibility
try:
    from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
except ImportError:
    RegimeMultiplicativeWeightManager = RegimeAdaptiveWeightCalculator

try:
    from tradingagents.graph.signal_processing import process_calibrated_signal
except ImportError:
    def process_calibrated_signal(
        current_price: float,
        action: str,
        regime: str,
        analyst_posteriors: Dict[str, Dict[str, Any]],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        details = compute_bayesian_log_odds_details(
            current_price=current_price,
            action=action,
            regime=regime,
            analyst_posteriors=analyst_posteriors,
            weights=weights,
        )
        return {
            "target_price": details["target_price"],
            "calibrated_prob": details["p_agg"],
            "p_agg": details["p_agg"],
            "aggregated_log_odds": details["l_agg"],
            "weighted_move_bps": details["weighted_move_bps"],
            "calibrated_return": details["calibrated_return"],
        }
```

### 3.2 Root Cause Analysis
1. In `core/agents/utils/weight_calculator.py`, `RegimeAdaptiveWeightCalculator` is defined at line 303, but the specification alias `RegimeMultiplicativeWeightManager` is not aliased or exported in `__all__`.
2. In `tradingagents/graph/signal_processing.py`, `calculate_bayesian_log_odds_target_price` and `compute_bayesian_log_odds_details` exist, but the dedicated public function `process_calibrated_signal` is not defined.
3. Furthermore, the mock `process_calibrated_signal` returns `target_price`, `calibrated_prob`, `p_agg`, `aggregated_log_odds`, `weighted_move_bps`, and `calibrated_return`, but omits `confidence` ($2 \cdot |P_{\text{agg}} - 0.5|$) and `risk_score` ($1.0 - \text{confidence}$), which are required by PROJECT.md Feature 16 and the Milestone 2 specification.

### 3.3 Concrete Removal Plan
Once Worker M2 implements the required symbols:
1. In `core/agents/utils/weight_calculator.py`:
   - Add alias: `RegimeMultiplicativeWeightManager = RegimeAdaptiveWeightCalculator`
   - Include in `__all__`.
2. In `tradingagents/graph/signal_processing.py`:
   - Implement `process_calibrated_signal(...)`:
     ```python
     def process_calibrated_signal(
         current_price: float,
         action: str,
         regime: str,
         analyst_posteriors: Dict[str, Dict[str, Any]],
         weights: Optional[Dict[str, float]] = None,
         default_move_bps: float = 50.0,
         is_china: bool = True,
     ) -> Dict[str, Any]:
         ...
         # derives target_price, calibrated_prob, confidence, risk_score, calibrated_return
     ```
   - Include in `__all__`.
3. In `tests/test_regime_weight_calculator.py`:
   - Replace lines 18–63 with clean, direct imports:
     ```python
     from core.agents.utils.weight_calculator import (
         DEFAULT_ANALYST_IDS,
         REGIMES,
         RegimeAdaptiveWeightCalculator,
         RegimeMultiplicativeWeightManager,
         calculate_report_weights,
         format_weighted_reports_prompt,
     )
     from tradingagents.graph.signal_processing import (
         SignalProcessor,
         calculate_bayesian_log_odds_target_price,
         compute_bayesian_log_odds_details,
         process_calibrated_signal,
     )
     ```
   - Enhance `test_process_calibrated_signal_contract` to explicitly verify `"confidence" in result` and `"risk_score" in result`.

---

## 4. Enumeration of Test Cases in `tests/test_regime_weights_signal.py`

`tests/test_regime_weights_signal.py` contains **32 comprehensive unit tests** across 6 classes. All 32 passed in 3.08 seconds.

### Class Breakdown:
1. `TestRegimeAdaptiveWeightCalculatorInit` (5 tests):
   - `test_default_initialization`: 7 default analysts, 3 regimes, uniform $1/7$ weights.
   - `test_custom_analyst_ids`: Custom 2 analysts, uniform 0.5 weights.
   - `test_custom_initial_weights`: Custom initial weight dictionary respected per regime.
   - `test_regime_normalization_and_unknown_fallback`: Case insensitivity ("BULL", "  bull  "), unknown regimes fallback to `"sideways"`, `None` defaults to `"sideways"`.
   - `test_active_analysts_subselection`: Weight filtering and re-normalization for subsets of active analysts.
2. `TestBrierLossCalculation` (4 tests):
   - `test_bull_market_outcomes`: $r > +50 \text{ bps} \implies \mathbf{y} = [1,0,0]$; tests perfect (0.0), worst (2.0), and intermediate (0.14) forecasts.
   - `test_bear_market_outcomes`: $r < -50 \text{ bps} \implies \mathbf{y} = [0,0,1]$; tests perfect (0.0) and worst (2.0) forecasts.
   - `test_sideways_neutral_market_outcomes`: $r \in [-50, +50] \text{ bps} \implies \mathbf{y} = [0,1,0]$; tests perfect (0.0) and polarized (1.50) forecasts.
   - `test_unnormalized_probabilities_normalization`: Normalizes percentage inputs (e.g. $[80, 10, 10]$) to $[0.8, 0.1, 0.1]$, yielding loss 0.06.
3. `TestMultiplicativeWeightsUpdate` (6 tests):
   - `test_mwu_rewards_accurate_analyst`: Accurate analyst weight increases relative to inaccurate analyst.
   - `test_regime_isolation`: Updating `"bull"` does not alter `"bear"` or `"sideways"` weights.
   - `test_zero_learning_rate_invariance`: $\eta = 0.0$ preserves original weights identically.
   - `test_sequential_multi_step_compounding`: 5 compounding updates amplify accurate analyst $> 5\times$.
   - `test_dynamic_analyst_addition`: Dynamically encountered analysts in posteriors are added to registry.
   - `test_reset_weights`: `reset()` restores uniform distribution across all regimes.
4. `TestLegacyReportWeightsFallback` (4 tests):
   - `test_short_term_style_inference`: Infers short-term style from market, news, sentiment reports.
   - `test_long_term_style_inference`: Infers long-term style from fundamentals report.
   - `test_empty_or_whitespace_reports`: Gracefully returns `{}` on blank reports.
   - `test_format_weighted_reports_prompt`: Formats prompts with weight headers.
5. `TestBayesianLogOddsAggregation` (5 tests):
   - `test_bull_regime_prior_effect`: Balanced posteriors yield $P_{\text{agg}} > 0.5$ in bull, $P_{\text{agg}} = 0.5$ in sideways, $P_{\text{agg}} < 0.5$ in bear.
   - `test_strong_bull_consensus_price_projection`: Target price strictly between 100 and 120.
   - `test_strong_bear_consensus_price_projection`: Target price strictly between 80 and 100.
   - `test_hold_action_preserves_current_price`: Hold retains current price.
   - `test_empty_posteriors_fallback_to_legacy_multipliers`: China A-share 1.15 / 0.95 and US 1.12 / 0.92 multipliers verified.
6. `TestSignalProcessorIntegration` (8 tests):
   - `test_smart_price_estimation_with_state_posteriors`: Evaluates Bayesian target when posteriors are in state.
   - `test_smart_price_estimation_without_state_fallback`: Fallback to 1.15 / 0.95 when state is None.
   - `test_smart_price_estimation_percentage_in_text`: Regex extraction of explicit target move percentage.
   - `test_process_signal_offline_fallback_with_state`: Offline fallback when `quick_thinking_llm` is None.
   - `test_process_signal_with_mock_llm`: Replaces null LLM target price with Bayesian estimate.
   - `test_process_signal_state_passed_as_dict_symbol`: Handles state passed as second argument.
   - `test_invalid_signal_returns_default_decision`: Blank input produces `"hold"` decision.
   - `test_extract_target_price_helper`: Extracts floating point price target from textual report.

---

## 5. Critical Mathematical & Architectural Nuances

### 5.1 Multiclass Brier Loss Scaling
- `PROJECT.md` Feature 12 mentions "Evaluates 3-class posterior against deadband outcome vector $y_{t+1}$ with $\frac{1}{3}$ scaling", while `TEST_INFRA.md` line 43 notes "$\frac{1}{3}$ or Euclidean in $[0, 2]$".
- **Crucial Observation**: All existing unit tests in `test_regime_weight_calculator.py` (lines 80–93, 121–132) and `test_regime_weights_signal.py` (lines 125, 131, 158) assert Euclidean Brier loss:
  $$\text{Loss} = \sum_{k=1}^3 (p_k - y_k)^2 \in [0.0, 2.0]$$
  e.g., orthogonal forecast loss is exactly `2.0`, uniform forecast loss is `2/3`, intermediate forecast loss is `0.14`.
- **Worker Warning**: If `compute_brier_loss()` is altered to unconditionally divide by 3, all 49 existing test cases will fail. If $1/3$ scaling is introduced, it must either be an optional flag (e.g. `normalized: bool = False`) or the test assertions must be systematically updated in coordination. Euclidean $[0, 2]$ is currently standard.

### 5.2 Weight Floor $w_{\min} = 0.03$ Implementation
- `PROJECT.md` Feature 13 specifies a weight floor $w_{\min} = 0.03$ to prevent sleeping experts from reaching true zero.
- In `tests/test_m2_empirical_challenge.py` (line 83), test `test_100_plus_sequential_updates_calibrated_vs_miscalibrated` asserts:
  `assert final_w["miscalibrated_c"] < 1e-4`
- If a hard $w_{\min} = 0.03$ floor is applied unconditionally during all updates, `miscalibrated_c` would be clamped at $0.03$, causing `test_m2_empirical_challenge.py` to fail.
- **Architectural Solution**: Parameterize `min_weight: float = 0.0` in `RegimeAdaptiveWeightCalculator`, with default `min_weight=0.03` when instantiated via `RegimeMultiplicativeWeightManager` or configurable per instance.

---

## 6. Test Runner Requirements & Verification Commands

### 6.1 Test Environment Findings
- **Operating System**: Linux (x86_64).
- **Python Version**: Python 3.10.21.
- **Virtual Environment**: `/home/bramy/Documents/TradingAgents-EN/.venv`.
- **System PATH**: `pytest` is NOT in the default `/usr/bin` PATH. Executing `pytest` directly in bash yields `bash: line 1: pytest: command not found` (exit code 127).
- **Mandatory Invocation**: All test runners, scripts, and verification agents must invoke:
  ```bash
  /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest <test_file>
  ```
  or activate the venv beforehand (`source /home/bramy/Documents/TradingAgents-EN/.venv/bin/activate`).

### 6.2 Pytest Configuration (`pytest.ini`)
- Located at: `/home/bramy/Documents/TradingAgents-EN/pytest.ini`
- Default options: `testpaths = tests`, `addopts = -m "not integration" -k "not (test_server_config or test_stock_codes)"`
- Markers defined: `integration`, `smoke`, `acceptance`.

### 6.3 Verification Command Matrix

| Purpose | Exact Shell Command | Expected Result |
|---------|---------------------|-----------------|
| **Milestone 2 Acceptance & Regression Suites** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py tests/test_regime_weights_signal.py -v` | **49 passed** in ~3.1s |
| **Canonical AC 2 Suite Only** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py -v` | **17 passed** in ~3.1s |
| **Unit & Signal Processor Suite Only** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weights_signal.py -v` | **32 passed** in ~3.1s |
| **Empirical Challenge Stress Test** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_m2_empirical_challenge.py -v` | **29 passed** in ~0.7s |
| **Adversarial Hardening Suite** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_reviewer_m2_adversarial.py tests/test_empirical_challenger_m2_2.py -v` | **111 passed** in ~3.2s |
| **Combined M1 + M2 Verification** | `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_cbs_debate_gating.py tests/test_regime_weight_calculator.py -v` | **38 passed** in ~3.2s |

---

## 7. Milestone 2 Acceptance Criteria Checklist

- [x] **AC 2.1 — Multiclass Brier Loss**: Computes $\sum (p_k - y_k)^2 \in [0.0, 2.0]$ against deadband $\pm 50 \text{ bps}$; verified for bull, bear, and sideways neutral outcomes.
- [x] **AC 2.2 — Weight Convergence**: 20-day synthetic sequences verify accurate specialists dominate ($w > 0.65$) and inaccurate specialists decay ($w < 0.10$ or $0.20$).
- [x] **AC 2.3 — Strict Regime Isolation**: Weight table updates in `"bull"` regime strictly preserve `"bear"` and `"sideways"` tables unchanged.
- [x] **AC 2.4 — Bayesian Log-Odds Opinion Pooling**: Log-odds prior $L_0(\text{regime})$ properly elevates BUY targets in bull markets and lowers SELL targets in bear markets, eliminating static $1.15 / 0.95$ multipliers.
- [x] **AC 2.5 — SignalProcessor Integration**: Fallback handling for missing posteriors verified; state posteriors successfully parsed for calibrated target prices.
- [ ] **AC 2.6 — Symbol Exports**: Export `RegimeMultiplicativeWeightManager` in `core.agents.utils.weight_calculator.__all__` and `process_calibrated_signal` in `tradingagents.graph.signal_processing.__all__`.
- [ ] **AC 2.7 — Clean Direct Imports**: Eliminate lines 31–62 fallback mock definitions in `tests/test_regime_weight_calculator.py` once AC 2.6 is implemented.
- [ ] **AC 2.8 — Metric Contract Extension**: Verify `process_calibrated_signal()` outputs `confidence` ($2 \cdot |P_{\text{agg}} - 0.5|$) and `risk_score` ($1.0 - \text{confidence}$).
- [x] **AC 2.9 — Zero Regression**: All 32 legacy unit tests in `tests/test_regime_weights_signal.py` pass without regression.
