# Architecture & Implementation Design: M1_1 Structured Signal Block & V2 Analyst Adapters

## 1. Executive Summary

This document specifies the exact technical design and code changes required for **Milestone M1_1** of the CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Trading) project.

### Core Objectives:
1. Extend `AnalystAgent._parse_response()` in `core/agents/analyst.py` to extract a structured probability signal block:
   ```python
   {
       "p_optimistic": float,      # Probability of positive price move (> +50 bps)
       "p_neutral": float,         # Probability of sideways price move ([-50 bps, +50 bps])
       "p_cautious": float,        # Probability of negative price move (< -50 bps)
       "expected_move_bps": float, # Signed expectation in basis points
       "confidence": float,        # Confidence scalar in [0.0, 1.0]
       "market_regime": str        # "bull" | "bear" | "sideways"
   }
   ```
2. Enforce `p_optimistic + p_neutral + p_cautious == 1.0` strictly (with normalization and 4-decimal rounding, guaranteed within 1e-4 tolerance).
3. Preserve the clean markdown report string under `{output_field}` for full backward compatibility with downstream prompt consumers, report generators, and existing unit tests.
4. Update all 7 v2 analyst adapters (`index_analyst_v2`, `sector_analyst_v2`, `market_analyst_v2`, `fundamentals_analyst_v2`, `news_analyst_v2`, `social_analyst_v2`, `chip_distribution_analyst_v2`) so that each adapter's `execute()` method returns:
   ```python
   {
       self.output_field: report,
       "analyst_posteriors": {
           self.agent_id: posterior
       }
   }
   ```
   while preserving auxiliary fields (`tool_call_summaries`, `quality_flags`).

---

## 2. Current State Analysis

### 2.1 `core/agents/analyst.py`
- **Current `_parse_response()` (line 503)**:
  ```python
  def _parse_response(self, response: str) -> Dict[str, Any]:
      return {
          "content": response,
          "success": True
      }
  ```
- **Current `execute()` (lines 200–245)**:
  `report` is assigned directly from `self.invoke_with_tools(...)` or `self._llm.invoke(...)`. `_parse_response()` is never invoked within `execute()`.
  The method finishes with:
  ```python
  result = {output_key: report}
  ```
  `analyst_posteriors` is not generated or returned.

### 2.2 The 7 V2 Analyst Adapters
Our audit revealed three distinct patterns across the 7 adapters:

| # | Adapter File | Class Name | Base Class | `output_field` | `metadata.id` | Current Execution Pattern |
|---|---|---|---|---|---|---|
| 1 | `core/agents/adapters/index_analyst_v2.py` | `IndexAnalystV2` | `AnalystAgent` | `"index_report"` | `"index_analyst_v2"` | Checks cache, then calls `super().execute(state)` |
| 2 | `core/agents/adapters/sector_analyst_v2.py` | `SectorAnalystV2` | `AnalystAgent` | `"sector_report"` | `"sector_analyst_v2"` | Calls `super().execute(state)` directly |
| 3 | `core/agents/adapters/market_analyst_v2.py` | `MarketAnalystV2` | `AnalystAgent` | `"market_report"` | `"market_analyst_v2"` | **Overrides `execute()`**, does not call super |
| 4 | `core/agents/adapters/fundamentals_analyst_v2.py` | `FundamentalsAnalystAgentV2` | **`BaseAgent`** | `"fundamentals_report"` | `"fundamentals_analyst_v2"` | **Overrides `execute()`**, inherits from `BaseAgent` directly |
| 5 | `core/agents/adapters/news_analyst_v2.py` | `NewsAnalystV2` | `AnalystAgent` | `"news_report"` | `"news_analyst_v2"` | **Overrides `execute()`**, does not call super |
| 6 | `core/agents/adapters/social_analyst_v2.py` | `SocialMediaAnalystV2` | `AnalystAgent` | `"sentiment_report"` | `"social_analyst_v2"` | **Overrides `execute()`**, does not call super |
| 7 | `core/agents/adapters/chip_distribution_analyst_v2.py` | `ChipDistributionAnalystV2` | `AnalystAgent` | `"chip_report"` | `"chip_distribution_analyst_v2"` | **Overrides `execute()`**, does not call super |

#### Key Observations:
1. **Cache Bypass in `IndexAnalystV2`**: When `_get_cached_index_report()` hits a cached report, it returns `{"index_report": cached_report}` directly without calling `super().execute()`. The cached report must be parsed so that `analyst_posteriors` is also returned on cache hits.
2. **Inheritance Gap in `FundamentalsAnalystAgentV2`**: It inherits from `BaseAgent` rather than `AnalystAgent`. It should inherit from `AnalystAgent` so it has uniform access to `_parse_response()`, `_normalize_posterior()`, and `_get_default_posterior()`.
3. **Field Naming Uniformity**: `SocialMediaAnalystV2` uses `"sentiment_report"` as its `output_field` (matching both `metadata.output_field` and `AgentState.sentiment_report`).

---

## 3. Detailed Code Design: `core/agents/analyst.py`

### 3.1 Structured Signal Block Format
The LLM is prompted to include a structured JSON block at the conclusion of its report:
```json
{
  "p_optimistic": 0.65,
  "p_neutral": 0.25,
  "p_cautious": 0.10,
  "expected_move_bps": 75.0,
  "confidence": 0.80,
  "market_regime": "bull"
}
```

### 3.2 Robust Extraction Algorithm
To ensure 100% resilience across all model variants and mocks:
1. **Targeted Extraction Regexes**:
   - Tagged block: `r'<signal_block>\s*({[\s\S]*?})\s*</signal_block>'`
   - Comment block: `r'<!--\s*SIGNAL_BLOCK\s*:\s*({[\s\S]*?})\s*-->'`
   - Markdown JSON fence: `r'```(?:json|signal_block)?\s*({[\s\S]*?"p_optimistic"[\s\S]*?})\s*```'`
   - Generic JSON block containing `"p_optimistic"`: `r'({[^{}]*"p_optimistic"[^{}]*})'`
2. **Report Cleaning**:
   The matched signal block span is stripped from the raw response string to yield `clean_report`. If stripping leaves the text empty (e.g. LLM produced only JSON), `clean_report` falls back to the original response text to avoid tripping quality gates.
3. **Heuristic & Neutral Fallback**:
   If no JSON block is present (e.g. mock test returns `"REPORT"` or legacy output), the parser scans the text for bullish/bearish lexical cues:
   - Bullish dominant: `p_optimistic=0.55, p_neutral=0.35, p_cautious=0.10, expected_move_bps=50.0, confidence=0.60, market_regime="bull"`
   - Bearish dominant: `p_optimistic=0.10, p_neutral=0.35, p_cautious=0.55, expected_move_bps=-50.0, confidence=0.60, market_regime="bear"`
   - Neutral default: `p_optimistic=0.3333, p_neutral=0.3334, p_cautious=0.3333, expected_move_bps=0.0, confidence=0.50, market_regime="sideways"`

### 3.3 Probability Normalization Algorithm
```python
def _normalize_posterior(self, raw: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Parse and clamp raw probabilities
    try:
        p_opt = max(0.0, float(raw.get("p_optimistic", 1.0 / 3.0)))
    except (ValueError, TypeError):
        p_opt = 1.0 / 3.0

    try:
        p_neu = max(0.0, float(raw.get("p_neutral", 1.0 / 3.0)))
    except (ValueError, TypeError):
        p_neu = 1.0 / 3.0

    try:
        p_cau = max(0.0, float(raw.get("p_cautious", 1.0 / 3.0)))
    except (ValueError, TypeError):
        p_cau = 1.0 / 3.0

    total = p_opt + p_neu + p_cau
    if total <= 1e-6:
        p_opt, p_neu, p_cau = 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
    else:
        p_opt /= total
        p_neu /= total
        p_cau /= total

    # Enforce sum == 1.0 exactly to 4 decimal places
    p_opt = round(p_opt, 4)
    p_neu = round(p_neu, 4)
    p_cau = round(1.0 - p_opt - p_neu, 4)
    if p_cau < 0.0:
        p_cau = 0.0
        p_neu = round(1.0 - p_opt, 4)

    # 2. expected_move_bps
    try:
        expected_move = float(raw.get("expected_move_bps", 0.0))
    except (ValueError, TypeError):
        expected_move = 0.0
    if expected_move == 0.0 and abs(p_opt - p_cau) > 0.1:
        expected_move = round((p_opt - p_cau) * 100.0, 1)

    # 3. confidence (support [0.0, 1.0] or [0, 100])
    try:
        conf = float(raw.get("confidence", 0.5))
        if conf > 1.0 and conf <= 100.0:
            conf /= 100.0
    except (ValueError, TypeError):
        conf = 0.5
    conf = max(0.0, min(1.0, round(conf, 4)))

    # 4. market_regime
    regime_raw = str(raw.get("market_regime", "")).strip().lower()
    if regime_raw in ("bull", "bullish", "long", "up"):
        regime = "bull"
    elif regime_raw in ("bear", "bearish", "short", "down"):
        regime = "bear"
    elif regime_raw in ("sideways", "neutral", "range", "flat", "consolidation"):
        regime = "sideways"
    else:
        if p_opt > p_cau and p_opt > p_neu and expected_move > 20.0:
            regime = "bull"
        elif p_cau > p_opt and p_cau > p_neu and expected_move < -20.0:
            regime = "bear"
        else:
            regime = "sideways"

    return {
        "p_optimistic": p_opt,
        "p_neutral": p_neu,
        "p_cautious": p_cau,
        "expected_move_bps": round(expected_move, 2),
        "confidence": conf,
        "market_regime": regime,
    }
```

### 3.4 Updated `AnalystAgent._parse_response()`
```python
def _parse_response(self, response: Any) -> Dict[str, Any]:
    """
    Parse LLM response to extract structured signal block and clean markdown report.
    """
    if response is None:
        raw_text = ""
    elif isinstance(response, dict):
        if "p_optimistic" in response:
            posterior = self._normalize_posterior(response)
            content = response.get("content") or response.get("report") or ""
            return {
                "content": content,
                "report": content,
                "posterior": posterior,
                "success": True,
                **posterior
            }
        raw_text = str(response.get("content") or response.get("report") or "")
    else:
        raw_text = str(response)

    raw_posterior: Optional[Dict[str, Any]] = None
    clean_report = raw_text

    # Search patterns
    patterns = [
        r'<signal_block>\s*({[\s\S]*?})\s*</signal_block>',
        r'<!--\s*SIGNAL_BLOCK\s*:\s*({[\s\S]*?})\s*-->',
        r'```(?:json|signal_block)?\s*({[\s\S]*?"p_optimistic"[\s\S]*?})\s*```',
        r'({[^{}]*"p_optimistic"[^{}]*})',
    ]

    for pat in patterns:
        match = re.search(pat, raw_text)
        if match:
            json_candidate = match.group(1).strip()
            try:
                data = json.loads(json_candidate)
                if isinstance(data, dict):
                    raw_posterior = data
                    # Strip signal block from clean report
                    start, end = match.span()
                    clean_report = (raw_text[:start] + raw_text[end:]).strip()
                    break
            except Exception:
                # Try cleaning common trailing commas
                cleaned_json = re.sub(r',\s*}', '}', json_candidate)
                try:
                    data = json.loads(cleaned_json)
                    if isinstance(data, dict):
                        raw_posterior = data
                        start, end = match.span()
                        clean_report = (raw_text[:start] + raw_text[end:]).strip()
                        break
                except Exception:
                    continue

    if not clean_report:
        clean_report = raw_text

    if raw_posterior is not None:
        posterior = self._normalize_posterior(raw_posterior)
    else:
        posterior = self._heuristic_extract_posterior(raw_text)

    return {
        "content": clean_report,
        "report": clean_report,
        "posterior": posterior,
        "success": True,
        **posterior
    }
```

### 3.5 Updated `AnalystAgent.execute()`
In `core/agents/analyst.py`, lines 240–288:
```python
# 5. Parse response to extract structured signal block and clean report
parsed = self._parse_response(report)
clean_report = parsed.get("report") or parsed.get("content") or report
posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

output_key = self.output_field or f"{self.analyst_type}_report"

logger.info(f"analyst Agent {self.agent_id} Executed successfully")
result = {
    output_key: clean_report,
    "analyst_posteriors": {
        self.agent_id: posterior
    }
}

if quality_flag:
    result["quality_flags"] = [quality_flag]

tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}

return result
```
And in `except Exception as e:` (lines 299–305):
```python
output_key = self.output_field or f"{self.analyst_type}_report"
return {
    output_key: {
        "error": GENERIC_REPORT_FALLBACK,
        "success": False
    },
    "analyst_posteriors": {
        self.agent_id: self._get_default_posterior()
    }
}
```

### 3.6 Prompt Engineering in `_build_post_tool_analysis_prompt()`
Append to `_build_post_tool_analysis_prompt()`:
```
8. **Structured Probability Assessment (Mandatory)**:
At the very end of your report, append a structured JSON probability signal block in the following format:
```json
{
  "p_optimistic": <float 0.0 to 1.0, probability of price increase > +50 bps>,
  "p_neutral": <float 0.0 to 1.0, probability of price change in [-50 bps, +50 bps]>,
  "p_cautious": <float 0.0 to 1.0, probability of price decrease < -50 bps>,
  "expected_move_bps": <signed float, expected price change in basis points>,
  "confidence": <float 0.0 to 1.0, confidence score>,
  "market_regime": "<bull | bear | sideways>"
}
```
Constraints:
- p_optimistic + p_neutral + p_cautious MUST sum to 1.0.
```

---

## 4. Code Design for all 7 V2 Analyst Adapters

### 4.1 `core/agents/adapters/index_analyst_v2.py`
In `IndexAnalystV2.execute(state)`:
1. When report exists in state (line 261):
   ```python
   existing_report = state.get("index_report", "")
   if existing_report and len(existing_report) > 100:
       posteriors = state.get("analyst_posteriors", {})
       if self.agent_id in posteriors:
           return {}
       parsed = self._parse_response(existing_report)
       return {
           "analyst_posteriors": {
               self.agent_id: parsed["posterior"]
           }
       }
   ```
2. When cached report is found (line 270):
   ```python
   cached_report = _get_cached_index_report(analysis_date)
   if cached_report:
       parsed = self._parse_response(cached_report)
       clean_report = parsed.get("report") or parsed.get("content") or cached_report
       return {
           "index_report": clean_report,
           "analyst_posteriors": {
               self.agent_id: parsed["posterior"]
           }
       }
   ```
3. Live execution (line 280):
   `result = super().execute(state)`
   `result` already includes `index_report` and `"analyst_posteriors": {self.agent_id: posterior}`.
   Cache `result.get("index_report", "")`. Return `result`.

### 4.2 `core/agents/adapters/sector_analyst_v2.py`
In `SectorAnalystV2.execute(state)`:
1. When report exists in state (line 299):
   ```python
   existing_report = state.get("sector_report", "")
   if existing_report and len(existing_report) > 100:
       posteriors = state.get("analyst_posteriors", {})
       if self.agent_id in posteriors:
           return {}
       parsed = self._parse_response(existing_report)
       return {
           "analyst_posteriors": {
               self.agent_id: parsed["posterior"]
           }
       }
   ```
2. Live execution (line 311):
   `result = super().execute(state)`
   Returns `{ "sector_report": clean_report, "analyst_posteriors": {self.agent_id: posterior}, ... }`.

### 4.3 `core/agents/adapters/market_analyst_v2.py`
In `MarketAnalystV2.execute(state)`:
Lines 222–229:
```python
# Before:
report = self._sanitize_report(report)
result = {self.output_field: report}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result

# After:
parsed = self._parse_response(report)
raw_clean_report = parsed.get("report") or parsed.get("content") or report
clean_report = self._sanitize_report(raw_clean_report)
posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

result = {
    self.output_field: clean_report,
    "analyst_posteriors": {
        self.agent_id: posterior
    }
}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result
```
In `except Exception as e:` (line 231):
```python
return {
    self.output_field: GENERIC_REPORT_FALLBACK,
    "analyst_posteriors": {
        self.agent_id: self._get_default_posterior()
    }
}
```

### 4.4 `core/agents/adapters/fundamentals_analyst_v2.py`
1. **Inheritance change**:
   ```python
   # Before:
   from ..base import BaseAgent
   ...
   class FundamentalsAnalystAgentV2(BaseAgent):

   # After:
   from core.agents.analyst import AnalystAgent
   ...
   class FundamentalsAnalystAgentV2(AnalystAgent):
   ```
2. **Execute return update** (lines 208–215):
   ```python
   # Before:
   result = {"fundamentals_report": analysis}
   tool_summary = self._format_tool_call_summary()
   if tool_summary:
       result["tool_call_summaries"] = {self.agent_id: tool_summary}
   return result

   # After:
   parsed = self._parse_response(analysis)
   clean_report = parsed.get("report") or parsed.get("content") or analysis
   posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

   result = {
       self.output_field: clean_report,
       "analyst_posteriors": {
           self.agent_id: posterior
       }
   }
   tool_summary = self._format_tool_call_summary()
   if tool_summary:
       result["tool_call_summaries"] = {self.agent_id: tool_summary}
   return result
   ```

### 4.5 `core/agents/adapters/news_analyst_v2.py`
In `NewsAnalystV2.execute(state)` (lines 345–351):
```python
# Before:
result = {self.output_field: report}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result

# After:
parsed = self._parse_response(report)
clean_report = parsed.get("report") or parsed.get("content") or report
posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

result = {
    self.output_field: clean_report,
    "analyst_posteriors": {
        self.agent_id: posterior
    }
}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result
```
In `except Exception as e:` (lines 352–355):
```python
return {
    self.output_field: GENERIC_REPORT_FALLBACK,
    "analyst_posteriors": {
        self.agent_id: self._get_default_posterior()
    }
}
```

### 4.6 `core/agents/adapters/social_analyst_v2.py`
In `SocialMediaAnalystV2.execute(state)` (lines 117–123):
```python
# Before:
result = {self.output_field: report}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result

# After:
parsed = self._parse_response(report)
clean_report = parsed.get("report") or parsed.get("content") or report
posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

result = {
    self.output_field: clean_report,
    "analyst_posteriors": {
        self.agent_id: posterior
    }
}
tool_summary = self._format_tool_call_summary()
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result
```
In `except Exception as e:` (lines 124–127):
```python
return {
    self.output_field: GENERIC_REPORT_FALLBACK,
    "analyst_posteriors": {
        self.agent_id: self._get_default_posterior()
    }
}
```

### 4.7 `core/agents/adapters/chip_distribution_analyst_v2.py`
In `ChipDistributionAnalystV2.execute(state)` (lines 151–155):
```python
# Before:
result = {self.output_field: report}
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result

# After:
parsed = self._parse_response(report)
clean_report = parsed.get("report") or parsed.get("content") or report
posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

result = {
    self.output_field: clean_report,
    "analyst_posteriors": {
        self.agent_id: posterior
    }
}
if tool_summary:
    result["tool_call_summaries"] = {self.analyst_type: tool_summary}
return result
```
In `except Exception as e:` (lines 156–159):
```python
return {
    self.output_field: f"Chip distribution analysis failed: {str(e)}",
    "analyst_posteriors": {
        self.agent_id: self._get_default_posterior()
    }
}
```

---

## 5. State Schema & Concurrency Integration

In LangGraph parallel execution, analyst nodes execute concurrently.
To merge dictionary updates without overwriting:
1. `core/workflow/builder.py` (`WorkflowState`):
   ```python
   analyst_posteriors: Annotated[dict, merge_dict]
   ```
2. `tradingagents/agents/utils/agent_states.py` (`AgentState`):
   ```python
   from core.state.reducers import merge_dict
   ...
   analyst_posteriors: Annotated[Dict[str, Any], merge_dict]
   ```
Because each analyst returns `{"analyst_posteriors": {self.agent_id: posterior}}`, LangGraph invokes `merge_dict(state_posteriors, node_posteriors)` after each node, producing the unified dictionary:
```python
state["analyst_posteriors"] = {
    "index_analyst_v2": {...},
    "sector_analyst_v2": {...},
    "market_analyst_v2": {...},
    "fundamentals_analyst_v2": {...},
    "news_analyst_v2": {...},
    "social_analyst_v2": {...},
    "chip_distribution_analyst_v2": {...}
}
```

---

## 6. Backward Compatibility Analysis

| Feature | Legacy Requirement | CARE-Agents Behavior | Compatibility Result |
|---|---|---|---|
| `result[output_field]` format | `str` markdown text | Clean `str` with signal JSON stripped | **100% Compatible** — tests asserting `result["market_report"] == "REPORT"` pass without modification |
| Direct `_parse_response` caller | Returns dict with `"content"`, `"success"` | Returns dict containing `"content"`, `"report"`, `"success"`, `"posterior"`, and unpacked fields | **100% Compatible** — legacy callers accessing `parsed["content"]` succeed |
| Mock/Missing JSON in response | String like `"REPORT"` or empty | Heuristic fallback creates valid normalized posterior vector | **100% Robust** — zero unhandled exceptions on unexpected LLM text |
| Auxiliary fields in `execute()` | `tool_call_summaries`, `quality_flags` | Untouched, passed through identical to existing code | **100% Preserved** |

---

## 7. Implementation Plan for Milestone Implementer

1. **Phase 1: `core/agents/analyst.py`**
   - Implement `_normalize_posterior()`, `_heuristic_extract_posterior()`, `_get_default_posterior()`.
   - Update `_parse_response()`.
   - Update `execute()` to extract clean report and posterior, and return `{"analyst_posteriors": {self.agent_id: posterior}}`.
   - Update `_build_post_tool_analysis_prompt()` to include structured signal block instructions.
2. **Phase 2: The 7 V2 Analyst Adapters**
   - Update `index_analyst_v2.py` (cache hit & state check).
   - Update `sector_analyst_v2.py` (state check).
   - Update `market_analyst_v2.py` (execute return).
   - Update `fundamentals_analyst_v2.py` (inherit from `AnalystAgent`, execute return).
   - Update `news_analyst_v2.py` (execute return).
   - Update `social_analyst_v2.py` (execute return).
   - Update `chip_distribution_analyst_v2.py` (execute return).
3. **Phase 3: Schema Registration**
   - Register `analyst_posteriors` with `merge_dict` in `tradingagents/agents/utils/agent_states.py` and `core/workflow/builder.py`.
4. **Phase 4: Unit Testing & Verification**
   - Run unit tests covering:
     - Posterior schema validation for all 7 analysts.
     - Exact probability sum == 1.0 constraint.
     - Markdown clean report retention.
     - Fallback handling on mock string outputs.
