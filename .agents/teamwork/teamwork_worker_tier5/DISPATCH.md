# Dispatch: Worker Tier 5 Hardening

**Assigned Agent**: `teamwork_worker_tier5`
**Role**: Worker Tier 5 Hardening
**Date**: 2026-10-30T14:24:00Z
**Parent**: `0c1b607b-8443-4c84-97bb-8256a9dd2707`
**Working Directory**: `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_tier5`
**Foundational Documents**:
- `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md` (MUST READ)
- `/home/bramy/Documents/TradingAgents-EN/PROJECT.md`
- `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_challenger_tier5_2/handoff.md`

## MANDATORY INTEGRITY WARNING
> DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective
Patch four defensive edge-case vulnerabilities identified by Challenger Tier 5 (Agent 2) in `tests/test_tier5_hardening_2.py`:

1. `tradingagents/graph/conditional_logic.py`:
   - Line ~398: When `state["estimated_spread_bps"]` is None, `float(state.get("estimated_spread_bps", 15.0))` raises `TypeError: float() argument must be a string or a real number, not 'NoneType'`.
     Fix: Guard against explicit None:
     ```python
     raw_spread = state.get("estimated_spread_bps") if isinstance(state, dict) else getattr(state, "estimated_spread_bps", 15.0)
     spread_bps = float(raw_spread if raw_spread is not None else 15.0)
     ```
   - Lines ~61-63: In `compute_base2_jsd` / posterior probability extraction, when posterior dict has non-numeric/string values (e.g. `{"p_optimistic": "corrupted"}`), `float(post.get(...))` raises `ValueError`.
     Fix: Wrap the float conversion in a try/except:
     ```python
     try:
         p_opt = max(0.0, float(post.get("p_optimistic", 0.3333)))
         p_neu = max(0.0, float(post.get("p_neutral", 0.3333)))
         p_cau = max(0.0, float(post.get("p_cautious", 0.3334)))
     except (ValueError, TypeError):
         p_opt, p_neu, p_cau = 0.3333, 0.3333, 0.3334
     ```

2. `core/backtest/result_evaluator.py`:
   - Line ~254: In `calculate_net_performance_metrics`, when `friction` is passed as a `dict` (e.g. `{"sell_stamp_duty_bps": 5.0, "commission_bps": 2.5, "slippage_bps": 5.0}`), `actual_friction` is retained as a raw `dict` rather than converted to `FrictionConfig(**friction)`.
     Fix: Handle dictionary friction configuration:
     ```python
     elif isinstance(friction, dict):
         actual_friction = FrictionConfig(**friction)
     elif "friction" in kwargs and isinstance(kwargs["friction"], dict):
         actual_friction = FrictionConfig(**kwargs["friction"])
     ```
   - Line ~491: In `calculate_cbs_and_coordination_cost`, when a debate record contains `"latency_ms": None`, `"latency_ms" in r` is True, calling `float(None)` and raising `TypeError`. Same for `latency_sec` and `cbs_bps`.
     Fix: Guard against None values:
     ```python
     if r.get("latency_ms") is not None:
         lat_ms = float(r["latency_ms"])
     elif r.get("latency_sec") is not None:
         lat_ms = float(r["latency_sec"]) * 1000.0
     ```
     and:
     ```python
     if r.get("cbs_bps") is not None:
         cbs_val = float(r["cbs_bps"])
         realized_cbs_list.append(cbs_val)
     ```

## Verification Requirement
Run tests to verify that both `tests/test_tier5_hardening_2.py` and all existing suites pass with 0 errors:
```bash
.venv/bin/pytest tests/test_tier5_hardening_2.py tests/test_tier5_hardening_1.py tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_challenger_m4_2_ablation.py tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py -v
```

## Handoff Output
Write `handoff.md` in `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_tier5/handoff.md` with Observation, Logic Chain, Caveats, Conclusion, and Verification results. Then notify parent via `send_message`.
