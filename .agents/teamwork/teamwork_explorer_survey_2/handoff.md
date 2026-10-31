# Handoff Report: R2 & R3 Survey and Architectural Design

## 1. Observation

### R2 Target 1: `core/agents/utils/weight_calculator.py`
- `calculate_report_weights()` (lines 10-60) accepts `reports: Dict[str, str]` and optional `trading_style: Optional[str]`.
- Line 25: `REPORT_TO_ANALYST_TYPE` maps 6 reports (`market_report`, `news_report`, `sentiment_report`, `fundamentals_report`, `sector_report`, `index_report`) to analyst categories.
- Line 46: If `trading_style is None`, it calls `_infer_trading_style()` (lines 63-87) which infers `"short"` or `"long"` based on presence of `fundamentals_report` or `market_report`.
- Lines 89-192: Static weights are hardcoded (Short-term: 40% technical, 30% news, 30% sentiment; Long-term: 50% fundamentals, 30% sector).
- Lines 212-282: `format_weighted_reports_prompt()` formats reports split at $\ge 20\%$ threshold.
- The file has no state, no tracking of analyst predictions, no regime awareness, and no dynamic loss-based updating.

### R2 Target 2: `tradingagents/graph/signal_processing.py`
- `SignalProcessor._smart_price_estimation()` (lines 216-280):
  * Lines 266-278:
    ```python
    if current_price:
        if action == 'buy':
            multiplier = 1.15 if is_china else 1.12
            return round(current_price * multiplier, 2)
        elif action == 'sell':
            multiplier = 0.95 if is_china else 0.92
            return round(current_price * multiplier, 2)
        else:  # hold
            return current_price
    ```
  * Multipliers $1.15$ / $0.95$ are static fallbacks when no price target is found in LLM JSON or regex.
  * In `tradingagents/graph/trading_graph.py:1392`:
    `decision = self.process_signal(final_state["final_trade_decision"], company_name)`
    `final_state` is currently not forwarded into `self.process_signal()` or `_smart_price_estimation()`.

### R3 Target 1: `core/memory/memory_manager.py`
- `Mem0AgentMemory._normalize_store_metadata()` (lines 87-97) only maps `ticker`, `symbol`, `object_type`, `object_key`, and `source`.
- `Mem0AgentMemory._normalize_recall_filters()` (lines 99-108) only filters `ticker` and `symbol`.
- `Mem0AgentMemory.search_memories()` (lines 139-185) queries memory without filtering on market regime.
- `_AGENT_ID_ALIAS_MAPPING` (lines 30-41) defines alias lists for the 5 agents:
  `bull_researcher`, `bear_researcher`, `research_manager`, `trader`, and `risk_manager` (and their `_v2` forms).

### R3 Target 2: `tradingagents/graph/reflection.py`
- Lines 63-76: `_reflect_on_component(component_type, report, situation, returns_losses)` constructs a prompt with uniform `Returns: {returns_losses}`.
- Lines 78-126: `reflect_bull_researcher`, `reflect_bear_researcher`, `reflect_trader`, `reflect_invest_judge`, and `reflect_risk_manager` all pass the identical scalar `returns_losses` to `_reflect_on_component()`.
- No counterfactual analysis is performed: agents whose advice was overridden or who accurately predicted market downturns receive identical negative return numbers as agents whose advice caused the loss.

### R3 Target 3 & 4: `core/agents/reflection_helper.py` & `core/agents/reflection_prompts.py`
- `core/agents/reflection_helper.py`: `run_reflection()` and `run_reflection_sync()` write structured lessons to mem0.
- `core/agents/reflection_prompts.py`: `build_debate_reflection_user_prompt()` (lines 153-191) builds user prompts from `ticker`, `debate_history`, `conclusion`, and `debate_type`. Does not take agent-specific attribution scores.
- Note: File on disk is named `core/agents/reflection_prompts.py` (lowercase 'r').

---

## 2. Logic Chain

1. **R2 Weight Calculator**:
   - Observations show that existing `calculate_report_weights()` is stateless and purely heuristic.
   - Introducing `RegimeAdaptiveWeightCalculator` requires maintaining persistent weight vectors $w[\text{regime}][\text{analyst\_id}]$ across `"bull"`, `"bear"`, and `"sideways"`.
   - Each analyst in R1 produces a posterior distribution $p_i = [p_{\text{opt}}, p_{\text{neu}}, p_{\text{caut}}]$ with $\sum p_{i, k} = 1.0$.
   - Using the realized return $R$, the market outcome is classified into one-hot target $y \in \{[1,0,0], [0,1,0], [0,0,1]\}$ with deadband threshold $\tau = 50\text{ bps}$.
   - Multiclass Brier loss $\text{BrierLoss}_i = \sum_{k=1}^3 (p_{i, k} - y_k)^2 \in [0, 2]$ penalizes miscalibration.
   - Multiplicative Weights Update $w_{\text{new}}[i] = w_{\text{old}}[i] \cdot \exp(-\eta \cdot \text{BrierLoss}_i)$ followed by normalization ensures bounded, non-negative, dynamically adapted weights.
   - Keeping `calculate_report_weights()` intact guarantees existing legacy code calling it experiences zero regression.

2. **R2 Calibrated Signal Processing**:
   - `SignalProcessor._smart_price_estimation()` currently uses $1.15$ / $0.95$.
   - When `state["analyst_posteriors"]` is available, Bayesian log-odds opinion pooling aggregates individual analyst log-odds $\ell_i = \ln(p_{i, \text{opt}} / p_{i, \text{caut}})$ weighted by $w[r][i]$ from `RegimeAdaptiveWeightCalculator`, adjusted by regime prior $L_0$.
   - The calibrated directional probability $P_{\text{agg}}(H_+) = \sigma(L_{\text{agg}})$ scales the weighted expected move $\bar{\Delta}_{\text{bps}}$ into an empirical price target.
   - If `state` or `analyst_posteriors` is absent, falling back to $1.15$ / $0.95$ maintains 100% backward compatibility with existing tests.

3. **R3 Memory Metadata & Circuit-Breaker**:
   - Adding mandatory keys `"market_regime"`, `"volatility_quintile"`, and `"brier_calibration_error"` in `_normalize_store_metadata()` and `_normalize_recall_filters()` equips memories with structured regime context.
   - Setting sensible defaults (`"sideways"`, $3$, $0.0$) ensures older callers that omit these keys will not raise exceptions.
   - When querying memory for the 5 target agents (`bull_researcher_v2`, `bear_researcher_v2`, `research_manager_v2`, `trader_v2`, `risk_manager_v2`), checking `regime_confidence`:
     * If $\ge 0.5$: filter out candidate memories where `stored_regime != current_regime`.
     * If $< 0.5$: bypass filtering to allow cross-regime memory recall during regime ambiguity.

4. **R3 Counterfactual Credit Assignment**:
   - A uniform scalar `returns_losses` conflates trade success with agent prediction quality.
   - By comparing an agent's directional stance $d_a$ with the realized return sign $y_{\text{sign}}$, and comparing $d_a$ with the manager's action $M$ ($\text{followed}_a$), we construct the 4-quadrant counterfactual attribution:
     * Q1: Vindicated & Followed ($+|R| \cdot \text{conf}$)
     * Q2: Vindicated & Overridden ($+|R|$ - counterfactual alpha)
     * Q3: Faulty & Followed ($-|R| \cdot \text{conf}$)
     * Q4: Faulty & Overridden ($-0.2 \cdot |R|$)
   - Injecting this attribution block into `tradingagents/graph/reflection.py` and `core/agents/reflection_prompts.py` resolves the multi-agent credit assignment problem.

---

## 3. Caveats

1. **Filename Casing**: The prompt references `core/agents/Reflection_prompts.py`, but the exact file on the Linux filesystem is `core/agents/reflection_prompts.py` (all lowercase). Import statements must use `core.agents.reflection_prompts`.
2. **MongoDB / Mem0 Environment in Tests**: In testing environments without a live MongoDB instance, `MemoryService` defaults to unavailable or memory fallback. Tests for R3 memory circuit-breaker should mock `MemoryService` or verify logic in `Mem0AgentMemory` client-side filtering.
3. **Pre-existing Failure in `test_memory_provider.py`**: A pre-existing whitespace mismatch exists in `tests/tradingagents/core/engine/test_memory_provider.py:49` (`\nKweichow` vs `\n Kweichow`). This is unrelated to R2/R3, but developers must avoid modifying that test unnecessarily.

---

## 4. Conclusion

The architectural investigation and design for R2 and R3 are complete:
1. `RegimeAdaptiveWeightCalculator` and Bayesian log-odds aggregation provide a principled, regime-sensitive alternative to static weights and hardcoded multipliers, with seamless fallback to `calculate_report_weights()` and $1.15$/$0.95$.
2. `Mem0AgentMemory` metadata normalization and regime circuit-breaker prevent regime contamination while preserving cross-regime memory when confidence $< 0.5$.
3. Counterfactual credit assignment replaces the uniform returns broadcast with a 4-quadrant attribution model that correctly credits ignored warnings and penalizes followed errors.
4. Comprehensive specifications and code blueprints have been documented in `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/survey_r2_r3.md`.

---

## 5. Verification Method

To verify the investigation and ensure the codebase remains clean:
1. **Inspect Survey Report**:
   `view_file` on `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/survey_r2_r3.md`
2. **Run Existing Tests**:
   ```bash
   .venv/bin/pytest tests/test_signal_processor_fix.py tests/test_target_price.py tests/core/agents/test_researcher_memory.py
   ```
   *Expected outcome: 5 passed in signal processor tests, 4 passed in researcher memory tests.*
3. **Invalidation Conditions**:
   - If `calculate_report_weights()` signature or return type changes, breaking backward compatibility.
   - If `SignalProcessor.process_signal()` fails when `state` is `None` or empty.
   - If `Mem0AgentMemory` rejects memories when mandatory metadata keys are not provided by legacy callers.
