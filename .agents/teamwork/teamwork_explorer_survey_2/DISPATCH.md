## 2026-10-30T03:32:09Z
You are Explorer Survey 2.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/
You must read /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md first.

Investigate:
1. Target files for R2:
   - `core/agents/utils/weight_calculator.py`
   - `tradingagents/graph/signal_processing.py`
2. In `core/agents/utils/weight_calculator.py`:
   - Inspect `calculate_report_weights()`, its inputs, outputs, and usage across the codebase.
   - Design requirements for `RegimeAdaptiveWeightCalculator`:
     * Maintaining weight vectors `w[regime][analyst_id]` across regimes: "bull", "bear", "sideways".
     * Implementing `update_weights(regime: str, analyst_posteriors: dict, realized_return: float, learning_rate: float = 0.2)` using Multiplicative Weights Update (Exponentially Weighted Forecaster) rule with multiclass Brier loss:
       `w_new[i] = w_old[i] * exp(-learning_rate * brier_loss[i])`, normalized so `sum(w_new) == 1.0`.
     * Preserving `calculate_report_weights()` as a fallback.
3. In `tradingagents/graph/signal_processing.py`:
   - Inspect `SignalProcessor._smart_price_estimation()`, current pricing fallback logic (multiplication by 1.15 or 0.95), where `state["analyst_posteriors"]` is available.
   - Design regime-calibrated Bayesian log-odds aggregation of `state["analyst_posteriors"]` weighted by `RegimeAdaptiveWeightCalculator`.
4. Target files for R3:
   - `core/memory/memory_manager.py`
   - `core/agents/reflection_helper.py`
   - `core/agents/Reflection_prompts.py`
   - `tradingagents/graph/reflection.py`
5. In `core/memory/memory_manager.py`:
   - Inspect `Mem0AgentMemory._normalize_store_metadata` and `_normalize_recall_filters`.
   - Enforce mandatory metadata keys: `"market_regime"` ("bull" | "bear" | "sideways"), `"volatility_quintile"` (int 1 to 5), `"brier_calibration_error"` (float).
   - Implement regime circuit-breaker on memory retrieval: when querying for `bull_researcher_v2`, `bear_researcher_v2`, `research_manager_v2`, `trader_v2`, or `risk_manager_v2`, filter out contradicting `market_regime` memories unless current regime confidence < 0.5.
6. In `tradingagents/graph/reflection.py`, `core/agents/reflection_helper.py`, and `core/agents/Reflection_prompts.py`:
   - Inspect uniform returns_losses scalar broadcast.
   - Design counterfactual credit assignment: compute marginal contribution (directional probability vs realized return sign, and whether manager overrode or followed), and inject agent-specific attribution score into reflection prompt.

Write your findings to `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/survey_r2_r3.md`.
Also write a structured `handoff.md` in your working directory.
When finished, notify the orchestrator with send_message.
