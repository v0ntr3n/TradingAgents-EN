# Task Assignment: Milestone 2 Worker (Online Regime Weights & Calibrated Signal Processing)

## Identity & Role
- Archetype: teamwork_worker
- Working Directory: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Exclusively Owned Files
- `core/agents/utils/weight_calculator.py`
- `core/agents/utils/__init__.py`
- `tradingagents/graph/signal_processing.py`
- `tests/test_regime_weight_calculator.py`

## Implementation Tasks

### 1. `core/agents/utils/weight_calculator.py`
Apply findings from `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/explorer_m2_1/analysis.md` and `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/explorer_m2_1/proposed_weight_calculator.patch`:
- Add `w_min: float = 0.0` parameter to `RegimeAdaptiveWeightCalculator.__init__`, storing `self.w_min = float(w_min)`.
- In `RegimeAdaptiveWeightCalculator.update_weights()`: apply `new_w = max(self.w_min, new_w)` prior to simplex normalization.
- In `RegimeAdaptiveWeightCalculator.compute_brier_loss()`: add `scaled: bool = False`. If `scaled=True`, return `brier / 3.0`; otherwise return `brier` in $[0.0, 2.0]$.
- Implement `RegimeAdaptiveWeightCalculator.aggregate_posteriors(posteriors, weights=None)` method and module-level function `aggregate_posteriors(posteriors, weights=None) -> Dict[str, float]`.
- Define subclass:
  ```python
  class RegimeMultiplicativeWeightManager(RegimeAdaptiveWeightCalculator):
      """Regime-partitioned analyst weights managed via online Exponentially Weighted Forecaster (MWU)."""
      def __init__(self, analyst_ids=None, learning_rate=0.2, return_threshold=0.005, w_min=0.03):
          super().__init__(
              analyst_ids=analyst_ids,
              learning_rate=learning_rate,
              return_threshold=return_threshold,
              w_min=w_min,
          )
  ```
- Define `__all__` exporting `DEFAULT_ANALYST_IDS`, `REGIMES`, `calculate_report_weights`, `format_weighted_reports_prompt`, `RegimeAdaptiveWeightCalculator`, `RegimeMultiplicativeWeightManager`, and `aggregate_posteriors`.
- Update `core/agents/utils/__init__.py` to export `RegimeAdaptiveWeightCalculator`, `RegimeMultiplicativeWeightManager`, and `aggregate_posteriors`.

### 2. `tradingagents/graph/signal_processing.py`
Apply findings from `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/explorer_m2_2/analysis.md`:
- Implement public function `process_calibrated_signal(current_price: float, action: str, regime: str, analyst_posteriors: Optional[Dict[str, Dict[str, Any]]] = None, weights: Optional[Dict[str, float]] = None, default_move_bps: float = 50.0, is_china: bool = True) -> Dict[str, Any]`.
  - When posteriors provided: calls `compute_bayesian_log_odds_details()`, computes:
    - `confidence = 2.0 * abs(p_agg - 0.5)`
    - `risk_score = 1.0 - confidence`
    - Returns dictionary with `target_price`, `confidence`, `risk_score`, `calibrated_prob`, `p_agg`, `aggregated_log_odds`, `l_agg`, `weighted_move_bps`, `calibrated_return`, `action`, `regime`, `weights_used`.
  - When posteriors missing/empty: fallback to legacy multipliers (`1.15` / `0.95` for China; `1.12` / `0.92` for US), default `confidence = 0.70`, default `risk_score = 0.30`.
- In `SignalProcessor`: update calls to derive confidence and risk score from calibrated signal processing when posteriors are available.
- Define `__all__` exporting `SignalProcessor`, `calculate_bayesian_log_odds_target_price`, `compute_bayesian_log_odds_details`, and `process_calibrated_signal`.

### 3. `tests/test_regime_weight_calculator.py`
- Replace `try...except ImportError` fallback shims with direct imports:
  ```python
  from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
  from tradingagents.graph.signal_processing import process_calibrated_signal
  ```
- Verify all tests pass cleanly.

## Verification Instructions
Run tests with:
```bash
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py tests/test_regime_weights_signal.py -v
```
Ensure 100% pass rate.

## Output Requirements
Write your detailed implementation and test report to `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/handoff.md`.
Notify the orchestrator via `send_message`.


## 2026-10-30T13:45:58Z
You are the Worker for Milestone 2 (Online Regime Weights & Calibrated Signal Processing).
Your working directory is /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/.
Read /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/DISPATCH.md, /home/bramy/Documents/TradingAgents-EN/PROJECT.md, and /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement the changes across your exclusively owned files:
1. core/agents/utils/weight_calculator.py
2. core/agents/utils/__init__.py
3. tradingagents/graph/signal_processing.py
4. tests/test_regime_weight_calculator.py

Run verification:
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weight_calculator.py tests/test_regime_weights_signal.py -v
Document build/test outcomes in /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/handoff.md.
Notify orchestrator when done via send_message.


## 2026-10-30T13:53:52Z
**Context**: Milestone 2 Implementation progress check.
**Content**: Changes across `core/agents/utils/weight_calculator.py`, `core/agents/utils/__init__.py`, `tradingagents/graph/signal_processing.py`, and `tests/test_regime_weight_calculator.py` are confirmed in place.
**Action**: Please complete test runs, compile `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m2/handoff.md`, and notify orchestrator when done.
