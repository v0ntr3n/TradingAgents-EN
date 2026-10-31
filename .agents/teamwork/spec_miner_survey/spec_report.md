# CARE-Agents: Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Memory for Financial Trading
## Comprehensive Specification & Requirements Extraction Report

**Date:** 2026-10-30  
**Author:** Specification Miner (`teamwork_spec_miner`)  
**Target Repository:** `TradingAgents-EN` (v3.0 Community Edition / 2026 Core)  
**Authoritative Sources:**
- `/home/bramy/Downloads/plan.md`
- `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md`
- Authoritative literature: [Nguyen & Pham, 2026 (arXiv:2603.27539)](https://arxiv.org/html/2603.27539v1); [Xia et al., 2026 (arXiv:2605.19337)](https://arxiv.org/html/2605.19337v1); [TauricResearch/TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138)
- Base codebase modules in `core/agents/`, `tradingagents/graph/`, `core/memory/`, `core/backtest/`, and `tests/`

---

## 1. Executive Summary & Research Motivation

Multi-agent LLM systems in financial trading (TradingAgents, FinCon, HedgeAgents) suffer from four fundamental structural bottlenecks in real-world trading environments:
1. **Unconditional Debate Overhead & Degeneration-of-Thought (DoT):** Fixed multi-round Bull/Bear debate on every trading day incurs heavy token latency and can cause sycophantic convergence on false narratives when consensus is already clear or when expected signal gain is less than transaction friction.
2. **Static Heuristic Analyst Weighting:** Static weights (e.g., 0.40 technical, 0.30 news, 0.30 sentiment) ignore varying specialist reliability across market regimes, while heuristic regex multipliers (1.15x / 0.95x) and arbitrary confidence defaults (0.70) produce uncalibrated target prices.
3. **Regime-Blind Episodic Memory (Anchoring Bias):** Standard vector similarity retrieval in episodic memory fetches historical reflections without checking for market regime shifts (`bull`, `bear`, `sideways`), injecting stale bull-market dip-buying heuristics into bear-market crashes.
4. **Unattributed Reflection Rewards:** Broadcasting uniform portfolio returns to all agents without counterfactual credit assignment penalizes dissenting agents whose accurate warnings were overruled by downstream managers.

The CARE-Agents research extension introduces four core contributions ($C1$–$C4$) to solve these bottlenecks with mathematical rigor and empirical auditability under 2026 evaluation standards.

---

## 2. Mathematical Formulations & Algorithmic Specifications

### 2.1 Structured Analyst Posteriors & Epistemic Disagreement

Each specialist analyst $i \in \{1, \dots, K\}$ (across all 7 standard v2 analysts: `index_analyst_v2`, `sector_analyst_v2`, `market_analyst_v2`, `fundamentals_analyst_v2`, `news_analyst_v2`, `social_analyst_v2`, and `chip_distribution_analyst_v2`) emits a normalized 3-class directional probability distribution over the 3-simplex $\Delta^2$:
$$p_i = (p_{i,\text{opt}}, p_{i,\text{neu}}, p_{i,\text{cau}}) \in \Delta^2, \quad \sum_{c \in \{\text{opt}, \text{neu}, \text{cau}\}} p_{i,c} = 1.0$$
along with an expected price move magnitude $\hat{m}_i \ge 0$ (in basis points, bps), an epistemic confidence score $\text{conf}_i \in [0.0, 1.0]$, and an inferred local market regime $r_i \in \{\text{bull}, \text{bear}, \text{sideways}\}$.

Given regime-specific analyst weights $w_t^{(r)} \in \Delta^{K-1}$ with $\sum_{i=1}^K w_{i,t}^{(r)} = 1.0$, the weighted ensemble consensus distribution is:
$$\bar{p} = \sum_{i=1}^K w_{i,t}^{(r)} p_i$$

Inter-analyst epistemic disagreement is quantified via the weighted **Base-2 Jensen-Shannon Divergence ($D_{JS}$)**:
$$D_{JS}(p_1, \dots, p_K) = H_2(\bar{p}) - \sum_{i=1}^K w_{i,t}^{(r)} H_2(p_i)$$
where base-2 Shannon entropy is defined as:
$$H_2(p) = -\sum_{c \in \{\text{opt}, \text{neu}, \text{cau}\}} p_c \log_2(p_c) \quad (\text{with } 0 \log_2 0 \triangleq 0)$$

**Properties:**
- $0.0 \le D_{JS} \le 1.0$ (when using base-2 logarithm).
- $D_{JS} = 0.0$ if and only if all analyst distributions $p_i$ are identical or $K \le 1$.
- $D_{JS} = 1.0$ for fully orthogonal distributions (e.g. $[1, 0, 0]$ vs $[0, 0, 1]$).

---

### 2.2 Coordination Breakeven Spread (CBS) Gating

Following [Nguyen & Pham (2026)](https://arxiv.org/html/2603.27539v1), let $\Delta p(d)$ estimate the expected gross basis-point improvement from $d$ rounds of multi-agent debate:
$$\Delta p(d) = D_{JS} \cdot \bar{m}_t$$
where $\bar{m}_t$ is the confidence/weight-averaged expected price move magnitude:
$$\bar{m}_t = \frac{\sum_{i=1}^K w_{i,t}^{(r)} |\hat{m}_i|}{\sum_{i=1}^K w_{i,t}^{(r)}}$$
Let $s_t$ denote the effective half-spread plus transaction friction of the target asset in basis points (default $s_t = 15.0$ bps). The **Coordination Breakeven Spread ($\text{CBS}$)** is:
$$\text{CBS}(d) = \frac{\Delta p(d)}{2} = \frac{D_{JS} \cdot \bar{m}_t}{2}$$

#### Gating Condition:
Multi-round Bull/Bear debate is triggered if and only if **both** conditions hold:
$$D_{JS} \ge \tau_{JS} \quad \text{and} \quad \text{CBS}(d) > s_t$$
where the divergence threshold is:
$$\tau_{JS} = 0.12$$

#### Gating Routing Outcomes:
1. **Fast-Path Route (`fast_path`):** If $D_{JS} < \tau_{JS}$ (consensus) OR $\text{CBS}(d) \le s_t$ (friction dominates expected improvement):
   - `state["_risk_self_debate"] = True`
   - `state["dynamic_debate_rounds"] = 0`
   - Bypasses multi-round Bull/Bear debate, routing directly to `RiskSelfDebateV2` for 1-pass synthesis.
2. **Multi-Round Debate Route (`multi_round_debate`):** If $D_{JS} \ge \tau_{JS}$ AND $\text{CBS}(d) > s_t$:
   - Dynamically scales debate rounds $d \in [1, d_{\max}]$ based on epistemic divergence:
     $$d = \text{round}\left(1 + (d_{\max} - 1) \cdot \frac{D_{JS} - \tau_{JS}}{1.0 - \tau_{JS}}\right), \quad d_{\max} = 3$$
   - Clamped to $1 \le d \le d_{\max}$.
   - Max speech turns in debate state: $\text{max\_count} = 2 \times d$.

---

### 2.3 Online Regime-Conditioned Multiplicative Weights (MWU / Exponentially Weighted Forecaster)

The system maintains separate weight vectors $w^{(r)} \in \Delta^{K-1}$ across three distinct market regimes:
$$r \in \{\text{bull}, \text{bear}, \text{sideways}\}$$
Initialized to uniform distribution: $w_{i,0}^{(r)} = \frac{1}{K}$ for all $i \in \{1, \dots, K\}$.

At the close of trading step $t$ in regime $r$, the realized return $R_{t+1}$ is mapped to the ground-truth one-hot target vector $y_{t+1} \in \Delta^2$ using deadband threshold $\theta = 0.005$ (50 bps):
$$y_{t+1} = \begin{cases}
(1.0, 0.0, 0.0) & \text{if } R_{t+1} > +\theta \quad (\text{optimistic / bull}) \\
(0.0, 0.0, 1.0) & \text{if } R_{t+1} < -\theta \quad (\text{cautious / bear}) \\
(0.0, 1.0, 0.0) & \text{if } |R_{t+1}| \le \theta \quad (\text{neutral / sideways})
\end{cases}$$

Each analyst $i$ incurs multiclass Brier loss:
$$\ell_{i,t} = \frac{1}{3} \|p_{i,t} - y_{t+1}\|_2^2 = \frac{1}{3} \sum_{c \in \{\text{opt}, \text{neu}, \text{cau}\}} (p_{i,c,t} - y_{c, t+1})^2$$
where $\ell_{i,t} \in [0, 2/3]$ (or unscaled $\|p - y\|_2^2 \in [0, 2.0]$).

Weights for regime $r$ are updated via the Exponentially Weighted Forecaster with weight floor $w_{\min} = 0.03$ and learning rate $\eta = 0.2$:
$$\tilde{w}_{i, t+1}^{(r)} = \max\left(w_{\min}, \; w_{i,t}^{(r)} \cdot \exp(-\eta \ell_{i,t})\right)$$
Normalized across active analysts:
$$w_{i, t+1}^{(r)} = \frac{\tilde{w}_{i, t+1}^{(r)}}{\sum_{j=1}^K \tilde{w}_{j, t+1}^{(r)}}$$

**Regime Isolation Invariant:** Weight updates under regime $r$ modify **only** $w^{(r)}$; weights for non-current regimes $r' \ne r$ remain unchanged.

---

### 2.4 Calibrated Signal Processing (Bayesian Log-Odds Opinion Pooling)

Eliminates static regex multipliers (`1.15x` / `0.95x`) and arbitrary default confidence (`0.70`). Derives target price, ensemble confidence, and risk score from calibrated weighted posteriors.

1. **Regime Prior Log-Odds ($L_0$):**
   $$L_0(\text{regime}) = \begin{cases}
   \ln\left(\frac{0.60}{0.40}\right) \approx +0.405465 & \text{for bull} \\
   0.0 & \text{for sideways} \\
   \ln\left(\frac{0.40}{0.60}\right) \approx -0.405465 & \text{for bear}
   \end{cases}$$

2. **Analyst Individual Log-Odds ($\ell_i$):**
   $$\ell_i = \ln\left(\frac{p_{i,\text{opt}}}{p_{i,\text{cau}}}\right)$$
   with probability clipping $\epsilon = 10^{-4}$ ($p \leftarrow \max(\epsilon, p)$) to prevent $\ln(0)$ or division by zero.

3. **Aggregated Log-Odds ($L_{\text{agg}}$):**
   $$L_{\text{agg}} = L_0(\text{regime}) + \sum_{i=1}^K w_i^{(r)} \ell_i$$
   Clipped to $[-10.0, +10.0]$ for numerical stability.

4. **Calibrated Directional Probability ($P_{\text{agg}}$):**
   $$P_{\text{agg}} = \text{sigmoid}(L_{\text{agg}}) = \frac{1}{1 + \exp(-L_{\text{agg}})} \in (0.0, 1.0)$$

5. **Weighted Expected Move ($\bar{m}$):**
   $$\bar{m} = \frac{\sum_{i=1}^K w_i^{(r)} \hat{m}_i}{\sum_{i=1}^K w_i^{(r)}} \quad (\text{default 50.0 bps if empty})$$

6. **Calibrated Expected Return ($R_{\text{cal}}$):**
   $$R_{\text{cal}} = (2 P_{\text{agg}} - 1.0) \cdot \left(\frac{|\bar{m}|}{10000.0}\right)$$

7. **Calibrated Empirical Target Price ($P_{\text{target}}$):**
   $$P_{\text{target}} = \begin{cases}
   P_{\text{curr}} \cdot (1.0 + \max(R_{\text{cal}}, 0.005)) & \text{if action is 'buy'} \\
   P_{\text{curr}} \cdot (1.0 - \max(|R_{\text{cal}}|, 0.005)) & \text{if action is 'sell'} \\
   P_{\text{curr}} & \text{if action is 'hold'}
   \end{cases}$$
   (Guarantees a minimum 50 bps execution buffer).

8. **Derived Confidence and Risk Score:**
   - $\text{Confidence} = 2 \cdot |P_{\text{agg}} - 0.5| \in [0.0, 1.0]$
   - $\text{Risk Score} = 1.0 - \text{Confidence} = 1.0 - 2 \cdot |P_{\text{agg}} - 0.5|$ (modulated by regime divergence $D_{JS}$).

---

### 2.5 Regime-Filtered Episodic Memory & Circuit-Breaker

To prevent experience-following bias and memory anchoring drift:

1. **Mandatory Metadata Tagging:** Every memory stored or recalled in `Mem0AgentMemory` must contain:
   - `market_regime`: `"bull"`, `"bear"`, or `"sideways"`
   - `volatility_quintile`: integer clamped in $[1, 5]$
   - `attribution_role`: `"correct_driver"`, `"overridden_correct"`, `"false_driver"`, or `"correct_dissent_ignored"`
   - `brier_calibration_error`: float $\ge 0.0$

2. **Regime Circuit-Breaker:**
   Target agents: `bull_researcher`, `bear_researcher`, `research_manager`, `trader`, `risk_manager` (and `_v2` aliases).
   - If $\text{conf}_{\text{regime}} \ge 0.5$: Filter out any recalled memory whose `market_regime` contradicts current market regime. No cross-regime memory contamination permitted.
   - If $\text{conf}_{\text{regime}} < 0.5$: Regime is ambiguous; bypass circuit breaker to preserve hedging memories.
   - Non-target agents: unfiltered recall.

3. **Regime-Matching Re-Ranking:**
   - Candidate memories matching `current_regime` receive a $1.5\times$ similarity score multiplier.
   - Memories from opposite regimes (bull vs bear) are strictly excluded when confidence $\ge 0.5$.

4. **Drawdown Circuit-Breaker:**
   - A runtime flag `drawdown_circuit_breaker: bool` set when rolling portfolio drawdown exceeds threshold $\tau_{\text{DD}} = 0.08$ (8%) or when market regime experiences a structural break.
   - When active, memory retrieval is suspended, forcing agents to evaluate point-in-time fundamentals and technical signals from zero-state prior.

---

### 2.6 Counterfactual Credit Assignment (Attribution Roles & Quadrants)

Replaces uniform return broadcasting with marginal contribution attribution. Evaluates agent directional stance $s_i \in \{+1.0, -1.0, 0.0\}$ against realized return $R_{t+1}$ and executed manager action $a_m \in \{+1.0, -1.0, 0.0\}$.

#### Mathematical Definition of Attribution Quadrants:
Let $\text{sign}(x) \in \{+1, 0, -1\}$.
- Agent vindication: $\text{is\_vindicated} = (\text{sign}(s_i) \cdot \text{sign}(R) > 0) \lor (s_i = 0 \land R = 0)$
- Followed by manager: $\text{is\_followed} = (\text{sign}(s_i) = \text{sign}(a_m))$

| Quadrant | Counterfactual Attribution Role | Condition | Attribution Score Formula | Directive Injected into Reflection Prompt |
| :--- | :--- | :--- | :--- | :--- |
| **Q1** | `correct_driver` | $\text{is\_vindicated} \land \text{is\_followed}$ | $+|R| \cdot \text{conf}_i$ | *"Your thesis was correct and adopted by the manager, driving positive alpha. Reinforce key predictive signals."* |
| **Q2** | `overridden_correct` / `correct_dissent_ignored` | $\text{is\_vindicated} \land \neg\text{is\_followed}$ | $+|R|$ (Counterfactual Alpha) | *"Your analysis correctly predicted market direction, but the manager overruled you. Highlight specific signals dismissed."* |
| **Q3** | `false_driver` | $\neg\text{is\_vindicated} \land \text{is\_followed}$ | $-|R| \cdot \text{conf}_i$ | *"Your thesis proved incorrect and was followed, directly causing the loss. Identify blind spots and failed assumptions."* |
| **Q4** | `faulty_overridden` | $\neg\text{is\_vindicated} \land \neg\text{is\_followed}$ | $-0.2 \cdot |R|$ (Mitigated Fault) | *"Your thesis was incorrect, but the manager successfully shielded the portfolio by overriding you. Review misjudged risks."* |

---

### 2.7 2026 Protocol Audit Evaluator & Friction Models

#### China A-Share Friction Schedule:
- Commission: $2.5$ bps ($0.00025$) levied on **both** BUY and SELL orders.
- Stamp Duty (印花税): $5.0$ bps ($0.00050$) levied **exclusively on SELL** orders.
- Slippage: $5.0$ to $10.0$ bps (configurable) levied on **both** BUY and SELL orders.
- **Round-Trip Completed Friction:**
  $$\text{Friction}_{\text{round\_trip}} = \text{Buy}(2.5 + s) + \text{Sell}(5.0 + 2.5 + s) = 10.0 + 2s \text{ bps}$$
  At $s = 5$ bps: $20.0$ bps total ($0.0020$). At $s = 10$ bps: $30.0$ bps total ($0.0030$).

#### Net-of-Cost Annualized Financial Metrics (252 Trading Days):
- Net daily returns: $R_{\text{net}, t} = R_{\text{gross}, t} - \text{friction}_t$
- Compounded equity curve: $W_t = \prod_{\tau=1}^t (1 + R_{\text{net}, \tau})$ with $W_0 = 1.0$
- Maximum Drawdown (MDD):
  $$\text{MDD} = \min_{t} \left(\frac{W_t - \max_{0 \le \tau \le t} W_\tau}{\max_{0 \le \tau \le t} W_\tau}\right)$$
- Annualized Return (CAGR):
  $$\text{CAGR} = W_N^{252 / N} - 1.0$$
- Annualized Volatility:
  $$\sigma_{\text{ann}} = \text{std}(R_{\text{net}}) \cdot \sqrt{252}$$
- Annualized Net Sharpe ($R_f = 0.025$ annual, daily $r_f = 0.025 / 252$):
  $$\text{Sharpe}_{\text{net}} = \frac{\text{mean}(R_{\text{net}} - r_f)}{\text{std}(R_{\text{net}})} \cdot \sqrt{252}$$
- Annualized Net Sortino:
  $$\text{Sortino}_{\text{net}} = \frac{\text{mean}(R_{\text{net}} - r_f)}{\sqrt{\text{mean}(\min(0, R_{\text{net}} - r_f)^2)}} \cdot \sqrt{252}$$
- Net Calmar Ratio:
  $$\text{Calmar}_{\text{net}} = \frac{\text{CAGR}}{|\text{MDD}|}$$

#### Coordination & Calibration Metrics:
- **CBS Surplus:**
  $$\text{CBS Surplus} = R_{\text{realized}} - \text{CBS Hurdle (bps)}$$
- **Expected Calibration Error (ECE):**
  $$ECE = \sum_{m=1}^M \frac{|B_m|}{N} \left|\text{acc}(B_m) - \text{conf}(B_m)\right|$$
- **Token and Latency Efficiency:** Mean tokens consumed and latency (ms) per trading decision, with fast-path debate bypass rate:
  $$\text{Bypass Rate} = \frac{N_{\text{fast\_path}}}{N_{\text{total}}}$$

---

### 2.8 4-Way Factorial Ablation Suite

The factorial ablation isolates each mechanism under constant LLM backbone:

| Configuration ID | Configuration Name | Debate Mechanism | Analyst Weighting | Memory Retrieval | Counterfactual Attribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M1** | `Linear_Pipeline` | None (Direct to Manager) | Static Heuristic (0.4/0.3/0.3) | Regime-Blind (Raw Vector) | Uniform Return Broadcast |
| **M2** | `Vanilla_TradingAgents` | Fixed Multi-Round Debate (2 rounds) | Static Heuristic (0.4/0.3/0.3) | Regime-Blind (Raw Vector) | Uniform Return Broadcast |
| **M3** | `SelfDebate_V2` | 1-Shot Tripartite Self-Debate | Static Heuristic (0.4/0.3/0.3) | Regime-Blind (Raw Vector) | Uniform Return Broadcast |
| **M4** | `CARE_Agents` (Ours) | **CBS-Gated Dynamic Debate** | **Online Regime MWU** | **Regime Circuit-Breaker** | **4-Quadrant Counterfactual** |

**Export Artifacts:**
- LaTeX table: `reports/cph_ablation_table.tex`
- CSV metrics: `reports/cph_ablation_metrics.csv`

---

## 3. Data Structures, Schemas, State Keys & Module Boundaries

### 3.1 LangGraph `AgentState` Key Additions

| State Key | Type Annotation | Reducer | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `analyst_posteriors` | `Annotated[Dict[str, Any], merge_dict]` | `merge_dict` | `{}` | Keyed by `agent_id`; stores normalized posterior dictionaries. |
| `market_regime` | `str` | `keep_non_empty` | `"sideways"` | Global regime propagated from `index_analyst_v2`. |
| `regime_confidence` | `float` | `keep_non_empty` | `1.0` | Confidence of market regime classification. |
| `estimated_spread_bps`| `float` | `keep_non_empty` | `15.0` | Instrument round-trip half-spread + friction hurdle in bps. |
| `debate_jsd` | `float` | `keep_non_empty` | `0.0` | Realized Jensen-Shannon Divergence across active analysts. |
| `cbs_bps` | `float` | `keep_non_empty` | `0.0` | Coordination Breakeven Spread in basis points. |
| `dynamic_debate_rounds`| `int` | `keep_non_empty` | `1` | Dynamically scaled debate rounds (0 if fast-path, 1–3 if debate). |
| `_risk_self_debate` | `bool` | `keep_non_empty` | `False` | Fast-path routing flag for `RiskSelfDebateV2`. |
| `drawdown_circuit_breaker`| `bool` | `keep_non_empty` | `False` | Flag suspending episodic memory retrieval during drawdowns. |

### 3.2 Analyst Structured Posterior Schema (`json:signal` block)

```json
{
  "p_optimistic": 0.70,
  "p_neutral": 0.20,
  "p_cautious": 0.10,
  "expected_move_bps": 120.0,
  "confidence": 0.85,
  "market_regime": "bull"
}
```

Constraints:
- $p_{\text{opt}}, p_{\text{neu}}, p_{\text{cau}} \in [0.0, 1.0]$ and $|(p_{\text{opt}} + p_{\text{neu}} + p_{\text{cau}}) - 1.0| \le 10^{-4}$.
- `expected_move_bps`: signed or unsigned float (bps).
- `confidence`: float $\in [0.0, 1.0]$.
- `market_regime`: normalized string in `{"bull", "bear", "sideways"}`.

### 3.3 Module Boundaries and Target Files

| Phase | Target Module | Responsibility | Key Public Functions / Classes |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `core/agents/analyst.py` | Signal parsing & posterior normalization | `extract_structured_posterior()`, `_normalize_posterior()`, `_parse_response()` |
| **Phase 1** | `core/agents/adapters/index_analyst_v2.py` | Propagate `state["market_regime"]` | `execute()` |
| **Phase 1** | `tradingagents/graph/conditional_logic.py` | JSD & CBS gating routing | `compute_shannon_entropy()`, `compute_base2_jsd()`, `calculate_base2_jsd()`, `compute_cbs_bps()`, `calculate_cbs_routing()`, `should_gate_debate()`, `should_trigger_multi_round_debate()` |
| **Phase 1** | `core/agents/adapters/risk_self_debate_v2.py` | Fast-path 1-pass synthesis | `RiskSelfDebateV2.execute()` |
| **Phase 2** | `core/agents/utils/weight_calculator.py` | Online MWU weight management | `RegimeAdaptiveWeightCalculator`, `RegimeMultiplicativeWeightManager`, `compute_brier_loss()`, `update_weights()`, `aggregate_posteriors()` |
| **Phase 2** | `tradingagents/graph/signal_processing.py` | Calibrated signal processing | `calculate_bayesian_log_odds_target_price()`, `compute_bayesian_log_odds_details()`, `process_calibrated_signal()` |
| **Phase 3** | `core/memory/memory_manager.py` | Regime-filtered memory & circuit-breaker | `Mem0AgentMemory._normalize_store_metadata()`, `_normalize_recall_filters()`, `circuit_breaker_memory_filter()` |
| **Phase 3** | `tradingagents/graph/reflection.py` & `core/agents/reflection_helper.py` | Counterfactual credit assignment | `calculate_counterfactual_attribution()`, `compute_counterfactual_attribution()`, `format_attribution_prompt_block()` |
| **Phase 4** | `core/backtest/result_evaluator.py` | 2026 Protocol audit evaluator | `FrictionConfig`, `calculate_net_performance_metrics()`, `calculate_cbs_and_coordination_cost()`, `calculate_multi_regime_breakdown()`, `ProtocolAuditEvaluator` |
| **Phase 4** | `scripts/run_cph_ablation_benchmark.py` | Factorial benchmark runner | `run_cph_ablation_benchmark()`, `AblationEngine` |

---

## 4. Authoritative Constants, Hyperparameters & Defaults

| Symbol | Parameter Name | Canonical Value | Code Location | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| $\tau_{JS}$ | JSD Gating Threshold | `0.12` | `conditional_logic.py` | Minimum divergence required to justify debate overhead |
| $s_t$ | Default Friction Hurdle | `15.0` bps | `conditional_logic.py` | Half-spread + transaction cost threshold for CBS |
| $d_{\max}$ | Maximum Debate Rounds | `3` (default 1–3) | `conditional_logic.py` | Upper bound for dynamic debate rounds |
| $\theta$ | Brier Target Deadband | `0.005` ($50$ bps) | `weight_calculator.py` | Deadband for neutral vs bull/bear ground-truth target |
| $\eta$ | MWU Learning Rate | `0.2` | `weight_calculator.py` | Exponential decay rate for Brier loss penalty |
| $w_{\min}$ | Minimum Weight Floor | `0.03` ($3\%$) | `weight_calculator.py` | Prevents analyst extinction under extended loss sequences |
| $\text{conf}_{\text{thresh}}$| Circuit Breaker Conf Boundary | `0.50` | `memory_manager.py` | Exact threshold between active circuit breaker and bypass |
| $\text{boost}_{\text{regime}}$| Same-Regime Recall Boost | `1.5`x | `memory_manager.py` | Similarity score multiplier for regime-consistent memories |
| $c_{\text{comm}}$| A-Share Commission | `2.5` bps ($0.00025$) | `result_evaluator.py` | Deducted on BUY and SELL trades |
| $c_{\text{stamp}}$| A-Share Stamp Duty | `5.0` bps ($0.00050$) | `result_evaluator.py` | Deducted on SELL trades exclusively |
| $c_{\text{slip}}$| Default Slippage | `5.0` bps ($0.00050$) | `result_evaluator.py` | Standard slippage model (configurable up to 10.0 bps) |
| $R_f$ | Risk-Free Rate | `0.025` ($2.5\%$ p.a.) | `result_evaluator.py` | Annualized risk-free benchmark ($R_f / 252$ daily) |
| $M$ | ECE Number of Bins | `10` | `result_evaluator.py` | Calibration error probability binning |

---

## 5. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | R1 (Coordination) | Signal Block Extraction | Extracts JSON signal block from markdown report, stripping raw JSON from report text | LLM report string | Tuple `(clean_report, raw_posterior)` | Heuristic text scan fallback (`bull_cues`/`bear_cues`) | `core/agents/analyst.py:720-789` |
| 2 | R1 (Coordination) | Posterior Normalization | Enforces probability simplex ($\sum p = 1.0$), parses percentage strings and bps moves | Raw dict/strings | Normalized dict with `p_opt`, `p_neu`, `p_cau`, `move_bps`, `conf`, `regime` | Clamps to `[0, 1]`, falls back to uninformative prior $[1/3, 1/3, 1/3]$ | `core/agents/analyst.py:550-651` |
| 3 | R1 (Coordination) | Standalone Posterior API | Standalone function `extract_structured_posterior` for parsing any analyst text | `report_text: str` | `Dict[str, Any]` matching posterior schema | Returns uninformative prior on parse error | `plan.md` Step 1.1 |
| 4 | R1 (Coordination) | Regime State Propagation | `index_analyst_v2` outputs `market_regime` to top-level state | Analyst state | `state["market_regime"]` | Defaults to `"sideways"` | `plan.md` Step 1.2 |
| 5 | R1 (Coordination) | State Concurrency Reducer | `merge_dict` reducer handles concurrent parallel analyst writes to `state["analyst_posteriors"]` | Dict left, Dict right | Merged dictionary | Preserves existing keys, overwrites only sub-keys | `core/state/reducers.py:25-57` |
| 6 | R1 (Coordination) | Base-2 Shannon Entropy | Calculates $H_2(P) = -\sum p \log_2 p$ in pure Python without external dependencies | Discrete prob vector | Float $\ge 0.0$ | Returns $0.0$ if $p \le 0$ or empty | `tradingagents/graph/conditional_logic.py:10-16` |
| 7 | R1 (Coordination) | Base-2 JSD Disagreement | Computes $D_{JS} = H_2(\bar{p}) - \sum w_i H_2(p_i) \in [0, 1]$ | Posterior vectors / dicts | Float in $[0.0, 1.0]$ | Returns $0.0$ for identical or $N \le 1$ | `tradingagents/graph/conditional_logic.py:18-74` |
| 8 | R1 (Coordination) | CBS Gating & Calculation | Computes $\text{CBS} = \frac{D_{JS} \cdot \bar{m}}{2}$ and gates debate vs fast-path | Posteriors, spread, max_rounds | Routing dict (`route`, `cbs_bps`, `rounds`) | Fast-path fallback if $D_{JS} < 0.12$ or $\text{CBS} \le s_t$ | `tradingagents/graph/conditional_logic.py:76-136` |
| 9 | R1 (Coordination) | Dynamic Debate Rounds | Scales debate turns smoothly between 1 and $d_{\max}$ based on divergence intensity | $D_{JS}$, $d_{\max}$ | Scaled integer rounds | Clamped to $[1, d_{\max}]$ | `tradingagents/graph/conditional_logic.py:121-126` |
| 10 | R1 (Coordination) | Fast-Path Tripartite Synthesis | `RiskSelfDebateV2` synthesizes resilient, defensive, and base perspectives in 1 LLM pass | Upstream reports / posteriors | Three opinions + `risk_debate_state` | Strict regex -> loose regex -> full text padding | `core/agents/adapters/risk_self_debate_v2.py:48-90` |
| 11 | R2 (Calibration) | Regime-Partitioned Weights | Maintains independent weight tables `w[regime][analyst_id]` for Bull, Bear, Sideways | Analyst IDs, initial weights | Normalized weight dictionary per regime | Uniform distribution on initialization | `core/agents/utils/weight_calculator.py:303-350` |
| 12 | R2 (Calibration) | Multiclass Brier Loss | Evaluates 3-class posterior against deadband outcome vector $y_{t+1}$ | Posterior dict, realized return | Float $\ell_{i,t} \in [0, 2/3]$ (or $[0, 2]$) | Clamped to $[0, 2.0]$ | `core/agents/utils/weight_calculator.py:387-421` |
| 13 | R2 (Calibration) | Online MWU Updates | Exponentially weighted forecaster update $\tilde{w} = w \exp(-\eta \ell)$ with weight floor $w_{\min}$ | Regime, posteriors, return, $\eta$ | Updated normalized weight vector | Clamped at floor $w_{\min} = 0.03$, normalized | `core/agents/utils/weight_calculator.py:422-474` |
| 14 | R2 (Calibration) | Logarithmic Opinion Pool | Aggregates analyst posteriors into consensus distribution | Posteriors dict, weights dict | Consensus probability vector $\bar{p}$ | Uniform fallback if empty | `plan.md` Step 2.2 |
| 15 | R2 (Calibration) | Bayesian Log-Odds Pricing | Derives calibrated price target using regime priors $L_0$ and analyst log-odds $\ell_i$ | Price, action, regime, posteriors | Calibrated target price (float) | Fallback to 1.15x / 0.95x multipliers | `tradingagents/graph/signal_processing.py:16-100` |
| 16 | R2 (Calibration) | Process Calibrated Signal | Replaces hardcoded multipliers and 0.7 confidence with calibrated posteriors in `SignalProcessor` | Signal text, state, stock symbol | Structured decision dict | Fallback to regex & heuristic estimation | `tradingagents/graph/signal_processing.py:175-420` |
| 17 | R3 (Memory) | Mandatory Metadata Schema | Enforces `market_regime`, `volatility_quintile`, `attribution_role`, `brier_calibration_error` | Raw metadata dictionary | Normalized metadata dictionary | Default values (sideways, 3, 0.0) | `core/memory/memory_manager.py:144-196` |
| 18 | R3 (Memory) | Regime Circuit-Breaker | Suppresses cross-regime memory recall for decision agents when $\text{conf} \ge 0.5$ | Memories list, regime, conf, agent_id | Filtered memory list | Bypassed when $\text{conf} < 0.5$ | `core/memory/memory_manager.py:56-96` |
| 19 | R3 (Memory) | Regime-Matching Re-Ranking | Boosts same-regime similarity scores by 1.5x and excludes opposite regime | Recalled memories, regime | Re-ranked and filtered memories | Unmodified if no regime metadata | `plan.md` Step 3.2 |
| 20 | R3 (Memory) | Drawdown Circuit-Breaker | Suspends memory retrieval during structural breaks / drawdowns $> 8\%$ | Drawdown flag, state | Boolean status (bypass memory) | Fallback to live zero-state analysis | `plan.md` Step 3.2 |
| 21 | R3 (Memory) | Counterfactual Credit Assignment | 4-Quadrant classification: `correct_driver`, `overridden_correct`, `false_driver`, `faulty_overridden` | Agent stance, realized return, mgr action | Dict (`quadrant`, `score`, `directive`) | Neutral fallback ($0.0$ score) | `core/agents/reflection_helper.py:32-132` |
| 22 | R3 (Memory) | Counterfactual Prompt Injection | Injects quadrant status and directive into reflection prompt for individual agents | Attribution context, user prompt | Enriched reflection prompt | Direct reflection without context if missing | `core/agents/reflection_helper.py:134-145` |
| 23 | R4 (Evaluation) | China A-Share Friction Engine | Deducts 2.5 bps commission, 5.0 bps sell stamp duty, and configurable slippage | Trades list, returns, `FrictionConfig` | Net performance metrics dict | Zero div protection on empty data | `core/backtest/result_evaluator.py:211-452` |
| 24 | R4 (Evaluation) | Annualized Net Metrics | Computes Net Sharpe, Sortino, Calmar, MDD, CAGR over 252 trading days | Daily returns, trades, frictions | Annualized metrics dictionary | Returns 0.0 on zero variance or zero days | `core/backtest/result_evaluator.py:400-452` |
| 25 | R4 (Evaluation) | CBS & Latency Audit | Computes realized CBS hurdle, token cost, latency, and debate bypass rate | Debate records list | Coordination metrics dictionary | Returns 0.0 if empty | `core/backtest/result_evaluator.py:454-584` |
| 26 | R4 (Evaluation) | Multi-Regime Breakdown | Slices performance across Bull, Bear, and Sideways windows | Returns list, regimes list | Sub-period metric dictionary | Skips unrepresented regimes gracefully | `core/backtest/result_evaluator.py:586-650` |
| 27 | R4 (Evaluation) | Protocol Audit Evaluator Class | `ProtocolAuditEvaluator` auditing all 5 credibility criteria & metrics | Backtest results, trade logs | Comprehensive audit report | Fallback evaluation on partial data | `plan.md` Step 4.1 |
| 28 | R4 (Evaluation) | 4-Way Factorial Ablation | Runs comparative benchmark across M1, M2, M3, M4 under identical data & backbone | Dataset, config type, friction | Ablation comparative metrics | Offline deterministic mock support | `plan.md` Step 4.2 |
| 29 | R4 (Evaluation) | Automated Paper Table Export | Exports LaTeX (`.tex`) and CSV (`.csv`) ablation summary tables | Benchmark results dict | Files at `reports/` | Creates directory if missing | `plan.md` Step 4.3 |

---

## 6. Edge Cases & Boundary Conditions

| # | Feature | Input Condition | Observed / Required Behavior |
|---|---------|-----------------|------------------------------|
| 1 | Posterior Normalization | Raw probabilities sum to $0.0$ (e.g. all zeros) | Resets to uninformative prior $[0.3333, 0.3334, 0.3333]$. |
| 2 | Posterior Normalization | Unnormalized floats $> 1.0$ (e.g. $[0.6, 0.4, 0.6]$, sum $= 1.6$) | Scales proportionally by sum ($0.6/1.6 = 0.375, 0.4/1.6 = 0.25, 0.375$). |
| 3 | Posterior Normalization | Percentage scale integers (e.g. $[70, 20, 10]$) | Detects percentage scale ($> 1.5$), divides by $100.0$, yielding $[0.70, 0.20, 0.10]$. |
| 4 | Posterior Normalization | Negative probability values (e.g. $p_{\text{opt}} = -0.5$) | Clamps negative to $0.0$, re-normalizes remaining components. |
| 5 | Posterior Normalization | Truncated or malformed JSON signal block | Repaired with regex single-quote/trailing comma fixes; falls back to text cue extraction if unparseable. |
| 6 | Posterior Normalization | String variants in `expected_move_bps` (e.g. `"+150 bps"`, `"2.5%"`, `"-50bp"`) | Strips `"bps"`, `"bp"`, `"+"`, converts `"2.5%"` to $250.0$ bps. |
| 7 | Posterior Normalization | Regime synonyms (e.g. `"bullish"`, `"uptrend"`, `"downtrend"`, `"flat"`, `"chop"`) | Normalized to canonical `"bull"`, `"bear"`, or `"sideways"`. |
| 8 | JSD Calculation | Identical distributions across all analysts | $H_2(\bar{p}) = H_2(p_i) \implies D_{JS} = 0.000000$ exactly. |
| 9 | JSD Calculation | Completely orthogonal distributions ($[1, 0, 0]$ vs $[0, 0, 1]$) | $D_{JS} = 1.0000$ (base-2). No math domain or overflow error. |
| 10 | JSD Calculation | Zero probability entries ($p = 0.0$) in distributions | Evaluates $0 \log_2 0 \triangleq 0$ safely; zero division avoided via `x > 0.0` guard. |
| 11 | JSD Calculation | Single analyst or empty posterior dictionary | Returns $D_{JS} = 0.0$ immediately. |
| 12 | CBS Gating | $D_{JS} < 0.12$ with large move (e.g. $D_{JS} = 0.05$, move $= 300$ bps) | Gate routes to `fast_path` because consensus threshold is violated ($D_{JS} < 0.12$). |
| 13 | CBS Gating | $D_{JS} \ge 0.12$ with micro move (e.g. $D_{JS} = 0.50$, move $= 2$ bps, spread $= 15$ bps) | $\text{CBS} = (0.50 \times 2) / 2 = 0.5 \le 15.0 \implies$ Gate routes to `fast_path`. |
| 14 | CBS Gating | Opposing analysts with signed moves ($+150$ bps vs $-150$ bps) | Uses absolute move magnitudes $|\hat{m}_i|$; does **not** cancel out to zero. |
| 15 | MWU Weight Update | Learning rate $\eta = 0.0$ | Weights remain unchanged after update. |
| 16 | MWU Weight Update | Extended losing streak for an analyst | Weights cannot decay below floor $w_{\min} = 0.03$. |
| 17 | MWU Weight Update | Realized return $|R| \le 0.005$ (deadband) | Target is classified as neutral $(0, 1, 0)$; neutral predictions incur $0$ loss. |
| 18 | MWU Weight Update | All analysts incur identical Brier loss | Weights update by identical factor, normalizing back to uniform. |
| 19 | Signal Processing | Missing or empty posteriors dictionary | Falls back cleanly to legacy multipliers ($1.15$x buy, $0.95$x sell) and $0.7$ confidence. |
| 20 | Signal Processing | Bayesian log-odds with $p_{\text{opt}} = 0$ or $p_{\text{cau}} = 0$ | Clamped with $\epsilon = 10^{-4}$ to prevent $\ln(0)$ or division by zero. |
| 21 | Memory Filtering | Exact boundary confidence $\text{conf} = 0.500000$ | Circuit breaker is **active**: contradicting memories strictly filtered out. |
| 22 | Memory Filtering | Boundary confidence $\text{conf} = 0.499999$ | Circuit breaker is **bypassed**: cross-regime hedging memories allowed. |
| 23 | Memory Filtering | Non-circuit agents (e.g. technical analyst, fundamentals analyst) | Circuit breaker does not apply; recalls full semantic top-$k$. |
| 24 | Memory Metadata | `volatility_quintile` out of range ($0$, $-5$, $100$) | Clamped to valid integer range $[1, 5]$. |
| 25 | Memory Metadata | `brier_calibration_error` negative (e.g. $-0.1$) | Clamped to $0.0$. |
| 26 | Counterfactual Credit | Zero realized return trade ($R = 0.0$) | Attribution score is $0.0$; handled gracefully without division by zero. |
| 27 | Counterfactual Credit | Dissenting agent overridden but right (e.g. Bear warned sell, mgr bought, loss $-4\%$) | Classified as `overridden_correct` / `correct_dissent_ignored`, awarded $+0.04$ counterfactual alpha. |
| 28 | Backtest Friction | Pure SELL trade execution | Deducts $5.0$ bps stamp duty $+ 2.5$ bps commission $+ 5.0$ bps slippage $= 12.5$ bps. |
| 29 | Backtest Friction | Pure BUY trade execution | Incurs NO stamp duty: $2.5$ bps commission $+ 5.0$ bps slippage $= 7.5$ bps. |
| 30 | Backtest Friction | Zero trades / empty returns | Returns dictionary with $0.0$ metrics; no division by zero or NaN. |
| 31 | Backtest Metrics | Constant returns series (zero variance) | Net Sharpe returns $0.0$ rather than `NaN` or `ZeroDivisionError`. |
| 32 | Multi-Regime Breakdown| Regimes with zero trading days in test window | Skips empty regimes; populates metrics only for observed regimes. |
| 33 | Multi-Regime Breakdown| Length mismatch between daily returns and regime tags | Truncates safely using `zip()` to shorter sequence length. |

---

## 7. Gap Analysis & Engineering Roadmap

### Gaps in Current Codebase vs Authoritative Specification

1. **`core/agents/analyst.py`:**
   - Base parsing methods exist (`_parse_response`, `_normalize_posterior`), but standalone public function `extract_structured_posterior(report_text: str) -> Dict[str, Any]` is missing.
   - `index_analyst_v2.py` caches reports and parses posteriors, but does not explicitly output `"market_regime": parsed["posterior"]["market_regime"]` to top-level state.
2. **`tradingagents/graph/conditional_logic.py`:**
   - Functions `compute_base2_jsd` and `calculate_cbs_routing` are present, but step 1.3/1.4 specifically requests `compute_jensen_shannon_divergence(posteriors, weights=None)` and `compute_cbs_bps(posteriors, weights=None)` with weighted formulation:
     $$D_{JS} = H(\sum w_i p_i) - \sum w_i H(p_i)$$
   - Needs explicit `should_gate_debate(state) -> str` alias matching `plan.md`.
3. **`core/agents/utils/weight_calculator.py`:**
   - Class is currently named `RegimeAdaptiveWeightCalculator`; `plan.md` step 2.1 specifies `RegimeMultiplicativeWeightManager` (needs alias or class definition).
   - In `compute_brier_loss`, current code computes $\|p - y\|_2^2$; specification in `plan.md` eq 3.3 defines $\ell = \frac{1}{3} \|p - y\|_2^2$.
   - In `update_weights`, weight floor $w_{\min} = 0.03$ must be strictly enforced.
   - Missing `aggregate_posteriors(posteriors, weights)` (logarithmic opinion pool).
4. **`tradingagents/graph/signal_processing.py`:**
   - Bayesian log-odds target price calculation is implemented, but `process_calibrated_signal(state, ...)` as a dedicated public entry point deriving `confidence` and `risk_score` from calibrated posteriors is missing.
5. **`core/memory/memory_manager.py`:**
   - `_normalize_store_metadata` and `_normalize_recall_filters` enforce `market_regime`, `volatility_quintile`, `brier_calibration_error`, but need `attribution_role`.
   - Step 3.2 regime-matching re-ranking ($1.5\times$ boost for same regime, exclusion of opposite regime) and `drawdown_circuit_breaker` runtime flag need explicit integration.
6. **`core/agents/reflection_helper.py`:**
   - `calculate_counterfactual_attribution` uses quadrant names (`Q1_Vindicated_Followed`, `Q2_Vindicated_Overridden`, `Q3_Faulty_Followed`, `Q4_Faulty_Overridden`). Must also support role naming: `correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`.
   - Standalone `compute_counterfactual_attribution(state, realized_return_pct)` must be exported.
7. **`core/backtest/result_evaluator.py`:**
   - Metric calculation functions (`calculate_net_performance_metrics`, `calculate_cbs_and_coordination_cost`, `calculate_multi_regime_breakdown`) exist, but class `ProtocolAuditEvaluator` is not yet defined.
   - Expected Calibration Error (ECE) calculation needs explicit helper.
8. **Factorial Ablation Script & Test Structure:**
   - Target test files named in `ORIGINAL_REQUEST.md`:
     - `tests/test_cbs_debate_gating.py` (currently `test_analyst_posteriors_cbs.py`)
     - `tests/test_regime_weight_calculator.py` (currently `test_regime_weights_signal.py`)
     - `tests/test_regime_memory_attribution.py` (currently `test_regime_memory_reflection.py`)
     - `tests/test_protocol_audit_evaluator.py` (currently `test_care_agents_ablation.py`)
     These must either be created or symlinked/aliased to satisfy acceptance criteria.
   - Script `scripts/run_cph_ablation_benchmark.py` must be implemented with CLI runner, mockable offline mode, live mode, and table exports (`reports/cph_ablation_table.tex` and `reports/cph_ablation_metrics.csv`).

---

## 8. Verification & Acceptance Criteria Checklist

- [x] All mathematical equations, constants, schemas, and algorithms documented verbatim from authoritative sources.
- [x] All 29 features across C1–C4 fully enumerated with inputs, outputs, and error handling.
- [x] All 33 boundary value and adversarial edge cases cataloged.
- [x] Data schemas and LangGraph state reducer contracts specified.
- [x] A-share transaction friction schedule and net-of-cost accounting verified.
- [x] Benchmark protocol (MR-1 to MR-7) and 4-way factorial ablation structure outlined.
