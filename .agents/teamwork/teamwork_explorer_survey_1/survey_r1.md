# CARE-Agents Architecture & R1 Investigation Survey Report

**Author**: Explorer Survey 1  
**Timestamp**: 2026-10-30T03:45:00Z  
**Target Milestone**: R1 — Structured Probability Distributions & CBS-Gated Dynamic Debate  
**Workspace**: `/home/bramy/Documents/TradingAgents-EN`  

---

## 1. Executive Summary

This investigation analyzed the target files and architectural components required for **R1: Structured Probability Distributions & CBS-Gated Dynamic Debate** in the CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Trading) framework within TradingAgents-EN (v3.0).

Key findings:
1. **Analyst Output & State**: `AnalystAgent._parse_response()` is defined in `core/agents/analyst.py:503` but currently unused by `AnalystAgent.execute()` and subclass adapters. All 7 v2 analysts (`index_analyst_v2`, `sector_analyst_v2`, `market_analyst_v2`, `fundamentals_analyst_v2`, `news_analyst_v2`, `social_analyst_v2`, `chip_distribution_analyst_v2`) currently output raw string reports into their respective `*_report` fields. Backward compatibility requires keeping `state["*_report"]` as `str` while injecting structured posterior probability blocks into `state["analyst_posteriors"][agent_id]`.
2. **LangGraph State Merging**: In `core/workflow/builder.py:1487`, `WorkflowState` uses custom reducers from `core/state/reducers.py`. By defining `analyst_posteriors: Annotated[dict, merge_dict]`, multiple parallel analyst nodes will concurrently merge their posterior distributions into `state["analyst_posteriors"]` without race conditions or overwriting.
3. **CBS & JSD Routing**: `tradingagents/graph/conditional_logic.py` currently handles sequential tool calling and fixed round debate routing (`max_debate_rounds = 1`). A new method `should_trigger_multi_round_debate(state: AgentState) -> str` can compute Jensen-Shannon Divergence ($JSD$) across active analyst posterior vectors, compute the Coordination Breakeven Spread ($CBS_{\text{bps}} = \frac{JSD \times \text{weighted\_expected\_move\_bps}}{2.0}$), compare it against `state.get("estimated_spread_bps", 15.0)`, and dynamically route between single-pass fast-path synthesis and $JSD$-scaled multi-round debate.
4. **Fast-Path Synthesis Connection**: `RiskSelfDebateV2` (`core/agents/adapters/risk_self_debate_v2.py`) already provides a single-node, 3-perspective self-debate mechanism that takes upstream analyst reports directly. When CBS gating triggers fast-path synthesis, bypassing the iterative multi-round bull/bear debate, it directly leverages `RiskSelfDebateV2`, cutting token latency and preventing Degeneration-of-Thought (DoT).
5. **Test Environment**: Python 3.10 virtual environment was established using `uv` with all project and CI dependencies. Existing baseline tests have several pre-existing issues (e.g. `KeyError: '标准'` in `core/api/workflow_api.py:997`, missing imports in `test_analysis_result_normalization.py`), highlighting the need for `tests/test_care_agents_ablation.py` to run fully offline using synthetic fixtures and mocks.

---

## 2. Target Files & State Architecture

### 2.1 File Map

| Component | File Path | Current Role | R1 Modification Scope |
|---|---|---|---|
| **Analyst Base Class** | `core/agents/analyst.py` | Base class for analysts, defines `_parse_response()` and `execute()` | Implement structured signal block extraction in `_parse_response()`, update `execute()` to populate `result["analyst_posteriors"]` |
| **Conditional Logic** | `tradingagents/graph/conditional_logic.py` | Handles tool-loops, debate continuation, and risk discussion routing | Add `should_trigger_multi_round_debate()` with $JSD$, $CBS_{\text{bps}}$, threshold comparison, and dynamic debate rounds |
| **Fast-Path Synthesizer** | `core/agents/adapters/risk_self_debate_v2.py` | Single-node risk self-debate across 3 perspectives | Acts as the fast-path target node; verify compatibility with optional inputs |
| **Classical State** | `tradingagents/agents/utils/agent_states.py` | Defines `AgentState(MessagesState)` | Add `analyst_posteriors` and `estimated_spread_bps` fields |
| **Workflow State** | `core/workflow/builder.py` | Defines `WorkflowState(MessagesState)` and graph compilation | Add `analyst_posteriors: Annotated[dict, merge_dict]` and conditional edges for CBS routing |
| **State Reducers** | `core/state/reducers.py` | Provides `keep_non_empty`, `merge_dict`, `keep_latest_list` | Existing `merge_dict` handles dictionary merging perfectly |

### 2.2 State Schema Requirements

In `tradingagents/agents/utils/agent_states.py`:
```python
class AgentState(MessagesState):
    ...
    # CARE-Agents Extensions
    analyst_posteriors: Annotated[Dict[str, Any], "Posterior probability distributions from analysts"]
    estimated_spread_bps: Annotated[float, "Estimated round-trip spread friction in basis points"]
    jsd: Annotated[float, "Jensen-Shannon Divergence across analyst posteriors"]
    cbs_bps: Annotated[float, "Coordination Breakeven Spread in basis points"]
    dynamic_debate_rounds: Annotated[int, "Dynamic debate rounds scaled by JSD"]
```

In `core/workflow/builder.py` (`WorkflowState` at line 1487):
```python
class WorkflowState(MessagesState):
    ...
    # CARE-Agents Extensions (Concurrent-safe reducers)
    analyst_posteriors: Annotated[dict, merge_dict]
    estimated_spread_bps: Annotated[float, keep_non_empty]
    jsd: Annotated[float, keep_non_empty]
    cbs_bps: Annotated[float, keep_non_empty]
    dynamic_debate_rounds: Annotated[int, keep_non_empty]
```

---

## 3. Detailed Investigation of `core/agents/analyst.py` & V2 Analysts

### 3.1 Current Implementation of `_parse_response()`

In `core/agents/analyst.py` lines 503-517:
```python
def _parse_response(self, response: str) -> Dict[str, Any]:
    """
    Parse LLM response (can be overridden by subclasses)

    Args:
        response: LLM response text

    Returns:
        Parsed report dictionary
    """
    # Default implementation: return text directly
    return {
        "content": response,
        "success": True
    }
```
In `AnalystAgent.execute()` lines 240-245:
```python
output_key = self.output_field or f"{self.analyst_type}_report"
logger.info(f"analyst Agent {self.agent_id} Executed successfully")
result = {output_key: report}
```
Currently, `_parse_response()` is not called inside `execute()`.

### 3.2 Inheritance and Execution across 7 V2 Analysts

| Agent ID | Class Name | File Path | Class Hierarchy | `execute()` Behavior |
|---|---|---|---|---|
| `index_analyst_v2` | `IndexAnalystV2` | `core/agents/adapters/index_analyst_v2.py:114` | `IndexAnalystV2 -> AnalystAgent -> BaseAgent` | Checks cache, then calls `super().execute(state)` at line 280 |
| `sector_analyst_v2` | `SectorAnalystV2` | `core/agents/adapters/sector_analyst_v2.py:166` | `SectorAnalystV2 -> AnalystAgent -> BaseAgent` | Prepares mode, calls `super().execute(state)` at line 311 |
| `market_analyst_v2` | `MarketAnalystV2` | `core/agents/adapters/market_analyst_v2.py:78` | `MarketAnalystV2 -> AnalystAgent -> BaseAgent` | Overrides `execute()`, calls tools/LLM, returns `{self.output_field: report}` at line 224 |
| `fundamentals_analyst_v2` | `FundamentalsAnalystAgentV2` | `core/agents/adapters/fundamentals_analyst_v2.py:30` | `FundamentalsAnalystAgentV2 -> BaseAgent` | Overrides `execute()`, returns `{"fundamentals_report": analysis}` at line 209 (Should inherit `AnalystAgent`) |
| `news_analyst_v2` | `NewsAnalystV2` | `core/agents/adapters/news_analyst_v2.py:29` | `NewsAnalystV2 -> AnalystAgent -> BaseAgent` | Overrides `execute()`, two-stage prefetch, returns `{self.output_field: report}` at line 345 |
| `social_analyst_v2` | `SocialMediaAnalystV2` | `core/agents/adapters/social_analyst_v2.py:29` | `SocialMediaAnalystV2 -> AnalystAgent -> BaseAgent` | Overrides `execute()`, returns `{self.output_field: report}` at line 117 |
| `chip_distribution_analyst_v2` | `ChipDistributionAnalystV2` | `core/agents/adapters/chip_distribution_analyst_v2.py:28` | `ChipDistributionAnalystV2 -> AnalystAgent -> BaseAgent` | Overrides `execute()`, returns `{self.output_field: report}` at line 151 |

### 3.3 Adding Structured Signal Block Parsing Without Breaking Workflows

To preserve 100% backward compatibility:
1. **Report Return Format**: The field `{self.output_field}` (e.g. `market_report`, `news_report`) must remain a `str` containing the markdown analysis.
2. **Prompt Instruction**: Prompt templates instructs the model to append a structured block at the end of the report:
   ```markdown
   ```json:signal
   {
     "p_optimistic": 0.65,
     "p_neutral": 0.25,
     "p_cautious": 0.10,
     "expected_move_bps": 80.0,
     "confidence": 0.85,
     "market_regime": "bull"
   }
   ```
   ```
3. **Structured Parser Implementation**:
   In `AnalystAgent._parse_response(self, response: str) -> Dict[str, Any]`:
   - Extracts JSON matching ````json:signal\s*(\{.*?\})\s*```` or general ````json\s*(\{.*?"p_optimistic".*?\})\s*```` or regex parsing.
   - Strips the signal code block from the markdown report so downstream users get clean markdown text.
   - Deserializes and validates:
     * `p_optimistic + p_neutral + p_cautious == 1.0` (normalizes if float drift occurs: $p_k \leftarrow \frac{p_k}{\sum p_j}$).
     * `expected_move_bps`: float.
     * `confidence`: float clamped to $[0.0, 1.0]$.
     * `market_regime`: string in `{"bull", "bear", "sideways"}`.
   - Robust Fallback: If no signal block is found (e.g. mock output or offline test), heuristically determines sentiment or returns a calibrated neutral distribution:
     `{"p_optimistic": 0.3333, "p_neutral": 0.3334, "p_cautious": 0.3333, "expected_move_bps": 0.0, "confidence": 0.5, "market_regime": "sideways"}`.
   - Return dictionary schema:
     ```python
     {
         "report": clean_markdown_text,
         "content": clean_markdown_text,
         "posterior": signal_dict,
         "success": True
     }
     ```
4. **Execution Flow Integration**:
   In `AnalystAgent.execute()` and all overridden `execute()` methods:
   ```python
   parsed = self._parse_response(report)
   clean_report = parsed.get("report") or report
   posterior = parsed.get("posterior")
   
   result = {self.output_field: clean_report}
   if posterior:
       result["analyst_posteriors"] = {self.agent_id: posterior}
   ```
   Because `WorkflowState` uses `merge_dict` for `analyst_posteriors`, all analysts running in parallel merge their `{agent_id: posterior}` into `state["analyst_posteriors"]`.

---

## 4. Detailed Investigation of `tradingagents/graph/conditional_logic.py`

### 4.1 Existing Routing Methods

`tradingagents/graph/conditional_logic.py:10-315` defines `ConditionalLogic`:
- `should_continue_market`: Routes to `tools_market` or `Msg Clear Market`.
- `should_continue_social`: Routes to `tools_social` or `Msg Clear Social`.
- `should_continue_news`: Routes to `tools_news` or `Msg Clear News`.
- `should_continue_fundamentals`: Routes to `tools_fundamentals` or `Msg Clear Fundamentals`.
- `should_continue_index_analyst`: Routes to `tools_index_analyst` or `Msg Clear Index Analyst`.
- `should_continue_sector_analyst`: Routes to `tools_sector_analyst` or `Msg Clear Sector Analyst`.
- `should_continue_debate`: Counts speeches up to `2 * self.max_debate_rounds`, alternating between `"Bull Researcher"` and `"Bear Researcher"`, then terminating to `"Research Manager"`.
- `should_continue_risk_analysis`: Alternates between `"Risky Analyst"`, `"Safe Analyst"`, and `"Neutral Analyst"` up to `3 * self.max_risk_discuss_rounds`, terminating to `"Risk Judge"`.

### 4.2 Design of `should_trigger_multi_round_debate(state: AgentState) -> str`

#### Mathematical Formulation:
1. **Active Distributions**:
   Extract all posterior dicts $P_1, P_2, \dots, P_N$ from `state.get("analyst_posteriors", {})`.
   Each distribution has probability vector:
   $$P_i = [p_{i,\text{optimistic}}, p_{i,\text{neutral}}, p_{i,\text{cautious}}], \quad \sum_{k=1}^3 P_{i,k} = 1.0$$

2. **Jensen-Shannon Divergence ($JSD$)**:
   If $N < 2$, $JSD = 0.0$.
   If $N \ge 2$:
   Compute the pointwise mean distribution $M$:
   $$M_k = \frac{1}{N} \sum_{i=1}^N P_{i,k}, \quad k \in \{1, 2, 3\}$$
   Compute Kullback-Leibler divergences:
   $$D_{\text{KL}}(P_i \parallel M) = \sum_{k: P_{i,k} > 0} P_{i,k} \log_2 \left( \frac{P_{i,k}}{M_k} \right)$$
   Compute generalized $JSD$:
   $$JSD = \frac{1}{N} \sum_{i=1}^N D_{\text{KL}}(P_i \parallel M)$$
   Bound: $0.0 \le JSD \le 1.0$ (for base 2).

3. **Weighted Expected Move**:
   $$\text{weighted\_expected\_move\_bps} = \frac{\sum_{i=1}^N |p_{i,\text{expected\_move\_bps}}| \cdot p_{i,\text{confidence}}}{\sum_{i=1}^N p_{i,\text{confidence}}}$$
   (If sum of confidences $\le 0$, fallback to simple unweighted average).

4. **Expected Debate Gain & Coordination Breakeven Spread ($CBS$)**:
   $$\text{expected\_debate\_gain\_bps} = JSD \times \text{weighted\_expected\_move\_bps}$$
   $$CBS_{\text{bps}} = \frac{\text{expected\_debate\_gain\_bps}}{2.0}$$

5. **Decision Rule & Dynamic Rounds**:
   Let $\text{friction} = \text{float}(\text{state.get("estimated\_spread\_bps", 15.0)})$.
   - **Condition for Fast-Path**:
     $$\text{If } JSD < 0.12 \quad \text{OR} \quad CBS_{\text{bps}} \le \text{friction}:$$
     Route to Fast-Path synthesis: return `"fast_path"` (or `"RiskSelfDebateV2"`).
   - **Condition for Multi-Round Debate**:
     $$\text{If } JSD \ge 0.12 \quad \text{AND} \quad CBS_{\text{bps}} > \text{friction}:$$
     Route to Multi-Round Debate: return `"multi_round_debate"` (or `"Bull Researcher"`).
     Dynamic rounds calculation (scaled between $1$ and $\text{max\_debate\_rounds}$):
     $$\text{dynamic\_rounds} = \max\left(1, \min\left(\text{max\_debate\_rounds}, \text{round}\left(1 + (\text{max\_debate\_rounds} - 1) \cdot \frac{JSD - 0.12}{1.0 - 0.12}\right)\right)\right)$$

6. **State Mutation**:
   The method updates `state` with:
   - `state["jsd"] = float(JSD)`
   - `state["cbs_bps"] = float(CBS_bps)`
   - `state["expected_debate_gain_bps"] = float(expected_debate_gain_bps)`
   - `state["dynamic_debate_rounds"] = dynamic_rounds`
   - `state["_max_debate_rounds"] = dynamic_rounds`

In `should_continue_debate()`, update:
```python
max_rounds = state.get("dynamic_debate_rounds", state.get("_max_debate_rounds", self.max_debate_rounds))
max_count = 2 * max_rounds
```

---

## 5. Detailed Investigation of `core/agents/adapters/risk_self_debate_v2.py`

### 5.1 Architecture & Single-Pass Synthesis

`RiskSelfDebateV2` is defined in `core/agents/adapters/risk_self_debate_v2.py:93-396`:
- It replaces the 3-agent risk debate triangle (`risky_analyst_v2`, `safe_analyst_v2`, `neutral_analyst_v2` iterating over multiple rounds) with a single node executing 1 LLM call.
- It parses the response into three distinct scenario perspectives:
  * `risky_opinion`: Highly resilient scenario perspective
  * `safe_opinion`: Defensive situational view
  * `neutral_opinion`: Base case view
- It updates `risk_debate_state`:
  * `history`, `risky_history`, `safe_history`, `neutral_history`, `latest_speaker="SelfDebate"`, and `count = count + 3`.

### 5.2 Connection with Fast-Path Conditional Routing

In `core/workflow/builder.py:2718-2763`, conditional routing for `_risk_self_debate` is already implemented:
```python
if state.get("_risk_self_debate"):
    return _self_debate_node  # routes to risk_self_debate_v2
return _first_participant    # routes to risky_analyst_v2
```
When CBS gating triggers fast-path (consensus reached, $JSD < 0.12$ or $CBS_{\text{bps}} \le \text{estimated\_spread\_bps}$):
1. The Bull/Bear debate loop is bypassed, routing directly to `ResearchManager` or `RiskSelfDebateV2`.
2. `RiskSelfDebateV2` takes inputs from `market_report`, `fundamentals_report`, `news_report`, `sentiment_report`, etc., without requiring prior Bull/Bear debate transcripts (`bull_opinion` and `bear_opinion` are marked `required=False` in its metadata).
3. Setting `state["_risk_self_debate"] = True` on fast-path ensures both investment and risk stages execute in single-pass mode, maximizing latency and token efficiency while eliminating Degeneration-of-Thought.

---

## 6. Test Suite Baseline & Verification Status

### 6.1 Virtual Environment & Pytest Execution

- `pytest 9.2.0` and all core dependencies (`langchain`, `pydantic`, `fastapi`, `numpy`, `akshare`, `tushare`, `baostock`, etc.) were installed in `.venv`.
- Verified execution: `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest --version` -> `pytest 9.2.0`.

### 6.2 Existing Test Status & Failures Observed

1. **`tests/test_conditional_logic_config.py`**:
   - `test_conditional_logic_default_params`: **PASSED**
   - `test_conditional_logic_custom_params`: **PASSED**
   - Graph tests (`test_trading_graph_with_level_4_config`, etc.): Attempt live connections to MongoDB/Redis, timing out when services are offline.
2. **`tests/unit/test_parallel_opening.py`**:
   - 8 tests passed, 5 tests failed.
   - Root cause: `core/api/workflow_api.py:997` has `depth_config = depth_mapping.get(research_depth, depth_mapping["标准"])`. The dictionary keys were translated to English (`"Standard"`), but line 997 references the Chinese key `"标准"`, raising `KeyError: '标准'`.
3. **`tests/unit/app/test_analysis_result_normalization.py`**:
   - Collection error: `ImportError: cannot import name 'has_meaningful_result_payload' from 'app.routers.analysis'`.
4. **`tests/tradingagents/core/engine/test_memory_provider.py`**:
   - Failed due to leading whitespace differences in string formatting.
5. **`tests/tradingagents/test_app_cache_toggle.py`**:
   - Failed due to missing legacy attributes (`_get_from_tdx_api`) and missing module `tradingagents.dataflows.app_cache_adapter`.

### 6.3 Implications for CARE-Agents Testing (R4 / Acceptance Criteria)

All tests for CARE-Agents (`tests/test_care_agents_ablation.py` and unit tests for R1-R3) must be:
- 100% offline and deterministic.
- Purely synthetic: use mocked LLM responses and mock data fixtures.
- Independent of local MongoDB/Redis daemons to avoid hanging or timeout failures.

---

## 7. Actionable Implementation Plan for R1

1. **`core/agents/analyst.py`**:
   - Enhance `_build_post_tool_analysis_prompt()` to instruct models to append the structured ````json:signal```` block.
   - Implement `_parse_response(self, response: str) -> Dict[str, Any]` to extract the signal block, validate/normalize probabilities ($p_{\text{opt}} + p_{\text{neu}} + p_{\text{caut}} = 1.0$), and return clean markdown report text along with `posterior`.
   - Update `AnalystAgent.execute()` to populate `result["analyst_posteriors"] = {self.agent_id: posterior}`.
   - Ensure all 7 v2 analyst adapters (`index_analyst_v2`, `sector_analyst_v2`, `market_analyst_v2`, `fundamentals_analyst_v2`, `news_analyst_v2`, `social_analyst_v2`, `chip_distribution_analyst_v2`) call `_parse_response()` and return `analyst_posteriors`.
2. **`tradingagents/agents/utils/agent_states.py` & `core/workflow/builder.py`**:
   - Add `analyst_posteriors: Annotated[dict, merge_dict]` and `estimated_spread_bps: Annotated[float, keep_non_empty]` to `AgentState` and `WorkflowState`.
3. **`tradingagents/graph/conditional_logic.py`**:
   - Implement `should_trigger_multi_round_debate(state: AgentState) -> str` using the exact $JSD$ and $CBS_{\text{bps}}$ equations.
   - Route to `"fast_path"` if $JSD < 0.12$ or $CBS_{\text{bps}} \le \text{estimated\_spread\_bps}$; else route to `"multi_round_debate"`.
   - Compute dynamic rounds and set `state["dynamic_debate_rounds"]` and `state["_max_debate_rounds"]`.
   - Update `should_continue_debate()` to respect `dynamic_debate_rounds`.
4. **Unit Tests**:
   - Create unit tests verifying $JSD$ calculation, $CBS$ calculation, edge cases (identical distributions, orthogonal distributions, zero expected move, missing confidences), and routing decisions.
