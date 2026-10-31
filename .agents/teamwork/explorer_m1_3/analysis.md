# Analysis Report: Milestone 1 Test Suite Coverage, Boundary Analysis & CBS Gating Integration

**Agent**: Explorer 3 (`teamwork_explorer_m1_3`)  
**Target Milestone**: Milestone 1 (Structured Posteriors & CBS-Gated Dynamic Coordination)  
**Date**: 2026-10-30  
**Repository Working Directory**: `/home/bramy/Documents/TradingAgents-EN`  
**Execution Environment**: Python 3.10.21, pytest 9.2.0 (`/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest`)  

---

## 1. Executive Summary

Milestone 1 introduces the **CBS-Gated Dynamic Coordination** subsystem (Contribution C1) of CARE-Agents. This subsystem extracts structured 3-class directional posteriors $(p_{\text{opt}}, p_{\text{neu}}, p_{\text{cau}})$ from all specialist analysts, quantifies epistemic disagreement using base-2 Jensen-Shannon Divergence ($D_{JS}$), and evaluates the **Coordination Breakeven Spread ($\text{CBS}$)** against market transaction friction $s_t$. When expected signal improvement fails to exceed friction ($D_{JS} < \tau_{JS} = 0.12$ or $\text{CBS} \le s_t = 15.0$ bps), the graph router bypasses multi-round debate in favor of a single-pass tripartite fast path (`RiskSelfDebateV2`).

This analysis evaluates:
1. The **existing test baseline**: `tests/test_analyst_posteriors_cbs.py` (38 tests, 100% passing in 16.35s).
2. The **canonical acceptance test suite**: `tests/test_cbs_debate_gating.py` required by `ORIGINAL_REQUEST.md` and `PROJECT.md`.
3. The **exact mathematical boundary conditions** ($D_{JS} = 0.0$ and $D_{JS} = 1.0$), threshold boundary behaviors ($\tau_{JS} = 0.12, s_t = 15.0$ bps), and dynamic round scaling (1 to 3 rounds).
4. The **interface contract requirements and public function aliases** that Worker M1 must expose (`compute_jensen_shannon_divergence`, `compute_cbs_bps`, `should_gate_debate`, `extract_structured_posterior`).
5. A comprehensive **zero-regression plan** ensuring existing tests across all test suites remain 100% passing.

---

## 2. Investigation of Existing Test Baseline: `tests/test_analyst_posteriors_cbs.py`

### 2.1 Baseline Execution Status
Executing the existing suite under the project virtual environment:
```bash
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_analyst_posteriors_cbs.py -v
```
**Result**: `38 passed, 19 warnings in 16.35s` (Exit Code: 0).

### 2.2 Inventory of Existing 38 Tests by Class

| Suite Class | Lines | Test Count | Features Covered | Key Assertions / Invariants |
|-------------|:-----:|:----------:|------------------|-----------------------------|
| `TestAnalystResponseParsing` | 59–262 | 11 | F1, F2 | Probability simplex $\sum p = 1.0 \pm 10^{-4}$, percentage string conversion (`70% -> 0.70`), negative value clamping to 0.0, fallback on unstructured text and truncated JSON, move string parsing (`+150 bps`, `-1.0%`), regime normalization (`BULL -> bull`, `range-bound -> sideways`). |
| `TestV2AnalystAdapters` | 266–424 | 9 | F1, F2, F4 | Inheritance from `AnalystAgent` for all 7 specialist adapters (`IndexAnalystV2`, `SectorAnalystV2`, `MarketAnalystV2`, `FundamentalsAnalystAgentV2`, `NewsAnalystV2`, `SocialMediaAnalystV2`, `ChipDistributionAnalystV2`), report extraction without tag leaks, posterior generation on execution, cache-hit and existing report state parsing. |
| `TestJSDAndEntropyPurePython` | 428–484 | 6 | F6, F7 | Base-2 Shannon entropy properties: $H_2([1,0,0]) = 0.0$, $H_2([0.5, 0.5]) = 1.0$, $H_2([1/3, 1/3, 1/3]) = \log_2(3) \approx 1.585$. JSD boundary: identical distributions yield $0.0$, orthogonal yield $1.0$, zero entries numerical stability (no `log2(0)` crash), empty/single analyst yields $0.0$, consensus across all 7 analysts yields $D_{JS} < 0.02$. |
| `TestCBSDebateGating` | 488–568 | 6 | F8, F9 | Fast-path routing when $D_{JS} < 0.12$; fast-path when $D_{JS} \ge 0.12$ but move is 10 bps ($\text{CBS} = 1.9 \le 15.0$ bps); debate path when $D_{JS} \ge 0.12$ and move is 150 bps ($\text{CBS} = 46.5 > 15.0$ bps); opposing bull/bear analyst move magnitudes not canceling out ($|\pm 150| = 150$ bps); dynamic debate rounds setting (2 to 3 rounds); `ConditionalLogic.should_continue_debate` termination at $2 \times \text{rounds}$; module-level gateway setting `state["_risk_self_debate"] = True`. |
| `TestRiskSelfDebateV2FastPath` | 572–632 | 3 | F10 | `RiskSelfDebateV2` metadata input/output registration, prompt construction synthesizing analyst posteriors when `investment_plan` is empty, single-pass execution populating `investment_plan` and `investment_debate_state`. |
| `TestStateSchemaAndConcurrency` | 636–679 | 3 | F3, F5 | `AgentState` annotations include `analyst_posteriors`, `estimated_spread_bps`, `debate_jsd`, `cbs_bps`, `dynamic_debate_rounds`; `WorkflowBuilder` default state schema includes identical annotations; `merge_dict` correctly accumulates parallel writes from all 7 analysts without overwriting keys. |

### 2.3 Existing Challenger & Hardening Suites Baseline
Beyond `test_analyst_posteriors_cbs.py`, the repository contains several related empirical test suites that directly test Milestone 1 mechanisms:
- `tests/test_challenger_m1.py` & `tests/test_challenger_m1_2.py`: **36/36 passed** in 15.96s.
  - Tests 10,000 random simplex Dirichlet samples for JSD bounded in $[0.0, 1.0]$.
  - Tests 7-thread barrier simultaneous concurrent writes to `merge_dict`.
  - Tests exact binary boundaries: $D_{JS} = 0.1199$ vs $0.1201$, $\text{CBS} = 14.99$ vs $15.01$ bps.
  - Tests `should_continue_debate` round stepping (turns $1 \dots 2 \cdot d$).
- `tests/test_tier5_hardening_1.py` & `tests/test_tier5_hardening_2.py`: **74/74 passed** in 3.43s.
- `tests/test_care_agents_ablation.py`: **52/52 passed** in 1.33s.

---

## 3. Detailed Specification for Canonical Acceptance Suite: `tests/test_cbs_debate_gating.py`

### 3.1 Suite Purpose & Role
According to `ORIGINAL_REQUEST.md` (§ Acceptance Criteria) and `PROJECT.md` (§ Milestones M1):
> *"Unit tests in `tests/test_cbs_debate_gating.py` pass, verifying boundary conditions ($D_{JS} = 0$, $D_{JS} = 1$) and dynamic routing switches between multi-round debate and fast-path synthesis based on spread thresholds."*

`tests/test_cbs_debate_gating.py` is the official acceptance test file for Milestone 1. It must provide standalone, zero-network, deterministic verification of Features 1 through 10.

### 3.2 Required Test Cases & Formal Assertions

#### Suite A: Mathematical Disagreement & Boundary Conditions ($D_{JS} = 0$, $D_{JS} = 1$)
1. **Case A1 — Exact Zero Boundary ($D_{JS} = 0.0$) via Consensus**:
   - *Input*: Two or more analysts with identical posterior vectors:
     $p_1 = [0.60, 0.25, 0.15]$, $p_2 = [0.60, 0.25, 0.15]$, $p_3 = [0.60, 0.25, 0.15]$.
   - *Theory*: $M = p_1 \implies H_2(M) = H_2(p_1) \implies D_{JS} = H_2(M) - \frac{1}{N}\sum H_2(p_i) = 0.0$.
   - *Assertions*:
     - `compute_base2_jsd(...) == 0.0`
     - `compute_jensen_shannon_divergence(...) == 0.0`
     - `calculate_base2_jsd(...) == 0.0`
     - $\text{CBS} = 0.0 \text{ bps}$.
     - Dynamic route is strictly `"fast_path"`.

2. **Case A2 — Degenerate Null Boundaries ($D_{JS} = 0.0$)**:
   - *Inputs*:
     - Single analyst: `{"analyst_1": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1}}`
     - Empty posteriors: `{}`
     - `None` posteriors
     - All-zero vectors: `[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]`
     - Uniform priors: all analysts with $[1/3, 1/3, 1/3]$
   - *Assertions*:
     - All evaluate cleanly to $0.0$ without `ZeroDivisionError` or `ValueError`.
     - Routing returns `"fast_path"`.

3. **Case A3 — Exact Orthogonal Boundary ($D_{JS} = 1.0$)**:
   - *Input*: Two mutually disjoint probability vectors with zero support overlap:
     $p_1 = [1.0, 0.0, 0.0]$, $p_2 = [0.0, 1.0, 0.0]$ (or $p_2 = [0.0, 0.0, 1.0]$).
   - *Theory*:
     $M = \frac{1}{2} [1.0, 1.0, 0.0] = [0.5, 0.5, 0.0]$
     $H_2(M) = - (0.5 \log_2 0.5 + 0.5 \log_2 0.5) = - (0.5(-1) + 0.5(-1)) = 1.0$
     $H_2(p_1) = -(1 \log_2 1) = 0.0$, $H_2(p_2) = 0.0$
     $D_{JS} = H_2(M) - \frac{1}{2}(0 + 0) = 1.0$.
   - *Assertions*:
     - `abs(compute_base2_jsd([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]) - 1.0) < 1e-6`
     - `abs(compute_jensen_shannon_divergence(orthogonal_posteriors) - 1.0) < 1e-4`
     - Pure base-2 calculation (natural log $\ln$ would yield $\ln(2) \approx 0.693$, which is a fatal defect).

4. **Case A4 — Three Orthogonal Distributions Clamping**:
   - *Input*: $p_1 = [1, 0, 0]$, $p_2 = [0, 1, 0]$, $p_3 = [0, 0, 1]$.
   - *Theory*: Generalized unnormalized JSD yields $H_2(M) = \log_2(3) \approx 1.585$.
   - *Assertion*: Under the CARE-Agents specification, $D_{JS}$ is strictly clamped via `min(1.0, max(0.0, ...))` to ensure $D_{JS} \in [0.0, 1.0]$. Assertion verifies `D_JS == 1.0`.

5. **Case A5 — Zero-Entry Numerical Stability**:
   - *Input*: Vectors containing exact `0.0` elements, e.g. $[1.0, 0.0, 0.0]$ and $[0.5, 0.5, 0.0]$.
   - *Assertion*: Zero entries must not trigger `math.log2(0)` domain errors; entropy must treat $0 \log_2 0 \equiv 0$.

---

#### Suite B: Dynamic Routing Switches Between Debate & Fast-Path

The routing equation from `plan.md` §3.2 and `PROJECT.md` §1:
$$\text{CBS}(d) = \frac{\Delta p(d)}{2} = \frac{D_{JS} \cdot \bar{m}}{2}$$
$$\text{Route} = \begin{cases} \text{multi\_round\_debate} & \text{if } D_{JS} \ge \tau_{JS} \;(0.12) \;\land\; \text{CBS} > s_t \;(15.0 \text{ bps}) \\ \text{fast\_path} & \text{otherwise} \end{cases}$$

1. **Case B1 — Low Divergence Bypass (Consensus Safe Path)**:
   - Condition: $D_{JS} < 0.12$.
   - Scenario: $D_{JS} = 0.05$, huge move $\bar{m} = 800.0$ bps.
   - Calculation: $\text{CBS} = (0.05 \times 800) / 2 = 20.0 \text{ bps} > 15.0 \text{ bps}$.
   - Assertion: Even though $\text{CBS} > 15.0$, the consensus condition $D_{JS} < 0.12$ forces `route == "fast_path"`, `state["_risk_self_debate"] = True`, `state["dynamic_debate_rounds"] = 0`. Prevents unneeded debate when analysts already agree.

2. **Case B2 — High Divergence, Low Stakes Bypass (Friction Barrier)**:
   - Condition: $D_{JS} \ge 0.12$ but $\text{CBS} \le s_t$.
   - Scenario: $D_{JS} = 0.65$ (severe disagreement), but tiny move $\bar{m} = 20.0$ bps.
   - Calculation: $\text{CBS} = (0.65 \times 20) / 2 = 6.5 \text{ bps} \le 15.0 \text{ bps}$.
   - Assertion: Router returns `"fast_path"`, `state["_risk_self_debate"] = True`. Prevents burning LLM tokens and latency debating a 20 bps move that cannot overcome a 15 bps spread.

3. **Case B3 — High Divergence, High Stakes Trigger (Debate Path)**:
   - Condition: $D_{JS} \ge 0.12$ AND $\text{CBS} > s_t$.
   - Scenario: $D_{JS} = 0.60$, large move $\bar{m} = 150.0$ bps.
   - Calculation: $\text{CBS} = (0.60 \times 150) / 2 = 45.0 \text{ bps} > 15.0 \text{ bps}$.
   - Assertion: Router triggers `"multi_round_debate"`, `dynamic_debate_rounds` in $[1, 3]$, `state["_risk_self_debate"]` is not True.

4. **Case B4 — Exact Threshold Boundary Cutoffs**:
   - $D_{JS}$ boundary around $\tau_{JS} = 0.12$:
     - $D_{JS} = 0.1199$ with $\text{CBS} = 50.0 \text{ bps} \implies \text{fast\_path}$.
     - $D_{JS} = 0.1201$ with $\text{CBS} = 50.0 \text{ bps} \implies \text{multi\_round\_debate}$.
   - $s_t$ boundary around $s_t = 15.0$ bps:
     - $D_{JS} = 0.50$ with $\text{CBS} = 14.99 \text{ bps} \implies \text{fast\_path}$.
     - $D_{JS} = 0.50$ with $\text{CBS} = 15.00 \text{ bps} \implies \text{fast\_path}$ (strict inequality $\text{CBS} > s_t$).
     - $D_{JS} = 0.50$ with $\text{CBS} = 15.01 \text{ bps} \implies \text{multi\_round\_debate}$.

5. **Case B5 — Opposing Move Direction Sign Invariance**:
   - Analyst 1 expects $+150.0$ bps (Bull), Analyst 2 expects $-150.0$ bps (Bear).
   - Assertion: Net expected move magnitude $\bar{m}$ must take absolute value $|\hat{m}_i|$, yielding $\bar{m} = 150.0$ bps rather than arithmetic cancellation to $0.0$ bps.

6. **Case B6 — Dynamic Spread Threshold Adaptability**:
   - Test with non-default spreads, e.g. $s_t = 5.0$ bps (liquid mega-cap ETF) and $s_t = 30.0$ bps (small-cap illiquid).
   - Verify router respects runtime `estimated_spread_bps` from `state`.

---

#### Suite C: Dynamic Scaling of Debate Rounds (1 to 3 Rounds)

The round scaling formula:
$$\text{scaled\_rounds} = 1 + (d_{\max} - 1) \cdot \frac{D_{JS} - \tau_{JS}}{1.0 - \tau_{JS}} = 1 + 2 \cdot \frac{D_{JS} - 0.12}{0.88}$$
$$\text{dynamic\_debate\_rounds} = \text{int}\left(\max\left(1, \min\left(d_{\max}, \text{round}(\text{scaled\_rounds})\right)\right)\right)$$

1. **Case C1 — Low Divergence Scaling**:
   - $D_{JS} \in [0.12, 0.34) \implies \text{dynamic\_debate\_rounds} = 1$.
   - Example: $D_{JS} = 0.20 \implies \text{scaled} = 1 + 2(0.08 / 0.88) = 1.18 \implies 1$ round.

2. **Case C2 — Moderate Divergence Scaling**:
   - $D_{JS} \in [0.34, 0.78) \implies \text{dynamic\_debate\_rounds} = 2$.
   - Example: $D_{JS} = 0.56 \implies \text{scaled} = 1 + 2(0.44 / 0.88) = 2.00 \implies 2$ rounds.

3. **Case C3 — Extreme Divergence Scaling**:
   - $D_{JS} \in [0.78, 1.00] \implies \text{dynamic\_debate\_rounds} = 3$.
   - Example: $D_{JS} = 0.90 \implies \text{scaled} = 1 + 2(0.78 / 0.88) = 2.77 \implies 3$ rounds.
   - Example: $D_{JS} = 1.00 \implies \text{scaled} = 1 + 2(1.00) = 3.00 \implies 3$ rounds.

4. **Case C4 — Debate Termination Stepping via `should_continue_debate`**:
   - In LangGraph, each debate round consists of 2 turns (Bull speech + Bear speech).
   - Total allowed speeches before termination = $2 \times \text{dynamic\_debate\_rounds}$.
   - Verify that when `count < 2 * dynamic_debate_rounds`, debate alternates between `"Bull Researcher"` and `"Bear Researcher"`.
   - Verify that when `count >= 2 * dynamic_debate_rounds`, router terminates to `"Research Manager"`.

---

#### Suite D: Public API Aliases & Contract Verification
`PROJECT.md` § Interface Contracts and Feature Inventory specify key public functions that must be exported:

1. **Case D1 — `compute_jensen_shannon_divergence` Public Function**:
   - Signature: `compute_jensen_shannon_divergence(posteriors: Dict[str, Dict[str, Any]], weights: Optional[Dict[str, float]] = None) -> float`
   - Located in: `tradingagents.graph.conditional_logic`
   - Accepts posteriors dictionary, extracts directional probabilities, supports optional analyst reliability weights $w_i$, computes weighted consensus $\bar{p} = \sum w_i p_i$, and returns base-2 $D_{JS} \in [0.0, 1.0]$.

2. **Case D2 — `compute_cbs_bps` Public Function**:
   - Signature: `compute_cbs_bps(posteriors: Dict[str, Dict[str, Any]], weights: Optional[Dict[str, float]] = None, estimated_spread_bps: float = 15.0) -> float`
   - Located in: `tradingagents.graph.conditional_logic`
   - Returns $\text{CBS} = \frac{D_{JS} \cdot \bar{m}}{2.0}$ as a `float`.

3. **Case D3 — `should_gate_debate` Public Function**:
   - Signature: `should_gate_debate(state: Dict[str, Any]) -> str`
   - Located in: `tradingagents.graph.conditional_logic`
   - Evaluates state, mutates `state["debate_jsd"]`, `state["cbs_bps"]`, `state["dynamic_debate_rounds"]`, sets `state["_risk_self_debate"] = True` on fast path, and returns `"fast_path"` or `"multi_round_debate"`.

4. **Case D4 — `extract_structured_posterior` Public Function & Static Alias**:
   - Signatures:
     - `core.agents.analyst.extract_structured_posterior(report_text: str) -> Dict[str, Any]`
     - `core.agents.analyst.AnalystAgent.extract_structured_posterior(report_text: str) -> Dict[str, Any]`
   - Parses markdown report text, extracts JSON signal block, normalizes simplex $\sum p = 1.0 \pm 10^{-4}$, extracts signed move bps, confidence, and market regime.

5. **Case D5 — `IndexAnalystV2` Top-Level `market_regime` State Propagation**:
   - Signature: `IndexAnalystV2.execute(state) -> Dict[str, Any]`
   - Returns `result["market_regime"]` at top level across all 3 execution paths:
     1. Fresh LLM execution
     2. Cache hit (`_get_cached_index_report`)
     3. Existing report in state (`state["index_report"]`)

---

## 4. Discovered Implementation Gaps for Worker M1

During our investigation of the existing implementation in `tradingagents/graph/conditional_logic.py` and `core/agents/analyst.py`, we identified several missing aliases and functions required by `PROJECT.md`:

| Module | Target Symbol | Current Status | Required Remediation for Worker M1 |
|--------|---------------|----------------|-------------------------------------|
| `tradingagents/graph/conditional_logic.py` | `compute_jensen_shannon_divergence` | Missing (only `compute_base2_jsd` and `calculate_base2_jsd` exist) | Add public function `compute_jensen_shannon_divergence(posteriors, weights=None)` supporting optional reliability weights. |
| `tradingagents/graph/conditional_logic.py` | `compute_cbs_bps` | Missing (only `calculate_cbs_routing` returns CBS in a dict) | Add public function `compute_cbs_bps(posteriors, weights=None, estimated_spread_bps=15.0) -> float`. |
| `tradingagents/graph/conditional_logic.py` | `should_gate_debate` | Missing (only `should_trigger_multi_round_debate` exists) | Add alias `should_gate_debate = should_trigger_multi_round_debate` and expose at module level and on `ConditionalLogic`. |
| `core/agents/analyst.py` | `extract_structured_posterior` (standalone) | Missing | Add module-level public function `extract_structured_posterior(report_text: str) -> Dict[str, Any]`. |
| `core/agents/analyst.py` | `AnalystAgent.extract_structured_posterior` (static) | Missing | Add static method alias `extract_structured_posterior = staticmethod(...)` on `AnalystAgent`. |
| `core/agents/adapters/index_analyst_v2.py` | `market_regime` in `result` | Partial (present in `analyst_posteriors["index_analyst_v2"]`, but not consistently at `result["market_regime"]`) | Ensure `result["market_regime"] = posterior.get("market_regime", "sideways")` is returned across all return branches in `execute()`. |

---

## 5. Zero-Regression Plan Across All Test Suites

To preserve the 100% pass rate across the existing 38 tests in `tests/test_analyst_posteriors_cbs.py` and all companion test suites:

1. **Non-Breaking Aliases**:
   - New functions (`compute_jensen_shannon_divergence`, `compute_cbs_bps`, `should_gate_debate`) must wrap or sit alongside existing functions (`calculate_base2_jsd`, `calculate_cbs_routing`, `should_trigger_multi_round_debate`).
   - Do NOT rename, remove, or modify existing function signatures in `conditional_logic.py`.

2. **Analyst Posteriors Output Contract**:
   - `AnalystAgent._parse_response` and `_normalize_posterior` must retain their exact return keys:
     `{"content", "report", "posterior", "success", "p_optimistic", "p_neutral", "p_cautious", "expected_move_bps", "confidence", "market_regime"}`.
   - `extract_structured_posterior` should extract and return the `posterior` sub-dictionary.

3. **Concurrency Reducer Preservation**:
   - `core/state/reducers.py::merge_dict` must continue to recursively merge dictionaries so parallel analyst executions in LangGraph do not overwrite sister analyst keys.

4. **Independent Test Execution**:
   - `tests/test_cbs_debate_gating.py` and `tests/test_analyst_posteriors_cbs.py` must be completely independent and runnable separately or together in any order.

---

## 6. Verification Commands & Acceptance Checklist for Milestone 1

### 6.1 Test Harness Verification Commands

```bash
# 1. Verify the canonical Milestone 1 Acceptance Suite
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_cbs_debate_gating.py -v

# 2. Verify zero regression across existing 38 tests
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_analyst_posteriors_cbs.py -v

# 3. Verify adversarial challenger suites
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_challenger_m1.py tests/test_challenger_m1_2.py -v

# 4. Run all Milestone 1 verification tests in unified run
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest \
  tests/test_analyst_posteriors_cbs.py \
  tests/test_cbs_debate_gating.py \
  tests/test_challenger_m1.py \
  tests/test_challenger_m1_2.py -v

# 5. Full regression check across downstream tiers
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest \
  tests/test_tier5_hardening_1.py \
  tests/test_tier5_hardening_2.py \
  tests/test_care_agents_ablation.py -q
```

### 6.2 Milestone 1 Acceptance Criteria Checklist

- [ ] **AC 1.1**: Standalone `extract_structured_posterior(report_text)` and static alias `AnalystAgent.extract_structured_posterior` correctly parse markdown and enforce probability simplex $\sum p = 1.0 \pm 10^{-4}$.
- [ ] **AC 1.2**: `IndexAnalystV2.execute()` propagates `market_regime` to top-level state across fresh execution, cache hit, and existing report paths.
- [ ] **AC 1.3**: Base-2 Shannon entropy and JSD satisfy theoretical boundary conditions:
  - $D_{JS} = 0.0$ for identical probability distributions, empty posteriors, and single analyst.
  - $D_{JS} = 1.0$ for orthogonal disjoint probability vectors.
  - $0.0 \le D_{JS} \le 1.0$ strictly for all inputs.
- [ ] **AC 1.4**: Public functions `compute_jensen_shannon_divergence`, `compute_cbs_bps`, and `should_gate_debate` exist and operate correctly in `tradingagents.graph.conditional_logic`.
- [ ] **AC 1.5**: Dynamic debate router switches strictly based on $\tau_{JS} = 0.12$ and $s_t = 15.0$ bps:
  - $D_{JS} < 0.12 \implies \text{fast\_path}$ (`RiskSelfDebateV2`), setting `state["_risk_self_debate"] = True`.
  - $\text{CBS} \le 15.0 \text{ bps} \implies \text{fast\_path}$.
  - $D_{JS} \ge 0.12 \land \text{CBS} > 15.0 \text{ bps} \implies \text{multi\_round\_debate}$.
- [ ] **AC 1.6**: Debate rounds dynamically scale between 1 and 3 rounds based on divergence intensity, and `should_continue_debate` terminates at $2 \times \text{rounds}$.
- [ ] **AC 1.7**: Opposing analyst moves ($+150$ bps and $-150$ bps) preserve absolute move magnitude and do not arithmetically cancel to 0 bps.
- [ ] **AC 1.8**: Zero regression across existing 38 tests in `tests/test_analyst_posteriors_cbs.py` (38/38 PASS).
- [ ] **AC 1.9**: 100% pass rate in canonical acceptance suite `tests/test_cbs_debate_gating.py`.
