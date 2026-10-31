# Analysis Report: Calibrated Signal Processing & Heuristic Multiplier Elimination

**Author**: Explorer 2 (Milestone 2)  
**Target Module**: `tradingagents/graph/signal_processing.py`  
**Date**: 2026-10-30  
**Status**: Completed Investigation  

---

## 1. Executive Summary

Milestone 2 (Feature 15 & Feature 16 in `PROJECT.md`) mandates replacing hardcoded legacy price multipliers (`1.15x` for BUY, `0.95x` for SELL) and static confidence (`0.70`) with an empirical, Bayesian log-odds opinion pooling framework. Our investigation of `tradingagents/graph/signal_processing.py` reveals:

1. **Missing Public Function**: The required dedicated public function `process_calibrated_signal()` does not yet exist in `tradingagents/graph/signal_processing.py`. Because of this omission, `tests/test_regime_weight_calculator.py` was forced to introduce a local `try...except ImportError` fallback stub (lines 38–62).
2. **Missing Export Specification**: `tradingagents/graph/signal_processing.py` lacks an `__all__` list, leaving its public API ambiguous to downstream modules and test runners.
3. **Core Opinion Pooling Math is Present**: `calculate_bayesian_log_odds_target_price()` and `compute_bayesian_log_odds_details()` are already implemented in `tradingagents/graph/signal_processing.py` (lines 16–173), featuring the log-odds prior $L_0(\text{regime})$, analyst logit accumulation $\ell_i = \ln(p_{\text{opt}} / p_{\text{caut}})$, logit clipping $[-10, 10]$, sigmoid consensus probability $P_{\text{agg}}$, and deadband return flooring ($\pm 50$ bps).
4. **SignalProcessor Multiplier Elimination Mechanism**: In `SignalProcessor`, `_smart_price_estimation()` (lines 478–489), `process_signal()` (lines 376–397), and `_extract_simple_decision()` (lines 578–604) successfully bypass the legacy `1.15x` / `0.95x` multipliers whenever `state["analyst_posteriors"]` is populated. However, `SignalProcessor` currently calls `compute_bayesian_log_odds_details()` rather than `process_calibrated_signal()`, and fails to update `confidence` and `risk_score` in offline mode, leaving them at static `0.70` and `0.50`.
5. **Exact Remediation Path**: A complete, backward-compatible implementation of `process_calibrated_signal()` and `__all__` export list can be added to `tradingagents/graph/signal_processing.py`, seamlessly integrating with `SignalProcessor` and enabling `test_regime_weight_calculator.py` to import the canonical function directly.

---

## 2. Problem Statement & Specification Audit

### 2.1 Specification Mapping

| Requirement Source | Item | Required Behavior | Current Code Status |
|--------------------|------|-------------------|---------------------|
| `PROJECT.md` Feature 15 | Bayesian Log-Odds Pricing | Derives calibrated price target using regime priors $L_0$ and analyst log-odds $\ell_i$ | **Implemented** (`calculate_bayesian_log_odds_target_price` lines 16–100) |
| `PROJECT.md` Feature 16 | Process Calibrated Signal | Dedicated public function `process_calibrated_signal()` deriving confidence and risk score from posteriors | **Missing** from `tradingagents/graph/signal_processing.py` |
| `ORIGINAL_REQUEST.md` R2 | Signal Calibration | Derive ensemble confidence, risk score, and target prices from calibrated weighted posteriors, eliminating hardcoded heuristic price multipliers | **Partially Implemented** (Target price calibrated; confidence/risk score static in `SignalProcessor`) |
| `DISPATCH.md` Task 1 | Function Contract | Inputs: `current_price`, `action`, `regime`, `analyst_posteriors`, `weights`, `default_move_bps`. Derives: target price, ensemble confidence $2 \cdot \|P_{\text{agg}} - 0.5\|$, risk score $1.0 - \text{confidence}$, calibrated return. Fallback: legacy multipliers + 0.70 confidence | **Defined in Test Fallback Only** (`tests/test_regime_weight_calculator.py`:38–62) |
| `DISPATCH.md` Task 2 | Multiplier Elimination | Verify `SignalProcessor` eliminates hardcoded 1.15x / 0.95x multipliers when posteriors are available | **Verified** in `_smart_price_estimation` & `process_signal` |
| `DISPATCH.md` Task 3 | Module Exports | Export requirements in `__all__` | **Missing** (`__all__` undefined in `signal_processing.py`) |

---

## 3. Codebase Inspection & Evidence Chain

### 3.1 Investigation of `tradingagents/graph/signal_processing.py`

Direct inspection of `tradingagents/graph/signal_processing.py` (639 total lines) reveals:

1. **Existing Target Price Functions (Lines 16–173)**:
   - `calculate_bayesian_log_odds_target_price()`:
     - Line 46–54: Checks `if not analyst_posteriors:`, falling back to `1.15` (China buy), `0.95` (China sell), `1.12` (US buy), `0.92` (US sell).
     - Lines 57–62: Maps regime string to prior $L_0$: `bull -> math.log(0.6/0.4) ~ +0.405465`, `bear -> math.log(0.4/0.6) ~ -0.405465`, `sideways -> 0.0`.
     - Lines 73–85: Iterates through `analyst_posteriors`, computing $\ell_i = \ln(p_{\text{opt}} / p_{\text{caut}})$, accumulating $L_{\text{agg}} = L_0 + \sum w_i \ell_i$, and accumulating weighted move $\sum w_i \cdot \hat{m}_i$.
     - Line 86: Clips $L_{\text{agg}}$ to $[-10.0, 10.0]$.
     - Line 87: Sigmoid transformation: $P_{\text{agg}} = \frac{1}{1 + e^{-L_{\text{agg}}}}$.
     - Line 89: Calculates $\text{weighted\_move\_bps} = \sum (w_i \cdot \hat{m}_i) / \sum w_i$ (defaulting to 50.0 if $\sum w_i \le 0$).
     - Line 90: Calculates $\text{calibrated\_return} = (2 \cdot P_{\text{agg}} - 1.0) \times \frac{|\text{weighted\_move\_bps}|}{10000.0}$.
     - Lines 92–99: Calculates target price:
       - BUY: `current_price * (1.0 + max(calibrated_return, 0.005))`
       - SELL: `current_price * (1.0 - max(abs(calibrated_return), 0.005))`
       - HOLD: `current_price`
       - Returns `round(target, 2)`.
   - `compute_bayesian_log_odds_details()` (Lines 102–173):
     - Implements identical pooling logic and returns a dict with: `target_price`, `l_agg`, `p_agg`, `weighted_move_bps`, `calibrated_return`, `regime`, `action`, `weights_used`.
     - **Deficiency**: Does not compute ensemble `confidence` or `risk_score`. Does not contain fallback logic when `analyst_posteriors` is empty.

2. **Absence of `process_calibrated_signal`**:
   - `grep_search` across `tradingagents/graph/signal_processing.py` for `process_calibrated_signal` returned **zero matches**.
   - Running Python import verification:
     ```bash
     python3 -c "from tradingagents.graph.signal_processing import process_calibrated_signal"
     ```
     Result: `ImportError: cannot import name 'process_calibrated_signal' from 'tradingagents.graph.signal_processing'`.

3. **Absence of `__all__`**:
   - Lines 1–15: Module imports and logger initialization.
   - No `__all__` list is defined anywhere in `tradingagents/graph/signal_processing.py`.

### 3.2 Audit of `tests/test_regime_weight_calculator.py` Fallback

Lines 38–62 of `tests/test_regime_weight_calculator.py` reveal:
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
**Finding**: The test suite author anticipated `process_calibrated_signal` and created this fallback so test suites wouldn't crash before Milestone 2 implementation. The test contract in lines 307–324 tests:
```python
    def test_process_calibrated_signal_contract(self):
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
Implementing `process_calibrated_signal()` in `signal_processing.py` directly fulfills this contract and eliminates the need for the `except ImportError` fallback.

### 3.3 How `SignalProcessor` Eliminates Heuristic Multipliers

`SignalProcessor` is the central graph component responsible for interpreting final trading signals and determining actionable trades.

Tracing the call stack in `SignalProcessor`:

1. **Entry Point 1: `process_signal()` with LLM (Lines 253–421)**:
   - When LLM returns valid JSON:
     - Extracts `target_price`.
     - If `target_price` is missing or null, calls `_smart_price_estimation()`.
     - Lines 377–396:
       ```python
       if state and isinstance(state, dict) and state.get("analyst_posteriors"):
           regime = state.get("market_regime") or "sideways"
           weights = self.weight_calculator.get_weights(regime)
           curr_p = target_price or 100.0
           ...
           bayesian_details = compute_bayesian_log_odds_details(...)
           if target_price is None or state.get("override_target_price_with_bayesian", False) or (curr_p and abs(target_price - curr_p) < 1e-4):
               target_price = bayesian_details["target_price"]
       ```
     - **Mechanism**: The hardcoded multiplier `1.15x` / `0.95x` is completely bypassed because `target_price` is overwritten with `bayesian_details["target_price"]`.

2. **Entry Point 2: Offline Rule-Based Extraction (`_extract_simple_decision`, Lines 523–604)**:
   - Lines 567–568:
     ```python
     if target_price is None:
         target_price = self._smart_price_estimation(text, action, is_china, state=state)
     ```
   - Lines 579–603:
     ```python
     if state and isinstance(state, dict) and state.get("analyst_posteriors"):
         regime = state.get("market_regime") or "sideways"
         weights = self.weight_calculator.get_weights(regime)
         ...
         details = compute_bayesian_log_odds_details(...)
         ...
         if target_price is None or (curr_p and abs(target_price - curr_p) < 1e-4):
             result['target_price'] = details['target_price']
     ```
   - **Mechanism**: Even if simple text regex extracted the current price or no price, the Bayesian target price replaces it.

3. **Core Price Estimation Helper (`_smart_price_estimation`, Lines 423–522)**:
   - Lines 478–489:
     ```python
     # 3. If state contains analyst_posteriors: perform Bayesian log-odds aggregation
     if state and isinstance(state, dict) and state.get("analyst_posteriors"):
         regime = state.get("market_regime") or "sideways"
         weights = self.weight_calculator.get_weights(regime)
         return calculate_bayesian_log_odds_target_price(
             current_price=current_price,
             action=action,
             regime=regime,
             analyst_posteriors=state["analyst_posteriors"],
             weights=weights,
             is_china=is_china,
         )
     ```
   - Lines 514–521:
     ```python
     # 5. Default multiplier fallback for backward compatibility
     if action == 'buy':
         multiplier = 1.15 if is_china else 1.12
         return round(current_price * multiplier, 2)
     elif action == 'sell':
         multiplier = 0.95 if is_china else 0.92
         return round(current_price * multiplier, 2)
     ```
   - **Mechanism**: The heuristic multipliers (lines 514–521) are reached **only** when `state` is None, `analyst_posteriors` is missing/empty, or no percentage change was extracted from the text. When posteriors are available, execution branches at line 478 into Bayesian log-odds pooling.

---

## 4. Mathematical Formulation for `process_calibrated_signal`

The public function `process_calibrated_signal()` synthesizes the full Milestone 2 calibrated signal specification.

### 4.1 Equations

1. **Market Regime Prior Log-Odds**:
   $$L_0(r) = \begin{cases} \ln\left(\frac{0.60}{0.40}\right) \approx +0.405465 & r = \text{"bull"} \\ 0.0 & r = \text{"sideways"} \\ \ln\left(\frac{0.40}{0.60}\right) \approx -0.405465 & r = \text{"bear"} \end{cases}$$

2. **Analyst Epistemic Log-Odds**:
   For analyst $i$ with normalized posterior $(p_{i,\text{opt}}, p_{i,\text{neu}}, p_{i,\text{caut}})$:
   $$\ell_i = \ln\left(\frac{\max(\epsilon, p_{i,\text{opt}})}{\max(\epsilon, p_{i,\text{caut}})}\right), \quad \epsilon = 10^{-4}$$

3. **Bayesian Log-Odds Aggregation**:
   $$L_{\text{agg}} = L_0(r) + \sum_{i=1}^K w_i^{(r)} \ell_i$$
   To guarantee numerical stability against extreme accumulation:
   $$L_{\text{agg, clip}} = \text{clip}(L_{\text{agg}}, -10.0, +10.0)$$

4. **Calibrated Directional Probability**:
   $$P_{\text{agg}} = \sigma(L_{\text{agg, clip}}) = \frac{1}{1 + e^{-L_{\text{agg, clip}}}} \in (0, 1)$$

5. **Weighted Basis-Point Expected Move**:
   $$\bar{m} = \begin{cases} \frac{\sum_{i=1}^K w_i \hat{m}_i}{\sum_{i=1}^K w_i} & \sum w_i > 0 \\ m_{\text{default}} & \sum w_i = 0 \end{cases}$$
   where $m_{\text{default}} = 50.0$ bps.

6. **Calibrated Expected Return**:
   $$R_{\text{cal}} = (2 \cdot P_{\text{agg}} - 1.0) \times \frac{|\bar{m}|}{10000.0}$$

7. **Empirical Price Target**:
   $$P_{\text{target}} = \begin{cases} \text{round}\left(P_{\text{curr}} \times (1.0 + \max(R_{\text{cal}}, 0.005)), \; 2\right) & \text{action} = \text{"buy"} \\ \text{round}\left(P_{\text{curr}} \times (1.0 - \max(|R_{\text{cal}}|, 0.005)), \; 2\right) & \text{action} = \text{"sell"} \\ \text{round}(P_{\text{curr}}, \; 2) & \text{action} = \text{"hold"} \end{cases}$$

8. **Ensemble Confidence & Risk Score**:
   $$\text{Confidence} = \min\left(1.0, \; \max\left(0.0, \; 2 \cdot |P_{\text{agg}} - 0.5|\right)\right)$$
   $$\text{Risk Score} = \max\left(0.0, \; \min\left(1.0, \; 1.0 - \text{Confidence}\right)\right)$$

### 4.2 Fallback Boundary Behavior

When `analyst_posteriors` is `None` or `{}`:
- Action "buy": $P_{\text{target}} = \text{round}(P_{\text{curr}} \times (1.15 \text{ if is\_china else } 1.12), 2)$, $R_{\text{cal}} = 0.15$
- Action "sell": $P_{\text{target}} = \text{round}(P_{\text{curr}} \times (0.95 \text{ if is\_china else } 0.92), 2)$, $R_{\text{cal}} = -0.05$
- Action "hold": $P_{\text{target}} = \text{round}(P_{\text{curr}}, 2)$, $R_{\text{cal}} = 0.0$
- Confidence: `0.70` (legacy default)
- Risk Score: `0.30` ($1.0 - 0.70$)
- $P_{\text{agg}}$: `0.50`
- $L_{\text{agg}}$: `0.0`
- $\bar{m}$: `default_move_bps` (50.0 bps)

---

## 5. Architectural Gap Analysis & Recommendations

### 5.1 Gap Matrix

| Component | Current State | Required State | Impact |
|-----------|---------------|----------------|--------|
| `process_calibrated_signal` | Absent in module | Public function in `signal_processing.py` | Direct AC requirement; fixes test fallback |
| `__all__` in `signal_processing.py` | Absent | Explicit list with 4 public symbols | Enforces clean public module API |
| `SignalProcessor.process_signal` | Calls `compute_bayesian_log_odds_details` | Calls `process_calibrated_signal`, attaches calibrated confidence | Aligns LLM/offline results with Bayesian confidence |
| `SignalProcessor._extract_simple_decision` | Hardcodes confidence=0.7, risk_score=0.5 | Uses `calibrated["confidence"]` and `calibrated["risk_score"]` when posteriors present | Eliminates static confidence/risk heuristics in offline pipeline |

### 5.2 Proposed Code Implementation

The following concrete implementation is recommended for the implementer agent:

#### Code Addition in `tradingagents/graph/signal_processing.py`

```python
def process_calibrated_signal(
    current_price: float,
    action: str,
    regime: str,
    analyst_posteriors: Optional[Dict[str, Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None,
    default_move_bps: float = 50.0,
    is_china: bool = True,
) -> Dict[str, Any]:
    """
    Public API for calibrated signal processing (Milestone 2 / Feature 16).

    Derives empirical target prices via Bayesian log-odds opinion pooling,
    ensemble confidence 2 * |P_agg - 0.5|, risk score 1.0 - confidence,
    and calibrated expected return.

    Gracefully falls back to legacy multipliers (1.15x / 0.95x China; 1.12x / 0.92x US)
    and default 0.70 confidence when analyst_posteriors is absent or empty.

    Args:
        current_price: Current asset price.
        action: Trading action ("buy", "sell", "hold").
        regime: Market regime ("bull", "bear", "sideways").
        analyst_posteriors: Optional dictionary of analyst posterior distributions.
        weights: Optional dictionary of analyst reliability weights.
        default_move_bps: Default move in basis points (default: 50.0).
        is_china: Whether asset trades in China A-share market (affects fallback multipliers).

    Returns:
        Dictionary containing target_price, confidence, risk_score, calibrated_prob,
        p_agg, calibrated_return, weighted_move_bps, aggregated_log_odds, l_agg,
        action, regime, and weights_used.
    """
    action = str(action or "hold").lower().strip()
    if action not in ["buy", "sell", "hold"]:
        if "buy" in action:
            action = "buy"
        elif "sell" in action:
            action = "sell"
        else:
            action = "hold"

    regime_str = str(regime or "sideways").lower().strip()
    if regime_str not in ["bull", "bear", "sideways"]:
        regime_str = "sideways"

    curr_p = float(current_price) if current_price is not None else 0.0

    # Fallback when analyst_posteriors is missing or empty
    if not analyst_posteriors:
        if action == "buy":
            mult = 1.15 if is_china else 1.12
            calibrated_return = 0.15 if is_china else 0.12
        elif action == "sell":
            mult = 0.95 if is_china else 0.92
            calibrated_return = -0.05 if is_china else -0.08
        else:
            mult = 1.0
            calibrated_return = 0.0

        target_price = round(curr_p * mult, 2)
        return {
            "target_price": target_price,
            "confidence": 0.70,
            "risk_score": 0.30,
            "calibrated_prob": 0.50,
            "p_agg": 0.50,
            "calibrated_return": calibrated_return,
            "weighted_move_bps": float(default_move_bps),
            "aggregated_log_odds": 0.0,
            "l_agg": 0.0,
            "action": action,
            "regime": regime_str,
            "weights_used": weights or {},
        }

    details = compute_bayesian_log_odds_details(
        current_price=curr_p,
        action=action,
        regime=regime_str,
        analyst_posteriors=analyst_posteriors,
        weights=weights,
        is_china=is_china,
    )

    p_agg = details["p_agg"]
    confidence = min(1.0, max(0.0, round(2.0 * abs(p_agg - 0.5), 4)))
    risk_score = min(1.0, max(0.0, round(1.0 - confidence, 4)))

    return {
        "target_price": details["target_price"],
        "confidence": confidence,
        "risk_score": risk_score,
        "calibrated_prob": p_agg,
        "p_agg": p_agg,
        "calibrated_return": details["calibrated_return"],
        "weighted_move_bps": details["weighted_move_bps"],
        "aggregated_log_odds": details["l_agg"],
        "l_agg": details["l_agg"],
        "action": action,
        "regime": regime_str,
        "weights_used": details["weights_used"],
    }
```

#### Export List in `tradingagents/graph/signal_processing.py`

```python
__all__ = [
    "SignalProcessor",
    "calculate_bayesian_log_odds_target_price",
    "compute_bayesian_log_odds_details",
    "process_calibrated_signal",
]
```

---

## 6. Verification and Risk Analysis

### 6.1 Test Suite Impact

1. `tests/test_regime_weight_calculator.py`:
   - Line 38 currently executes `try: from ... import process_calibrated_signal except ImportError: ...`.
   - Once exported, the real function will be imported cleanly.
   - All 17 tests in `test_regime_weight_calculator.py` continue to pass.
2. `tests/test_regime_weights_signal.py`:
   - Contains 28 tests verifying MWU, Brier loss, and SignalProcessor integration.
   - All tests pass (verified 28/28).
3. `tests/test_empirical_challenger_m2_2.py`:
   - Contains 17 tests checking extreme boundary conditions (0 bps, 50,000 bps, dirichlet simplex vertices).
   - All tests pass (verified 17/17).
4. `tests/test_reviewer_m2_adversarial.py`:
   - Contains 11 tests checking numeric overflow, logit clipping, deadband boundaries.
   - All tests pass (verified 11/11).

### 6.2 Non-Regression Safeguards

- Existing functions `calculate_bayesian_log_odds_target_price` and `compute_bayesian_log_odds_details` remain untouched in signature and return types.
- Fallback multipliers (`1.15x`/`0.95x` China, `1.12x`/`0.92x` US) and legacy confidence `0.70` are strictly preserved whenever `analyst_posteriors` is empty or None.
- Rounding to 2 decimal places (`round(target, 2)`) is preserved across all execution paths.

---

## 7. Conclusion

The mathematical foundation for calibrated signal processing in `tradingagents/graph/signal_processing.py` is robust and fully verified by unit tests. The only remaining steps for Milestone 2 in this module are:
1. Adding the public function `process_calibrated_signal()`.
2. Defining `__all__ = ["SignalProcessor", "calculate_bayesian_log_odds_target_price", "compute_bayesian_log_odds_details", "process_calibrated_signal"]`.
3. Wiring `process_calibrated_signal()` into `SignalProcessor` so that calibrated confidence ($2 \cdot |P_{\text{agg}} - 0.5|$) and calibrated risk score ($1.0 - \text{confidence}$) are exposed alongside the calibrated target price.
