# Technical Analysis Report: CARE-Agents Phase 1 & Phase 2 Codebase Survey

**Author:** Teamwork Explorer Survey 1  
**Target:** TradingAgents-EN Codebase for CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Memory)  
**Date:** 2026-10-30  
**Status:** Read-only Investigation Completed  

---

## 1. Executive Summary

This exploration provides a line-level architectural investigation of the `TradingAgents-EN` codebase for **Phase 1** (*Structured Analyst Posteriors & CBS-Gated Dynamic Coordination*) and **Phase 2** (*Online Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing*).

### Core Survey Findings:
1. **Phase 1 Foundations**:
   - The structured JSON probability block requirement (`p_optimistic`, `p_neutral`, `p_cautious`, `expected_move_bps`, `confidence`, `market_regime`) is integrated in `AnalystAgent._build_post_tool_analysis_prompt()` (`core/agents/analyst.py:95-106`).
   - `AnalystAgent._parse_response()` and `_normalize_posterior()` (`core/agents/analyst.py:549-796`) parse, clean, and normalize probability distributions (enforcing $\sum p = 1.0$), with heuristic fallbacks and regex repairs.
   - All 7 v2 analyst adapters inherit from `AnalystAgent` and return `analyst_posteriors` dictionaries.
   - Base-2 Shannon entropy and Jensen-Shannon Divergence ($D_{JS}$) are implemented in pure Python in `tradingagents/graph/conditional_logic.py:10-74`.
   - The Coordination Breakeven Spread ($\text{CBS}$) gating formula and dynamic debate round scaling are implemented in `tradingagents/graph/conditional_logic.py:76-136`.
   - `RiskSelfDebateV2` (`core/agents/adapters/risk_self_debate_v2.py`) provides the 1-shot tripartite fast-path synthesis (`Highly resilient`, `defensive`, `base case`).
2. **Phase 2 Foundations**:
   - `RegimeAdaptiveWeightCalculator` (`core/agents/utils/weight_calculator.py:303-481`) implements regime-partitioned tables (`bull`, `bear`, `sideways`), multiclass Brier loss ($[0, 2]$), and Exponentially Weighted Forecaster multiplicative weight updates ($w \exp(-\eta \ell)$).
   - Bayesian log-odds opinion pooling (`calculate_bayesian_log_odds_target_price` and `compute_bayesian_log_odds_details` in `tradingagents/graph/signal_processing.py:16-173`) derives calibrated target prices using regime prior log-odds and weighted expected moves.
   - `SignalProcessor` (`tradingagents/graph/signal_processing.py:175-639`) integrates Bayesian calibration with fallback to legacy multipliers (1.15x / 0.95x).
3. **Identified Discrepancies & Gaps**:
   - `plan.md` Step 1.1 specifies `extract_structured_posterior(report_text: str) -> Dict[str, Any]` in `core/agents/analyst.py`; currently it exists only as internal methods `_parse_response` and `_normalize_posterior`.
   - `plan.md` Step 1.2 specifies propagating `state["market_regime"]` from `index_analyst_v2`; currently `index_analyst_v2.py` does not output top-level `market_regime` to `state`.
   - `plan.md` Step 1.3/1.4 specify function names `compute_jensen_shannon_divergence`, `compute_cbs_bps`, and `should_gate_debate`; currently `conditional_logic.py` uses `calculate_base2_jsd`, `calculate_cbs_routing`, and `should_trigger_multi_round_debate`.
   - `plan.md` Step 2.1 specifies `RegimeMultiplicativeWeightManager` and Step 2.2 specifies `aggregate_posteriors()`; currently the class is named `RegimeAdaptiveWeightCalculator` and posterior aggregation resides in `signal_processing.py`.
   - The acceptance criteria explicitly target `tests/test_cbs_debate_gating.py` and `tests/test_regime_weight_calculator.py`, but the existing tests are placed in `tests/test_analyst_posteriors_cbs.py` and `tests/test_regime_weights_signal.py`.

---

## 2. Phase 1 Deep Dive: Structured Analyst Posteriors & CBS Debate Routing

### 2.1 `core/agents/analyst.py`: Architecture & Implementation

`AnalystAgent` is the common base class for specialist analysts.

#### Key Line Locations:
- **Default Posterior Prior** (lines 22-29):
  ```python
  DEFAULT_UNINFORMATIVE_POSTERIOR: Dict[str, Any] = {
      "p_optimistic": 0.3333,
      "p_neutral": 0.3334,
      "p_cautious": 0.3333,
      "expected_move_bps": 0.0,
      "confidence": 0.0,
      "market_regime": "sideways",
  }
  ```
- **Post-Tool Analysis Prompt Modification** (lines 95-109):
  Instructs LLM to append a structured JSON block:
  ```
  8. **Structured Probability Assessment (Mandatory)**:
  ```json:signal
  {
    "p_optimistic": <float 0.0 to 1.0, probability of price increase > +50 bps>,
    "p_neutral": <float 0.0 to 1.0, probability of price change in [-50 bps, +50 bps]>,
    "p_cautious": <float 0.0 to 1.0, probability of price decrease < -50 bps>,
    "expected_move_bps": <signed float, expected price change in basis points>,
    "confidence": <float 0.0 to 1.0, confidence score>,
    "market_regime": "<bull | bear | sideways>"
  }
  ```
  Constraints: p_optimistic + p_neutral + p_cautious MUST sum to 1.0.
  ```
- **Execution & State Output** (lines 264-276):
  ```python
  parsed = self._parse_response(report)
  clean_report = parsed.get("report") or parsed.get("content") or report
  posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

  output_key = self.output_field or f"{self.analyst_type}_report"
  result = {
      output_key: clean_report,
      "analyst_posteriors": {
          self.agent_id: posterior
      }
  }
  ```
- **Probability Normalization** (lines 549-650):
  - Validates float types, handles strings with `%` symbols.
  - Automatically rescales percentage-based inputs (e.g. `[70, 20, 10] -> [0.7, 0.2, 0.1]`).
  - Clamps negative values to 0.0, handles zero sum by defaulting to uninformative prior `[0.3333, 0.3334, 0.3333]`.
  - Normalizes so sum equals 1.0 to within $10^{-4}$ tolerance.
  - Parses `expected_move_bps` from string variants (`+150 bps`, `-50bp`, `2.5%`, `80.5`).
  - Normalizes `market_regime` synonyms:
    - `"bull"`, `"bullish"`, `"long"`, `"up"`, `"uptrend"` $\to$ `"bull"`
    - `"bear"`, `"bearish"`, `"short"`, `"down"`, `"downtrend"` $\to$ `"bear"`
    - `"sideways"`, `"neutral"`, `"range"`, `"flat"`, `"consolidation"`, `"chop"` $\to$ `"sideways"`
- **Response Parsing & Signal Extraction** (lines 685-796):
  - Detects signal blocks via multiple delimiter regexes:
    - `<signal_block>...</signal_block>`
    - `<!-- SIGNAL_BLOCK: ... -->`
    - ````json:signal ... ````
    - ````json ... ````
  - Repaired malformed JSON (replaces single quotes, strips trailing commas, handles Python literals `None`, `True`, `False`).
  - Strips the signal block from `clean_report` so report displays clean markdown text without JSON artifacts.
  - Heuristic fallback (`_heuristic_extract_posterior` lines 652-683) when JSON is completely absent.

### 2.2 Specialist V2 Analyst Adapters

The 7 specialist analysts inherit from `AnalystAgent`:
1. `IndexAnalystV2` (`core/agents/adapters/index_analyst_v2.py`) $\to$ `index_report`
2. `SectorAnalystV2` (`core/agents/adapters/sector_analyst_v2.py`) $\to$ `sector_report`
3. `MarketAnalystV2` (`core/agents/adapters/market_analyst_v2.py`) $\to$ `market_report`
4. `FundamentalsAnalystAgentV2` (`core/agents/adapters/fundamentals_analyst_v2.py`) $\to$ `fundamentals_report`
5. `NewsAnalystV2` (`core/agents/adapters/news_analyst_v2.py`) $\to$ `news_report`
6. `SocialMediaAnalystV2` (`core/agents/adapters/social_analyst_v2.py`) $\to$ `sentiment_report`
7. `ChipDistributionAnalystV2` (`core/agents/adapters/chip_distribution_analyst_v2.py`) $\to$ `chip_report`

**Caching Behavior**:
- `IndexAnalystV2` and `SectorAnalystV2` implement cache checks (`_get_cached_index_report`, lines 34-67).
- If cached report hits, `IndexAnalystV2` executes `self._parse_response(cached_report)` and returns both the report and parsed `analyst_posteriors` (lines 280-288).
- If report already exists in `state["index_report"]`, it extracts posteriors and avoids redundant LLM invocation (lines 262-272).

### 2.3 `tradingagents/graph/conditional_logic.py`: JSD & CBS Debate Routing

#### Mathematical Definitions:
1. **Base-2 Shannon Entropy**:
   $$H(p) = -\sum_{c \in \{\text{opt, neu, cau}\}} p_c \log_2(p_c) \quad \text{for } p_c > 0$$
   Implemented in `compute_shannon_entropy` (lines 10-15).
2. **Base-2 Jensen-Shannon Divergence ($D_{JS}$)**:
   Given $N$ analyst probability distributions $p_1, \dots, p_N$ with mixture distribution $\bar{p} = \frac{1}{N}\sum_{i=1}^N p_i$:
   $$D_{JS}(p_1, \dots, p_N) = H(\bar{p}) - \frac{1}{N}\sum_{i=1}^N H(p_i)$$
   Guaranteed properties: $0 \le D_{JS} \le 1.0$ (base-2), $D_{JS} = 0$ for identical distributions, $D_{JS} = 1.0$ for orthogonal distributions.
   Implemented in `compute_base2_jsd` (lines 18-51) and `calculate_base2_jsd` (lines 53-73).
3. **Coordination Breakeven Spread ($\text{CBS}$)**:
   - Expected debate gain: $\Delta p(d) = D_{JS} \cdot \bar{m}$, where $\bar{m} = \frac{\sum w_i |\hat{m}_i|}{\sum w_i}$ is the confidence-weighted price move magnitude.
   - Breakeven spread: $\text{CBS}(d) = \frac{\Delta p(d)}{2}$.
   - Gating condition:
     $$\text{Trigger Multi-Round Debate} \iff D_{JS} \ge \tau_{JS} \ (0.12) \quad \text{and} \quad \text{CBS}(d) > s_t$$
     Where $s_t$ is `estimated_spread_bps` (default 15.0 bps).
   - If either condition fails $\to$ `"fast_path"`.
   - If triggered $\to$ `"multi_round_debate"`, with dynamically scaled debate rounds:
     $$d = \text{round}\left(1 + (\text{max\_rounds} - 1) \cdot \frac{D_{JS} - 0.12}{1.0 - 0.12}\right)$$
   Implemented in `calculate_cbs_routing` (lines 76-136).
4. **Conditional Routing Method**:
   `ConditionalLogic.should_trigger_multi_round_debate(state: AgentState) -> str`:
   - Returns `"fast_path"` or `"multi_round_debate"`.
   - Populates state metadata: `state["debate_jsd"]`, `state["cbs_bps"]`, `state["expected_debate_gain_bps"]`, `state["weighted_expected_move_bps"]`, `state["dynamic_debate_rounds"]`, `state["_max_debate_rounds"]`.
   - When `"fast_path"`: sets `state["_risk_self_debate"] = True`.

### 2.4 `core/agents/adapters/risk_self_debate_v2.py`: Fast-Path Synthesis

- Executes when `state["_risk_self_debate"] = True`.
- Ingests `investment_plan`, `bull_opinion`, `bear_opinion`, all analyst reports, and `analyst_posteriors` (lines 115-135).
- If `investment_plan` is empty (e.g. Bull/Bear debate bypassed by CBS gating), `_build_user_prompt` synthesizes a fast-path consensus summary from `analyst_posteriors` (lines 233-235).
- In a single deep LLM call, produces 3 risk perspectives:
  1. `[Highly resilient scenario perspective]`
  2. `[defensive situational view]`
  3. `[base case view]`
- Populates `investment_plan` and `investment_debate_state` with fast-path records (lines 410-424) so downstream trader and manager agents receive valid state without missing keys.

---

## 3. Phase 2 Deep Dive: Online Multiplicative Weights & Calibrated Signal Processing

### 3.1 `core/agents/utils/weight_calculator.py`: Multiplicative Weights Update

#### 1. Legacy Static Weighting (Backward Compatibility)
- `calculate_report_weights(reports, trading_style)` (lines 11-61):
  - Short-term: `market_report` (40%), `news_report` (30%), `sentiment_report` (30%), others (5-10%).
  - Long-term: `fundamentals_report` (50%), `sector_report` (30%), others (5-10%).
- `format_weighted_reports_prompt(reports, weights)` (lines 213-284):
  - Formats markdown prompt separating reports into `[Important report]` ($\ge 20\%$) and `[Secondary report]` ($< 20\%$).

#### 2. `RegimeAdaptiveWeightCalculator` (Online MWU)
- **Regime Partitioning** (lines 303-350):
  - Regimes: `["bull", "bear", "sideways"]`.
  - Default analysts: 7 v2 analyst IDs.
  - Maintains `self.weights[regime][analyst_id]`, initialized uniformly to $1 / K$ ($1/7 \approx 0.142857$).
- **Multiclass Brier Loss** (lines 387-421):
  - Analyst prediction: $p = (p_{\text{opt}}, p_{\text{neu}}, p_{\text{caut}})$.
  - Realized return $R_{t+1}$ mapped to one-hot ground-truth $y$:
    $$y = \begin{cases} (1, 0, 0) & \text{if } R_{t+1} > \theta \ (50 \text{ bps}) \\ (0, 0, 1) & \text{if } R_{t+1} < -\theta \ (-50 \text{ bps}) \\ (0, 1, 0) & \text{if } |R_{t+1}| \le \theta \ (\text{neutral}) \end{cases}$$
  - Multiclass Brier score:
    $$\ell_{i,t} = \|p_{i,t} - y_{t+1}\|_2^2 = (p_{\text{opt}} - y_1)^2 + (p_{\text{neu}} - y_2)^2 + (p_{\text{caut}} - y_3)^2 \in [0, 2.0]$$
- **Exponentially Weighted Forecaster Update** (lines 423-474):
  $$\tilde{w}_{i, t+1}^{(r)} = w_{i,t}^{(r)} \exp(-\eta \ell_{i,t}), \quad w_{i, t+1}^{(r)} = \frac{\tilde{w}_{i, t+1}^{(r)}}{\sum_{j=1}^K \tilde{w}_{j, t+1}^{(r)}}$$
  - Learning rate $\eta = 0.2$ (default).
  - Regime isolation: updates to `bull` weights never touch `bear` or `sideways` tables.
  - Dynamic analyst expansion: auto-registers newly seen analysts with uniform initial share.

### 3.2 `tradingagents/graph/signal_processing.py`: Calibrated Signal Processing

#### Bayesian Log-Odds Opinion Pooling Formulation
Implemented in `calculate_bayesian_log_odds_target_price` (lines 16-100) and `compute_bayesian_log_odds_details` (lines 102-173):
1. **Regime Prior Log-Odds**:
   $$L_0(\text{bull}) = \ln\left(\frac{0.60}{0.40}\right) \approx +0.405465, \quad L_0(\text{sideways}) = 0.0, \quad L_0(\text{bear}) = \ln\left(\frac{0.40}{0.60}\right) \approx -0.405465$$
2. **Analyst Log-Odds**:
   $$\ell_i = \ln\left(\frac{\max(\epsilon, p_{i, \text{opt}})}{\max(\epsilon, p_{i, \text{caut}})}\right), \quad \epsilon = 10^{-4}$$
3. **Aggregated Log-Odds**:
   $$L_{agg} = L_0 + \sum_{i=1}^K w_i^{(r)} \ell_i$$
4. **Calibrated Probability**:
   $$P_{agg} = \sigma(\text{clip}(L_{agg}, -10, 10)) = \frac{1}{1 + e^{-L_{agg}}}$$
5. **Calibrated Expected Return**:
   $$\overline{m}_{bps} = \frac{\sum w_i \hat{m}_i}{\sum w_i}, \quad R_{cal} = (2 P_{agg} - 1.0) \cdot \frac{|\overline{m}_{bps}|}{10000}$$
6. **Empirical Price Target**:
   $$\text{Target Price} = \begin{cases} P_{curr} \cdot (1.0 + \max(R_{cal}, 0.005)) & \text{if action = buy} \\ P_{curr} \cdot (1.0 - \max(|R_{cal}|, 0.005)) & \text{if action = sell} \\ P_{curr} & \text{if action = hold} \end{cases}$$
7. **SignalProcessor Integration**:
   - `SignalProcessor.process_signal()` (lines 190-422):
     - Extracts structured decision from LLM response.
     - When `analyst_posteriors` are present in `state`, computes Bayesian target price and attaches metrics (`bayesian_target_price`, `p_agg`, `log_odds_agg`, `weighted_move_bps`, `calibrated_return`).
     - In offline mode (`quick_thinking_llm=None`), runs `_extract_simple_decision` with Bayesian calibration.
     - Fallback path (`_smart_price_estimation`, lines 423-522) preserves backward-compatible 1.15x / 0.95x multipliers when posteriors are absent.

---

## 4. State Schema & Concurrency Management

### 4.1 State Definitions
- `tradingagents/agents/utils/agent_states.py:66-113`:
  - `AgentState(MessagesState)` declares:
    ```python
    analyst_posteriors: Annotated[Dict[str, Any], merge_dict]
    estimated_spread_bps: Annotated[float, "Estimated round-trip friction in basis points (default 15.0)"]
    debate_jsd: Annotated[float, "Jensen-Shannon divergence across active analyst posteriors"]
    cbs_bps: Annotated[float, "Coordination Breakeven Spread in basis points"]
    dynamic_debate_rounds: Annotated[int, "Dynamically scaled debate rounds (1 to max_debate_rounds)"]
    ```
- `core/workflow/builder.py:1550-1565`:
  - `WorkflowBuilder._get_default_state_schema()` declares identical fields and adds `_risk_self_debate: Annotated[bool, keep_non_empty]`.

### 4.2 Concurrency Reducer: `merge_dict`
- In `core/state/reducers.py`:
  ```python
  def merge_dict(left: Optional[Dict], right: Optional[Dict]) -> Dict:
      if left is None:
          return right or {}
      if right is None:
          return left or {}
      result = dict(left)
      result.update(right)
      return result
  ```
- Because LangGraph runs analyst nodes in parallel, `merge_dict` allows each analyst to return `{"analyst_posteriors": {self.agent_id: posterior}}` without overwriting peer analysts' posteriors.

---

## 5. Existing Test Suites & Verification Execution

Using the virtual environment Python interpreter (`/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest`), the following test suites were executed:

| Test Suite File | Tests Count | Status | Scope Tested |
| :--- | :--- | :--- | :--- |
| `tests/test_analyst_posteriors_cbs.py` | 38 passed | **PASS** (100%) | Posterior parsing, normalizer, 7 adapters, Base-2 Shannon entropy, JSD properties, CBS gating, dynamic rounds, RiskSelfDebateV2, state concurrency |
| `tests/test_regime_weights_signal.py` | 32 passed | **PASS** (100%) | `RegimeAdaptiveWeightCalculator`, Brier loss, MWU updates, regime isolation, Bayesian log-odds pooling, `SignalProcessor` calibration & fallback |
| `tests/test_care_agents_ablation.py` | 52 passed | **PASS** (100%) | 4-Tier test architecture: feature coverage (F1-F20), boundary analysis, cross-feature interaction, 4-way ablation comparison |
| `tests/test_regime_memory_reflection.py` | 31 passed | **PASS** (100%) | Regime metadata tagging, circuit-breaker filtering, 4-quadrant counterfactual attribution |
| `tests/test_regime_circuit_breaker_stress.py` | 31 passed | **PASS** (100%) | Boundary confidence thresholds, agent whitelisting, zero-leakage defense |
| **Combined Phase 1 & 2 Tests** | **70 passed** | **PASS** | `test_analyst_posteriors_cbs.py` + `test_regime_weights_signal.py` |

---

## 6. Gap Analysis & Proposed Code Modifications

### Gap 1: Standalone `extract_structured_posterior()` in `core/agents/analyst.py`
- **Requirement (`plan.md` Step 1.1)**: Add `extract_structured_posterior(report_text: str) -> Dict[str, Any]` to parse or derive posteriors.
- **Current Status**: Implemented only as instance methods `self._parse_response()` and `self._normalize_posterior()`.
- **Proposed Solution**: Expose a module-level helper function:
  ```python
  def extract_structured_posterior(report_text: str) -> Dict[str, Any]:
      """Public utility function to extract and normalize structured posterior from report text."""
      from core.agents.analyst import AnalystAgent
      # Instantiate or reuse parser logic
      ...
  ```
  And add a `@staticmethod` alias `AnalystAgent.extract_structured_posterior(report_text: str)`.

### Gap 2: Propagating `market_regime` from `IndexAnalystV2`
- **Requirement (`plan.md` Step 1.2)**: `Propagate state["market_regime"] from index_analyst_v2`.
- **Current Status**: In `core/agents/adapters/index_analyst_v2.py`, all return statements (cache hit line 283, existing report line 268, execute line 293) return `{"index_report": ..., "analyst_posteriors": ...}`, omitting top-level `"market_regime"`.
- **Proposed Solution**: In `IndexAnalystV2.execute()`, extract `regime = posterior.get("market_regime", "sideways")` and include `"market_regime": regime` in the returned dictionary.

### Gap 3: Naming Aliases in `tradingagents/graph/conditional_logic.py`
- **Requirement (`plan.md` Steps 1.3 & 1.4)**:
  - `compute_jensen_shannon_divergence(posteriors)`
  - `compute_cbs_bps(posteriors, weights=None)`
  - `should_gate_debate(state)`
- **Current Status**: Currently named `calculate_base2_jsd`, `calculate_cbs_routing`, and `should_trigger_multi_round_debate`.
- **Proposed Solution**: Export explicit aliases at the module level in `tradingagents/graph/conditional_logic.py`:
  ```python
  compute_jensen_shannon_divergence = calculate_base2_jsd
  should_gate_debate = should_trigger_multi_round_debate

  def compute_cbs_bps(posteriors: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> float:
      routing = calculate_cbs_routing(posteriors)
      return routing["cbs_bps"]
  ```

### Gap 4: Class & Method Aliases in `core/agents/utils/weight_calculator.py`
- **Requirement (`plan.md` Steps 2.1 & 2.2)**:
  - Class named `RegimeMultiplicativeWeightManager`
  - Method `aggregate_posteriors()` (logarithmic opinion pool)
  - Weight floor $w_{\min} = 0.03$ (Section 3.3)
- **Current Status**: Class is named `RegimeAdaptiveWeightCalculator`. `aggregate_posteriors()` is not in `weight_calculator.py`. Weight updates do not clamp to $w_{\min} = 0.03$.
- **Proposed Solution**:
  1. Add `RegimeMultiplicativeWeightManager = RegimeAdaptiveWeightCalculator` (or subclass).
  2. Implement `aggregate_posteriors(regime, posteriors, weights)` forwarding to `compute_bayesian_log_odds_details`.
  3. Add `min_weight: float = 0.03` parameter to `update_weights()`.

### Gap 5: Explicit Function `process_calibrated_signal()` in `tradingagents/graph/signal_processing.py`
- **Requirement (`plan.md` Step 2.3)**: Add `process_calibrated_signal()` deriving confidence, risk score, and target prices from calibrated ensemble posteriors.
- **Current Status**: `SignalProcessor.process_signal()` performs calibration if state has posteriors, but no standalone module-level `process_calibrated_signal()` exists.
- **Proposed Solution**: Add module function `process_calibrated_signal(full_signal, stock_symbol, state, quick_thinking_llm=None)` that derives `confidence` and `risk_score` directly from calibrated posterior metrics.

### Gap 6: Acceptance Criteria Test File Alignment
- **Requirement (`ORIGINAL_REQUEST.md` Acceptance Criteria)**:
  - `tests/test_cbs_debate_gating.py`
  - `tests/test_regime_weight_calculator.py`
- **Current Status**: The test implementations exist in `tests/test_analyst_posteriors_cbs.py` and `tests/test_regime_weights_signal.py`.
- **Proposed Solution**: Create dedicated test wrapper/import files `tests/test_cbs_debate_gating.py` and `tests/test_regime_weight_calculator.py` that import the corresponding test classes from existing test suites, ensuring both test filenames pass independently.

---

## 7. Exploration Summary Table

| Module | Current State | Phase 1/2 Requirement | Readiness | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `core/agents/analyst.py` | `_parse_response` and `_normalize_posterior` fully functional | `extract_structured_posterior()` | 95% | Export `extract_structured_posterior` function and staticmethod |
| `core/agents/adapters/index_analyst_v2.py` | Outputs `analyst_posteriors` with `market_regime` inside posterior dict | Propagate top-level `state["market_regime"]` | 90% | Return `"market_regime": posterior.get("market_regime")` in `execute()` |
| `tradingagents/graph/conditional_logic.py` | `calculate_base2_jsd`, `calculate_cbs_routing`, `should_trigger_multi_round_debate` | `compute_jensen_shannon_divergence`, `compute_cbs_bps`, `should_gate_debate` | 95% | Add function aliases for exact plan.md naming |
| `core/agents/adapters/risk_self_debate_v2.py` | Fast-path 3-perspective synthesis, populates `investment_plan` & `investment_debate_state` | Fast-path debate bypass | 100% | Ready, tests pass |
| `core/agents/utils/weight_calculator.py` | `RegimeAdaptiveWeightCalculator`, Brier loss, MWU updates | `RegimeMultiplicativeWeightManager`, `aggregate_posteriors`, floor $w_{\min}=0.03$ | 90% | Add class alias `RegimeMultiplicativeWeightManager`, export `aggregate_posteriors` |
| `tradingagents/graph/signal_processing.py` | `calculate_bayesian_log_odds_target_price`, `SignalProcessor` | `process_calibrated_signal()` deriving confidence & risk score | 95% | Add `process_calibrated_signal()` function |
| `tradingagents/agents/utils/agent_states.py` | `AgentState` has `analyst_posteriors`, `estimated_spread_bps`, `cbs_bps`, `debate_jsd`, `dynamic_debate_rounds` | Structured posteriors & CBS state fields | 100% | Optionally add `market_regime` type annotation |
| `tests/` | `test_analyst_posteriors_cbs.py` (38 pass), `test_regime_weights_signal.py` (32 pass) | Acceptance test filenames | 90% | Provide `test_cbs_debate_gating.py` and `test_regime_weight_calculator.py` entrypoints |
