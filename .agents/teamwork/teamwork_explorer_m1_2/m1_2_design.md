# M1.2 Code Design Specification: CBS-Gated Dynamic Debate & Fast-Path Routing

**Author**: Explorer M1_2  
**Date**: 2026-10-30  
**Scope**: 
1. `tradingagents/graph/conditional_logic.py` — JSD base-2 calculation, CBS evaluation, dynamic debate gating, and round scaling.
2. `core/agents/adapters/risk_self_debate_v2.py` — Fast-path routing and single-pass tripartite consensus synthesis.
3. `tradingagents/agents/utils/agent_states.py` & `core/workflow/builder.py` — `analyst_posteriors` registration with `merge_dict` reducer.

---

## 1. Executive Summary & Architectural Overview

The CARE-Agents framework introduces **Cost-Aware, Regime-Adaptive Multi-Agent Trading**. In multi-agent debate pipelines, unconditional multi-round debates cause:
1. **Degeneration of Thought (DoT)**: When analysts already agree or when expected market move is smaller than execution friction, excessive debate forces artificial polarization, introducing hallucinated contradictions.
2. **Excessive Latency and Token Cost**: Up to 6x unnecessary LLM invocations during low-volatility or consensus regimes.

To solve this, M1 introduces the **Coordination Breakeven Spread (CBS)** gating mechanism:
```
                    ┌────────────────────────────────────────┐
                    │      7x V2 Analyst Agents              │
                    │   (Markdown Report + Posteriors Dict)  │
                    └───────────────────┬────────────────────┘
                                        │
                                        ▼
                    ┌────────────────────────────────────────┐
                    │  Conditional Logic Gate (JSD & CBS)     │
                    │   JSD < 0.12  OR  CBS_bps <= Spread    │
                    └───────────┬────────────────┬───────────┘
               Fast-Path        │                │ High Divergence
          (Single-Pass Synth)   ▼                ▼ & High Stake
                    ┌──────────────────┐   ┌───────────────────────────┐
                    │ RiskSelfDebateV2 │   │ Dynamic Multi-Round       │
                    │ (1-Pass Triad)   │   │ Bull/Bear Debate          │
                    └───────────┬──────┘   │ (1 to max_debate_rounds)  │
                                │          └─────────────┬─────────────┘
                                └────────────────┬───────┘
                                                 ▼
                                ┌─────────────────────────────┐
                                │ Downstream Signal Processor │
                                │ & Portfolio Execution       │
                                └─────────────────────────────┘
```

---

## 2. Mathematical Specifications

### 2.1 Base-2 Jensen-Shannon Divergence (JSD)
Let $N$ denote the number of active analyst posteriors in `state["analyst_posteriors"]`.  
Each posterior provides a 3-class probability distribution:
$$P_i = [p_{i,\text{opt}}, p_{i,\text{neu}}, p_{i,\text{cau}}] \quad \text{such that} \quad \sum_{k=1}^3 p_{i,k} = 1.0, \quad p_{i,k} \ge 0$$

1. **Mixture Distribution ($M$)**:
   Using uniform distribution weighting across the $N$ active analysts:
   $$M_k = \frac{1}{N} \sum_{i=1}^N P_{i,k} \quad \text{for } k \in \{\text{opt}, \text{neu}, \text{cau}\}$$

2. **Base-2 Shannon Entropy ($H_2$)**:
   For any probability distribution $P$:
   $$H_2(P) = - \sum_{k: P_k > 0} P_k \log_2(P_k)$$
   *(Note: by convention $0 \log_2 0 = 0$)*.

3. **Base-2 JSD Formulation**:
   $$\text{JSD}(P_1, \ldots, P_N) = H_2(M) - \frac{1}{N} \sum_{i=1}^N H_2(P_i)$$
   - When all analysts output identical distributions: $\text{JSD} = 0.0$.
   - When all analysts output uniform distributions $[1/3, 1/3, 1/3]$: $\text{JSD} = 0.0$.
   - For diametrically opposed bull vs bear distributions ($[0.9, 0.05, 0.05]$ vs $[0.05, 0.05, 0.9]$): $\text{JSD} \approx 0.667$.
   - **Crucial Dependency Note**: Because neither `scipy` nor other scientific libraries are present in the environment, this must be implemented using pure Python (`math.log2`), guaranteeing zero dependency errors and microsecond execution speed.

### 2.2 Confidence-Weighted Expected Move & CBS Formulation
Each analyst posterior $i$ provides:
- `expected_move_bps`: signed price expectation in basis points.
- `confidence`: confidence scalar in $[0.0, 1.0]$ (defaults to $1.0$).

The stake magnitude is determined by the confidence-weighted absolute expected move:
$$w_i = \max(\text{confidence}_i, 10^{-4})$$
$$\text{weighted\_expected\_move\_bps} = \frac{\sum_{i=1}^N w_i \cdot |\text{expected\_move\_bps}_i|}{\sum_{i=1}^N w_i}$$

The **Expected Debate Gain** measures the expected value (in basis points) unlocked by reconciling the analyst divergence:
$$\text{expected\_debate\_gain\_bps} = \text{JSD} \times \text{weighted\_expected\_move\_bps}$$

The **Coordination Breakeven Spread (CBS)** allocates half the gain as the breakeven hurdle against transaction frictions:
$$\text{CBS\_bps} = \frac{\text{expected\_debate\_gain\_bps}}{2.0}$$

### 2.3 Decision Rule & Friction Comparison
The round-trip friction hurdle is obtained from state:
$$\text{estimated\_spread\_bps} = \text{float}(state.\text{get}("estimated\_spread\_bps", 15.0))$$
*(Default is 15.0 bps, reflecting China A-shares round-trip frictions: 5 bps sell stamp duty, 2.5 bps buy commission, 2.5 bps sell commission, and 5 bps slippage)*.

**Gate Logic**:
$$\text{Decision} = \begin{cases} 
\text{"fast\_path"}, & \text{if } \text{JSD} < 0.12 \quad \text{OR} \quad \text{CBS\_bps} \le \text{estimated\_spread\_bps} \\
\text{"multi\_round\_debate"}, & \text{if } \text{JSD} \ge 0.12 \quad \text{AND} \quad \text{CBS\_bps} > \text{estimated\_spread\_bps}
\end{cases}$$

### 2.4 Dynamic Rounds Scaling
When debate is triggered, rounds scale dynamically between $1$ and $\text{max\_debate\_rounds}$ according to divergence severity:
$$\text{ratio} = \min\left(1.0, \max\left(0.0, \frac{\text{JSD} - 0.12}{0.48}\right)\right)$$
$$\text{dynamic\_rounds} = 1 + \text{round}\Big(\text{ratio} \times (\text{max\_debate\_rounds} - 1)\Big)$$
$$\text{dynamic\_rounds} = \max\Big(1, \min(\text{max\_debate\_rounds}, \text{dynamic\_rounds})\Big)$$

---

## 3. Detailed Component Designs

### 3.1 Target 1: `tradingagents/graph/conditional_logic.py`

#### Proposed Changes
1. Add pure-Python base-2 entropy and JSD calculation helpers at the module level:
   - `compute_shannon_entropy(p: Sequence[float]) -> float`
   - `compute_base2_jsd(distributions: List[List[float]]) -> float`
   - `calculate_cbs_metrics(analyst_posteriors: Dict[str, Any], estimated_spread_bps: float = 15.0) -> Dict[str, Any]`
2. Add method `should_trigger_multi_round_debate(self, state: AgentState) -> str` to `ConditionalLogic`.
3. Add module-level function `should_trigger_multi_round_debate(state: AgentState) -> str` for standalone/functional invocation.
4. Update `should_continue_debate(self, state: AgentState) -> str` to read `dynamic_debate_rounds` from state or instance, falling back to `self.max_debate_rounds`.

#### Complete Code Implementation for `tradingagents/graph/conditional_logic.py`
```python
import math
from typing import Any, Dict, List, Sequence
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.utils.logging_init import get_logger

logger = get_logger("graph.conditional_logic")


def compute_shannon_entropy(p: Sequence[float]) -> float:
    """Compute base-2 Shannon entropy for a discrete probability vector.
    
    H_2(P) = -sum(p * log2(p)) for p > 0.
    """
    return -sum(x * math.log2(x) for x in p if x > 0.0)


def compute_base2_jsd(distributions: List[List[float]]) -> float:
    """Compute base-2 Jensen-Shannon Divergence across N discrete distributions.
    
    Formula:
        M = (1/N) * sum(P_i)
        JSD = H_2(M) - (1/N) * sum(H_2(P_i))
    
    Edge cases handled:
    - Empty or single distribution -> returns 0.0
    - Non-normalized vectors -> normalized on the fly
    - Uniform distributions -> returns 0.0
    - Numerical precision clamping to max(0.0, ...)
    """
    if not distributions or len(distributions) <= 1:
        return 0.0

    normalized_dists: List[List[float]] = []
    k_len = len(distributions[0])

    for dist in distributions:
        if len(dist) != k_len:
            raise ValueError(f"Inconsistent distribution dimensions: expected {k_len}, got {len(dist)}")
        s = sum(dist)
        if s > 0:
            normalized_dists.append([x / s for x in dist])
        else:
            # Fallback for all-zero distribution
            normalized_dists.append([1.0 / k_len] * k_len)

    n = len(normalized_dists)
    # Mixture distribution M
    mixture = [sum(dist[k] for dist in normalized_dists) / n for k in range(k_len)]

    h_m = compute_shannon_entropy(mixture)
    avg_h = sum(compute_shannon_entropy(dist) for dist in normalized_dists) / n
    return max(0.0, h_m - avg_h)


def calculate_cbs_metrics(
    analyst_posteriors: Dict[str, Any],
    estimated_spread_bps: float = 15.0,
) -> Dict[str, Any]:
    """Calculate JSD, weighted expected move, expected gain, and CBS from posteriors.
    
    Returns:
        dict containing:
            - jsd (float)
            - weighted_expected_move_bps (float)
            - expected_debate_gain_bps (float)
            - cbs_bps (float)
            - estimated_spread_bps (float)
            - active_analysts_count (int)
    """
    if not analyst_posteriors or not isinstance(analyst_posteriors, dict):
        return {
            "jsd": 0.0,
            "weighted_expected_move_bps": 0.0,
            "expected_debate_gain_bps": 0.0,
            "cbs_bps": 0.0,
            "estimated_spread_bps": estimated_spread_bps,
            "active_analysts_count": 0,
        }

    dists: List[List[float]] = []
    moves: List[float] = []
    weights: List[float] = []

    for agent_id, post in analyst_posteriors.items():
        if not isinstance(post, dict):
            continue

        p_opt = float(post.get("p_optimistic", 1.0 / 3.0))
        p_neu = float(post.get("p_neutral", 1.0 / 3.0))
        p_cau = float(post.get("p_cautious", 1.0 / 3.0))

        # Handle missing or invalid numbers
        p_opt = max(0.0, p_opt)
        p_neu = max(0.0, p_neu)
        p_cau = max(0.0, p_cau)
        total_p = p_opt + p_neu + p_cau
        if total_p > 0:
            dists.append([p_opt / total_p, p_neu / total_p, p_cau / total_p])
        else:
            dists.append([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

        # Expected move (in bps)
        if "expected_move_bps" in post and post["expected_move_bps"] is not None:
            raw_move = float(post["expected_move_bps"])
        else:
            # Fallback derived from directional spread
            raw_move = (p_opt - p_cau) * 100.0

        # Confidence weight
        conf = float(post.get("confidence", 1.0))
        w = max(1e-4, min(1.0, conf if conf > 0 else 1.0))

        moves.append(abs(raw_move))
        weights.append(w)

    n_active = len(dists)
    if n_active <= 1:
        return {
            "jsd": 0.0,
            "weighted_expected_move_bps": moves[0] if moves else 0.0,
            "expected_debate_gain_bps": 0.0,
            "cbs_bps": 0.0,
            "estimated_spread_bps": estimated_spread_bps,
            "active_analysts_count": n_active,
        }

    jsd = compute_base2_jsd(dists)
    sum_w = sum(weights)
    weighted_move = sum(w * m for w, m in zip(weights, moves)) / sum_w if sum_w > 0 else 0.0
    expected_gain = jsd * weighted_move
    cbs_bps = expected_gain / 2.0

    return {
        "jsd": jsd,
        "weighted_expected_move_bps": weighted_move,
        "expected_debate_gain_bps": expected_gain,
        "cbs_bps": cbs_bps,
        "estimated_spread_bps": estimated_spread_bps,
        "active_analysts_count": n_active,
    }


class ConditionalLogic:
    """Handles conditional logic for determining graph flow and CARE-Agents debate gating."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.dynamic_debate_rounds = max_debate_rounds

    def should_trigger_multi_round_debate(self, state: AgentState) -> str:
        """Evaluate JSD and CBS against transaction spread to gate multi-round debate.
        
        Returns:
            "fast_path" or "multi_round_debate"
        """
        posteriors = state.get("analyst_posteriors") if isinstance(state, dict) else getattr(state, "analyst_posteriors", None)
        spread_bps = float(state.get("estimated_spread_bps", 15.0) if isinstance(state, dict) else getattr(state, "estimated_spread_bps", 15.0))

        metrics = calculate_cbs_metrics(posteriors, estimated_spread_bps=spread_bps)
        jsd = metrics["jsd"]
        cbs_bps = metrics["cbs_bps"]
        expected_gain = metrics["expected_debate_gain_bps"]
        weighted_move = metrics["weighted_expected_move_bps"]

        # Check gating conditions: JSD < 0.12 OR CBS <= estimated_spread_bps
        if jsd < 0.12 or cbs_bps <= spread_bps:
            decision = "fast_path"
            dynamic_rounds = 0
            logger.info(
                f"🔀 [CBS Debate Gate] -> FAST_PATH | JSD={jsd:.4f} (<0.12: {jsd < 0.12}), "
                f"CBS={cbs_bps:.2f} bps <= Spread={spread_bps:.2f} bps ({cbs_bps <= spread_bps})"
            )
        else:
            decision = "multi_round_debate"
            # Scale dynamic rounds between 1 and max_debate_rounds based on JSD
            ratio = min(1.0, max(0.0, (jsd - 0.12) / 0.48))
            dynamic_rounds = 1 + int(round(ratio * (self.max_debate_rounds - 1)))
            dynamic_rounds = max(1, min(self.max_debate_rounds, dynamic_rounds))
            logger.info(
                f"🔀 [CBS Debate Gate] -> MULTI_ROUND_DEBATE | JSD={jsd:.4f} >= 0.12, "
                f"CBS={cbs_bps:.2f} bps > Spread={spread_bps:.2f} bps | Dynamic Rounds={dynamic_rounds}/{self.max_debate_rounds}"
            )

        # Store runtime metrics in state (for observability and downstream logging)
        if isinstance(state, dict):
            state["debate_jsd"] = jsd
            state["cbs_bps"] = cbs_bps
            state["expected_debate_gain_bps"] = expected_gain
            state["weighted_expected_move_bps"] = weighted_move
            state["dynamic_debate_rounds"] = dynamic_rounds
            state["_max_debate_rounds"] = dynamic_rounds if dynamic_rounds > 0 else 1
            if decision == "fast_path":
                state["_risk_self_debate"] = True

        self.dynamic_debate_rounds = dynamic_rounds if dynamic_rounds > 0 else self.max_debate_rounds
        return decision

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""
        current_count = state["investment_debate_state"]["count"]
        # Use dynamic debate rounds if scaled by should_trigger_multi_round_debate, fallback to max_debate_rounds
        effective_rounds = state.get("dynamic_debate_rounds") if isinstance(state, dict) else None
        if not effective_rounds:
            effective_rounds = getattr(self, "dynamic_debate_rounds", self.max_debate_rounds)
        if not effective_rounds or effective_rounds < 1:
            effective_rounds = self.max_debate_rounds

        max_count = 2 * effective_rounds
        current_speaker = state["investment_debate_state"]["current_response"]

        logger.info(
            f"🔍 [investment debate control] Speeches: {current_count}, Max: {max_count} "
            f"(Configured: {self.max_debate_rounds}, Effective: {effective_rounds})"
        )
        logger.info(f"🔍 [investment debate control] current speaker: {current_speaker}")

        if current_count >= max_count:
            logger.info(f"✅ [investment debate control] Debate round limit reached -> Research Manager")
            return "Research Manager"

        next_speaker = "Bear Researcher" if current_speaker.startswith("Bull") else "Bull Researcher"
        logger.info(f"🔄 [investment debate control] continue debate -> {next_speaker}")
        return next_speaker


def should_trigger_multi_round_debate(state: AgentState) -> str:
    """Module-level convenience gateway for conditional debate routing."""
    logic = ConditionalLogic()
    return logic.should_trigger_multi_round_debate(state)
```

---

### 3.2 Target 2: Integration with `core/agents/adapters/risk_self_debate_v2.py`

#### Role in the CARE-Agents Pipeline
When `should_trigger_multi_round_debate` selects `"fast_path"`, multi-round bull/bear adversarial debate is bypassed. The system immediately routes to `RiskSelfDebateV2`, which performs single-pass synthesis of the three risk perspectives (high elasticity, defensive, baseline).

#### Required Modifications to `RiskSelfDebateV2`

1. **Metadata Declaration (`metadata`)**:
   Add `analyst_posteriors` to `inputs` and declare `investment_plan` in `outputs` (when synthesizing in fast-path mode):
   ```python
   # In RiskSelfDebateV2.metadata.inputs:
   AgentInput(
       name="analyst_posteriors",
       type="object",
       description="Structured probability posteriors from v2 analysts",
       required=False,
       source="state",
       state_field="analyst_posteriors"
   ),
   # In RiskSelfDebateV2.metadata.outputs:
   AgentOutput(
       name="investment_plan",
       type="string",
       description="Fast-path consensus investment plan if bypassing multi-round debate"
   ),
   ```

2. **User Prompt Construction (`_build_user_prompt`)**:
   Extend prompt formatting to include a summary of the active analyst posteriors:
   ```python
   # Format analyst posteriors summary
   analyst_posteriors = state.get("analyst_posteriors") or {}
   posteriors_summary = ""
   if isinstance(analyst_posteriors, dict) and analyst_posteriors:
       lines = []
       for aid, post in analyst_posteriors.items():
           if isinstance(post, dict):
               lines.append(
                   f"- {aid}: Bull={post.get('p_optimistic', 0.0):.2f}, "
                   f"Neutral={post.get('p_neutral', 0.0):.2f}, "
                   f"Bear={post.get('p_cautious', 0.0):.2f}, "
                   f"Expected Move={post.get('expected_move_bps', 0.0):.1f} bps, "
                   f"Regime={post.get('market_regime', 'unknown')}"
               )
       posteriors_summary = "\n".join(lines)

   investment_plan = state.get("investment_plan", "") or state.get("trader_investment_plan", "")
   if not investment_plan and posteriors_summary:
       investment_plan = f"Fast-Path Consensus Synthesis: Multi-round debate bypassed due to low divergence. Analyst consensus:\n{posteriors_summary}"
   ```

3. **Output Execution (`execute`)**:
   Ensure that if `state["investment_plan"]` was not populated (because Bull/Bear debate was bypassed), `RiskSelfDebateV2` populates both `investment_plan` and `investment_debate_state`:
   ```python
   result = {
       "risky_opinion": risky,
       "safe_opinion": safe,
       "neutral_opinion": neutral,
       "risk_debate_state": new_risk_debate_state,
   }

   # Populate investment plan fallback for downstream consumers if empty
   if not state.get("investment_plan"):
       result["investment_plan"] = f"Fast-Path Tripartite Synthesis: {neutral[:300]}"

   # Initialize investment_debate_state if bypassing bull/bear debate
   if not state.get("investment_debate_state"):
       result["investment_debate_state"] = {
           "history": "Fast-Path: Multi-round debate bypassed by CBS gating.",
           "bull_history": "Bypassed via Fast-Path",
           "bear_history": "Bypassed via Fast-Path",
           "current_response": "Fast-Path",
           "judge_decision": result["investment_plan"],
           "count": 0,
       }
   ```

#### Workflow Graph Integration
In `tradingagents/graph/setup.py`:
Add `workflow.add_node("Risk Self Debate", risk_self_debate_node)`.  
Following the last analyst:
```python
workflow.add_conditional_edges(
    current_clear,
    self.conditional_logic.should_trigger_multi_round_debate,
    {
        "fast_path": "Risk Self Debate",
        "multi_round_debate": "Bull Researcher",
    },
)
workflow.add_edge("Risk Self Debate", "Research Manager")
```

In `core/workflow/builder.py`:
In `_add_edges()`:
```python
# Check CBS gating for investment debate
def investment_entry_router(state, _first_p=participants[0], _self_node=self_debate_node_id):
    decision = self.conditional_logic.should_trigger_multi_round_debate(state)
    if decision == "fast_path":
        logger.info(f"[CARE-Agents] Fast-Path activated: bypassing multi-round debate -> {_self_node}")
        return _self_node
    return _first_p
```

---

### 3.3 Target 3: State Schemas & Concurrency Reducer

#### A. `tradingagents/agents/utils/agent_states.py`
In `tradingagents/agents/utils/agent_states.py`, `AgentState` must register `analyst_posteriors` using the `merge_dict` reducer from `core.state.reducers`.

```python
# In tradingagents/agents/utils/agent_states.py

try:
    from core.state.reducers import merge_dict
except ImportError:
    def merge_dict(left: dict, right: dict) -> dict:
        if left is None:
            return right
        if right is None:
            return left
        res = left.copy()
        res.update(right)
        return res

class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]
    # ... existing fields ...

    # 🆕 CARE-Agents R1: Structured probability posteriors & CBS debate gating
    analyst_posteriors: Annotated[Dict[str, Any], merge_dict]
    estimated_spread_bps: Annotated[float, "Estimated round-trip friction in basis points (default 15.0)"]
    debate_jsd: Annotated[float, "Jensen-Shannon divergence across active analyst posteriors"]
    cbs_bps: Annotated[float, "Coordination Breakeven Spread in basis points"]
    dynamic_debate_rounds: Annotated[int, "Dynamically scaled debate rounds (1 to max_debate_rounds)"]
```

#### B. `core/workflow/builder.py`
In `core/workflow/builder.py`, `_get_default_state_schema()` dynamically creates `WorkflowState(MessagesState)`.  
Add `analyst_posteriors` with `merge_dict`:

```python
# In core/workflow/builder.py: _get_default_state_schema()
        class WorkflowState(MessagesState):
            # ... existing fields ...

            # 🆕 CARE-Agents R1: Structured probability posteriors & CBS debate gating
            analyst_posteriors: Annotated[dict, merge_dict]
            estimated_spread_bps: Annotated[float, keep_non_empty]
            debate_jsd: Annotated[float, keep_non_empty]
            cbs_bps: Annotated[float, keep_non_empty]
            dynamic_debate_rounds: Annotated[int, keep_non_empty]
```

#### C. Concurrency Guarantee via `merge_dict`
In LangGraph, when 7 analyst nodes execute concurrently in parallel:
1. Each analyst $i$ returns `{ "analyst_posteriors": { agent_id: posterior_dict } }`.
2. LangGraph invokes the channel reducer `merge_dict(left, right)`:
   - `left` contains existing accumulated posteriors `{ "market_analyst_v2": {...} }`.
   - `right` contains `{ "fundamentals_analyst_v2": {...} }`.
   - `result = left.copy(); result.update(right)`.
3. Without `merge_dict`, LangGraph raises `InvalidUpdateError` on concurrent dictionary updates or arbitrarily discards all but one analyst's output. With `merge_dict`, all 7 analyst posteriors are preserved without loss.

---

## 4. Edge Cases & Decision Truth Table

| Scenario | Inputs (`analyst_posteriors`) | JSD | Weighted Move | CBS (bps) | Spread (bps) | Expected Route | Rationale |
|---|---|---|---|---|---|---|---|
| **Empty Posteriors** | `{}` or `None` | `0.0` | `0.0` | `0.0` | `15.0` | `"fast_path"` | No posterior data; bypass debate safely |
| **Single Analyst** | Only 1 analyst present | `0.0` | `100.0` | `0.0` | `15.0` | `"fast_path"` | No counterparty to debate; single-pass synthesis |
| **Consensus / Low Disagreement** | All analysts Bullish ($[0.6, 0.3, 0.1]$ vs $[0.55, 0.35, 0.1]$) | `0.002` | `50.0` | `0.05` | `15.0` | `"fast_path"` | $\text{JSD} < 0.12$; consensus prevents DoT |
| **Uniform Uncertainty** | All analysts $[0.333, 0.333, 0.333]$ | `0.0` | `0.0` | `0.0` | `15.0` | `"fast_path"` | $\text{JSD} = 0.0 < 0.12$; zero debate gain |
| **High Disagreement, Low Stake** | Opposing stances ($[0.7, 0.2, 0.1]$ vs $[0.1, 0.2, 0.7]$) but expected move = 10 bps | `0.38` | `10.0` | `1.9` | `15.0` | `"fast_path"` | $\text{JSD} \ge 0.12$ BUT $\text{CBS} \le 15.0$; coordination cost exceeds gain |
| **High Disagreement, High Stake** | Opposing stances ($[0.85, 0.1, 0.05]$ vs $[0.05, 0.1, 0.85]$), move = 150 bps | `0.62` | `150.0` | `46.5` | `15.0` | `"multi_round_debate"` | $\text{JSD} \ge 0.12$ AND $\text{CBS} > 15.0$; scales to max rounds |
| **Missing Keys in Posterior** | Dict missing `expected_move_bps` or `confidence` | Valid | Derived | Computed | `15.0` | Deterministic | Gracefully falls back to directional spread and default confidence |

---

## 5. Verification & Test Plan

A dedicated deterministic unit test suite will be written in `tests/test_cbs_debate_gate.py`:
1. `test_base2_shannon_entropy()`: Verifies $H_2([1, 0, 0]) = 0.0$ and $H_2([0.5, 0.5]) = 1.0$.
2. `test_base2_jsd_edge_cases()`: Verifies JSD on single distribution, identical distributions, uniform distributions, and diametric opposites.
3. `test_cbs_gating_fast_path_on_low_jsd()`: Verifies fast-path when $\text{JSD} < 0.12$.
4. `test_cbs_gating_fast_path_on_low_cbs()`: Verifies fast-path when $\text{JSD} \ge 0.12$ but $\text{CBS} \le 15.0$.
5. `test_cbs_gating_multi_round_debate()`: Verifies multi-round debate when $\text{JSD} \ge 0.12$ and $\text{CBS} > 15.0$.
6. `test_dynamic_debate_rounds_scaling()`: Verifies dynamic rounds scale from 1 to `max_debate_rounds` smoothly based on JSD.
7. `test_state_schema_registration()`: Verifies `analyst_posteriors` exists in `AgentState.__annotations__` with `merge_dict` reducer.
8. `test_merge_dict_concurrency()`: Verifies simulated concurrent writes from multiple analysts preserve all posteriors.

All tests run 100% offline without requiring LLM API calls, MongoDB, or external network connectivity.
