# Task Assignment: Milestone 1 Worker (Structured Posteriors & CBS Gating)

## Identity & Role
- Archetype: teamwork_worker
- Working Directory: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m1/

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Exclusively Owned Files
- `core/agents/analyst.py`
- `core/agents/adapters/index_analyst_v2.py`
- `tradingagents/graph/conditional_logic.py`
- `tests/test_cbs_debate_gating.py`

## Implementation Tasks

### 1. `core/agents/analyst.py`
Add public standalone function:
```python
def extract_structured_posterior(report_text: str) -> Dict[str, Any]:
    """Extract and normalize structured posterior assessment from analyst report text."""
    dummy = AnalystAgent("parser_agent", "market")
    parsed = dummy._parse_response(report_text)
    return parsed.get("posterior") or dummy._normalize_posterior(parsed)
```
And add static method to `AnalystAgent`:
```python
    @staticmethod
    def extract_structured_posterior(report_text: str) -> Dict[str, Any]:
        return extract_structured_posterior(report_text)
```
Ensure it is exported in `__all__` if `__all__` exists.

### 2. `core/agents/adapters/index_analyst_v2.py`
In `IndexAnalystV2.execute(state)`:
Ensure `"market_regime": posterior.get("market_regime", "sideways")` is returned at the root of `result` across all execution branches (existing report, cache hit, and fresh execution).

### 3. `tradingagents/graph/conditional_logic.py`
Implement public functions as analyzed by `explorer_m1_2` in `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/explorer_m1_2/proposed_conditional_logic.patch`:
- `compute_jensen_shannon_divergence(posteriors, weights=None) -> float`: Base-2 JSD in $[0.0, 1.0]$. Returns $0.0$ for identical or empty, $1.0$ for orthogonal distributions under uniform weights.
- `compute_cbs_bps(posteriors, weights=None, estimated_spread_bps=15.0) -> float`: $(D_{JS} \cdot \bar{m}) / 2.0$.
- `calculate_base2_jsd(posteriors, weights=None)`: delegate to `compute_jensen_shannon_divergence`.
- `calculate_cbs_routing(posteriors, estimated_spread_bps=15.0, max_debate_rounds=3, weights=None)`: uses `compute_jensen_shannon_divergence`.
- `should_gate_debate(state: Dict[str, Any]) -> str`: alias for `should_trigger_multi_round_debate`.
- In `ConditionalLogic.should_trigger_multi_round_debate(state)`:
  ```python
  if decision == "fast_path":
      state["_risk_self_debate"] = True
  else:
      state["_risk_self_debate"] = False
  ```

### 4. `tests/test_cbs_debate_gating.py`
Ensure canonical acceptance test suite exists and covers:
- Boundary conditions: $D_{JS} = 0.0$ (identical posteriors, empty), $D_{JS} = 1.0$ (orthogonal posteriors).
- Dynamic routing switches: $D_{JS} < 0.12$ or $\text{CBS} \le s_t \to$ `fast_path`, $D_{JS} \ge 0.12 \land \text{CBS} > s_t \to$ `multi_round_debate`.
- Dynamic debate rounds scaling (1 to 3 rounds).
- All tests pass with exit code 0.

## Verification Instructions
Run tests with:
```bash
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_cbs_debate_gating.py tests/test_analyst_posteriors_cbs.py -v
```
Ensure all tests pass.

## Output Requirements
Write your detailed report and test results in `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m1/handoff.md`.
Notify the orchestrator via `send_message`.


## 2026-10-30T13:02:17Z
[Message] timestamp=2026-10-30T13:02:17Z sender=bd289244-ec47-4a27-b46c-23051e4ad90a priority=MESSAGE_PRIORITY_HIGH content=You are the Worker for Milestone 1 (Structured Posteriors & CBS Gating).
Your working directory is /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m1/.
Read /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m1/DISPATCH.md, /home/bramy/Documents/TradingAgents-EN/PROJECT.md, and /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement the changes across your exclusively owned files:
1. core/agents/analyst.py
2. core/agents/adapters/index_analyst_v2.py
3. tradingagents/graph/conditional_logic.py
4. tests/test_cbs_debate_gating.py

Run verification:
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_cbs_debate_gating.py tests/test_analyst_posteriors_cbs.py -v
Document build/test outcomes in /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/worker_m1/handoff.md.
Notify orchestrator when done via send_message.
