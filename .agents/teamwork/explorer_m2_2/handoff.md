# Milestone 2 Explorer 2 Handoff Report: Calibrated Signal Processing

**Author**: Explorer 2 (Milestone 2)  
**Target Module**: `tradingagents/graph/signal_processing.py`  
**Date**: 2026-10-30  
**Handoff Type**: Hard (Task Complete)  

---

## 1. Observation

1. **Missing Public Function `process_calibrated_signal`**:
   - In `tradingagents/graph/signal_processing.py`, ripgrep search for `process_calibrated_signal` returned zero occurrences:
     ```
     grep_search(Query="process_calibrated_signal", SearchPath="/home/bramy/Documents/TradingAgents-EN/tradingagents/graph/signal_processing.py") -> No results found
     ```
   - Direct Python import attempt returned verbatim error:
     ```
     ImportError: cannot import name 'process_calibrated_signal' from 'tradingagents.graph.signal_processing' (/home/bramy/Documents/TradingAgents-EN/tradingagents/graph/signal_processing.py)
     ```

2. **Test Fallback Shim in `tests/test_regime_weight_calculator.py`**:
   - Verbatim lines 38–62 of `tests/test_regime_weight_calculator.py`:
     ```python
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
   - Verbatim test asserting `process_calibrated_signal` contract (lines 307–324):
     ```python
     def test_process_calibrated_signal_contract(self):
         """process_calibrated_signal returns comprehensive calibrated metrics."""
         posteriors = {
             "index_analyst_v2": {"p_optimistic": 0.65, "p_neutral": 0.25, "p_cautious": 0.10, "expected_move_bps": 100.0},
             "market_analyst_v2": {"p_optimistic": 0.60, "p_neutral": 0.30, "p_cautious": 0.10, "expected_move_bps": 90.0},
         }
         result = process_calibrated_signal(
             current_price=10.0,
             action="buy",
             regime="bull",
             analyst_posteriors=posteriors,
         )
         assert "target_price" in result
         assert "calibrated_prob" in result
         assert "calibrated_return" in result
         assert result["target_price"] > 10.0
         assert 0.5 < result["calibrated_prob"] < 1.0
     ```

3. **Missing Module Exports**:
   - `tradingagents/graph/signal_processing.py` contains 639 lines but does not define `__all__`.

4. **Existing Opinion Pooling Math in `tradingagents/graph/signal_processing.py`**:
   - Lines 16–100: `calculate_bayesian_log_odds_target_price()` correctly computes:
     - Prior log-odds: $L_0(\text{bull}) = \ln(0.60/0.40) \approx +0.405465$, $L_0(\text{sideways}) = 0.0$, $L_0(\text{bear}) = \ln(0.40/0.60) \approx -0.405465$.
     - Analyst log-odds: $\ell_i = \ln(p_{\text{opt}} / p_{\text{caut}})$.
     - Accumulation: $L_{\text{agg}} = L_0 + \sum w_i \ell_i$, clipped to $[-10.0, 10.0]$.
     - Sigmoid: $P_{\text{agg}} = \frac{1}{1 + e^{-L_{\text{agg}}}}$.
     - Return: $R_{\text{cal}} = (2 \cdot P_{\text{agg}} - 1.0) \times \frac{|\text{weighted\_move\_bps}|}{10000.0}$.
     - Target: `current_price * (1.0 + max(calibrated_return, 0.005))` for BUY; `current_price * (1.0 - max(|calibrated_return|, 0.005))` for SELL.
     - Fallback for empty posteriors: `1.15` / `0.95` (China) and `1.12` / `0.92` (US).
   - Lines 102–173: `compute_bayesian_log_odds_details()` computes and returns a dict with: `target_price`, `l_agg`, `p_agg`, `weighted_move_bps`, `calibrated_return`, `regime`, `action`, `weights_used`. It lacks confidence, risk score, and empty posteriors fallback.

5. **Heuristic Multiplier Elimination in `SignalProcessor`**:
   - Lines 478–489 in `_smart_price_estimation()`: When `state` contains `analyst_posteriors`, branches to `calculate_bayesian_log_odds_target_price()`, completely skipping legacy multipliers (`1.15x`/`0.95x` lines 514–521).
   - Lines 377–396 in `process_signal()`: Calls `compute_bayesian_log_odds_details()`, overwriting `target_price` with `bayesian_details["target_price"]`.
   - Lines 579–603 in `_extract_simple_decision()`: Overwrites `target_price` with `details["target_price"]`.
   - In both `process_signal()` and `_extract_simple_decision()`, `confidence` and `risk_score` remain static `0.70` and `0.50` instead of deriving from $2 \cdot |P_{\text{agg}} - 0.5|$ and $1.0 - \text{confidence}$.

6. **Current Test Suite Passing**:
   - Running `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weights_signal.py tests/test_empirical_challenger_m2_2.py tests/test_reviewer_m2_adversarial.py -v`:
     `143 passed in 3.19s`
   - Running `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py -v`:
     `17 passed in 3.07s`

---

## 2. Logic Chain

1. **From Observation 1 & 2 to Need for Public Function**:
   - Observation 1 demonstrates `process_calibrated_signal` is missing from `tradingagents/graph/signal_processing.py`.
   - Observation 2 demonstrates that `tests/test_regime_weight_calculator.py` explicitly tests `process_calibrated_signal` contract, but had to stub it out with `except ImportError`.
   - Therefore, implementing and exporting `process_calibrated_signal()` directly in `tradingagents/graph/signal_processing.py` is required to fulfill Feature 16 (`PROJECT.md`) and remove test shimming.

2. **From Observation 4 to Mathematical Reuse**:
   - Observation 4 demonstrates that the underlying Bayesian log-odds pooling mathematics is already completely implemented and tested in `calculate_bayesian_log_odds_target_price()` and `compute_bayesian_log_odds_details()`.
   - Therefore, `process_calibrated_signal()` can be implemented cleanly by utilizing `compute_bayesian_log_odds_details()`, augmenting the output with ensemble confidence $2 \cdot |P_{\text{agg}} - 0.5|$ and risk score $1.0 - \text{confidence}$, and providing the legacy fallback when `analyst_posteriors` is empty or None.

3. **From Observation 3 to Module Exports**:
   - Observation 3 shows `signal_processing.py` lacks `__all__`.
   - Defining `__all__ = ["SignalProcessor", "calculate_bayesian_log_odds_target_price", "compute_bayesian_log_odds_details", "process_calibrated_signal"]` establishes an explicit, well-defined public contract.

4. **From Observation 5 to SignalProcessor Enhancement**:
   - Observation 5 confirms that heuristic multipliers `1.15x` and `0.95x` are already successfully eliminated for target prices when posteriors are available.
   - However, confidence and risk score remain hardcoded heuristics (`0.70` and `0.50`).
   - By routing `SignalProcessor` through `process_calibrated_signal()`, confidence and risk score will also be dynamically derived from the calibrated posterior distribution, fully satisfying R2 of `ORIGINAL_REQUEST.md`.

---

## 3. Caveats

1. **Penny Stock Tick Quantization**: As identified in `test_penny_stock_rounding_quantization_edge_case` (`tests/test_empirical_challenger_m2_2.py`), for penny stocks with current price $\le 0.50$, a 50 bps move with 2-decimal rounding yields `round(0.5025, 2) == 0.50`. This is expected behavior under currency tick size rules.
2. **Extreme Moves Under SELL Action**: In `test_extreme_move_50000_bps_sell_action_boundary`, a 50,000 bps move (500%) produces a negative target price because $1.0 - \text{abs}(R_{\text{cal}}) < 0$. The test explicitly expects this mathematical behavior; no artificial positive price floor should be added without updating test expectations.
3. **LLM Explicit Confidence Override**: When the LLM explicitly returns a confidence score (e.g. `0.85` in JSON), `SignalProcessor.process_signal` preserves the LLM-reported confidence while exposing `calibrated_confidence` and `calibrated_risk_score` in the returned dictionary. In offline rule-based mode, the calibrated metrics directly overwrite the default `0.70` and `0.50`.

---

## 4. Conclusion

1. Implement `process_calibrated_signal()` in `tradingagents/graph/signal_processing.py` with:
   - Inputs: `current_price: float`, `action: str`, `regime: str`, `analyst_posteriors: Optional[Dict[str, Dict[str, Any]]] = None`, `weights: Optional[Dict[str, float]] = None`, `default_move_bps: float = 50.0`, `is_china: bool = True`.
   - Outputs: `target_price`, `confidence` ($2 \cdot |P_{\text{agg}} - 0.5|$), `risk_score` ($1.0 - \text{confidence}$), `calibrated_prob`, `p_agg`, `calibrated_return`, `weighted_move_bps`, `aggregated_log_odds`, `l_agg`, `action`, `regime`, `weights_used`.
   - Fallback: Legacy `1.15x` / `0.95x` multipliers (or `1.12x` / `0.92x` for US), default `0.70` confidence, and `0.30` risk score when posteriors are absent.
2. Add `__all__ = ["SignalProcessor", "calculate_bayesian_log_odds_target_price", "compute_bayesian_log_odds_details", "process_calibrated_signal"]` to `tradingagents/graph/signal_processing.py`.
3. In `SignalProcessor`:
   - Replace calls to `compute_bayesian_log_odds_details()` with `process_calibrated_signal()`.
   - In offline mode (`_extract_simple_decision`), set `result['confidence'] = details['confidence']` and `result['risk_score'] = details['risk_score']` when posteriors are present.
   - Maintain the existing fallback to `1.15x`/`0.95x` when posteriors are absent.

---

## 5. Verification Method

To independently verify the implementation:

1. **Verify Clean Import of Public API**:
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/python3 -c "from tradingagents.graph.signal_processing import process_calibrated_signal, __all__; assert 'process_calibrated_signal' in __all__; print('Import verification: SUCCESS')"
   ```

2. **Run Canonical Acceptance Suite**:
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py -v
   ```
   *Expected*: All 17 tests pass. Specifically, `test_process_calibrated_signal_contract` and `test_fallback_when_posteriors_missing` must pass using the real module function.

3. **Run M2 Adversarial and Challenger Suites**:
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weights_signal.py tests/test_empirical_challenger_m2_2.py tests/test_reviewer_m2_adversarial.py -v
   ```
   *Expected*: All 143 tests pass.

4. **Verify Tier 5 Hardening Suites**:
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_tier5_hardening_1.py tests/test_tier5_hardening_2.py -v
   ```
   *Expected*: All tests pass without any regression in `SignalProcessor`.

5. **Invalidation Conditions**:
   - If `process_calibrated_signal()` raises `KeyError` or `TypeError` when `analyst_posteriors={}` or `analyst_posteriors=None`, the implementation is invalid.
   - If `confidence` does not equal $2 \cdot |P_{\text{agg}} - 0.5|$ or falls outside $[0.0, 1.0]$, the implementation is invalid.
   - If `target_price` is equal to `115.00` when valid bull posteriors with `expected_move_bps=100.0` are provided (at price 100.0), the heuristic multiplier was not eliminated and the implementation is invalid.
