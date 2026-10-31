# CARE-Agents Milestone M1 Design Report: Integration, Edge Cases, and Unit Test Suite

**Author**: Explorer M1_3  
**Date**: 2026-10-30  
**Target Files**:
- `core/agents/analyst.py` (`AnalystAgent._parse_response`)
- `tradingagents/graph/conditional_logic.py` (`should_trigger_multi_round_debate`, JSD, CBS, dynamic rounds)
- `core/agents/adapters/risk_self_debate_v2.py` (Fast-path integration)
- `tests/test_conditional_logic_config.py` (Regression verification)
- `tests/test_care_m1_conditional_gate.py` (Proposed unit test suite)

---

## 1. Executive Summary

Milestone M1 introduces Cost-Aware, Regime-Adaptive Multi-Agent Trading (CARE-Agents) gating to TradingAgents-EN:
1. **Analyst Posteriors & Structured Signal Block**: Analyst agents output structured tri-state probability distributions alongside their qualitative markdown reports.
2. **CBS-Gated Dynamic Debate**: The debate routing calculates base-2 Jensen-Shannon Divergence (JSD) and the Coordination Breakeven Spread (CBS). Low divergence ($JSD < 0.12$) or low expected economic gain ($CBS \le \text{spread}$) routes directly to single-pass synthesis (`RiskSelfDebateV2`), saving latency and token cost while avoiding Degeneration-of-Thought. High divergence and gain trigger multi-round debate with dynamic rounds scaled by JSD.

This report addresses the critical engineering challenges:
- **Resilience against noisy/unstructured LLM outputs** (multi-tier regex extraction, JSON repair, clamping, and neutral uninformative fallback).
- **Numerical stability in JSD computation** (handling $P(k) = 0$, $M_{dist}(k) = 0$, $M=1$, $M=0$, without `ZeroDivisionError` or math domain errors).
- **Correct economic formulation of CBS** (preventing directional cancellation between opposing bullish/bearish analysts by using move magnitudes).
- **Dynamic rounds bounds checking and concurrency safety** (storing per-run rounds in `state` to prevent race conditions on graph singletons).
- **Unit test suite design & regression preservation** (full offline determinism and 100% passing tests for `tests/test_conditional_logic_config.py`).

---

## 2. Edge Case Analysis & Robust Parsing Fallback for `AnalystAgent._parse_response`

### 2.1 Failure Modes in Real-World LLM Outputs

When prompting LLMs to return a combined markdown report and JSON signal block, empirical evaluation identifies six failure modes:
1. **Unstructured Markdown-Only**: The LLM omits the JSON block entirely, returning only free-form text.
2. **Syntactically Malformed JSON**:
   - Single quotes instead of double quotes (`{'p_optimistic': 0.6}`).
   - Trailing commas before closing braces (`{"p_optimistic": 0.6,}`).
   - Truncated output caused by token budget exhaustion.
   - Code-fenced markdown without language tag or with unescaped characters.
3. **Probability Normalization Violations**:
   - Probabilities do not sum to $1.0$ (e.g., $0.6 + 0.3 + 0.2 = 1.1$).
   - Output given as percentages ($60, 30, 10$) rather than fractions in $[0.0, 1.0]$.
   - Negative probabilities or values exceeding $1.0$ (e.g., hallucinated $-0.1$ or $1.2$).
   - All probabilities returned as $0.0$.
4. **Non-Standard Field Values**:
   - `expected_move_bps` given as strings with units: `"+75 bps"`, `"-1.5%"`.
   - `market_regime` using non-standard strings: `"bullish"`, `"BULL"`, `"bear market"`, `"range-bound"`, `"volatile"`.
   - `confidence` outside $[0.0, 1.0]$ or non-numeric (`"high"`).
5. **Report Contamination**:
   - Leaving raw unparsed JSON blocks in the user-facing report string `{output_field}`, breaking downstream report renderers or UI components.

### 2.2 Four-Tier Parsing Pipeline

To achieve 100% resilience without crashing the workflow, `AnalystAgent._parse_response` must follow a 4-tier pipeline:

```
Raw LLM Response
      │
      ▼
[Tier 1: Fenced Code Block Extraction] ──(found)──► [Validate & Repair JSON]
      │ (not found)                                           │
      ▼                                                       ▼
[Tier 2: Bare JSON Object Regex] ────────(found)──► [Field Extraction & Normalization]
      │ (not found)                                           │
      ▼                                                       │
[Tier 3: Loose JSON Extractor] ──────────(found)──►           │
      │ (not found)                                           │
      ▼                                                       │
[Tier 4: Neutral Uninformative Prior Fallback]                │
      │                                                       │
      └───────────────────────┬───────────────────────────────┘
                              ▼
           Clean Report Text + Structured Posterior
```

#### Tier 1: Fenced Code Block Extraction
Matches `r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"`. If matched, extracts JSON substring and strips the block from the markdown text to keep the report clean.

#### Tier 2: Bare JSON Object with Key Anchoring
If no fenced block is present, scans for a JSON object containing the signature key `"p_optimistic"`:
`r"\{[^{}]*(?:\"p_optimistic\"|'p_optimistic')[^{}]*\}"`.

#### Tier 3: Loose Braced Block & Repair
Attempts to find the outer braces `{ ... }` and applies syntax repairs:
- Replace single quotes with double quotes: `re.sub(r"'([^']*)'", r'"\1"', text)`
- Remove trailing commas: `re.sub(r",\s*([\]}])", r"\1", text)`
- Replace `None` with `null`, `True` with `true`, `False` with `false`.

#### Tier 4: Fallback to Neutral Uninformative Prior
If all JSON extraction fails or fields cannot be parsed:
```python
DEFAULT_UNINFORMATIVE_POSTERIOR = {
    "p_optimistic": 0.3333,
    "p_neutral": 0.3334,
    "p_cautious": 0.3333,
    "expected_move_bps": 0.0,
    "confidence": 0.0,       # Zero confidence signals uncalibrated / fallback
    "market_regime": "sideways"
}
```
*Note*: `0.3333 + 0.3334 + 0.3333 == 1.0` exactly, adhering to the contract tolerance $10^{-4}$. Setting `confidence = 0.0` prevents uncalibrated fallbacks from heavily weighting downstream Bayesian aggregation.

### 2.3 Posterior Field Normalization Rules

1. **Probability Normalization**:
   - Check if values represent percentages: if $p_{opt} + p_{neu} + p_{cau} > 1.5$ and $\approx 100$, divide each by $100.0$.
   - Non-negative clamping: $p = \max(0.0, \text{float}(p))$.
   - Sum check: $s = p_{opt} + p_{neu} + p_{cau}$. If $s > 0$, divide each by $s$. If $s \le 0$, assign $1/3, 1/3, 1/3$.
   - Rounding constraint: Set $p_{cautious} = 1.0 - p_{optimistic} - p_{neutral}$ to guarantee $\sum p = 1.0 \pm 10^{-4}$.
2. **Expected Move Parsing**:
   - If string: strip `"bps"`, `"bp"`, `"+"`, `","`. If `"%"`, parse float and multiply by $100.0$ (e.g., `1.5%` $\to 150.0$ bps).
   - Fallback to $0.0$ if non-numeric.
3. **Confidence Clamping**:
   - $\text{confidence} = \max(0.0, \min(1.0, \text{float}(\text{confidence})))$, fallback to $0.0$.
4. **Market Regime Normalization**:
   - Mapping dictionary:
     * Bullish synonyms: `{"bull", "bullish", "up", "uptrend", "long"} -> "bull"`
     * Bearish synonyms: `{"bear", "bearish", "down", "downtrend", "short"} -> "bear"`
     * Sideways synonyms: `{"sideways", "neutral", "range", "flat", "consolidation", "chop"} -> "sideways"`
   - If missing/unrecognized: infer from dominant probability ($\arg\max(p_{opt}, p_{neu}, p_{cau})$) or default to `"sideways"`.

---

## 3. Posteriors with Zero Probabilities & Numerical Stability in JSD

### 3.1 Mathematical Definition

For $M$ active analyst probability distributions $P_1, P_2, \dots, P_M$ over $K=3$ outcomes (optimistic, neutral, cautious), with uniform analyst weighting $w_i = \frac{1}{M}$:

The equal-weight mixture distribution $\bar{P}$ is:
$$\bar{P}(k) = \frac{1}{M} \sum_{i=1}^M P_i(k), \quad k \in \{1, 2, 3\}$$

The generalized Jensen-Shannon Divergence using base-2 logarithm is:
$$JSD_2(P_1, \dots, P_M) = \frac{1}{M} \sum_{i=1}^M D_{KL}(P_i \parallel \bar{P})$$
where the Kullback-Leibler (KL) divergence is:
$$D_{KL}(P \parallel Q) = \sum_{k=1}^K P(k) \log_2 \frac{P(k)}{Q(k)}$$

### 3.2 Singularities & Zero-Probability Edge Cases

| Case | Scenario | Mathematical Truth | Naive Code Error | Required Guard |
|---|---|---|---|---|
| 1 | $P_i(k) = 0, \bar{P}(k) > 0$ | $\lim_{x \to 0^+} x \log_2(x/q) = 0$ | `math.log2(0)` $\to$ `ValueError` | `if p <= 0: continue` |
| 2 | $P_i(k) = 0, \bar{P}(k) = 0$ | All analysts have prob 0 for outcome $k$, term is identically $0$ | `0 / 0` $\to$ `ZeroDivisionError` | `if p <= 0: continue` |
| 3 | $P_i(k) > 0, \bar{P}(k) = 0$ | Impossible by definition: $\bar{P}(k) \ge \frac{1}{M} P_i(k) > 0$ | Underflow if floats are $\approx 10^{-320}$ | `q_safe = max(q, 1e-12)` |
| 4 | Identical Distributions | $P_1 = P_2 = \dots = P_M \implies \bar{P} = P_1$ | May produce small negative float due to roundoff (e.g., $-10^{-17}$) | `max(0.0, jsd)` |
| 5 | Single Analyst ($M=1$) | $\bar{P} = P_1 \implies KL(P_1 \parallel P_1) = 0$ | Valid mathematical result | Early return $0.0$ |
| 6 | Zero Analysts ($M=0$) | No distributions | `ZeroDivisionError: division by zero` | Early return $0.0$ |

### 3.3 Production-Grade Numerically Stable JSD Implementation

```python
import math
from typing import Dict, List, Any

def compute_analyst_jsd(posteriors: Dict[str, Dict[str, Any]], eps: float = 1e-12) -> float:
    """
    Computes base-2 Jensen-Shannon Divergence across active analyst probability vectors.
    Fully guarded against zero probabilities, math domain errors, and division by zero.
    """
    if not posteriors or len(posteriors) <= 1:
        return 0.0

    # Extract probability vectors [p_optimistic, p_neutral, p_cautious]
    vectors: List[List[float]] = []
    for p in posteriors.values():
        if isinstance(p, dict):
            vec = [
                float(p.get("p_optimistic", 0.3333)),
                float(p.get("p_neutral", 0.3334)),
                float(p.get("p_cautious", 0.3333)),
            ]
            s = sum(vec)
            if s > 0:
                vec = [x / s for x in vec]
            else:
                vec = [1/3, 1/3, 1/3]
            vectors.append(vec)

    M = len(vectors)
    if M <= 1:
        return 0.0

    K = 3  # 3 outcome states
    # Compute mixture distribution bar_P
    bar_P = [0.0] * K
    for k in range(K):
        bar_P[k] = sum(vectors[i][k] for i in range(M)) / M

    # Compute sum of KL divergences
    total_kl = 0.0
    for vec in vectors:
        kl = 0.0
        for k in range(K):
            pk = vec[k]
            if pk <= 0.0:
                continue  # 0 * log(0 / q) = 0 by standard information theory limit
            qk = max(bar_P[k], eps)
            kl += pk * math.log2(pk / qk)
        total_kl += max(0.0, kl)

    jsd = total_kl / M
    return max(0.0, float(jsd))
```

---

## 4. Dynamic Debate Rounds Calculation and Bounds Checking

### 4.1 Coordination Breakeven Spread (CBS) Economic Formulation

The Coordination Breakeven Spread represents the minimum return necessary for multi-round debate to generate net economic value after accounting for market transaction costs:
$$\text{expected\_debate\_gain\_bps} = JSD \times \text{weighted\_expected\_move\_bps}$$
$$\text{CBS\_bps} = \frac{\text{expected\_debate\_gain\_bps}}{2.0}$$

#### Critical Insight on `weighted_expected_move_bps`:
If Analyst A (Bull) expects $+150$ bps and Analyst B (Bear) expects $-150$ bps:
- Disagreement is **maximal**.
- If signed moves were averaged, $+150 + (-150) = 0$, which yields $\text{CBS\_bps} = 0$, bypassing debate precisely when debate is most urgently needed!
- **Rule**: `weighted_expected_move_bps` MUST measure the anticipated **magnitude** of price displacement:
  $$\text{weighted\_expected\_move\_bps} = \frac{\sum_{i=1}^M \text{confidence}_i \times |\text{expected\_move\_bps}_i|}{\sum_{i=1}^M \text{confidence}_i}$$
  (with fallback to unweighted mean of absolute moves if confidence sum is zero).

### 4.2 Gating Decision Logic

The gate evaluates:
1. `JSD < 0.12`: Analysts are in broad consensus; multi-round debate adds redundant token latency and risks Degeneration-of-Thought $\to$ **Fast-Path**.
2. `CBS_bps <= estimated_spread_bps` (default $15.0$ bps for A-shares round-trip friction): Even if analysts disagree, the expected gain is insufficient to overcome transaction costs $\to$ **Fast-Path**.
3. `JSD >= 0.12` AND `CBS_bps > estimated_spread_bps`: High disagreement on high-stakes moves $\to$ **Multi-Round Debate**.

### 4.3 Dynamic Rounds Scaling & Bounds Checking

When routed to `"multi_round_debate"`, the debate round count should dynamically scale between $1$ and $R_{max} = \text{max\_debate\_rounds}$ (configured via analysis depth):

$$\text{dynamic\_rounds} = \text{clamp}\left(1 + \text{round}\left((R_{max} - 1) \times \frac{JSD - 0.12}{1.0 - 0.12}\right), 1, R_{max}\right)$$

#### Strict Bounds Checking Rules:
1. $R_{max}$ validation: Ensure $R_{max} = \max(1, \text{int}(\text{config.get}("max\_debate\_rounds", 1)))$. If $R_{max} = 1$, dynamic rounds is always $1$.
2. Clamp output: $1 \le \text{dynamic\_rounds} \le R_{max}$ for all possible $JSD \in [0.12, \infty)$.
3. Return integer type explicitly (`int(...)`).

#### Concurrency & State Safety:
Mutating `self.max_debate_rounds` directly on the `ConditionalLogic` instance causes race conditions when multiple analyses run concurrently.
Instead:
- Store the computed dynamic rounds in state: `state["dynamic_debate_rounds"] = dynamic_rounds`.
- In `should_continue_debate(state)`:
  ```python
  effective_max_rounds = state.get("dynamic_debate_rounds", self.max_debate_rounds)
  max_count = 2 * effective_max_rounds
  ```
  This guarantees thread safety and preserves backward compatibility.

---

## 5. Comprehensive Unit Test Suite Design for M1

The proposed test suite will reside in `tests/test_care_m1_conditional_gate.py` and run fully offline without network or database dependencies.

### 5.1 Test Suite 1: `TestAnalystResponseParsing`
Tests `AnalystAgent._parse_response`:
1. `test_clean_markdown_and_json_codeblock`: Verifies exact extraction of all 6 posterior fields and clean separation of the markdown report.
2. `test_unnormalized_probabilities_scaled`: Verifies $[0.6, 0.4, 0.6]$ is normalized to $[0.375, 0.25, 0.375]$ summing to $1.0$.
3. `test_percentage_probabilities_converted`: Verifies $[70, 20, 10]$ is converted to $[0.7, 0.2, 0.1]$.
4. `test_negative_and_out_of_bound_probabilities`: Clamps negative numbers to $0$ and renormalizes.
5. `test_all_zero_probabilities_fallback`: Verifies $[0.0, 0.0, 0.0]$ falls back to $[1/3, 1/3, 1/3]$.
6. `test_pure_text_unstructured_fallback`: Verifies response with no JSON yields `DEFAULT_UNINFORMATIVE_POSTERIOR` (`confidence=0.0`, `"sideways"`) without raising exceptions.
7. `test_malformed_json_repair`: Tests single quotes, trailing commas, and unquoted keys.
8. `test_truncated_json_fallback`: Tests unterminated JSON string degrades to safe default.
9. `test_expected_move_bps_string_variants`: Tests `"+150 bps"`, `"-50bp"`, `"2.5%"`, `"-1.0%"`.
10. `test_market_regime_synonym_normalization`: Tests `"BULL"`, `"bullish"`, `"bearish"`, `"range-bound"`, `"unknown"`.

### 5.2 Test Suite 2: `TestJSDNumericalStability`
Tests JSD calculation and boundary behavior:
1. `test_jsd_identical_distributions_is_zero`: $P_1 = P_2 = [0.7, 0.2, 0.1] \implies JSD = 0.0$.
2. `test_jsd_maximal_divergence_is_one`: $P_1 = [1.0, 0.0, 0.0]$, $P_2 = [0.0, 1.0, 0.0] \implies JSD = 1.0$.
3. `test_jsd_zero_probability_entries`: Tests distributions containing exact $0.0$ entries without `ZeroDivisionError` or `ValueError`.
4. `test_jsd_all_zero_entry_for_one_outcome`: Outcome where all analysts have $0.0$ probability.
5. `test_jsd_single_analyst`: Dict with 1 analyst returns $0.0$.
6. `test_jsd_empty_posteriors`: Empty dict returns $0.0$.
7. `test_jsd_seven_analysts`: Computes JSD across all 7 v2 analysts deterministically.

### 5.3 Test Suite 3: `TestCBSDebateGating`
Tests `should_trigger_multi_round_debate(state)`:
1. `test_low_jsd_routes_to_fast_path`: $JSD = 0.05 < 0.12 \implies$ returns `"fast_path"`.
2. `test_high_jsd_low_cbs_routes_to_fast_path`: $JSD = 0.25$, move $= 40$ bps $\implies CBS = 5.0 \le 15.0 \implies$ returns `"fast_path"`.
3. `test_high_jsd_high_cbs_routes_to_multi_round_debate`: $JSD = 0.35$, move $= 200$ bps $\implies CBS = 35.0 > 15.0 \implies$ returns `"multi_round_debate"`.
4. `test_opposing_analysts_magnitude_calculation`: Verifies Bull $+150$ bps vs Bear $-150$ bps triggers debate and does not cancel to $0$.
5. `test_missing_posteriors_defaults_to_fast_path`: State with empty/missing posteriors defaults cleanly to `"fast_path"`.
6. `test_custom_estimated_spread_bps`: State specifying `estimated_spread_bps=50.0` gates appropriately against higher threshold.

### 5.4 Test Suite 4: `TestDynamicDebateRoundsBounds`
Tests debate round scaling:
1. `test_dynamic_rounds_min_bound`: With $R_{max} = 3$ and $JSD = 0.12 \implies 1$ round.
2. `test_dynamic_rounds_max_bound`: With $R_{max} = 3$ and $JSD = 0.90 \implies 3$ rounds.
3. `test_dynamic_rounds_intermediate`: With $R_{max} = 3$ and $JSD = 0.50 \implies 2$ rounds.
4. `test_dynamic_rounds_with_rmax_one`: With $R_{max} = 1 \implies$ always $1$ round regardless of JSD.
5. `test_dynamic_rounds_state_thread_safety`: Ensures `state["dynamic_debate_rounds"]` is populated and `self.max_debate_rounds` is not mutated.

---

## 6. Verification of Existing Tests (`tests/test_conditional_logic_config.py`)

### 6.1 Diagnostic Findings

When running `pytest tests/test_conditional_logic_config.py` in the clean environment:
1. `test_conditional_logic_default_params` and `test_conditional_logic_custom_params` pass immediately.
2. `test_trading_graph_with_level_4_config` and related graph tests fail if `OPENAI_API_KEY` is not set because `TradingAgentsGraph.__init__` instantiates `ChatOpenAI`. With `OPENAI_API_KEY=mock-key`, all 6 tests in `TestConditionalLogicConfig` pass 100%.
3. `TestDebateRoundsProgression` invokes `create_analysis_config(...)`, which calls `app.services.simple_analysis_service.get_provider_and_url_by_model_sync`. If MongoDB is not running locally, this causes a 30-second timeout per call (up to 300 seconds for 5 levels). When mocked or with MongoDB configured, all 5 progression tests pass 100%.

### 6.2 Backward Compatibility & Zero-Regression Guarantee

The CARE-Agents M1 extensions strictly adhere to backward compatibility:
1. **No Existing Signatures Changed**:
   - `ConditionalLogic.__init__(max_debate_rounds=1, max_risk_discuss_rounds=1)` is unchanged.
   - All `should_continue_*` methods remain identical.
   - `should_trigger_multi_round_debate` is an added method.
2. **Safe Default for Dynamic Rounds**:
   - `should_continue_debate` uses `state.get("dynamic_debate_rounds", self.max_debate_rounds)`. If `dynamic_debate_rounds` is absent, it falls back to `self.max_debate_rounds`, ensuring all existing graph workflows and tests operate identically.
