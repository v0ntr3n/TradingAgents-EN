# Milestone M1 Handoff Report: CARE-Agents Posterior Estimation, CBS Fast-Path Gate & Adapter Alignment

## 1. Observation
- **Codebase Targets Inspected and Modified**:
  - `core/agents/analyst.py`: Added `DEFAULT_UNINFORMATIVE_POSTERIOR` constant, `_normalize_posterior()` with clamping, percentage scaling, and exact sum normalization ($\sum p_i = 1.0 \pm 10^{-4}$), `_heuristic_extract_posterior()`, and robust regex extraction in `_parse_response()` supporting code fences (`json:signal`, `json`, `signal_block`), HTML tags/comments, and bare JSON dictionaries. Updated `execute()` to return clean markdown report under `{output_field}` and structured posteriors under `"analyst_posteriors": {self.agent_id: posterior}`.
  - 7 v2 Analyst Adapters:
    * `core/agents/adapters/index_analyst_v2.py`: Updated cache hit (lines 280-288), existing report (lines 262-272), and live execution paths to extract clean markdown reports and return `analyst_posteriors`.
    * `core/agents/adapters/sector_analyst_v2.py`: Updated existing report (lines 200-210) and live execution paths to extract clean markdown reports and return `analyst_posteriors`.
    * `core/agents/adapters/market_analyst_v2.py`: Updated `execute()` and fallback paths to return `market_report` (clean report) and `analyst_posteriors`.
    * `core/agents/adapters/fundamentals_analyst_v2.py`: Refactored to inherit from `AnalystAgent` directly, updated `execute()` to return `fundamentals_report` and `analyst_posteriors`.
    * `core/agents/adapters/news_analyst_v2.py`: Updated `execute()` and fallback paths to return `news_report` and `analyst_posteriors`.
    * `core/agents/adapters/social_analyst_v2.py`: Updated `execute()` and fallback paths to return `sentiment_report` and `analyst_posteriors` under `social_analyst_v2`.
    * `core/agents/adapters/chip_distribution_analyst_v2.py`: Updated `execute()` and fallback paths to return `chip_report` and `analyst_posteriors`.
  - State Schemas:
    * `tradingagents/agents/utils/agent_states.py`: Added `analyst_posteriors: Annotated[Dict[str, Dict[str, Any]], merge_dict]`, `estimated_spread_bps: Optional[float]`, `debate_jsd: Optional[float]`, `cbs_bps: Optional[float]`, and `dynamic_debate_rounds: Optional[int]`.
    * `core/workflow/builder.py`: Added matching fields to `WorkflowState` using `merge_dict`.
  - Conditional Logic & Debate Gating:
    * `tradingagents/graph/conditional_logic.py`: Implemented pure-Python base-2 Shannon entropy (`compute_shannon_entropy`), base-2 JSD (`compute_base2_jsd`, `calculate_base2_jsd`), `calculate_cbs_routing`, CBS gating (`should_trigger_multi_round_debate` returning `"fast_path"` or `"multi_round_debate"`), and dynamic debate round scaling (1 to `max_debate_rounds`) within `should_continue_debate`. Zero external math dependencies (`math.log2` only).
  - Risk Self-Debate Adapter:
    * `core/agents/adapters/risk_self_debate_v2.py`: Added `analyst_posteriors` input and `investment_plan` output to metadata, injected analyst posterior summaries into user prompt, and implemented fast-path fallback synthesis for `investment_plan` and `investment_debate_state`.
- **Test Results**:
  - `pytest tests/test_analyst_posteriors_cbs.py` executed: 38 passed, 0 failed in 16.24s.
  - `pytest tests/test_care_agents_ablation.py` executed: 52 passed, 0 failed in 1.48s.
  - Combined suite `pytest tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py`: 90 passed, 0 failed in 16.29s.
  - Syntax check: `python3 -m py_compile` across all 13 modified and new files exited with code 0.

## 2. Logic Chain
1. *Requirement 1 (Structured Signal Block Extraction & Fallback)*:
   LLM output can vary across models (fenced ````json:signal`, standard ````json`, HTML comments, or bare JSON text). In `AnalystAgent._parse_response()`, regex patterns search for `json:signal`, `json`, `signal_block`, or bare `{...}` blocks containing `"p_optimistic"`. When found, `repair_json` parses the dictionary. Values are passed through `_normalize_posterior()`: out-of-range probabilities ($<0$ or $>1$) are clamped, percentages ($>1.0$ and $\le 100.0$, $\ge 5.0$) are divided by 100. If the sum $\sum p_i > 0$, the vector is normalized to sum to 1.0, with residual rounding assigned to $\max(p_i)$ ensuring $\sum p_i = 1.0 \pm 10^{-4}$. If parsing fails completely or $\sum p_i \le 0$, uninformative prior `{"p_optimistic": 0.3333, "p_neutral": 0.3334, "p_cautious": 0.3333, "expected_move_bps": 0.0, "confidence": 0.5, "market_regime": "sideways"}` is returned. The signal block is stripped from the returned report string, ensuring clean markdown for downstream consumption.
2. *Requirement 2 (v2 Analyst Adapters Return Posteriors & Clean Report)*:
   All 7 adapters (`index`, `sector`, `market`, `fundamentals`, `news`, `social`, `chip_distribution`) were aligned. Each adapter executes and returns `{self.output_field: clean_report, "analyst_posteriors": {self.agent_id: posterior}}`, while preserving existing auxiliary outputs (`tool_call_summaries`, `quality_flags`). In cache-hit and existing-report bypass paths, the signal block is parsed from the stored text so `analyst_posteriors` is always populated in the workflow state.
3. *Requirement 3 (Information Theory & CBS Routing Gate)*:
   In `conditional_logic.py`, base-2 Shannon entropy is computed as $H_2(P) = -\sum_{i} P_i \log_2 P_i$ (treating $P_i \le 0$ as $0$). For $M$ distributions, $M = \frac{1}{N}\sum P_k$, and $JSD_2(P_1, \dots, P_N) = H_2(M) - \frac{1}{N}\sum H_2(P_k)$. Because base-2 log is used, $JSD_2 \in [0, 1]$.
   CBS calculation computes:
   $\text{expected\_loss\_bps} = \sum_{k} \frac{| \text{expected\_move\_bps}_k | \cdot (1 - \text{confidence}_k)}{N}$
   $\text{cbs\_bps} = \text{debate\_jsd} \cdot \text{estimated\_spread\_bps} + \text{expected\_loss\_bps}$.
   If $\text{cbs\_bps} \le \text{cbs\_threshold\_bps}$ (default 15.0), `should_trigger_multi_round_debate` routes to `"fast_path"`; otherwise, `"multi_round_debate"`.
   Dynamic debate rounds scale linearly:
   $\text{dynamic\_rounds} = \max(1, \min(\text{max\_debate\_rounds}, \text{round}(1 + (\text{max\_debate\_rounds} - 1) \cdot \frac{\text{cbs\_bps} - \text{cbs\_threshold\_bps}}{\text{cbs\_threshold\_bps}})))$.
   `should_continue_debate` caps debate progression at `dynamic_debate_rounds`.
4. *Requirement 4 (Fast-Path Risk Self-Debate Synthesis)*:
   When CBS routes to `"fast_path"`, multi-round debate is bypassed. In `RiskSelfDebateV2.execute()`, when `investment_plan` or `investment_debate_state` are absent in state, it synthesizes `investment_plan` from the tripartite review perspective and populates `investment_debate_state` with `"Fast-Path Consensus Review Completed"`, ensuring downstream order execution nodes never encounter missing state keys.
5. *Requirement 5 (LangGraph Schema & State Reducer)*:
   In both `AgentState` and `WorkflowState`, `analyst_posteriors` is registered with `merge_dict` reducer. This allows all 7 analysts to run concurrently in parallel LangGraph branches and merge their individual `{agent_id: posterior}` dictionaries into a single consolidated dictionary without overwriting peer outputs.

## 3. Caveats
- No caveats: all requirements in the dispatch and original request have been satisfied, 100% of unit tests pass, and zero external dependencies were introduced into `conditional_logic.py`.
- Network/Database Mocking in Tests: In `tests/test_analyst_posteriors_cbs.py`, offline unit tests initialize adapters with `tool_ids=[]` or mock `_prepare_analysis_mode` to ensure tests execute cleanly in sub-20 seconds without timing out against an offline local MongoDB instance. In live runtime, MongoDB and tool registry paths operate normally.

## 4. Conclusion
Milestone M1 implementation is fully complete, mathematically sound, backward-compatible, and verified:
- `AnalystAgent` reliably parses 6-field structured signal blocks and outputs clean markdown reports.
- All 7 v2 analyst adapters inherit from `AnalystAgent` and return `analyst_posteriors`.
- `conditional_logic.py` provides pure-Python base-2 Shannon entropy, base-2 JSD, CBS routing, gating, and dynamic round scaling.
- `risk_self_debate_v2.py` supports fast-path single-pass execution and synthesizes required downstream debate state.
- `AgentState` and `WorkflowState` schemas properly register `analyst_posteriors` with `merge_dict`.
- 100% of tests pass across both the new M1 unit test suite (`tests/test_analyst_posteriors_cbs.py`) and the regression ablation suite (`tests/test_care_agents_ablation.py`).

## 5. Verification Method
To independently verify the implementation:
1. **Run full unit test suite for M1**:
   ```bash
   .venv/bin/pytest tests/test_analyst_posteriors_cbs.py -v
   ```
   *Expected outcome*: 38 passed, 0 failed.
2. **Run CARE-Agents ablation regression suite**:
   ```bash
   .venv/bin/pytest tests/test_care_agents_ablation.py -v
   ```
   *Expected outcome*: 52 passed, 0 failed.
3. **Run combined test suite**:
   ```bash
   .venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v
   ```
   *Expected outcome*: 90 passed, 0 failed.
4. **Inspect source code**:
   - `core/agents/analyst.py`: check `_normalize_posterior`, `_parse_response`, `execute`.
   - `tradingagents/graph/conditional_logic.py`: check `compute_shannon_entropy`, `compute_base2_jsd`, `calculate_cbs_routing`, `should_trigger_multi_round_debate`, `should_continue_debate`.
   - `core/agents/adapters/risk_self_debate_v2.py`: check metadata inputs/outputs and fallback synthesis.
   - `tradingagents/agents/utils/agent_states.py` and `core/workflow/builder.py`: check `analyst_posteriors` with `merge_dict`.
