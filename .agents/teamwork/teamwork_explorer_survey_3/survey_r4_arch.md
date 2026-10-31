# Architecture, R4 Result Evaluator, and Ablation Testing Survey

**Document Target**: `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_3/survey_r4_arch.md`  
**Author**: Explorer Survey 3  
**Date**: 2026-10-30  
**Working Directory**: `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_3/`  
**Reference**: `ORIGINAL_REQUEST.md` (R4, R1, R2, R3)

---

## Executive Summary

This survey provides a comprehensive architectural and mathematical investigation for:
1. Target files and responsibilities for Requirement 4 (R4: Evaluation & Ablation Benchmark Suite).
2. Friction mechanics (China A-share stamp duty, commissions, slippage) and exact quantitative formulas for Net-of-cost Sharpe, Sortino, Calmar, and Maximum Drawdown in `core/backtest/result_evaluator.py`.
3. Metrics for Realized Coordination Breakeven Spread (`CBS_bps`), token cost, and decision latency.
4. Multi-regime window partitioning (Bull, Bear, Sideways) for comparative evaluation.
5. Concrete implementation plan for running all four ablation configurations (Config A, B, C, D) in `tests/test_care_agents_ablation.py`.
6. 100% deterministic, offline mocking strategy for LLM calls and market data feeds.

---

## 1. Target Files for R4

| Target File | Status | Current Role | Target Changes for R4 |
|-------------|--------|--------------|------------------------|
| `core/backtest/result_evaluator.py` | Existing (438 lines) | High-level LLM prompt wrapper (`evaluate_backtest_result`, `optimize_strategy_based_on_evaluation`) extracting basic summary dict items | Add mathematical calculation of net-of-cost risk-adjusted metrics (Sharpe, Sortino, Calmar, MDD), friction deductions (stamp duty on sells, commissions, slippage), realized CBS & token/latency costs, and multi-regime breakdown. Preserve existing LLM functions for backward compatibility. |
| `tests/test_care_agents_ablation.py` | New file to create | None | Suite of unit and integration tests executing all 4 ablation configurations (Config A, B, C, D) over synthetic multi-regime data feeds with deterministic mock LLMs. |

---

## 2. Deep Dive: `core/backtest/result_evaluator.py`

### 2.1 Current State Inspection
- `core/backtest/result_evaluator.py` lines 207–236 currently extract metrics only from a coarse summary dictionary:
  ```python
  if "summary" in backtest_result:
      summary = backtest_result.get("summary", {})
  else:
      summary = backtest_result
  total_return = summary.get('total_return', 0)
  win_rate = summary.get('win_rate', 0)
  max_drawdown = summary.get('max_drawdown_pct', 0)
  trade_count = summary.get('trade_count', 0)
  final_value = summary.get('final_value', 0)
  ```
- **Crucial Observation**: There is currently **zero programmatic calculation** of Sharpe, Sortino, Calmar, Maximum Drawdown, transaction frictions (stamp duty, commission, slippage), CBS_bps, or market regime breakdowns in `core/backtest/result_evaluator.py`.
- In other parts of the codebase (`core/tools/implementations/portfolio/performance_metrics.py` lines 250–370 and `extended_performance.py` lines 126–225, 440–510), individual tool functions compute gross Sharpe, Sortino, and Calmar for single stock price histories, but these do not support transaction cost deduction, trade-by-trade friction, decision latency/token overhead, or multi-regime slicing.

### 2.2 Transaction Fee & Friction Mechanics (China A-Shares)
In Chinese A-share equity trading:
1. **Stamp Duty (印花税)**:
   - Rate: **5 bps** ($0.05\%$ or $0.0005$).
   - Levied **only on SELL (exit) orders**. Buyer does not pay stamp duty.
2. **Broker Commission (佣金)**:
   - Rate: **2.5 bps** ($0.025\%$ or $0.00025$).
   - Levied on **both BUY and SELL orders** (two-way).
3. **Execution Slippage (滑点)**:
   - Rate: Configurable parameter `slippage_bps` (e.g. default **5.0 bps** or $0.05\%$).
   - Applied symmetrically to execution prices on both BUY and SELL orders.

#### Round-Trip Cost Calculation:
For a completed round-trip trade (Buy $\to$ Sell):
$$\text{Total Round-Trip Friction (bps)} = \text{Commission}_{\text{buy}} + \text{Slippage}_{\text{buy}} + \text{StampDuty}_{\text{sell}} + \text{Commission}_{\text{sell}} + \text{Slippage}_{\text{sell}}$$
$$\text{Total Round-Trip Friction (bps)} = 2.5 + \text{slippage\_bps} + 5.0 + 2.5 + \text{slippage\_bps} = 10.0 + 2 \times \text{slippage\_bps}$$
With default `slippage_bps = 5.0`, total round-trip friction is:
$$10.0 + 10.0 = 20.0 \text{ bps} \quad (0.20\%)$$

For trade-level returns:
$$R_{\text{net}} = R_{\text{gross}} - \frac{\text{Total Friction (bps)}}{10000.0}$$

For daily portfolio returns with turnover $\tau_t = \tau_{\text{buy}, t} + \tau_{\text{sell}, t}$:
$$R_{t, \text{net}} = R_{t, \text{gross}} - \left( \tau_{\text{buy}, t} \times \frac{\text{commission} + \text{slippage}}{10000} + \tau_{\text{sell}, t} \times \frac{\text{stamp\_duty} + \text{commission} + \text{slippage}}{10000} \right)$$
If turnover is 100% daily rebalancing, the daily friction deduction matches the full round-trip friction.

### 2.3 Required Additions to `core/backtest/result_evaluator.py`

#### 1. Net-of-Cost Performance Metrics:
Given a sequence of net returns $R_{t, \text{net}}$ for $t = 1, \dots, N$ and daily risk-free rate $R_f = \frac{r_f}{252}$ (default $r_f = 0.025$):

- **Daily Excess Return**:
  $$e_t = R_{t, \text{net}} - R_f$$
  $$\bar{e} = \frac{1}{N}\sum_{t=1}^N e_t, \quad \sigma_e = \sqrt{\frac{1}{N-1}\sum_{t=1}^N (e_t - \bar{e})^2}$$

- **Net Sharpe Ratio (Annualized)**:
  $$\text{Sharpe}_{\text{net}} = \begin{cases} \frac{\bar{e}}{\sigma_e} \times \sqrt{252}, & \sigma_e > 0 \\ 0.0, & \sigma_e = 0 \end{cases}$$

- **Net Sortino Ratio (Annualized)**:
  Penalizes only downside deviation below target return (default $\text{target} = 0.0$ or $R_f$):
  $$d_t = \min(0, R_{t, \text{net}} - \text{target})$$
  $$\sigma_{\text{down}} = \sqrt{\frac{1}{N-1}\sum_{t=1}^N d_t^2}$$
  $$\text{Sortino}_{\text{net}} = \begin{cases} \frac{\bar{e}}{\sigma_{\text{down}}} \times \sqrt{252}, & \sigma_{\text{down}} > 0 \\ 0.0, & \sigma_{\text{down}} = 0 \end{cases}$$

- **Net Maximum Drawdown (MDD)**:
  Cumulative compounded equity:
  $$W_t = \prod_{k=1}^t (1 + R_{k, \text{net}}), \quad W_0 = 1.0$$
  Peak at time $t$:
  $$P_t = \max_{0 \le s \le t} W_s$$
  Drawdown at time $t$:
  $$D_t = \frac{W_t - P_t}{P_t}$$
  $$\text{MDD}_{\text{net}} = \min_{1 \le t \le N} D_t \quad (\text{negative decimal, e.g. } -0.15 \text{ for } 15\% \text{ drawdown})$$

- **Net Calmar Ratio**:
  Annualized Compound Return (CAGR):
  $$\text{CAGR} = W_N^{252 / N} - 1$$
  $$\text{Calmar}_{\text{net}} = \begin{cases} \frac{\text{CAGR}}{|\text{MDD}_{\text{net}}|}, & |\text{MDD}_{\text{net}}| > 0 \\ 0.0, & |\text{MDD}_{\text{net}}| = 0 \end{cases}$$

#### 2. Realized Coordination Breakeven Spread (`CBS_bps`) & Token/Latency Cost:
From Requirement 1 (R1):
$$\text{Expected Debate Gain (bps)} = \text{JSD} \times \text{weighted\_expected\_move\_bps}$$
$$\text{CBS}_{\text{bps}} = \frac{\text{Expected Debate Gain (bps)}}{2.0}$$
In backtest evaluation:
- **Decision Records**: Each trading decision record includes:
  * `timestamp` or `trade_date`
  * `debate_triggered`: `bool` (whether CBS gate triggered multi-round debate)
  * `debate_rounds`: `int` (number of debate rounds conducted)
  * `jsd`: `float` (analyst posterior Jensen-Shannon divergence)
  * `cbs_bps`: `float` (computed CBS threshold)
  * `tokens_consumed`: `int` (input + output tokens for this decision)
  * `latency_seconds`: `float` (wall-clock inference time)
  * `realized_pnl_bps`: `float` (post-trade realized return in bps)
- **Computed Evaluator Metrics**:
  * `mean_tokens_per_decision` = $\frac{1}{M} \sum_{m=1}^M \text{tokens}_m$
  * `mean_latency_sec_per_decision` = $\frac{1}{M} \sum_{m=1}^M \text{latency}_m$
  * `total_token_cost_usd` = estimated using model pricing config (or standard token rates)
  * `mean_cbs_bps` = average CBS hurdle
  * `realized_cbs_bps` = empirical hurdle where debate alpha pays for coordination friction:
    $$\text{Realized CBS (bps)} = \frac{\text{Total Coordination Cost (tokens + latency in CNY/USD)}}{\text{Capital per Trade}} \times 10000 + \text{Friction (bps)}$$
  * `debate_efficiency_ratio` = $\frac{\text{Mean Realized Gain (Debate Decisions)}}{\text{Mean Realized Gain (Fast-Path Decisions)}}$

#### 3. Multi-Regime Breakdown Across Windows:
Markets exhibit distinct statistical properties across regimes. The evaluator must accept or partition data into three regimes:
- `"bull"`: Periods where benchmark / price trend > threshold (e.g. SMA20 > SMA60, or positive drift window).
- `"bear"`: Periods with negative drift and elevated volatility.
- `"sideways"`: Range-bound periods with low absolute drift.

The evaluator groups trade decisions and return series by regime:
$$\text{regime\_breakdown}[R] = \left\{ \text{trade\_count}, \text{net\_return}, \text{net\_sharpe}, \text{net\_sortino}, \text{net\_calmar}, \text{net\_mdd}, \text{win\_rate}, \text{avg\_cbs\_bps}, \text{avg\_latency\_sec}, \text{avg\_tokens} \right\}$$
for $R \in \{\text{"bull"}, \text{"bear"}, \text{"sideways"}\}$.

### 2.4 Code Architecture Proposal for `core/backtest/result_evaluator.py`
Add the following data classes and pure calculation functions to `core/backtest/result_evaluator.py`:

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Sequence
import numpy as np

@dataclass
class FrictionConfig:
    stamp_duty_bps: float = 5.0      # 5 bps on sells (China A-share)
    commission_bps: float = 2.5      # 2.5 bps on buys and sells
    slippage_bps: float = 5.0        # configurable slippage in bps

@dataclass
class PerformanceMetrics:
    gross_return: float
    net_return: float
    gross_sharpe: float
    net_sharpe: float
    gross_sortino: float
    net_sortino: float
    gross_calmar: float
    net_calmar: float
    gross_max_drawdown: float
    net_max_drawdown: float
    win_rate: float
    trade_count: int
    mean_tokens_per_decision: float
    mean_latency_sec_per_decision: float
    realized_cbs_bps: float
    regime_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)

def calculate_net_returns(
    gross_returns: Sequence[float],
    trades: Optional[List[Dict[str, Any]]] = None,
    friction: Optional[FrictionConfig] = None
) -> np.ndarray: ...

def calculate_net_performance_metrics(
    returns: Sequence[float],
    trades: Optional[List[Dict[str, Any]]] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    regimes: Optional[Sequence[str]] = None,
    risk_free_rate: float = 0.025,
    friction: Optional[FrictionConfig] = None,
) -> Dict[str, Any]: ...
```

In `evaluate_backtest_result()`, if `backtest_result` contains daily returns or decision logs, automatically invoke `calculate_net_performance_metrics()` and inject the structured net-of-cost metrics into the returned evaluation JSON and LLM prompt context.

---

## 3. Graph Architecture & The 4 Ablation Configurations

### 3.1 Graph Building Architecture in `tradingagents/graph/`
- `TradingAgentsGraph` (`tradingagents/graph/trading_graph.py`):
  * Coordinates `quick_thinking_llm` and `deep_thinking_llm`.
  * Instantiates `MemoryProvider` for episodic memories (`bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`).
  * Passes dependencies into `GraphSetup` (`tradingagents/graph/setup.py`).
  * Uses `ConditionalLogic` (`tradingagents/graph/conditional_logic.py`) to determine transitions between nodes.
- `GraphSetup.setup_graph()`:
  * Adds analyst nodes (Market, News, Social, Fundamentals, Index, Sector).
  * Adds researcher nodes (`Bull Researcher`, `Bear Researcher`).
  * Adds manager nodes (`Research Manager`, `Trader`).
  * Adds risk analysis nodes (`Risky Analyst`, `Neutral Analyst`, `Safe Analyst`, `Risk Judge`).
  * Currently, after the last analyst, an unconditional edge points to `Bull Researcher`:
    `workflow.add_edge(current_clear, "Bull Researcher")` (line 316).
  * Debate continuation is checked via `conditional_logic.should_continue_debate` (lines 319–334).
  * Risk continuation is checked via `conditional_logic.should_continue_risk_analysis` (lines 337–360).

### 3.2 The 4 Ablation Configurations Matrix

| Config | Name | Debate Strategy | Weights Mechanism | Memory Policy | Expected Profile |
|--------|------|-----------------|-------------------|---------------|------------------|
| **Config A** | **Linear Pipeline** | No debate (0 debate rounds, bypass to Manager / Risk Judge) | Static weights (`calculate_report_weights` or uniform $1/N$) | Regime-blind standard memory | Lowest token count & latency; no debate alpha; vulnerable to regime shifts. |
| **Config B** | **Vanilla TradingAgents** | Fixed multi-round debate (`max_debate_rounds = 1` or 2, fixed loop) | Static weights (`calculate_report_weights`) | Regime-blind standard memory | High token overhead; rigid debate regardless of analyst consensus; static weights lag market changes. |
| **Config C** | **Self-Debate 1-Shot** | Single-pass self-debate (`RiskSelfDebateV2`, 1 LLM call replaces 3 agents) | Static weights (`calculate_report_weights`) | Regime-blind standard memory | Significantly lower token/latency than Config B; preserves self-critique; still lacks regime adaptation. |
| **Config D** | **CARE-Agents** | **CBS-Gated Dynamic Debate** (JSD < 0.12 or CBS $\le$ 15 bps $\to$ Fast-Path / Self-Debate; JSD $\ge$ 0.12 and CBS > 15 bps $\to$ Dynamic debate) | **Regime-Adaptive Multiplicative Weights** (MWU via Brier loss per regime + Bayesian log-odds aggregation) | **Regime-Filtered Memory** (Circuit-breaker when regime confidence $\ge 0.5$ + counterfactual credit assignment) | Optimal Pareto efficiency: high net Sharpe/Calmar, low drawdown in Bear/Sideways, debate tokens spent only when alpha > friction. |

### 3.3 How to Run the 4 Ablations in a Test Environment
In `tests/test_care_agents_ablation.py`, we construct a clean test harness:

```python
class AblationHarness:
    """Executes trading pipeline under any of the 4 ablation configurations."""
    
    @staticmethod
    def run_configuration(
        config_type: str,  # "CONFIG_A", "CONFIG_B", "CONFIG_C", "CONFIG_D"
        market_series: List[Dict[str, Any]],
        analyst_signals: List[Dict[str, Any]],
        friction: FrictionConfig,
    ) -> Dict[str, Any]:
        # Config A: debate_rounds=0, static_weights=True, regime_memory=False
        # Config B: debate_rounds=2, static_weights=True, regime_memory=False
        # Config C: use_risk_self_debate=True, static_weights=True, regime_memory=False
        # Config D: cbs_gated=True, mwu_regime_weights=True, regime_filtered_memory=True
        ...
```

For each step in `market_series`:
1. **Analyst Step**: Evaluates analysts (or synthetic posteriors `p_optimistic`, `p_neutral`, `p_cautious`, `expected_move_bps`, `confidence`, `market_regime`).
2. **Debate Routing**:
   - In Config A: Bypass debate. Fast single-pass synthesis.
   - In Config B: Always run fixed multi-round debate (2 rounds).
   - In Config C: Run `RiskSelfDebateV2` 1-shot self-debate.
   - In Config D: Compute $\text{JSD}$ across analyst posteriors. Compute $\text{CBS}_{\text{bps}} = \frac{\text{JSD} \times \text{weighted\_move}}{2.0}$. If $\text{JSD} < 0.12$ or $\text{CBS} \le 15.0$, route to Fast-Path / Self-Debate. Otherwise, route to multi-round debate.
3. **Weight Updating**:
   - In Config A, B, C: Weights remain static.
   - In Config D: Update weights via `RegimeAdaptiveWeightCalculator.update_weights(regime, posteriors, realized_return)`.
4. **Memory Retrieval**:
   - In Config A, B, C: Retrieve top memories unfiltered.
   - In Config D: Filter out memories where `memory.metadata["market_regime"] != current_regime` when `regime_confidence >= 0.5`.
5. **Execution & Metric Recording**:
   - Record tokens, latency, gross return, net return (deducting stamp duty on sells, commissions, slippage).
6. **Pass to Evaluator**:
   - Invoke `calculate_net_performance_metrics()` to get Net Sharpe, Net Sortino, Net Calmar, Net MDD, Realized CBS, and multi-regime breakdown.

---

## 4. Offline & Deterministic Testing Strategy

### 4.1 Lessons from Existing Tests
- `tests/tradingagents/graph/test_trading_graph_memory_provider.py` demonstrated that mock components run cleanly and pass in **3.47 seconds** without network or API dependencies.
- `tests/core/agents/test_manager_memory.py` uses `_DummyLLM` and `_Mem0StyleMemory` to execute in-memory tests in milliseconds.
- Calling external endpoints (Volcengine, DashScope, Tushare) without configured keys causes timeouts and task hangs (as observed when testing full integration without mocks).
- **Rule**: `tests/test_care_agents_ablation.py` must NEVER instantiate live network clients or download real-time market data.

### 4.2 Mocking LLM Calls
We design a deterministic `AblationMockLLM`:
```python
class AblationMockLLM:
    """Deterministic, zero-network LLM mock for ablation testing."""
    def __init__(self, mode: str = "consensus"):
        self.mode = mode
        self.call_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.latency_seconds = 0.01  # Simulated deterministic latency

    def invoke(self, messages, *args, **kwargs):
        self.call_count += 1
        self.total_prompt_tokens += 120
        self.total_completion_tokens += 40
        
        # Depending on prompt type, return calibrated structured responses:
        # 1. Analyst response with structured probability block
        # 2. Bull/Bear researcher argument
        # 3. Manager synthesis
        # 4. Trader action ("buy", "hold", "sell")
        return MockAIMessage(content=self._get_content(messages))
```

### 4.3 Deterministic Synthetic Market Feed Across 3 Regimes
Create a 60-trading-day synthetic dataset with known, reproducible properties:

| Regime Window | Days | Drift & Volatility | Analyst Posterior Behavior | Expected Debate Behavior in Config D |
|---------------|------|--------------------|----------------------------|---------------------------------------|
| **Window 1: Bull** | Days 1–20 | Daily $+1.5\%$ drift, $0.4\%$ noise. Price rises from 100 to $\approx 135$. | High agreement on optimism ($P(\text{bull}) \approx 0.75$, $P(\text{bear}) \approx 0.10$). $\text{JSD} \approx 0.03 < 0.12$. | Fast-path triggered (bypasses debate, saves tokens/latency). |
| **Window 2: Bear** | Days 21–40 | Daily $-1.8\%$ drift, $0.8\%$ noise. Price drops from $\approx 135$ to $\approx 95$. | High disagreement: Market analyst detects breakdown ($P(\text{bear}) = 0.85$), while Social analyst is still hopeful ($P(\text{bull}) = 0.65$). $\text{JSD} \approx 0.38 > 0.12, \text{CBS} \approx 28 \text{ bps} > 15 \text{ bps}$. | Multi-round debate triggered; Bear researcher exposes downside risk; avoids severe drawdown. |
| **Window 3: Sideways** | Days 41–60 | Mean-reverting sine oscillation between 93 and 98, drift $\approx 0\%$. | Moderate divergence, low expected move ($\approx 5$ bps). $\text{CBS} \approx 2.5 \text{ bps} \le 15 \text{ bps}$. | Fast-path triggered (spread does not cover 15 bps friction hurdle). |

### 4.4 Verification and Invalidation Criteria
- **Pass Conditions**:
  1. All 4 ablation configurations execute without errors or unhandled exceptions.
  2. Execution finishes in $< 10$ seconds completely offline.
  3. Config D (CARE-Agents) demonstrates:
     - Statistically significantly fewer tokens and lower latency than Config B.
     - Higher Net Sharpe and Net Calmar than Config A and Config B.
     - Lower Maximum Drawdown during Bear window than Config A and Config B due to regime-filtered memory and debate trigger.
  4. Deducted frictions match exactly: 5 bps stamp duty on sells, 2.5 bps commissions on buys/sells, specified slippage.
- **Invalidation Conditions**:
  - Any test attempting external HTTP requests (`httpx.ConnectError`, `requests.exceptions.ConnectionError`).
  - Net return exceeding gross return (violating friction subtraction).
  - JSD or CBS gating failing to branch appropriately under the specified thresholds.

---

## 5. Summary of Recommended Implementation Steps for Next Phases

1. **Phase 1 (R1 - Probabilities & Debate Gating)**:
   - Add structured distribution parsing in `core/agents/analyst.py`.
   - Implement `should_trigger_multi_round_debate` with JSD & CBS formula in `tradingagents/graph/conditional_logic.py`.
2. **Phase 2 (R2 - Regime Adaptive Weights & Signal Processor)**:
   - Implement `RegimeAdaptiveWeightCalculator` with Brier-loss MWU update in `core/agents/utils/weight_calculator.py`.
   - Replace fixed multiplier fallback with Bayesian log-odds aggregation in `tradingagents/graph/signal_processing.py`.
3. **Phase 3 (R3 - Regime-Filtered Memory & Counterfactual Attribution)**:
   - Add regime metadata filtering & circuit breaker in `core/memory/memory_manager.py`.
   - Implement counterfactual credit assignment in `tradingagents/graph/reflection.py`.
4. **Phase 4 (R4 - Evaluator & Ablation Suite)**:
   - Enhance `core/backtest/result_evaluator.py` with `FrictionConfig`, `calculate_net_performance_metrics`, `calculate_cbs_and_coordination_cost`, and `calculate_multi_regime_breakdown`.
   - Create `tests/test_care_agents_ablation.py` implementing the 4 ablation configurations with deterministic mock LLM and 60-day multi-regime feed.
