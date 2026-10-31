# CARE-Agents Survey & Architectural Design: R2 & R3

**Author**: Explorer Survey 2  
**Date**: 2026-10-30  
**Target Codebase**: TradingAgents-EN (v3.0)  
**Scope**:  
- **R2**: Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing  
- **R3**: Regime-Filtered Episodic Memory & Counterfactual Credit Assignment  

---

## 1. Executive Summary

The CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Trading) framework extends TradingAgents-EN to overcome critical limitations in agent weighting, price calibration, memory pollution, and credit assignment:
1. **Static / Uncalibrated Analyst Weights (R2)**: Currently, `core/agents/utils/weight_calculator.py` uses fixed heuristic weights based purely on coarse trading styles ("short" vs "long"), completely ignoring market regimes and historical prediction accuracy. Furthermore, `tradingagents/graph/signal_processing.py` relies on arbitrary hardcoded price multipliers (`1.15` / `0.95` for China; `1.12` / `0.92` for US) when target prices are missing.
2. **Regime-Blind Memory & Uniform Scalar Broadcast (R3)**: Currently, `core/memory/memory_manager.py` does not track market regime, volatility quintile, or prediction calibration error. Agents recall bull-market lessons during severe bear crashes (causing "bear PTSD" or dangerous dip-buying). In `tradingagents/graph/reflection.py`, a uniform scalar `returns_losses` is broadcast to every agent regardless of whether that agent's advice was right or wrong, or whether the manager followed or overrode the agent.

This document delivers a thorough code investigation of the six target files across R2 and R3, rigorous mathematical formalizations (Multiplicative Weights Update with multiclass Brier loss, Bayesian log-odds opinion pooling, regime circuit-breaking, and counterfactual credit assignment), and concrete implementation specifications that guarantee 100% backward compatibility.

---

## 2. Investigation of R2: Target Files & Current Code State

### 2.1 `core/agents/utils/weight_calculator.py`

#### Observation
- **Lines 10-60**: Defines `calculate_report_weights(reports: Dict[str, str], trading_style: Optional[str] = None) -> Dict[str, float]`.
  * **Input**: `reports` dictionary mapping report key (e.g., `"market_report"`, `"news_report"`, `"sentiment_report"`, `"fundamentals_report"`, `"sector_report"`, `"index_report"`) to textual report content.
  * **Style Inference** (`_infer_trading_style` lines 63-87): If `"fundamentals_report"` or `"sector_report"` is present, it infers `"long"`; if `"market_report"`, `"news_report"`, and `"sentiment_report"` are present, it infers `"short"`; defaults to `"short"`.
  * **Static Weights**:
    - Short-term: `market_report` (40%), `news_report` (30%), `sentiment_report` (30%), other reports (5%-10%).
    - Long-term: `fundamentals_report` (50%), `sector_report` (30%), other reports (0%-10%).
    - Equal fallback: `1.0 / len(reports)`.
  * **Prompt Formatter** (`format_weighted_reports_prompt` lines 212-282): Partitions reports into `[Important report]` ($\ge 20\%$) and `[Secondary report]` ($< 20\%$).
- **Usage across codebase**:
  * Exported in `core/agents/utils/__init__.py`.
  * No stateful tracking of analyst accuracy over time.
  * No concept of `"bull"`, `"bear"`, or `"sideways"` market regimes.

### 2.2 `tradingagents/graph/signal_processing.py`

#### Observation
- **Class**: `SignalProcessor`
- **Method `process_signal(full_signal: str, stock_symbol: str = None) -> dict`** (lines 19-215):
  * Invokes `quick_thinking_llm` to extract JSON `{ "action": "buy/hold/sell", "target_price": float, "confidence": float, "risk_score": float, "reasoning": str }`.
  * If `target_price` is `None`, `"null"`, or empty in the LLM response, it searches with regex for pricing keywords.
  * If regex fails, lines 176 & 318 call:
    `target_price = self._smart_price_estimation(full_text, action, is_china)`
- **Method `_smart_price_estimation(text: str, action: str, is_china: bool) -> float`** (lines 216-280):
  * Tries to parse current price and percentage change from text.
  * Lines 266-278:
    ```python
    if current_price:
        if action == 'buy':
            multiplier = 1.15 if is_china else 1.12
            return round(current_price * multiplier, 2)
        elif action == 'sell':
            multiplier = 0.95 if is_china else 0.92
            return round(current_price * multiplier, 2)
        else:  # hold
            return current_price
    ```
  * **Critical Flaw**:
    The multipliers $1.15$ and $0.95$ are completely static and uncalibrated. In a bear regime, projecting a $+15\%$ bounce on a buy signal is overly optimistic; in a sideways regime, a $15\%$ move is unrealistic noise.
  * **Integration Point**:
    In `tradingagents/graph/trading_graph.py:1392`, `decision = self.process_signal(final_state["final_trade_decision"], company_name)` is invoked where `final_state` contains `analyst_posteriors` (produced by R1). Currently, `final_state` is NOT passed into `process_signal()`.

---

## 3. Architecture & Implementation Design for R2

### 3.1 `RegimeAdaptiveWeightCalculator` Design

#### Class Structure & Regimes
`RegimeAdaptiveWeightCalculator` will reside in `core/agents/utils/weight_calculator.py` and be exported in `core/agents/utils/__init__.py`.
It maintains a persistent 2D weight structure:
$$w[\text{regime}][\text{analyst\_id}]$$
where $\text{regime} \in \{\text{"bull"}, \text{"bear"}, \text{"sideways"}\}$.

Supported analyst IDs:
- `"index_analyst_v2"`
- `"sector_analyst_v2"`
- `"market_analyst_v2"`
- `"fundamentals_analyst_v2"`
- `"news_analyst_v2"`
- `"social_analyst_v2"`
- `"chip_distribution_analyst_v2"`
*(Also maps seamlessly to legacy report keys: `"market_report"`, `"news_report"`, `"sentiment_report"`, `"fundamentals_report"`, `"sector_report"`, `"index_report"`, `"chip_distribution_report"`).*

#### Initial Weight Distribution
For each regime $r$, initialize weights uniformly across active analysts:
$$w_0[r][i] = \frac{1}{N}$$
where $N$ is the number of active analysts (e.g., $1/7 \approx 0.1428$).
Optionally, financial domain priors can seed the initial state:
- **Bull**: Higher prior on `market_analyst_v2` (momentum), `social_analyst_v2` (sentiment), and `chip_distribution_analyst_v2` (capital flow).
- **Bear**: Higher prior on `fundamentals_analyst_v2` (defensive balance sheet) and `index_analyst_v2` (macro risk).
- **Sideways**: Higher prior on `sector_analyst_v2` (sector rotation) and `fundamentals_analyst_v2` (stock picking).

#### Multiclass Brier Loss
In R1, each analyst outputs a 3-class probability distribution:
$$p_i = \left[ p_{i, \text{optimistic}}, \, p_{i, \text{neutral}}, \, p_{i, \text{cautious}} \right], \quad \text{with } \sum_{k=1}^3 p_{i, k} = 1.0$$

Given the realized return $R_{\text{realized}}$ over the evaluation period:
Define a neutral deadband threshold $\tau = 0.005$ (50 bps, configurable):
- If $R_{\text{realized}} > \tau$: Realized class is **Optimistic**, $y = [1, 0, 0]$
- If $R_{\text{realized}} < -\tau$: Realized class is **Cautious**, $y = [0, 0, 1]$
- If $-\tau \le R_{\text{realized}} \le \tau$: Realized class is **Neutral**, $y = [0, 1, 0]$

The multiclass Brier loss for analyst $i$ is:
$$\text{BrierLoss}_i = \sum_{k=1}^3 \left( p_{i, k} - y_k \right)^2 \in [0, 2]$$
- If an analyst assigned probability $1.0$ to optimistic when the market was optimistic: $\text{BrierLoss} = (1-1)^2 + 0 + 0 = 0.0$ (Perfect).
- If an analyst assigned probability $1.0$ to optimistic when the market crashed (cautious): $\text{BrierLoss} = (1-0)^2 + 0 + (0-1)^2 = 2.0$ (Maximum penalty).

#### Multiplicative Weights Update (MWU) / Exponentially Weighted Forecaster
For the current regime $r$:
$$w_{\text{new}}[r][i] = w_{\text{old}}[r][i] \cdot \exp\left( -\eta \cdot \text{BrierLoss}_i \right)$$
where $\eta = \text{learning\_rate}$ (default $0.2$).

Normalize across all active analysts in regime $r$:
$$w_{\text{new}}[r][i] \leftarrow \frac{w_{\text{new}}[r][i]}{\sum_{j \in \mathcal{A}} w_{\text{new}}[r][j]}$$
This guarantees $\sum_{i \in \mathcal{A}} w_{\text{new}}[r][i] = 1.0$ and strictly bounds weight degradation without allowing negative weights.

#### API Interface & Fallback
```python
class RegimeAdaptiveWeightCalculator:
    def __init__(self, learning_rate: float = 0.2, return_threshold: float = 0.005):
        self.learning_rate = learning_rate
        self.return_threshold = return_threshold
        self.regimes = ["bull", "bear", "sideways"]
        self.analyst_ids = [
            "index_analyst_v2", "sector_analyst_v2", "market_analyst_v2",
            "fundamentals_analyst_v2", "news_analyst_v2", "social_analyst_v2",
            "chip_distribution_analyst_v2"
        ]
        self.weights: Dict[str, Dict[str, float]] = {
            regime: {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}
            for regime in self.regimes
        }

    def get_weights(self, regime: str, active_analysts: Optional[List[str]] = None) -> Dict[str, float]:
        regime = self._normalize_regime(regime)
        active = active_analysts or self.analyst_ids
        sub_weights = {aid: self.weights[regime].get(aid, 1.0 / len(active)) for aid in active}
        total = sum(sub_weights.values())
        return {aid: w / total for aid, w in sub_weights.items()} if total > 0 else calculate_report_weights({})

    def update_weights(
        self,
        regime: str,
        analyst_posteriors: Dict[str, Dict[str, Any]],
        realized_return: float,
        learning_rate: Optional[float] = None,
    ) -> Dict[str, float]:
        regime = self._normalize_regime(regime)
        lr = learning_rate if learning_rate is not None else self.learning_rate
        ...
```
- **Fallback**: Existing `calculate_report_weights(reports, trading_style)` is 100% preserved as a standalone function and as a fallback in `RegimeAdaptiveWeightCalculator`.

---

### 3.2 Calibrated Signal Processing in `SignalProcessor`

#### Bayesian Log-Odds Aggregation
Instead of the ad-hoc $1.15$ / $0.95$ multipliers, we perform regime-calibrated Bayesian aggregation of the analyst posteriors:

1. **Regime Prior Log-Odds**:
   Prior probability of an upward move $P_0(H_+)$:
   - Bull: $P_0 = 0.60 \implies L_0 = \ln(0.60 / 0.40) \approx +0.405$
   - Sideways: $P_0 = 0.50 \implies L_0 = \ln(0.50 / 0.50) = 0.0$
   - Bear: $P_0 = 0.40 \implies L_0 = \ln(0.40 / 0.60) \approx -0.405$

2. **Analyst Log-Odds Evidence**:
   Each analyst $i$ provides $p_{i, \text{opt}}$ and $p_{i, \text{caut}}$. The analyst's directional log-odds is:
   $$\ell_i = \ln \left( \frac{\max(p_{i, \text{opt}}, \epsilon)}{\max(p_{i, \text{caut}}, \epsilon)} \right), \quad \epsilon = 10^{-4}$$
   Using weights $w_i = w[r][i]$ from `RegimeAdaptiveWeightCalculator`:
   $$L_{\text{agg}} = L_0 + \sum_{i \in \mathcal{A}} w_i \cdot \ell_i$$

3. **Calibrated Directional Probability**:
   $$P_{\text{agg}}(H_+) = \sigma(L_{\text{agg}}) = \frac{1}{1 + e^{-L_{\text{agg}}}}$$

4. **Weighted Expected Move & Target Price Estimation**:
   Analyst $i$ predicts $\Delta_{i, \text{bps}} = \text{expected\_move\_bps}$.
   $$\bar{\Delta}_{\text{bps}} = \sum_{i \in \mathcal{A}} w_i \cdot \Delta_{i, \text{bps}}$$
   The calibrated return target is:
   $$\hat{r} = (2 \cdot P_{\text{agg}}(H_+) - 1) \cdot \frac{|\bar{\Delta}_{\text{bps}}|}{10\,000}$$
   Target price calculation based on `action`:
   - If `action == "buy"`:
     $$\text{target\_price} = \text{round}\left( \text{current\_price} \times \left(1 + \max(\hat{r}, 0.01)\right), \, 2 \right)$$
   - If `action == "sell"`:
     $$\text{target\_price} = \text{round}\left( \text{current\_price} \times \left(1 - \max(|\hat{r}|, 0.01)\right), \, 2 \right)$$
   - If `action == "hold"`:
     $$\text{target\_price} = \text{current\_price}$$

5. **Backward-Compatibility Fallback**:
   If `state` is not provided, or `state.get("analyst_posteriors")` is empty, `_smart_price_estimation()` falls back to the original:
   `multiplier = 1.15 if is_china else 1.12` for buy, `0.95 if is_china else 0.92` for sell.

---

## 4. Investigation of R3: Target Files & Current Code State

### 4.1 `core/memory/memory_manager.py`

#### Observation
- **`Mem0AgentMemory` (lines 76-193)**:
  * Adapter connecting the v2 AgentMemory interface (`add_memory`, `search_memories`) to `MemoryService` (mem0).
  * `_normalize_store_metadata(metadata)` (lines 87-97):
    ```python
    @staticmethod
    def _normalize_store_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(metadata or {})
        ticker = str(merged.get("ticker") or merged.get("symbol") or "").strip().upper()
        if ticker:
            merged["ticker"] = ticker
            merged.setdefault("symbol", ticker)
            merged.setdefault("object_type", "stock")
            merged.setdefault("object_key", ticker)
        merged.setdefault("source", "legacy_agent_memory_runtime")
        return merged
    ```
    *No enforcement of `"market_regime"`, `"volatility_quintile"`, or `"brier_calibration_error"`.*
  * `_normalize_recall_filters(filter_metadata)` (lines 99-108):
    Only checks `ticker` and `symbol`.
  * `search_memories(query, n_results=5, filter_metadata=None)` (lines 139-185):
    Recalls memories across `self.agent_ids` via `svc.recall(...)`.
    *No regime circuit-breaker: memories from bull runs are recalled during bear markets without filtering.*
  * `_AGENT_ID_ALIAS_MAPPING` (lines 30-41):
    Contains exact mappings for:
    - `"bull_researcher"` / `"bull_researcher_v2"`
    - `"bear_researcher"` / `"bear_researcher_v2"`
    - `"research_manager"` / `"research_manager_v2"`
    - `"trader"` / `"trader_v2"`
    - `"risk_manager"` / `"risk_manager_v2"`

### 4.2 `tradingagents/graph/reflection.py`

#### Observation
- **`Reflector` (lines 11-127)**:
  * Generates LLM reflections on past trades and stores them in agent memory collections.
  * In lines 63-76:
    ```python
    def _reflect_on_component(self, component_type: str, report: str, situation: str, returns_losses) -> str:
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]
        result = self.quick_thinking_llm.invoke(messages).content
        return result
    ```
  * In `reflect_bull_researcher`, `reflect_bear_researcher`, `reflect_trader`, `reflect_invest_judge`, `reflect_risk_manager` (lines 78-126):
    The exact same scalar `returns_losses` (e.g., `-0.04` or `+0.05`) is passed to all 5 agents identically.
  * **Critical Flaw (Credit Assignment Problem)**:
    If a trade lost $-4\%$, but the Bear Researcher correctly identified severe downside risk and argued for a SELL, the Bear Researcher is told `Returns: -0.04` in the prompt without acknowledging that their thesis was right and was overridden by the manager!

### 4.3 `core/agents/reflection_helper.py` & `core/agents/reflection_prompts.py`

#### Observation
- **`core/agents/reflection_helper.py`**:
  * Provides `run_reflection_sync()` and `run_reflection()` to distill lessons into JSON via LLM and write to mem0 (`infer=False, memory_kind="xxx_lesson"`).
  * Provides `recall_lessons_sync()` to fetch lessons for prompt injection.
- **`core/agents/reflection_prompts.py`**:
  * Centralizes prompts: `TRADE_REFLECTION_SYSTEM_PROMPT`, `ANALYSIS_REFLECTION_SYSTEM_PROMPT`, `DEBATE_REFLECTION_SYSTEM_PROMPT`.
  * `build_debate_reflection_user_prompt(ticker, debate_history, conclusion, debate_type)`:
    Takes `debate_history` and `conclusion`. Currently does not accept or inject counterfactual attribution scores.

---

## 5. Architecture & Implementation Design for R3

### 5.1 Mandatory Metadata Keys in `Mem0AgentMemory`

In `core/memory/memory_manager.py`, modify `_normalize_store_metadata()` and `_normalize_recall_filters()` to enforce three mandatory metadata keys:

1. **`"market_regime"`**: `"bull"` | `"bear"` | `"sideways"`
   - Validation: Convert to lowercase string. If value $\notin \{"bull", "bear", "sideways"\}$, default to `"sideways"`.
2. **`"volatility_quintile"`**: `int` (1 to 5)
   - Validation: Coerce to integer, clamped to $[1, 5]$. If missing or invalid, default to $3$ (median volatility).
3. **`"brier_calibration_error"`**: `float`
   - Validation: Coerce to float, clamped to $\ge 0.0$. If missing or invalid, default to $0.0$.

#### Implementation in `Mem0AgentMemory`:
```python
@staticmethod
def _normalize_store_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(metadata or {})
    ticker = str(merged.get("ticker") or merged.get("symbol") or "").strip().upper()
    if ticker:
        merged["ticker"] = ticker
        merged.setdefault("symbol", ticker)
        merged.setdefault("object_type", "stock")
        merged.setdefault("object_key", ticker)
    merged.setdefault("source", "legacy_agent_memory_runtime")

    # Enforce mandatory R3 metadata keys
    regime = str(merged.get("market_regime") or "sideways").strip().lower()
    merged["market_regime"] = regime if regime in {"bull", "bear", "sideways"} else "sideways"

    try:
        vol = int(merged.get("volatility_quintile", 3))
        merged["volatility_quintile"] = max(1, min(5, vol))
    except (ValueError, TypeError):
        merged["volatility_quintile"] = 3

    try:
        brier = float(merged.get("brier_calibration_error", 0.0))
        merged["brier_calibration_error"] = max(0.0, brier)
    except (ValueError, TypeError):
        merged["brier_calibration_error"] = 0.0

    return merged
```

---

### 5.2 Regime Circuit-Breaker on Memory Retrieval

#### Target Agents
The regime circuit-breaker applies when querying memory for:
$$\mathcal{S}_{\text{circuit}} = \{ \text{"bull\_researcher\_v2"}, \, \text{"bear\_researcher\_v2"}, \, \text{"research\_manager\_v2"}, \, \text{"trader\_v2"}, \, \text{"risk\_manager\_v2"} \}$$
*(along with their v1 aliases: `"bull_researcher"`, `"bear_researcher"`, `"research_manager"`, `"trader"`, `"risk_manager"`).*

#### Circuit-Breaker Logic
When `search_memories()` is invoked for an agent in $\mathcal{S}_{\text{circuit}}$:
1. Determine `current_regime` and `regime_confidence`:
   - Extract from `filter_metadata` (`"market_regime"` or `"current_regime"`, and `"regime_confidence"`).
   - If not specified, default `regime_confidence = 1.0` (active) or accept as method arguments.
2. **Circuit Condition**:
   - If `regime_confidence >= 0.5`:
     **CIRCUIT ACTIVE**: Filter out any candidate memory whose stored `market_regime` contradicts `current_regime`:
     $$\text{Keep memory } m \iff m.\text{metadata.get}("market\_regime") == \text{current\_regime}$$
     *(Prevents bullish dip-buying memories from contaminating a high-confidence bear market crash).*
   - If `regime_confidence < 0.5`:
     **CIRCUIT BYPASSED**: Allow all memories regardless of stored regime. Under regime uncertainty (e.g. choppy consolidation or early market transition), cross-regime memory diversity provides essential hedging insights.
3. Candidate Retrieval Budget:
   When circuit-breaking is active, increase the initial vector recall limit ($3 \times n\_results$) to ensure that after filtering contradicting regime entries, the returned set still satisfies $n\_results$.

---

### 5.3 Counterfactual Credit Assignment & Attribution Injection

#### The MARL Credit Assignment Problem
Uniform broadcast of scalar $R_{\text{realized}}$ to all agents leads to:
1. **False Blame**: A Bear researcher whose warnings were ignored is told they caused a $-5\%$ loss.
2. **False Credit**: A Bull researcher who advocated BUY right before a market drop takes unearned credit if the manager intervened with a protective SELL hedge.

#### Mathematical Formulation of Marginal Contribution
Let:
- $R \in \mathbb{R}$: Realized return of the executed trade.
- $y_{\text{sign}} = \text{sign}(R) \in \{+1, 0, -1\}$.
- $d_a \in [-1, 1]$: Directional stance of agent $a$.
  * Bull Researcher: $d_{\text{bull}} = +1.0$ (or $p_{\text{opt}} - p_{\text{caut}}$).
  * Bear Researcher: $d_{\text{bear}} = -1.0$ (or $p_{\text{opt}} - p_{\text{caut}}$).
  * Trader / Judge / Risk Manager: $d_a \in \{+1, 0, -1\}$ matching recommended action (buy $= +1$, sell $= -1$, hold $= 0$).
- $M \in \{+1, 0, -1\}$: Manager's final executed action.
- $\text{followed}_a = \begin{cases} +1 & \text{if } \text{sign}(d_a) == M \\ -1 & \text{if } \text{sign}(d_a) \neq M \end{cases}$

#### 4-Quadrant Counterfactual Attribution Matrix
We calculate the agent-specific attribution score $C_a \in [-1.0, 1.0]$:

| Quadrant | Condition | Status | Attribution Score $C_a$ | Reflection Prompt Instruction |
|---|---|---|---|---|
| **Q1** | $d_a \cdot y_{\text{sign}} > 0$ and $\text{followed}_a = +1$ | **Vindicated & Followed** | $+|R| \cdot \text{conf}_a$ | "Your thesis was correct and adopted by the manager, driving positive alpha. Reinforce your key predictive signals." |
| **Q2** | $d_a \cdot y_{\text{sign}} > 0$ and $\text{followed}_a = -1$ | **Vindicated & Overridden** | $+|R|$ (Counterfactual Alpha) | "Your analysis correctly predicted market direction, but the manager overruled you. Highlight the specific signals that were dismissed." |
| **Q3** | $d_a \cdot y_{\text{sign}} < 0$ and $\text{followed}_a = +1$ | **Faulty & Followed** | $-|R| \cdot \text{conf}_a$ | "Your thesis proved incorrect and was followed by the manager, directly causing the loss. Identify the blind spots and failed assumptions in your model." |
| **Q4** | $d_a \cdot y_{\text{sign}} < 0$ and $\text{followed}_a = -1$ | **Faulty & Overridden** | $-0.2 \cdot |R|$ (Mitigated Fault) | "Your thesis was incorrect, but the manager successfully shielded the portfolio by overriding you. Review why your scenario misjudged the risk." |

#### Prompt Injection in `tradingagents/graph/reflection.py`
In `_reflect_on_component()`:
Replace:
```python
f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}"
```
With the counterfactual attribution block:
```python
attribution_prompt = (
    f"=== Trade Outcome & Counterfactual Credit Assignment ===\n"
    f"- Realized Trade Return: {realized_return:+.2%}\n"
    f"- Agent Role / Stance: {component_type} ({agent_stance})\n"
    f"- Manager Decision: {manager_action} (Status: {followed_status})\n"
    f"- Counterfactual Attribution Score: {attribution_score:+.3f} [{quadrant_name}]\n"
    f"- Evaluation Directive: {quadrant_directive}\n\n"
    f"=== Agent Analysis / Decision under Review ===\n{report}\n\n"
    f"=== Objective Market Reports for Reference ===\n{situation}"
)
```

And in `core/agents/reflection_prompts.py`:
Update `build_debate_reflection_user_prompt` to accept `attribution_context: Optional[Dict[str, Any]] = None` and format the attribution score and quadrant verdict into the prompt.

---

## 6. Interaction Matrix & Cross-Cutting Integration

The following diagram illustrates how R1, R2, and R3 interlock:

```
+-----------------------------------------------------------------------------------+
| R1: Analyst Posteriors                                                            |
| p_opt, p_neu, p_caut, expected_move_bps, confidence, market_regime                 |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| R2: RegimeAdaptiveWeightCalculator & Calibrated Signal Processing                 |
| 1. Weights w[regime][analyst] updated via MWU with multiclass Brier loss          |
| 2. Bayesian log-odds pooling: L_agg = L_0(regime) + sum(w_i * log_odds_i)        |
| 3. Target price calibrated by sigmoid(L_agg) and weighted expected_move_bps       |
+-------------------+------------------------------------+--------------------------+
                    |                                    |
     Brier Loss     |                                    | Target Price & Action
                    v                                    v
+-------------------+--------------------+  +------------+--------------------------+
| R3: Episodic Memory Filtering          |  | R3: Counterfactual Credit Assignment  |
| - Store metadata:                      |  | - Evaluates agent stance vs outcome   |
|   market_regime, volatility_quintile,  |  | - Evaluates manager follow vs override|
|   brier_calibration_error              |  | - 4-Quadrant Attribution Score        |
| - Recall Circuit-Breaker:              |  | - Injected into Reflector prompt      |
|   confidence >= 0.5 -> filter contra-  |  |   to eliminate uniform scalar bias    |
|   regime memories; < 0.5 -> bypass     |  |                                       |
+----------------------------------------+  +---------------------------------------+
```

---

## 7. Actionable Implementation Blueprint

### 7.1 Target File Changes Summary

| File Path | Modifications Required | Backward Compatibility Guarantee |
|---|---|---|
| `core/agents/utils/weight_calculator.py` | Implement `RegimeAdaptiveWeightCalculator`. Add multiclass Brier loss computation and MWU update rule. | Keep `calculate_report_weights()` intact and use as fallback. |
| `core/agents/utils/__init__.py` | Export `RegimeAdaptiveWeightCalculator`. | Existing imports continue to work unchanged. |
| `tradingagents/graph/signal_processing.py` | Update `process_signal()` and `_smart_price_estimation()` to accept `state` / `analyst_posteriors`. Implement Bayesian log-odds aggregation. | If `state` lacks posteriors, fall back to $1.15$ / $0.95$ multipliers. |
| `core/memory/memory_manager.py` | Update `Mem0AgentMemory._normalize_store_metadata()` and `_normalize_recall_filters()` to validate mandatory keys. Implement regime circuit breaker in `search_memories()`. | If metadata keys are missing, supply safe defaults (`"sideways"`, $3$, $0.0$). Unaffected agents are not filtered. |
| `tradingagents/graph/reflection.py` | Calculate marginal contribution scores (Q1-Q4) in `reflect_and_remember()`. Inject attribution blocks into `_reflect_on_component()`. | If state lacks debate stances, fall back to uniform `Returns: {returns_losses}`. |
| `core/agents/reflection_prompts.py` | Extend prompt builders to accept attribution metrics. | Calling without attribution metrics produces original prompt. |

### 7.2 Verification Commands
To be run after implementation:
```bash
# 1. Existing signal processor and memory tests
.venv/bin/pytest tests/test_signal_processor_fix.py tests/test_target_price.py tests/core/agents/test_researcher_memory.py

# 2. Dedicated unit tests for R2 & R3 (once created by implementation agents)
.venv/bin/pytest tests/test_care_agents_ablation.py
```
