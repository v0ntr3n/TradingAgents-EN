# Milestone 2 Technical Investigation: Weight Calculator & MWU Management

**Investigator**: Explorer 1 (`teamwork_explorer`)  
**Target Module**: `core/agents/utils/weight_calculator.py`  
**Related Modules**: `core/agents/utils/__init__.py`, `tradingagents/graph/signal_processing.py`  
**Test Suites Examined**: `tests/test_regime_weight_calculator.py`, `tests/test_regime_weights_signal.py`, `tests/test_tier5_hardening_1.py`, `tests/test_m2_empirical_challenge.py`, `tests/test_reviewer_m2_adversarial.py`  
**Reference Docs**: `PROJECT.md` (Features 11–16), `plan.md` (§2.2, §3.3), `TEST_INFRA.md` (Tier 1–4)

---

## Executive Summary
This report analyzes `core/agents/utils/weight_calculator.py` and its surrounding infrastructure for Milestone 2 (CARE-Agents C2: Online Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing). 

The primary findings are:
1. **`RegimeMultiplicativeWeightManager`**: Missing in `weight_calculator.py` and `__init__.py`. In `tests/test_regime_weight_calculator.py`, it is imported inside a `try...except ImportError` fallback. It should be implemented as a subclass of `RegimeAdaptiveWeightCalculator` with default floor $w_{\min}=0.03$.
2. **Multiclass Brier Loss**: Deadband classification ($\theta = 0.005$) is already implemented correctly with proper boundary inclusion. However, regarding $\frac{1}{3}$ scaling vs unscaled $[0.0, 2.0]$, eight active test suites across the repository assert Euclidean Brier loss bounded in $[0.0, 2.0]$. Changing the default return value would break multiple existing suites. We propose adding an optional `scaled: bool = False` argument to satisfy both requirements without regression.
3. **MWU Weight Floor & Regime Isolation**: Currently, `update_weights` has no floor mechanism. In accordance with `plan.md` Eq (43), the unnormalized update must enforce $\tilde{w}_{i, t+1}^{(r)} = \max(w_{\min}, w_{i, t}^{(r)} \exp(-\eta \ell_{i,t}))$. In `RegimeAdaptiveWeightCalculator`, default `w_min=0.0` preserves numerical underflow test behavior in `test_tier5_hardening_1.py`, while `RegimeMultiplicativeWeightManager` defaults `w_min=0.03`. Regime isolation is already strictly maintained.
4. **Logarithmic Opinion Pool (`aggregate_posteriors`)**: Not yet implemented. We specify a mathematically robust, log-sum-exp stabilized implementation supporting both dictionary and sequence inputs.
5. **Exports & `__all__`**: Missing in `weight_calculator.py`, and `__init__.py` only exports legacy functions. Both files must export `RegimeMultiplicativeWeightManager`, `RegimeAdaptiveWeightCalculator`, `aggregate_posteriors`, `DEFAULT_ANALYST_IDS`, and `REGIMES`.

---

## 1. Investigation Findings by Requirement

### 1.1 `RegimeMultiplicativeWeightManager` Specification & Alias
- **Current State**:
  In `core/agents/utils/weight_calculator.py`, lines 303–482 define `RegimeAdaptiveWeightCalculator`. The symbol `RegimeMultiplicativeWeightManager` does not exist in the file.
  In `tests/test_regime_weight_calculator.py` lines 32–36:
  ```python
  try:
      from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
  except ImportError:
      RegimeMultiplicativeWeightManager = RegimeAdaptiveWeightCalculator
  ```
  Lines 250–256 test:
  ```python
  def test_manager_alias_instantiation(self):
      mgr = RegimeMultiplicativeWeightManager()
      assert set(mgr.weights.keys()) == {"bull", "bear", "sideways"}
      assert len(mgr.analyst_ids) == 7
  ```
- **Architectural Decision**:
  Implement `RegimeMultiplicativeWeightManager` as a direct subclass of `RegimeAdaptiveWeightCalculator`:
  ```python
  class RegimeMultiplicativeWeightManager(RegimeAdaptiveWeightCalculator):
      """
      Online Regime-Conditioned Multiplicative Weights Manager (MWU).
      Enforces weight floor w_min=0.03 by default as specified in CARE-Agents C2.
      """
      def __init__(
          self,
          analyst_ids: Optional[Sequence[str]] = None,
          initial_weights: Optional[Dict[str, Dict[str, float]]] = None,
          learning_rate: float = 0.2,
          return_threshold: float = 0.005,
          w_min: float = 0.03,
      ):
          super().__init__(
              analyst_ids=analyst_ids,
              initial_weights=initial_weights,
              learning_rate=learning_rate,
              return_threshold=return_threshold,
              w_min=w_min,
          )
  ```
  This guarantees `issubclass(RegimeMultiplicativeWeightManager, RegimeAdaptiveWeightCalculator)` and `isinstance(mgr, RegimeAdaptiveWeightCalculator)` both evaluate to `True`, while allowing default parameter customization.

---

### 1.2 Multiclass Brier Loss Calculation & Scaling Analysis
- **Current State (`core/agents/utils/weight_calculator.py:387-420`)**:
  ```python
  def compute_brier_loss(
      self,
      posterior: Dict[str, Any],
      realized_return: float,
  ) -> float:
  ```
- **Deadband Verification ($\theta = 0.005$)**:
  - `realized_return > 0.005` $\implies y = [1, 0, 0]$ (bullish).
  - `realized_return < -0.005` $\implies y = [0, 0, 1]$ (bearish).
  - `-0.005 <= realized_return <= 0.005` $\implies y = [0, 1, 0]$ (neutral/sideways).
  - Boundary check: When `realized_return == 0.005` or `-0.005`, it falls strictly into `else: y = [0, 1, 0]`. This is tested and asserted in `tests/test_tier5_hardening_1.py:409`:
    `assert calc.compute_brier_loss(perfect_neu, realized_return=0.005) == 0.0`
    and `tests/test_m2_empirical_challenge.py:250`:
    `assert pytest.approx(calc.compute_brier_loss(post, 0.005), abs=1e-5) == 2.0` (where `post` is 100% optimistic).

- **Loss Scaling Duality Analysis**:
  - **Specification**: `plan.md` Eq (42) and `PROJECT.md` Feature 12 specify $\ell_{i,t} = \frac{1}{3} \sum_{c} (p_c - y_c)^2 \in [0, \frac{2}{3}]$.
  - **Existing Test Reality**: 8 existing test files explicitly assert standard Euclidean Brier loss bounded in $[0.0, 2.0]$:
    - `tests/test_regime_weight_calculator.py:84`: `assert calculator.compute_brier_loss(worst_cautious, realized_return) == 2.0`
    - `tests/test_regime_weight_calculator.py:113`: `assert pytest.approx(calculator.compute_brier_loss(bullish_post, realized_return), abs=1e-4) == 1.46`
    - `tests/test_regime_weights_signal.py:126`: `assert pytest.approx(calc.compute_brier_loss(worst_post, realized_return), abs=1e-5) == 2.0`
    - `tests/test_tier5_hardening_1.py:398`: `assert calc.compute_brier_loss(perfect_caut, realized_return=0.010) == 2.0`
    - `tests/test_tier5_hardening_2.py:139`: `loss_worst = calc.compute_brier_loss(post_perfect, realized_return=-0.01)` (asserts 2.0)
    - `TEST_INFRA.md:43`: explicit note: *"multiclass Brier loss calculation ($\frac{1}{3}$ or Euclidean in $[0, 2]$)"*.
  - **Proposed Solution**:
    Add `scaled: bool = False` parameter to `compute_brier_loss`:
    ```python
    def compute_brier_loss(
        self,
        posterior: Dict[str, Any],
        realized_return: float,
        scaled: bool = False,
    ) -> float:
        ...
        brier = (p_opt - y[0]) ** 2 + (p_neu - y[1]) ** 2 + (p_caut - y[2]) ** 2
        brier = float(max(0.0, min(2.0, brier)))
        return (brier / 3.0) if scaled else brier
    ```
    This completely avoids breaking existing tests while providing full compliance with the $\frac{1}{3}$ scaling formula when called with `scaled=True`.

---

### 1.3 Online MWU Updates, Weight Floor $w_{\min}=0.03$, and Regime Isolation
- **Current State (`core/agents/utils/weight_calculator.py:422-474`)**:
  MWU update calculates `new_w = old_w * math.exp(-lr * loss)` and normalizes by `sum(updated.values())`. No floor is currently enforced.
- **`plan.md` Formulation (§3.3 Eq 43)**:
  $$\tilde{w}_{i, t+1}^{(r)} = \max\left(w_{\min}, \; w_{i,t}^{(r)} \exp(-\eta \ell_{i,t})\right), \quad w_{i, t+1}^{(r)} = \frac{\tilde{w}_{i, t+1}^{(r)}}{\sum_{j=1}^K \tilde{w}_{j, t+1}^{(r)}}$$
- **Compatibility Analysis**:
  In `tests/test_tier5_hardening_1.py:411-429`:
  ```python
  def test_mwu_learning_rate_extremes(self):
      calc = RegimeAdaptiveWeightCalculator(analyst_ids=["a1", "a2"], learning_rate=0.2)
      ...
      w_extreme = calc.update_weights("bull", posteriors, realized_return=0.02, learning_rate=50.0)
      assert pytest.approx(w_extreme["a1"], abs=1e-5) == 1.0
      assert w_extreme["a2"] < 1e-10
  ```
  If `w_min=0.03` were unconditionally hardcoded on `RegimeAdaptiveWeightCalculator`, `w_extreme["a2"]` would be $\approx 0.0566$, causing this test to fail.
- **Proposed Solution**:
  1. Add `w_min: float = 0.0` to `RegimeAdaptiveWeightCalculator.__init__`.
  2. In `RegimeMultiplicativeWeightManager.__init__`, default `w_min: float = 0.03`.
  3. In `update_weights()`, allow `w_min: Optional[float] = None`, defaulting to `self.w_min`:
     ```python
     effective_w_min = self.w_min if w_min is None else float(w_min)
     for aid in self.analyst_ids:
         old_w = current_w.get(aid, 1.0 / len(self.analyst_ids))
         if aid in analyst_posteriors and isinstance(analyst_posteriors[aid], dict):
             loss = self.compute_brier_loss(analyst_posteriors[aid], realized_return)
             new_w = old_w * math.exp(-lr * loss)
         else:
             new_w = old_w
         if effective_w_min > 0.0:
             new_w = max(effective_w_min, new_w)
         updated[aid] = new_w
     ```
- **Regime Isolation Verification**:
  Regime isolation is strictly maintained: `self.weights[regime] = normalized` assigns solely to the active regime key. `self.weights['bear']` and `self.weights['sideways']` remain untouched when updating `'bull'`. `get_weights()` returns a dictionary copy, preventing external mutation.

---

### 1.4 Logarithmic Opinion Pool (`aggregate_posteriors`)
- **Mathematical Grounding**:
  Under logarithmic opinion pooling (Log-OP) for $K$ analysts with weights $w_i \in [0, 1]$ ($\sum w_i = 1$) and posteriors $p_i \in \Delta^2$:
  $$p_{\text{agg}, c} = \frac{\exp\left(\sum_{i=1}^K w_i \log p_{i, c}\right)}{\sum_{c'} \exp\left(\sum_{i=1}^K w_i \log p_{i, c'}\right)}$$
- **Proposed Implementation**:
  ```python
  def aggregate_posteriors(
      posteriors: Union[Dict[str, Dict[str, Any]], Sequence[Dict[str, Any]]],
      weights: Optional[Dict[str, float]] = None,
      eps: float = 1e-12,
  ) -> Dict[str, float]:
      """
      Logarithmic opinion pooling (Log-OP) aggregating analyst 3-class posteriors
      into a single calibrated consensus distribution.
      """
      classes = ["p_optimistic", "p_neutral", "p_cautious"]
      
      if not posteriors:
          return {"p_optimistic": 1.0 / 3.0, "p_neutral": 1.0 / 3.0, "p_cautious": 1.0 / 3.0}

      items = (
          list(posteriors.items())
          if isinstance(posteriors, dict)
          else [(f"analyst_{i}", p) for i, p in enumerate(posteriors)]
      )

      # Extract and normalize analyst weights
      if weights is None:
          w_dict = {aid: 1.0 / len(items) for aid, _ in items}
      else:
          raw_w = {aid: max(0.0, float(weights.get(aid, 0.0))) for aid, _ in items}
          tot_w = sum(raw_w.values())
          w_dict = {aid: v / tot_w for aid, v in raw_w.items()} if tot_w > 0 else {aid: 1.0 / len(items) for aid, _ in items}

      log_agg = {c: 0.0 for c in classes}
      for aid, post in items:
          if not isinstance(post, dict):
              continue
          w = w_dict.get(aid, 0.0)
          raw_probs = [max(eps, float(post.get(c, 1.0 / 3.0))) for c in classes]
          sum_p = sum(raw_probs)
          norm_probs = [p / sum_p for p in raw_probs]
          for idx, c in enumerate(classes):
              log_agg[c] += w * math.log(norm_probs[idx])

      # Log-sum-exp stabilization
      max_log = max(log_agg.values())
      exp_probs = {c: math.exp(log_agg[c] - max_log) for c in classes}
      tot_exp = sum(exp_probs.values())
      if tot_exp <= 0:
          return {"p_optimistic": 1.0 / 3.0, "p_neutral": 1.0 / 3.0, "p_cautious": 1.0 / 3.0}

      return {c: float(exp_probs[c] / tot_exp) for c in classes}
  ```
- **Class Method on `RegimeAdaptiveWeightCalculator`**:
  ```python
  def aggregate_posteriors(
      self,
      analyst_posteriors: Dict[str, Dict[str, Any]],
      regime: str = "sideways",
      weights: Optional[Dict[str, float]] = None,
  ) -> Dict[str, float]:
      if weights is None:
          weights = self.get_weights(regime, active_analysts=list(analyst_posteriors.keys()))
      return aggregate_posteriors(analyst_posteriors, weights=weights)
  ```

---

### 1.5 Export Requirements & Interface Cleanliness
- **Target File 1**: `core/agents/utils/weight_calculator.py`
  Currently lacks `__all__`. Add:
  ```python
  __all__ = [
      "DEFAULT_ANALYST_IDS",
      "REGIMES",
      "RegimeAdaptiveWeightCalculator",
      "RegimeMultiplicativeWeightManager",
      "aggregate_posteriors",
      "calculate_report_weights",
      "format_weighted_reports_prompt",
  ]
  ```
- **Target File 2**: `core/agents/utils/__init__.py`
  Currently only imports and exports `calculate_report_weights` and `format_weighted_reports_prompt`.
  Update to import and re-export the full suite:
  ```python
  from .weight_calculator import (
      DEFAULT_ANALYST_IDS,
      REGIMES,
      RegimeAdaptiveWeightCalculator,
      RegimeMultiplicativeWeightManager,
      aggregate_posteriors,
      calculate_report_weights,
      format_weighted_reports_prompt,
  )

  __all__ = [
      "DEFAULT_ANALYST_IDS",
      "REGIMES",
      "RegimeAdaptiveWeightCalculator",
      "RegimeMultiplicativeWeightManager",
      "aggregate_posteriors",
      "calculate_report_weights",
      "format_weighted_reports_prompt",
  ]
  ```

---

## 2. Downstream Coordination: `process_calibrated_signal`
In `tests/test_regime_weight_calculator.py` lines 37–62, the test suite includes a compatibility shim for `process_calibrated_signal`:
```python
try:
    from tradingagents.graph.signal_processing import process_calibrated_signal
except ImportError:
    ...
```
In `tradingagents/graph/signal_processing.py`, `compute_bayesian_log_odds_details` is already implemented, but `process_calibrated_signal` as a standalone public function is missing. The implementer for Milestone 2 should add this public wrapper in `tradingagents/graph/signal_processing.py` to ensure complete contract fulfillment.

---

## 3. Comprehensive Verification Matrix

| Verification Target | Command | Expected Outcome |
|---|---|---|
| M2 Canonical Acceptance Suite | `.venv/bin/pytest tests/test_regime_weight_calculator.py -v` | 17/17 tests PASS |
| M2 Signal Processing Suite | `.venv/bin/pytest tests/test_regime_weights_signal.py -v` | 32/32 tests PASS |
| Tier 5 Hardening Suite | `.venv/bin/pytest tests/test_tier5_hardening_1.py -k "test_mwu or test_brier"` | All pass |
| Empirical Challenge Suite | `.venv/bin/pytest tests/test_m2_empirical_challenge.py -v` | 29/29 tests PASS |
| Reviewer Adversarial Suite | `.venv/bin/pytest tests/test_reviewer_m2_adversarial.py -v` | 10/10 tests PASS |
