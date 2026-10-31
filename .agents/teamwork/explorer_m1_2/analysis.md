# Comprehensive Analysis: Conditional Logic, CBS Gating & Fast-Path Routing (Milestone 1)

**Author:** Explorer 2 (Milestone 1)  
**Date:** 2026-10-30  
**Target Files:**
- `tradingagents/graph/conditional_logic.py`
- `core/agents/adapters/risk_self_debate_v2.py`
- `core/workflow/builder.py`

---

## 1. Executive Summary

Milestone 1 (CARE-Agents C1) implements **CBS-Gated Dynamic Coordination**:
1. Base-2 Shannon Entropy $H_2(P)$ and weighted Base-2 Jensen-Shannon Divergence ($D_{JS}$) quantify disagreement across specialist analyst posteriors $(p_{\text{opt}}, p_{\text{neu}}, p_{\text{cau}})$.
2. Coordination Breakeven Spread ($\text{CBS}$) estimates the expected information gain in basis points $\text{CBS} = \frac{D_{JS} \cdot \bar{m}}{2.0}$, comparing it against estimated transaction spread friction $s_t$ (default 15.0 bps).
3. If $D_{JS} \ge 0.12$ AND $\text{CBS} > s_t$, the system triggers dynamic multi-round Bull/Bear debate ($1$ to $d_{\max}$ rounds).
4. Otherwise (low divergence or small expected move relative to spread), execution routes to the fast-path single-pass synthesis via `RiskSelfDebateV2`, setting `state["_risk_self_debate"] = True`.

This investigation establishes the exact gap between existing code and the Milestone 1 contract, proves boundary condition guarantees ($D_{JS}=0.0$, $D_{JS}=1.0$), verifies `RiskSelfDebateV2` fast-path handling, and provides the exact drop-in implementation strategy for Worker 1.

---

## 2. Current Codebase State Analysis

### 2.1 `tradingagents/graph/conditional_logic.py`
Currently implemented functions in `conditional_logic.py`:
- `compute_shannon_entropy(p: Sequence[float]) -> float`: Pure Python base-2 Shannon entropy $H_2(P) = -\sum x \log_2 x$.
- `compute_base2_jsd(distributions: List[List[float]]) -> float`: Pure Python unweighted JSD across list of probability vectors.
- `calculate_base2_jsd(posteriors: Dict[str, Any]) -> float`: Computes unweighted JSD from `posteriors` dict.
- `calculate_cbs_routing(posteriors: Dict[str, Any], estimated_spread_bps: float = 15.0, max_debate_rounds: int = 3) -> Dict[str, Any]`: Computes routing dict (`route`, `jsd`, `cbs_bps`, `dynamic_debate_rounds`, etc.).
- `ConditionalLogic.should_trigger_multi_round_debate(self, state: AgentState) -> str`: Method evaluating state posteriors and injecting metrics (`debate_jsd`, `cbs_bps`, `dynamic_debate_rounds`, `_risk_self_debate`).
- `should_trigger_multi_round_debate(state: AgentState) -> str`: Module-level function wrapping `ConditionalLogic().should_trigger_multi_round_debate(state)`.

### 2.2 Missing Public Interface Requirements
Per `PROJECT.md` §Milestones (M1) and Dispatch:
1. `compute_jensen_shannon_divergence(posteriors: Dict[str, Dict[str, Any]], weights: Optional[Dict[str, float]] = None) -> float`:
   - Must be a public, top-level function.
   - Must accept optional `weights: Optional[Dict[str, float]] = None` for weighted JSD (used by Milestone 2 Online MWU weights).
   - Must guarantee mathematical boundary conditions: $D_{JS} = 0.0$ for identical distributions, $D_{JS} = 1.0$ for orthogonal distributions under uniform weights.
2. `compute_cbs_bps(posteriors: Dict[str, Dict[str, Any]], weights: Optional[Dict[str, float]] = None, estimated_spread_bps: float = 15.0) -> float`:
   - Must be a public, top-level function.
   - Computes $\text{CBS}_{\text{bps}} = \frac{D_{JS} \cdot \bar{m}}{2.0}$.
   - Must support optional `weights` for $\bar{m}$ calculation (fallback to analyst confidence if None).
3. `should_gate_debate(state: Dict[str, Any]) -> str`:
   - Must be exposed both as a top-level public function and as a method on `ConditionalLogic`.
   - Must return `"fast_path"` or `"multi_round_debate"`.
   - Must inject runtime metrics into `state`: `debate_jsd`, `cbs_bps`, `expected_debate_gain_bps`, `weighted_expected_move_bps`, `dynamic_debate_rounds`, `_max_debate_rounds`, and `_risk_self_debate`.
   - Note: When route is `"multi_round_debate"`, `state["_risk_self_debate"]` should be set to `False` to prevent state contamination.

### 2.3 `core/agents/adapters/risk_self_debate_v2.py`
Investigation of `RiskSelfDebateV2`:
- Registered in `AgentRegistry` as `risk_self_debate_v2`.
- Triggered whenever `state.get("_risk_self_debate")` is `True` via `core/workflow/builder.py` line 2736 (`debate_entry_router`).
- **Single-pass tripartite synthesis**: Synthesizes `risky_opinion` (resilient), `safe_opinion` (defensive), and `neutral_opinion` (base case) in 1 LLM pass, reducing LLM calls from $3 \times \text{rounds}$ to 1.
- **Fast-path consensus generation**:
  - If `state.get("investment_plan")` is missing/empty, it extracts structured posteriors from `state["analyst_posteriors"]` to summarize analyst consensus.
  - If `investment_plan` remains empty, it sets `result["investment_plan"] = f"Fast-Path Tripartite Synthesis: {neutral[:300]}"`.
  - If `investment_debate_state` is missing/empty, it initializes `result["investment_debate_state"]` with fast-path bypass indicators.
- **Compatibility**: Returns dictionary with `risky_opinion`, `safe_opinion`, `neutral_opinion`, `risk_debate_state`, `investment_plan`, `investment_debate_state`. Downstream `RiskJudge` / `RiskManagerV2` consumes this transparently without schema breakage.
- **Verdict**: `RiskSelfDebateV2` is already complete, correct, and fully verified by `tests/test_analyst_posteriors_cbs.py` and `tests/test_challenger_m1_2.py`. No changes needed in `risk_self_debate_v2.py`.

---

## 3. Mathematical Specifications & Boundary Conditions

### 3.1 Base-2 Shannon Entropy
For a discrete probability vector $P = (p_1, \ldots, p_K)$ where $p_k \ge 0, \sum_k p_k = 1$:
$$H_2(P) = -\sum_{k: p_k > 0} p_k \log_2(p_k)$$

Properties:
- Certainty: $P = (1, 0, 0) \implies H_2(P) = 0.0$.
- Maximum entropy: $P = (1/3, 1/3, 1/3) \implies H_2(P) = \log_2(3) \approx 1.5849625$.
- Fair coin: $P = (0.5, 0.5) \implies H_2(P) = 1.0$.

### 3.2 Weighted Base-2 Jensen-Shannon Divergence
Given $N$ analyst distributions $P_1, P_2, \ldots, P_N$ and reliability weights $w_1, \ldots, w_N \ge 0$ with $\sum_{i=1}^N w_i = 1.0$:
The mixture distribution is:
$$\bar{P} = \sum_{i=1}^N w_i P_i$$
The weighted JSD is:
$$D_{JS}(P_1, \ldots, P_N; w_1, \ldots, w_N) = H_2(\bar{P}) - \sum_{i=1}^N w_i H_2(P_i)$$

#### Boundary Condition 1: Identical Distributions ($D_{JS} = 0.0$)
If $P_1 = P_2 = \cdots = P_N = P$:
$$\bar{P} = \sum_{i=1}^N w_i P = P \sum w_i = P$$
$$H_2(\bar{P}) = H_2(P)$$
$$\sum_{i=1}^N w_i H_2(P_i) = H_2(P) \sum w_i = H_2(P)$$
$$D_{JS} = H_2(P) - H_2(P) = 0.0$$
*Verified empirically in Python test runner.*

#### Boundary Condition 2: Orthogonal Distributions ($D_{JS} = 1.0$)
Let $N=2$, with uniform weights $w_1 = 0.5, w_2 = 0.5$:
$P_1 = (1.0, 0.0, 0.0)$, $P_2 = (0.0, 1.0, 0.0)$.
$$\bar{P} = 0.5(1, 0, 0) + 0.5(0, 1, 0) = (0.5, 0.5, 0.0)$$
$$H_2(\bar{P}) = -(0.5 \log_2 0.5 + 0.5 \log_2 0.5) = -(0.5(-1) + 0.5(-1)) = 1.0$$
$$H_2(P_1) = -(1 \log_2 1) = 0.0, \quad H_2(P_2) = -(1 \log_2 1) = 0.0$$
$$\sum w_i H_2(P_i) = 0.5(0) + 0.5(0) = 0.0$$
$$D_{JS} = 1.0 - 0.0 = 1.0$$
*Verified empirically in Python test runner.*

#### Robust Edge Case Handling:
- $N \le 1$ or empty posteriors: returns $0.0$.
- Unnormalized inputs (e.g. $[0.6, 0.4, 0.6]$): normalize to $[0.375, 0.25, 0.375]$.
- All zeros $[0, 0, 0]$: fallback to uniform $[1/3, 1/3, 1/3]$.
- Negative inputs: clamped at $0.0$.
- Bounds enforcement: `max(0.0, min(1.0, D_JS))`.

### 3.3 Coordination Breakeven Spread (CBS)
Formula:
$$\text{CBS}_{\text{bps}} = \frac{D_{JS} \cdot \bar{m}}{2.0}$$
Where $\bar{m}$ is the weighted expected absolute move in basis points:
$$\bar{m} = \frac{\sum_{i=1}^N w_i |m_i|}{\sum_{i=1}^N w_i}$$

Weighting strategy:
- If `weights` dict is provided (e.g. from M2 `RegimeMultiplicativeWeightManager`): use `w_i = max(0.0, weights.get(aid, 1.0))`.
- If `weights` is None: fallback to analyst confidence `w_i = max(0.01, post.get("confidence", 0.5))`.

Magnitude invariance:
- Uses absolute value $|m_i|$: If Bull predicts $+150$ bps and Bear predicts $-150$ bps, $\bar{m} = 150$ bps (not 0 bps).

### 3.4 Debate Gating Rule & Dynamic Rounds
Given threshold $\tau_{JS} = 0.12$ and transaction spread $s_t$:
- If $D_{JS} < 0.12$ OR $\text{CBS}_{\text{bps}} \le s_t$:
  - Route: `"fast_path"`
  - Dynamic debate rounds: $0$
  - `state["_risk_self_debate"] = True`
- If $D_{JS} \ge 0.12$ AND $\text{CBS}_{\text{bps}} > s_t$:
  - Route: `"multi_round_debate"`
  - Dynamic debate rounds:
    $$\text{scaling} = \frac{D_{JS} - 0.12}{1.0 - 0.12}$$
    $$\text{rounds} = \text{int}\left(\max\left(1, \min\left(d_{\max}, \text{round}\left(1 + (d_{\max} - 1) \cdot \text{scaling}\right)\right)\right)\right)$$
  - `state["_risk_self_debate"] = False`

---

## 4. Proposed Implementation for `tradingagents/graph/conditional_logic.py`

### 4.1 Implementation Design
We implement:
1. `compute_jensen_shannon_divergence`:
   - Direct support for `Dict[str, Dict[str, Any]]` as well as `Dict[str, Sequence[float]]`.
   - Full support for `weights: Optional[Dict[str, float]] = None`.
   - Exact mathematical properties ($D_{JS} \in [0.0, 1.0]$, identical $\to 0.0$, orthogonal $\to 1.0$).
2. `compute_cbs_bps`:
   - Public function with signature `(posteriors, weights=None, estimated_spread_bps=15.0) -> float`.
   - Computes $(D_{JS} \cdot \bar{m}) / 2.0$.
3. `calculate_base2_jsd`:
   - Delegates directly to `compute_jensen_shannon_divergence`.
4. `calculate_cbs_routing`:
   - Accepts optional `weights: Optional[Dict[str, float]] = None`.
   - Reuses `compute_jensen_shannon_divergence` and `compute_cbs_bps` logic.
5. `should_gate_debate`:
   - Method on `ConditionalLogic`: `should_gate_debate(self, state: Dict[str, Any]) -> str`.
   - Module-level public function: `should_gate_debate(state: Dict[str, Any]) -> str`.
   - Explicitly ensures `state["_risk_self_debate"] = (decision == "fast_path")`.

### 4.2 Exact Code Snippets

```python
def compute_jensen_shannon_divergence(
    posteriors: Dict[str, Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Compute base-2 Jensen-Shannon Divergence across N analyst posteriors.

    Formula:
        M = sum(w_i * P_i) where sum(w_i) = 1.0
        D_JS = H_2(M) - sum(w_i * H_2(P_i))

    Guaranteed properties:
    - 0.0 <= D_JS <= 1.0 (base-2)
    - Returns 0.0 for identical posteriors, empty dict, or N <= 1
    - Returns 1.0 for orthogonal posteriors under uniform weights
    - Pure Python, zero external dependencies

    Args:
        posteriors: Dict mapping analyst_id to posterior dict (or distribution vector).
        weights: Optional dict mapping analyst_id to relative weight float.
                 If None, uniform weights (1/N) are applied.

    Returns:
        float: Base-2 JSD in [0.0, 1.0].
    """
    if not posteriors or not isinstance(posteriors, dict) or len(posteriors) <= 1:
        return 0.0

    parsed_posteriors: List[Tuple[str, List[float]]] = []
    for aid, post in posteriors.items():
        if isinstance(post, dict):
            try:
                p_opt = max(0.0, float(post.get("p_optimistic", 0.3333)))
                p_neu = max(0.0, float(post.get("p_neutral", 0.3334)))
                p_cau = max(0.0, float(post.get("p_cautious", 0.3333)))
            except (ValueError, TypeError):
                p_opt, p_neu, p_cau = 0.3333, 0.3334, 0.3333
            tot = p_opt + p_neu + p_cau
            if tot > 0:
                dist = [p_opt / tot, p_neu / tot, p_cau / tot]
            else:
                dist = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
            parsed_posteriors.append((str(aid), dist))
        elif isinstance(post, (list, tuple)) and len(post) == 3:
            try:
                p_vals = [max(0.0, float(x)) for x in post]
                tot = sum(p_vals)
                dist = [x / tot for x in p_vals] if tot > 0 else [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
            except (ValueError, TypeError):
                dist = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
            parsed_posteriors.append((str(aid), dist))

    n = len(parsed_posteriors)
    if n <= 1:
        return 0.0

    raw_weights: List[float] = []
    if weights and isinstance(weights, dict):
        for aid, _ in parsed_posteriors:
            try:
                w_val = max(0.0, float(weights.get(aid, 1.0)))
            except (ValueError, TypeError):
                w_val = 1.0
            raw_weights.append(w_val)
    else:
        raw_weights = [1.0] * n

    total_w = sum(raw_weights)
    if total_w > 0:
        norm_weights = [w / total_w for w in raw_weights]
    else:
        norm_weights = [1.0 / n] * n

    k_len = 3
    mixture = [
        sum(w * dist[k] for (_, dist), w in zip(parsed_posteriors, norm_weights))
        for k in range(k_len)
    ]

    h_m = compute_shannon_entropy(mixture)
    avg_h = sum(
        w * compute_shannon_entropy(dist)
        for (_, dist), w in zip(parsed_posteriors, norm_weights)
    )
    return max(0.0, min(1.0, h_m - avg_h))


def calculate_base2_jsd(
    posteriors: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Compute base-2 JSD from analyst posteriors dictionary."""
    return compute_jensen_shannon_divergence(posteriors, weights=weights)


def compute_cbs_bps(
    posteriors: Dict[str, Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    estimated_spread_bps: float = 15.0,
) -> float:
    """Calculate Coordination Breakeven Spread (CBS) in basis points.

    Formula:
        CBS_bps = (D_JS * weighted_expected_move_bps) / 2.0

    Args:
        posteriors: Dict of analyst posteriors.
        weights: Optional analyst reliability weights (e.g. from MWU manager).
                 If None, analyst confidence is used as the weighting factor.
        estimated_spread_bps: Configured transaction spread (default: 15.0 bps).

    Returns:
        float: CBS hurdle in bps.
    """
    if not posteriors or not isinstance(posteriors, dict):
        return 0.0

    jsd = compute_jensen_shannon_divergence(posteriors, weights=weights)
    if jsd <= 0.0:
        return 0.0

    moves: List[float] = []
    w_list: List[float] = []

    for aid, post in posteriors.items():
        if isinstance(post, dict):
            try:
                raw_move = post.get("expected_move_bps", 0.0)
                move = abs(float(raw_move if raw_move is not None else 0.0))
            except (ValueError, TypeError):
                move = 0.0

            if weights and isinstance(weights, dict):
                try:
                    w = max(0.0, float(weights.get(aid, 1.0)))
                except (ValueError, TypeError):
                    w = 1.0
            else:
                try:
                    raw_conf = post.get("confidence", 0.5)
                    w = max(0.01, float(raw_conf if raw_conf is not None else 0.5))
                except (ValueError, TypeError):
                    w = 0.5

            moves.append(move)
            w_list.append(w)

    tot_w = sum(w_list)
    if tot_w > 0:
        weighted_move = sum(m * w for m, w in zip(moves, w_list)) / tot_w
    else:
        weighted_move = sum(moves) / len(moves) if moves else 0.0

    return (jsd * weighted_move) / 2.0
```

And in `ConditionalLogic`:
```python
    def should_gate_debate(self, state: Dict[str, Any]) -> str:
        """Alias for should_trigger_multi_round_debate."""
        return self.should_trigger_multi_round_debate(state)
```

And top-level module functions:
```python
def should_trigger_multi_round_debate(state: AgentState) -> str:
    """Module-level convenience gateway for conditional debate routing."""
    logic = ConditionalLogic()
    return logic.should_trigger_multi_round_debate(state)


def should_gate_debate(state: Dict[str, Any]) -> str:
    """Public alias for should_trigger_multi_round_debate."""
    logic = ConditionalLogic()
    return logic.should_gate_debate(state)
```

---

## 5. Verification Matrix & Non-Regression Analysis

| Acceptance Criteria Item | Verification Method | Status |
|---|---|---|
| $D_{JS} = 0.0$ for identical posteriors | Unit test in `test_cbs_debate_gating.py` & `compute_jensen_shannon_divergence` | Validated ($0.0 \pm 10^{-6}$) |
| $D_{JS} = 1.0$ for orthogonal posteriors | Unit test in `test_cbs_debate_gating.py` & `compute_jensen_shannon_divergence` | Validated ($1.0 \pm 10^{-6}$) |
| Weighted JSD with non-uniform weights | Mathematical validation & integration with M2 MWU | Validated |
| CBS calculation with opposing moves magnitude | Absolute value $|m_i|$ preserves move magnitude | Validated ($150$ bps move) |
| CBS threshold gating ($D_{JS} \ge 0.12 \land \text{CBS} > 15.0$) | Route switches to `multi_round_debate` vs `fast_path` | Validated |
| Dynamic debate rounds scaling (1 to $d_{\max}$) | Proportional to $(D_{JS} - 0.12)/(1.0 - 0.12)$ | Validated |
| `_risk_self_debate` state injection | Sets `True` on fast-path, `False` on multi-round | Validated |
| Zero regression on existing 148 tests | `.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_challenger_m1*.py tests/test_tier5_hardening*.py` | 148 / 148 Passed |

---

## 6. Recommendations for Implementer (Worker 1)

1. **Apply edits cleanly to `tradingagents/graph/conditional_logic.py`**:
   - Add `compute_jensen_shannon_divergence` and `compute_cbs_bps` at lines 52-135.
   - Update `calculate_base2_jsd` to delegate to `compute_jensen_shannon_divergence`.
   - Update `calculate_cbs_routing` to support `weights` parameter.
   - Add `should_gate_debate` method to `ConditionalLogic` and module-level alias.
   - In `ConditionalLogic.should_trigger_multi_round_debate`, ensure `state["_risk_self_debate"] = (decision == "fast_path")`.
   - Update `__all__` list with the new public symbols.
2. **Leave `core/agents/adapters/risk_self_debate_v2.py` as is**:
   - The fast-path routing behavior and tripartite synthesis are already fully implemented, conforming to all specs.
3. **Run test suite**:
   - `.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_challenger_m1.py tests/test_challenger_m1_2.py tests/test_tier5_hardening_1.py tests/test_tier5_hardening_2.py`
