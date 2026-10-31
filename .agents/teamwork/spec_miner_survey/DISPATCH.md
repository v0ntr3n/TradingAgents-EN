# Task Assignment: Specification Mining from plan.md

## Identity & Role
- Archetype: teamwork_spec_miner
- Working Directory: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/

## Objective
Extract the comprehensive specification for the CARE-Agents research extensions from the reference plan at `/home/bramy/Downloads/plan.md` and `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md`.

## Scope Boundaries
- Do NOT modify any codebase files.
- Investigate `/home/bramy/Downloads/plan.md` thoroughly.
- Identify:
  1. Exact mathematical formulations and algorithms for:
     - Jensen-Shannon Divergence ($D_{JS}$) and Coordination Breakeven Spread ($\text{CBS}$) gating ($D_{JS} \ge \tau_{JS}$ and $\text{CBS} > s_t$).
     - Multi-class Brier loss, online Exponentially Weighted Forecaster, regime partitioning (bull, bear, sideways).
     - Calibrated signal processing (ensemble confidence, risk score, target prices).
     - Regime-filtered episodic memory, volatility quintiles, drawdown circuit-breaker.
     - Counterfactual credit assignment / reflection attribution roles (`correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`).
     - ProtocolAuditEvaluator (metrics, A-share transaction costs, commission, stamp duty, slippage, CBS surplus, Brier, ECE, token/latency costs).
     - Factorial ablation suite (4 configurations: Linear Pipeline, Vanilla TradingAgents, Self-Debate V2, CARE-Agents).
  2. Data structures, state dictionary keys, interface contracts, and module boundaries.
  3. Acceptance criteria and test requirements.

## Output Requirements
Write a detailed report to `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/spec_report.md` and summarize in your `handoff.md`.
Then notify the orchestrator with `send_message`.


## 2026-10-30T12:36:53Z
Sender: bd289244-ec47-4a27-b46c-23051e4ad90a
Priority: MESSAGE_PRIORITY_HIGH
Content:
You are a specification miner investigating the CARE-Agents research extension requirements.
Your working directory is /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/.
Read your task assignment in /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/DISPATCH.md and the user request in /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md.
Investigate /home/bramy/Downloads/plan.md thoroughly.
Extract all detailed specifications, mathematical equations, schemas, formulas, constants, and edge cases.
Write your full findings to /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/spec_report.md and your handoff summary to /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/handoff.md.
When finished, send a message to the orchestrator (caller).
