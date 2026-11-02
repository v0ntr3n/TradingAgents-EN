# Dispatch for Explorer Survey 1

## Objective
Survey the repository structure, existing test suite, baseline test execution, and R1 requirements.
- Target: `tests/`, `paper/`, `results/`, `reports/`, documentation (`PROJECT.md`, `PEER_REVIEW_READINESS_REPORT.md`, `REPRODUCIBILITY_R3.md`).
- Assess current test suite: run baseline CARE-Agents reproducibility suite (`pytest tests/test_cbs_debate_gating.py tests/test_regime_weight_calculator.py tests/test_regime_memory_attribution.py tests/test_protocol_audit_evaluator.py tests/test_ama_finben_integration.py tests/test_phase5_prompt_seed_and_real_data.py -v`) and unit tests. Record exact baseline status.
- Map files for test reorganization (`tests/legacy_debug/`, `tests/unit/`, `tests/integration/`) and `pytest.ini`.
- Check paper files (`care_agents_paper.tex`, `care_agents_paper.pdf`) and document references.
- Check benchmark outputs in `results/` vs figures/tables in `reports/`.

Write your full structured report to `/home/bramy/Downloads/TradingAgents-EN/.agents/teamwork/explorer_survey_1/handoff.md`.
## 2026-11-02T05:19:46Z
You are Explorer 1 (Codebase Researcher).
Your working directory is /home/bramy/Downloads/TradingAgents-EN/.agents/teamwork/explorer_survey_1/.
You MUST read /home/bramy/Downloads/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read /home/bramy/Downloads/TradingAgents-EN/.agents/teamwork/explorer_survey_1/DISPATCH.md.

Task:
Survey the repository structure, existing test suite, baseline test execution, and R1 requirements:
1. Run and document the baseline status of the core CARE-Agents benchmark tests:
   `pytest tests/test_cbs_debate_gating.py tests/test_regime_weight_calculator.py tests/test_regime_memory_attribution.py tests/test_protocol_audit_evaluator.py tests/test_ama_finben_integration.py tests/test_phase5_prompt_seed_and_real_data.py -v`
   Record passing/failing tests, error messages, and execution environment requirements.
2. Run and document the baseline status of all existing tests in `tests/`:
   `pytest tests/ -v` (note pre-existing failures vs passes).
3. Map existing test files to planned reorganization directories:
   - `tests/legacy_debug/` (to be excluded via `norecursedirs` in `pytest.ini`)
   - `tests/unit/`
   - `tests/integration/`
   Check `pytest.ini` current contents and requirements.
4. Verify canonical manuscript files in `paper/` (`care_agents_paper.tex`, `care_agents_paper.pdf`) and identify any obsolete root duplicates. Find references in `PROJECT.md`, `PEER_REVIEW_READINESS_REPORT.md`, `REPRODUCIBILITY_R3.md`, etc.
5. Survey benchmark outputs in `results/` vs figures/tables in `reports/` and identify experiment script paths that generate or reference them.

Write your complete findings with verified evidence and file paths to `/home/bramy/Downloads/TradingAgents-EN/.agents/teamwork/explorer_survey_1/handoff.md`. Update your `progress.md` periodically.
When finished, send a message to the orchestrator.
