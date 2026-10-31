## 2026-10-30T03:47:20Z
You are the E2E Test Writer.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_test_writer_e2e_1/
You must read:
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/bramy/Documents/TradingAgents-EN/PROJECT.md
- /home/bramy/Documents/TradingAgents-EN/TEST_INFRA.md

Your scope:
Build out the E2E test suite in `tests/test_care_agents_ablation.py` following the 4-tier test architecture described in TEST_INFRA.md.
Ensure:
1. All tests are 100% offline, deterministic, and fast (using synthetic fixtures and mocks for LLMs and market data feeds).
2. Cover the 4 ablation configurations:
   - Config A: Linear Pipeline (No debate, static weights)
   - Config B: Vanilla TradingAgents (Fixed multi-round debate, static weights, regime-blind memory)
   - Config C: Self-Debate 1-Shot (`RiskSelfDebateV2`, static weights)
   - Config D: CARE-Agents (CBS-gated debate + Regime-adaptive Multiplicative Weights + Regime-filtered Memory)
3. Cover Tier 1 (feature coverage), Tier 2 (boundaries), Tier 3 (interactions), Tier 4 (application scenarios).
4. Run tests with `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_care_agents_ablation.py`.
5. When ready, publish `/home/bramy/Documents/TradingAgents-EN/TEST_READY.md` containing runner commands, coverage summary, and feature checklist.
Write your handoff report to `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_test_writer_e2e_1/handoff.md`.
Notify the orchestrator with send_message when complete.
