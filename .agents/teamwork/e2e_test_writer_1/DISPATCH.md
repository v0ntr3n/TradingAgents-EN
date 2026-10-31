# Task Assignment: E2E Testing Track Orchestration & Test Suite Architecture

## Identity & Role
- Archetype: teamwork_test_writer
- Working Directory: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/e2e_test_writer_1/

## Objective
Establish the opaque-box E2E testing infrastructure for the CARE-Agents project and generate/align the four canonical acceptance criteria test suites:
1. `tests/test_cbs_debate_gating.py` (CBS debate gating, boundary conditions $D_{JS}=0, D_{JS}=1$, dynamic routing switches)
2. `tests/test_regime_weight_calculator.py` (regime-partitioned weights, multiclass Brier loss, weight convergence across synthetic sequences, calibrated signal processing)
3. `tests/test_regime_memory_attribution.py` (regime filtering, drawdown circuit-breaker, counterfactual attribution roles)
4. `tests/test_protocol_audit_evaluator.py` (ProtocolAuditEvaluator, net-of-cost metrics, A-share frictions, Brier, ECE, token/latency tracking)

Also create `TEST_INFRA.md` at project root following the E2E Testing Track methodology (Tiers 1-4).
When all test suites are verified and ready, create `TEST_READY.md` at project root.

## Scope Boundaries
- Do NOT modify application source code in `core/` or `tradingagents/`.
- Only write test files under `tests/` and documentation `TEST_INFRA.md`, `TEST_READY.md`.
- Ensure tests run with `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest`.
- Note: High-coverage existing tests exist in `tests/test_analyst_posteriors_cbs.py`, `tests/test_regime_weights_signal.py`, `tests/test_regime_memory_reflection.py`, `tests/test_care_agents_ablation.py`. You may wrap, import, or extend these to ensure the exact canonical files `test_cbs_debate_gating.py`, `test_regime_weight_calculator.py`, `test_regime_memory_attribution.py`, and `test_protocol_audit_evaluator.py` exist and pass with 100% success.

## Output Requirements
Write `TEST_INFRA.md` at project root.
Ensure the 4 canonical test files pass via `.venv/bin/pytest`.
Create `TEST_READY.md` at project root when complete.
Write handoff report to `.agents/teamwork/e2e_test_writer_1/handoff.md`.
Notify orchestrator via `send_message`.


## 2026-10-30T12:50:54Z
You are the E2E Test Writer for the CARE-Agents project.
Your working directory is /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/e2e_test_writer_1/.
Read /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/e2e_test_writer_1/DISPATCH.md, /home/bramy/Documents/TradingAgents-EN/PROJECT.md, and /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md.
Create TEST_INFRA.md at project root.
Align and write the four canonical acceptance criteria test suites:
- tests/test_cbs_debate_gating.py
- tests/test_regime_weight_calculator.py
- tests/test_regime_memory_attribution.py
- tests/test_protocol_audit_evaluator.py
Verify they execute cleanly via /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest.
When complete, write TEST_READY.md at project root, write your handoff.md, and notify the orchestrator.
