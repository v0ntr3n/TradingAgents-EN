"""
Backtest results evaluator
Analyze whether the backtest results meet user expectations, identify problems and make optimization suggestions
"""
import collections.abc
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

EVALUATE_SYSTEM = """You are a professional quantitative strategy evaluator. Your task is to analyze the backtest results, determine whether the strategy meets the original needs of users, identify problems and make optimization suggestions.

 [Evaluation Dimensions]
1. **Demand matching**: Whether the strategy logic conforms to the investment ideas described by the user
2. **Reasonableness of results**: Are indicators such as income, winning rate, retracement, etc. within a reasonable range?
3. **trading behavior**: Whether the timing of buying and selling and the distribution of positions are in line with expectations
4. **Data quality**: Are there any issues such as missing data, outliers, etc.
5. **Code logic**: Are there any obvious flaws in the implementation of the strategy?

 [Output format]
Please output the evaluation results in the following JSON format:
{
  "overall_score": 85,  // Overall rating 0-100
  "is_satisfactory": true,  // Are you satisfied (>= 70 Divided into satisfied)
  "issues": [
    {
      "type": "logic_error",  // Question type:logic_error/data_issue/performance_poor/requirement_mismatch
      "severity": "high",     // Severity:high/medium/low
      "description": "Specific problem description",
      "suggestion": "Optimization suggestions"
    }
  ],
  "strengths": ["Strategic advantages 1", "Strategic advantages 2"],
  "optimization_priority": "high",  // Optimization priority:high/medium/low/none
  "next_steps": "Specific suggestions for next-step optimization directions"
}

 [Evaluation criteria]
- Overall score: Comprehensive consideration of demand matching, rationality of results, transaction behavior, etc.
- Satisfaction threshold:>= 70 I think I am basically satisfied.< 70 Needs optimization
- Problem severity:
  * high: Seriously affects the effectiveness of the strategy and must be repaired
  * medium: Affects strategy performance, it is recommended to fix it  
  * low: Minor issue, optional fix

 [Frequently Asked Question Types]
- logic_error: Strategy logic errors (such as wrong buying and selling conditions, position management problems)
- data_issue: Data problems (such as empty stock pool, missing data)
- performance_poor: Poor performance (such as too low returns, too large drawdowns)
- requirement_mismatch: Not in line with user needs (such as expecting high dividends but choosing growth stocks)
"""

OPTIMIZE_SYSTEM = """You are a strategy optimization expert. Conduct targeted optimization of existing strategies based on the backtest result evaluation report.

 [Optimization principles]
1. **Targeted fixes**: Focus on addressing high-priority issues identified in the assessment report
2. **Keep core logic**: Optimize within the framework of users original needs without changing the basic investment ideas
3. **incremental improvements**: Only solve 1-2 major problems at a time to avoid major revisions
4. **data driven**: Optimize based on backtest data and transaction details

 [Important: Avoid Survivor Bias]
⚠️ Don t use current leading stocks to backtest the past 10-20 years! This can lead to serious survivor bias.

**Correct approach (priority from high to low)**: 

1. **🆕 Use industry classification + Historical market capitalization**: universe.type = "industry"
   - The system will automatically obtain the stock with the largest market capitalization in the industry on the start date of the backtest
   - For example, to backtest the liquor strategy from 2010 to 2020, the liquor faucet from 2010 will be used.
   - This is the best choice and can truly avoid survivor bias

2. **Use industry indices**: universe.type = "index"
   - Use index historical constituent stocks (some index historical data are limited)

3. **Shorten the backtest cycle**: Static stock pool is only used for backtesting in the past 3-5 years

 [Industry classification configuration]⭐ Recommended
Supported industries: liquor, food, home appliances, consumption, banking, insurance, securities firms, finance, semiconductors, software, technology, photovoltaics, lithium batteries, new energy, medicine, etc.

Example:
"universe": {"type": "industry", "industry": "Liquor", "max_symbols": 10}
"universe": {"type": "industry", "industry": "consumption", "max_symbols": 15}
"universe": {"type": "industry", "industry": "Finance", "max_symbols": 12}

 [Industry index code reference] (optional)
- Consumer category: 000932.SH (CSI Consumer), 399997.SZ (CSI Liquor)
- Financial: 399986.SZ (China Securities Bank), 000914.SH (300 Finance)
- Technology: 000993.SH (full index), 399006.SZ (GEM index)

 [Static stock pool configuration] (only recommended for backtesting in the past 3-5 years, long-term backtesting is not recommended)
Consumer category: 600519, 000858, 000568, 603288, 000651, 000333,600887

 [Output format]
Pure JSON must be output, in the following format:
{
  "code": "Optimized complete Python code string",
  "config": {
    "start_year": 2016,
    "end_year": 2025,
    "initial_capital": 1000000,
    "max_positions": 10,
    "benchmark": "000300",
    "market": "CN",
    "data_source": "tushare",
    "universe": {"type": "static", "symbols": ["600519", "000858", "000568", "002304", "000596", "603288", "000651", "000333", "600887", "601888"]}
  },
  "optimization_summary": "Description of the main improvements in this optimization"
}

 [Optimization strategy]
- Logic error: Correct buying and selling conditions, position management logic
- Data issues: Adjust the stock pool (increase the number of stocks, select more appropriate targets)
- Performance issues: optimize parameters and adjust position management
- Inconsistent needs: re-understand user intentions and adjust strategic direction
- Insufficient number of transactions: expand stock pool, relax entry conditions, shorten position holding period

 [Technical requirements]
- code Only import backtrader (as bt)
- datetime, date, timedelta Already injected and can be used directly
- Must output pure JSON, do not wrap markdown code blocks
- config Must contain complete configuration parameters
- Stock pool symbols are recommended to contain 8-15 stocks to ensure sufficient trading opportunities
"""


# ==============================================================================
# CARE-Agents Quantitative Evaluation: Frictions, Net Metrics, CBS, Regimes
# ==============================================================================

@dataclass
class FrictionConfig:
    """
    China A-share transaction friction configuration.

    Attributes:
        sell_stamp_duty_bps: float = 5.0 (levied exclusively on SELL trades)
        commission_bps: float = 2.5 (levied on both BUY and SELL trades)
        slippage_bps: float = 5.0 (configurable, levied on both BUY and SELL trades)
    """
    sell_stamp_duty_bps: float = 5.0
    commission_bps: float = 2.5
    slippage_bps: float = 5.0

    def __init__(
        self,
        sell_stamp_duty_bps: Optional[float] = None,
        commission_bps: float = 2.5,
        slippage_bps: float = 5.0,
        stamp_duty_bps: Optional[float] = None,
    ):
        if sell_stamp_duty_bps is not None:
            self.sell_stamp_duty_bps = float(sell_stamp_duty_bps)
        elif stamp_duty_bps is not None:
            self.sell_stamp_duty_bps = float(stamp_duty_bps)
        else:
            self.sell_stamp_duty_bps = 5.0
        self.commission_bps = float(commission_bps)
        self.slippage_bps = float(slippage_bps)

    @property
    def stamp_duty_bps(self) -> float:
        return self.sell_stamp_duty_bps


def _is_equity_curve(series: Any) -> bool:
    """
    Heuristic to distinguish whether a numeric sequence represents an equity curve
    (cumulative wealth levels) or a series of daily returns.
    """
    if not isinstance(series, (list, tuple, np.ndarray)) or len(series) < 2:
        return False
    try:
        arr = np.asarray(series, dtype=np.float64)
        if len(arr) < 2:
            return False
        # If any negative value exists, it cannot be an equity curve
        if (arr < 0.0).any():
            return False
        # If any value exceeds 1.5, it is an equity curve (daily returns > 150% do not occur in equities)
        if (arr > 1.5).any():
            return True
        # For normalized equity curves starting near 1.0 (e.g. [1.0, 1.02, 0.98]):
        first_val = float(arr[0])
        if abs(first_val - 1.0) < 1e-3 and float(np.mean(arr)) > 0.3:
            return True
    except (ValueError, TypeError):
        return False
    return False


def _is_trade_list(obj: Any) -> bool:
    """Returns True if obj is a non-empty sequence of trade dicts."""
    if isinstance(obj, (list, tuple)) and len(obj) > 0:
        return isinstance(obj[0], (dict, collections.abc.Mapping))
    return False


def _is_numeric_sequence(obj: Any) -> bool:
    """Returns True if obj is a non-empty sequence of numbers."""
    if isinstance(obj, (list, tuple, np.ndarray)) and len(obj) > 0:
        return isinstance(obj[0], (int, float, np.floating, np.integer))
    return False


def calculate_net_performance_metrics(
    trades: Optional[Any] = None,
    daily_returns: Optional[Any] = None,
    equity_curve: Optional[Any] = None,
    friction: Optional[FrictionConfig] = None,
    risk_free_rate: float = 0.025,
    **kwargs,
) -> Dict[str, float]:
    """
    Computes Net Sharpe, Net Sortino, Net Calmar, and Maximum Drawdown after deducting
    China A-share frictions (5 bps sell stamp duty, 2.5 bps commission, configurable slippage).
    Provides annualized metrics assuming 252 trading days.

    Supports multiple polymorphic calling conventions:
    1. calculate_net_performance_metrics(trades, daily_returns=..., equity_curve=..., friction=...)
    2. calculate_net_performance_metrics(trades, equity_curve, friction)
    3. calculate_net_performance_metrics(gross_returns, trades, friction)
    """
    # Step 1: Reconcile keyword arguments & aliases
    if "risk_free_rate" in kwargs:
        risk_free_rate = float(kwargs["risk_free_rate"])

    if daily_returns is None:
        if "gross_returns" in kwargs:
            daily_returns = kwargs["gross_returns"]
        elif "returns" in kwargs:
            daily_returns = kwargs["returns"]

    if equity_curve is None and "equity" in kwargs:
        equity_curve = kwargs["equity"]

    if trades is None and "trades" in kwargs:
        trades = kwargs["trades"]

    # Step 2: Friction extraction (disentangle FrictionConfig from equity_curve parameter)
    actual_friction: Optional[FrictionConfig] = None
    if isinstance(equity_curve, FrictionConfig):
        actual_friction = equity_curve
        equity_curve = None
    elif isinstance(equity_curve, dict) and any(k in equity_curve for k in ("sell_stamp_duty_bps", "commission_bps", "slippage_bps", "stamp_duty_bps")):
        actual_friction = FrictionConfig(**{k: v for k, v in equity_curve.items() if k in {"sell_stamp_duty_bps", "commission_bps", "slippage_bps", "stamp_duty_bps"} and v is not None})
        equity_curve = None
    elif isinstance(friction, FrictionConfig):
        actual_friction = friction
    elif isinstance(friction, dict):
        actual_friction = FrictionConfig(**{k: v for k, v in friction.items() if k in {"sell_stamp_duty_bps", "commission_bps", "slippage_bps", "stamp_duty_bps"} and v is not None})
    elif "friction" in kwargs and isinstance(kwargs["friction"], FrictionConfig):
        actual_friction = kwargs["friction"]
    elif "friction" in kwargs and isinstance(kwargs["friction"], dict):
        f_dict = kwargs["friction"]
        actual_friction = FrictionConfig(**{k: v for k, v in f_dict.items() if k in {"sell_stamp_duty_bps", "commission_bps", "slippage_bps", "stamp_duty_bps"} and v is not None})
    elif friction is not None:
        actual_friction = friction
    elif "friction" in kwargs:
        actual_friction = kwargs["friction"]

    if isinstance(actual_friction, dict):
        actual_friction = FrictionConfig(**{k: v for k, v in actual_friction.items() if k in {"sell_stamp_duty_bps", "commission_bps", "slippage_bps", "stamp_duty_bps"} and v is not None})
    elif not isinstance(actual_friction, FrictionConfig):
        actual_friction = FrictionConfig()

    # Step 3: Polymorphic parsing of trades, returns, equity_curve
    actual_returns: Optional[List[float]] = None
    actual_trades: List[Dict[str, Any]] = []
    actual_equity: Optional[List[float]] = None

    if equity_curve is not None and _is_numeric_sequence(equity_curve):
        actual_equity = [float(x) for x in equity_curve]
        if _is_numeric_sequence(trades):
            actual_returns = [float(x) for x in trades]
            actual_trades = []
        else:
            actual_trades = [t for t in trades if isinstance(t, dict)] if isinstance(trades, (list, tuple)) else []
            if _is_numeric_sequence(daily_returns):
                actual_returns = [float(x) for x in daily_returns]
    else:
        # equity_curve is None (or was FrictionConfig and has been extracted)
        if _is_numeric_sequence(trades):
            # Pattern 3: (gross_returns, trades, friction)
            if _is_equity_curve(trades):
                actual_equity = [float(x) for x in trades]
            else:
                actual_returns = [float(x) for x in trades]

            if _is_trade_list(daily_returns) or (isinstance(daily_returns, (list, tuple)) and len(daily_returns) == 0):
                actual_trades = [t for t in daily_returns if isinstance(t, dict)]
            else:
                actual_trades = []
        elif _is_trade_list(trades):
            # Pattern 1 & 2: trades is first argument
            actual_trades = [t for t in trades if isinstance(t, dict)]
            if _is_numeric_sequence(daily_returns):
                if _is_equity_curve(daily_returns):
                    # Pattern 2: (trades, equity_curve, friction)
                    actual_equity = [float(x) for x in daily_returns]
                else:
                    # Pattern 1: (trades, daily_returns, friction)
                    actual_returns = [float(x) for x in daily_returns]
            elif isinstance(daily_returns, (list, tuple, np.ndarray)) and len(daily_returns) == 0:
                actual_returns = []
        else:
            # trades is empty [] or None
            if _is_trade_list(daily_returns):
                # Pattern 3 with empty returns: ([], trades, friction)
                actual_trades = [t for t in daily_returns if isinstance(t, dict)]
                actual_returns = []
            elif _is_numeric_sequence(daily_returns):
                # Pattern 1/2 with empty trades: ([], returns/equity, friction)
                actual_trades = []
                if _is_equity_curve(daily_returns):
                    actual_equity = [float(x) for x in daily_returns]
                else:
                    actual_returns = [float(x) for x in daily_returns]
            else:
                actual_trades = []
                actual_returns = []

    # Step 4: Derive daily returns from equity curve if needed
    if actual_returns is None and actual_equity is not None and len(actual_equity) > 1:
        actual_returns = [
            (actual_equity[i] / actual_equity[i - 1]) - 1.0
            for i in range(1, len(actual_equity))
            if actual_equity[i - 1] > 0
        ]
    elif actual_returns is None:
        actual_returns = []

    # Step 5: Safe trade friction calculation with type coercion for shares
    total_frictions_bps = 0.0
    for t in actual_trades:
        if not isinstance(t, dict):
            continue
        action = str(t.get("action", t.get("side", t.get("type", "")))).lower().strip()
        if action == "buy":
            total_frictions_bps += actual_friction.commission_bps + actual_friction.slippage_bps
        elif action == "sell":
            total_frictions_bps += (
                actual_friction.sell_stamp_duty_bps
                + actual_friction.commission_bps
                + actual_friction.slippage_bps
            )
        else:
            raw_shares = t.get("shares")
            if raw_shares is None:
                raw_shares = t.get("amount")
            if raw_shares is None:
                raw_shares = t.get("qty", None)
            shares = 0.0
            if raw_shares is not None:
                try:
                    shares = float(raw_shares)
                except (ValueError, TypeError):
                    shares = 0.0

            if shares > 0:
                total_frictions_bps += actual_friction.commission_bps + actual_friction.slippage_bps
            elif shares < 0:
                total_frictions_bps += (
                    actual_friction.sell_stamp_duty_bps
                    + actual_friction.commission_bps
                    + actual_friction.slippage_bps
                )
            else:
                # Default completed round trip (1 buy + 1 sell)
                total_frictions_bps += (
                    actual_friction.sell_stamp_duty_bps
                    + 2.0 * (actual_friction.commission_bps + actual_friction.slippage_bps)
                )

    n = len(actual_returns)
    if n == 0:
        return {
            "gross_return": 0.0,
            "net_return": 0.0,
            "net_sharpe": 0.0,
            "net_sortino": 0.0,
            "net_calmar": 0.0,
            "net_max_drawdown": 0.0,
            "total_frictions_bps": float(total_frictions_bps),
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "win_rate": 0.0,
            "trade_count": len(actual_trades),
        }

    friction_per_period = (total_frictions_bps / 10000.0) / max(1, n)
    gross_arr = np.array(actual_returns, dtype=np.float64)
    net_returns = gross_arr - friction_per_period

    # Compounded equity curve starting at W_0 = 1.0
    equity = np.cumprod(1.0 + net_returns)
    net_total_return = float(equity[-1] - 1.0) if len(equity) > 0 else 0.0
    gross_total_return = float(np.cumprod(1.0 + gross_arr)[-1] - 1.0)

    # Maximum Drawdown starting from peak 1.0
    full_equity = np.insert(equity, 0, 1.0)
    peaks = np.maximum.accumulate(full_equity)
    drawdowns = (full_equity - peaks) / peaks
    net_mdd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Annualized CAGR assuming 252 trading days
    if len(equity) > 0 and equity[-1] > 0:
        cagr = float(equity[-1] ** (252.0 / max(1, n)) - 1.0)
    elif len(equity) > 0 and equity[-1] <= 0:
        cagr = -1.0
    else:
        cagr = 0.0

    # Sharpe ratio (excess return over daily risk-free rate)
    daily_rf = risk_free_rate / 252.0
    excess_returns = net_returns - daily_rf
    mean_excess = float(np.mean(excess_returns))
    std_excess = float(np.std(excess_returns, ddof=1)) if n > 1 else 0.0
    net_sharpe = float((mean_excess / std_excess) * math.sqrt(252.0)) if std_excess > 1e-12 else 0.0

    # Sortino ratio (downside deviation below risk-free rate)
    downside_diff = np.minimum(0.0, excess_returns)
    downside_dev = float(math.sqrt(np.mean(downside_diff ** 2))) if n > 0 else 0.0
    net_sortino = float((mean_excess / downside_dev) * math.sqrt(252.0)) if downside_dev > 1e-12 else 0.0

    # Calmar ratio (CAGR / |MDD|)
    net_calmar = float(cagr / abs(net_mdd)) if abs(net_mdd) > 1e-6 else 0.0

    std_returns = float(np.std(net_returns, ddof=1)) if n > 1 else 0.0
    ann_vol = float(std_returns * math.sqrt(252.0))
    positive_days = sum(1 for r in net_returns if r > 0)
    win_rate = float((positive_days / n) * 100.0) if n > 0 else 0.0

    return {
        "gross_return": gross_total_return,
        "net_return": net_total_return,
        "net_sharpe": net_sharpe,
        "net_sortino": net_sortino,
        "net_calmar": net_calmar,
        "net_max_drawdown": net_mdd,
        "total_frictions_bps": float(total_frictions_bps),
        "annualized_return": cagr,
        "annualized_volatility": ann_vol,
        "win_rate": win_rate,
        "trade_count": len(actual_trades),
    }


def calculate_cbs_and_coordination_cost(debate_records: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Computes realized Coordination Breakeven Spread (CBS_bps), token cost per decision,
    latency ms per decision, and fast-path debate bypass rate.

    Args:
        debate_records: List of debate decision records.

    Returns:
        Dict[str, float] containing:
            - realized_cbs_bps / cbs_bps: Mean realized CBS hurdle in bps
            - token_cost_per_decision / tokens_per_decision: Average tokens consumed per decision
            - latency_ms_per_decision: Average latency in milliseconds per decision
            - latency_sec_per_decision: Average latency in seconds per decision
            - fast_path_debate_bypass_rate / fast_path_bypass_rate: Proportion bypassing debate to fast-path
            - debate_trigger_rate: Proportion routed to multi-round debate
            - total_decisions: Total decision records processed
    """
    if not debate_records:
        return {
            "realized_cbs_bps": 0.0,
            "cbs_bps": 0.0,
            "mean_cbs_bps": 0.0,
            "token_cost_per_decision": 0.0,
            "tokens_per_decision": 0.0,
            "latency_ms_per_decision": 0.0,
            "latency_sec_per_decision": 0.0,
            "fast_path_debate_bypass_rate": 0.0,
            "fast_path_bypass_rate": 0.0,
            "debate_trigger_rate": 0.0,
            "total_decisions": 0.0,
        }

    cbs_list: List[float] = []
    tokens_list: List[float] = []
    latency_ms_list: List[float] = []
    fast_path_count = 0

    for r in debate_records:
        if not isinstance(r, dict):
            continue

        raw_cbs = r.get("cbs_bps")
        if raw_cbs is None:
            raw_cbs = r.get("cbs")
        if raw_cbs is None:
            raw_cbs = r.get("cbs_hurdle_bps")
        try:
            cbs = float(raw_cbs) if raw_cbs is not None else 0.0
        except (ValueError, TypeError):
            cbs = 0.0
        cbs_list.append(cbs)

        raw_tok = r.get("tokens")
        if raw_tok is None:
            raw_tok = r.get("tokens_consumed")
        if raw_tok is None:
            raw_tok = r.get("total_tokens")
        try:
            tok = float(raw_tok) if raw_tok is not None else 0.0
        except (ValueError, TypeError):
            tok = 0.0
        if tok == 0.0 and ("prompt_tokens" in r or "completion_tokens" in r):
            p_tok = r.get("prompt_tokens") or 0
            c_tok = r.get("completion_tokens") or 0
            try:
                tok = float(p_tok) + float(c_tok)
            except (ValueError, TypeError):
                tok = 0.0
        tokens_list.append(tok)

        lat_ms = 0.0
        if r.get("latency_ms") is not None:
            try:
                lat_ms = float(r["latency_ms"])
            except (ValueError, TypeError):
                lat_ms = 0.0
        elif r.get("latency_sec") is not None:
            try:
                lat_ms = float(r["latency_sec"]) * 1000.0
            except (ValueError, TypeError):
                lat_ms = 0.0
        elif r.get("latency_seconds") is not None:
            try:
                lat_ms = float(r["latency_seconds"]) * 1000.0
            except (ValueError, TypeError):
                lat_ms = 0.0
        elif r.get("latency") is not None:
            try:
                val = float(r["latency"])
                lat_ms = val * 1000.0 if val < 10.0 else val
            except (ValueError, TypeError):
                lat_ms = 0.0
        latency_ms_list.append(lat_ms)

        route = str(r.get("route", "")).lower().strip()
        is_fast_path = (
            route == "fast_path"
            or r.get("fast_path") is True
            or r.get("is_fast_path") is True
            or r.get("debate_triggered") is False
            or r.get("debate_rounds", 1) == 0
            or r.get("dynamic_debate_rounds", 1) == 0
        )
        if is_fast_path:
            fast_path_count += 1

    n = len(debate_records)
    mean_cbs = float(np.mean(cbs_list)) if cbs_list else 0.0
    mean_tokens = float(np.mean(tokens_list)) if tokens_list else 0.0
    mean_lat_ms = float(np.mean(latency_ms_list)) if latency_ms_list else 0.0
    mean_lat_sec = float(mean_lat_ms / 1000.0)
    bypass_rate = float(fast_path_count / n) if n > 0 else 0.0
    trigger_rate = float(1.0 - bypass_rate)

    return {
        "realized_cbs_bps": mean_cbs,
        "cbs_bps": mean_cbs,
        "mean_cbs_bps": mean_cbs,
        "token_cost_per_decision": mean_tokens,
        "tokens_per_decision": mean_tokens,
        "mean_tokens_per_decision": mean_tokens,
        "latency_ms_per_decision": mean_lat_ms,
        "mean_latency_ms_per_decision": mean_lat_ms,
        "latency_sec_per_decision": mean_lat_sec,
        "fast_path_debate_bypass_rate": bypass_rate,
        "fast_path_bypass_rate": bypass_rate,
        "debate_trigger_rate": trigger_rate,
        "total_decisions": float(n),
    }


def calculate_multi_regime_breakdown(
    daily_returns: List[float],
    regimes: List[str],
    friction_per_period: float = 0.0002,
    risk_free_rate: float = 0.025,
) -> Dict[str, Dict[str, float]]:
    """
    Returns a multi-regime breakdown across "bull", "bear", and "sideways" windows
    (computing return, Sharpe, Sortino, Calmar, Max Drawdown per regime).
    """
    target_regimes = ["bull", "bear", "sideways"]
    breakdown: Dict[str, Dict[str, float]] = {}

    for r in target_regimes:
        sub_returns = [
            float(ret) - friction_per_period
            for ret, reg in zip(daily_returns, regimes)
            if str(reg).lower().strip() == r
        ]
        if not sub_returns:
            continue

        arr = np.array(sub_returns, dtype=np.float64)
        n = len(arr)

        cum_ret = float(np.cumprod(1.0 + arr)[-1] - 1.0) if n > 0 else 0.0

        full_eq = np.insert(np.cumprod(1.0 + arr), 0, 1.0)
        peaks = np.maximum.accumulate(full_eq)
        dds = (full_eq - peaks) / peaks
        mdd = float(np.min(dds)) if len(dds) > 0 else 0.0

        daily_rf = risk_free_rate / 252.0
        excess = arr - daily_rf
        std = float(np.std(excess, ddof=1)) if n > 1 else 0.0
        sharpe = float((np.mean(excess) / std) * math.sqrt(252.0)) if std > 1e-12 else 0.0

        downside = np.minimum(0.0, excess)
        downside_std = float(math.sqrt(np.mean(downside ** 2))) if n > 0 else 0.0
        sortino = float((np.mean(excess) / downside_std) * math.sqrt(252.0)) if downside_std > 1e-12 else 0.0

        if full_eq[-1] > 0 and n > 0:
            cagr = float(full_eq[-1] ** (252.0 / n) - 1.0)
        elif full_eq[-1] <= 0:
            cagr = -1.0
        else:
            cagr = 0.0
        calmar = float(cagr / abs(mdd)) if abs(mdd) > 1e-6 else 0.0

        breakdown[r] = {
            "count": float(n),
            "return": cum_ret,
            "net_return": cum_ret,
            "max_drawdown": mdd,
            "net_max_drawdown": mdd,
            "sharpe": sharpe,
            "net_sharpe": sharpe,
            "sortino": sortino,
            "net_sortino": sortino,
            "calmar": calmar,
            "net_calmar": calmar,
        }

    return breakdown


async def evaluate_backtest_result(
    user_description: str,
    strategy: Dict[str, Any],
    backtest_result: Dict[str, Any],
    llm_client: Optional[UnifiedLLMClient] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether the backtest results meet user expectations
    
    Args:
        user_description: Description of original user needs
        strategy: policy definition (code + config) 
        backtest_result: Backtest results (summary + trades etc.)
        llm_client: LLM client
        
    Returns:
        Assessment results JSON
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config
        
        cfg = await get_coding_llm_config()
        if not cfg:
            raise ValueError("LLM is not configured and result evaluation is not possible")
        client = UnifiedLLMClient.from_config(cfg)
    
    # Build an evaluation context
    context = _build_evaluation_context(user_description, strategy, backtest_result)
    
    messages = [
        Message(role=MessageRole.SYSTEM, content=EVALUATE_SYSTEM),
        Message(role=MessageRole.USER, content=context),
    ]
    
    try:
        response = await client.achat(messages)
        result_text = (response.content or "").strip()
        
        # Parse JSON results
        import json
        evaluation = json.loads(result_text)
        
        # Validate required fields
        required_fields = ["overall_score", "is_satisfactory", "issues", "optimization_priority"]
        for field in required_fields:
            if field not in evaluation:
                raise ValueError(f"Assessment results are missing required fields: {field}")
                
        return evaluation
        
    except json.JSONDecodeError as e:
        logger.warning("Evaluation result JSON parsing failed: %s", e)
        # Returns the default evaluation result
        return {
            "overall_score": 50,
            "is_satisfactory": False,
            "issues": [{"type": "logic_error", "severity": "high", 
                       "description": "Error in evaluation process", "suggestion": "Please check the policy logic"}],
            "optimization_priority": "high",
            "next_steps": "Requires manual inspection of policy implementation"
        }
    except Exception as e:
        logger.exception("Backtest result evaluation failed")
        raise ValueError(f"Evaluation failed: {e}")


def _build_evaluation_context(
    user_description: str,
    strategy: Dict[str, Any],
    backtest_result: Dict[str, Any]
) -> str:
    """Build an evaluation context"""

    # debug log
    logger.info(
        "[_build_evaluation_context] received backtest_result keys=%s",
        list(backtest_result.keys()) if backtest_result else "None"
    )

    # Extract key information
    # Two data structures are supported:1) direct summary 2) Nested under result
    if "summary" in backtest_result:
        summary = backtest_result.get("summary", {})
    else:
        summary = backtest_result  # Directly summary

    logger.info(
        "[_build_evaluation_context] summary: total_return=%s, win_rate=%s, trade_count=%s, final_value=%s",
        summary.get("total_return"),
        summary.get("win_rate"),
        summary.get("trade_count"),
        summary.get("final_value"),
    )

    # Extract run logs and warnings
    logs = backtest_result.get("logs", [])
    warnings = backtest_result.get("warnings", [])
    trades = backtest_result.get("trades", [])
    
    # Formatted backtest results summary
    result_summary = f"""
 [Summary of backtest results]
- total revenue: {summary.get('total_return', 0):.1f}%
- winning rate: {summary.get('win_rate', 0):.1f}%
- maximum drawdown: {summary.get('max_drawdown_pct', 0):.1f}%
- Number of transactions: {summary.get('trade_count', 0)}
- final value: {summary.get('final_value', 0):,.0f}
"""

    # Format CARE-Agents net performance and cost analysis if available or derivable
    net_section = ""
    net_perf = summary.get("net_performance") or summary.get("performance") or summary
    has_net = any(
        k in net_perf
        for k in ["net_return", "net_sharpe", "net_sortino", "net_calmar", "net_max_drawdown", "total_frictions_bps"]
    )

    if not has_net and ("trades" in backtest_result or "daily_returns" in backtest_result):
        try:
            net_perf = calculate_net_performance_metrics(
                trades=backtest_result.get("trades", []),
                daily_returns=backtest_result.get("daily_returns"),
                equity_curve=backtest_result.get("equity_curve"),
            )
            has_net = True
        except Exception as e:
            logger.debug("Failed to auto-compute net performance metrics: %s", e)

    if has_net:
        nr = net_perf.get("net_return", 0.0)
        nr_str = f"{nr * 100.0:.2f}%" if abs(nr) <= 1.0 else f"{nr:.2f}%"
        nmdd = net_perf.get("net_max_drawdown", net_perf.get("max_drawdown", 0.0))
        nmdd_str = f"{nmdd * 100.0:.2f}%" if abs(nmdd) <= 1.0 else f"{nmdd:.2f}%"

        net_section = f""" [Net Performance & Cost Analysis (CARE-Agents)]
- Net Return: {nr_str}
- Net Sharpe: {net_perf.get('net_sharpe', 0.0):.2f}
- Net Sortino: {net_perf.get('net_sortino', 0.0):.2f}
- Net Calmar: {net_perf.get('net_calmar', 0.0):.2f}
- Net Max Drawdown: {nmdd_str}
- Total Frictions: {net_perf.get('total_frictions_bps', 0.0):.1f} bps\n"""
        if "realized_cbs_bps" in net_perf or "cbs_bps" in summary:
            net_section += f"- Realized CBS: {net_perf.get('realized_cbs_bps', summary.get('cbs_bps', 0.0)):.1f} bps\n"
        if "token_cost_per_decision" in net_perf or "tokens_per_decision" in summary:
            net_section += f"- Token Cost per Decision: {net_perf.get('token_cost_per_decision', summary.get('tokens_per_decision', 0.0)):.0f}\n"
        if "fast_path_debate_bypass_rate" in net_perf or "fast_path_bypass_rate" in summary:
            bpr = net_perf.get("fast_path_debate_bypass_rate", summary.get("fast_path_bypass_rate", 0.0))
            net_section += f"- Fast-Path Bypass Rate: {bpr * 100.0:.1f}%\n"

    # Multi-regime breakdown summary
    regimes_section = ""
    regime_data = summary.get("regime_breakdown") or summary.get("multi_regime_breakdown") or backtest_result.get("regime_breakdown")
    if regime_data and isinstance(regime_data, dict):
        regimes_section = "\n [Multi-Regime Breakdown]\n"
        for r_name, r_info in regime_data.items():
            if isinstance(r_info, dict):
                r_ret = r_info.get("net_return", r_info.get("return", 0.0))
                r_ret_str = f"{r_ret * 100.0:.2f}%" if abs(r_ret) <= 1.0 else f"{r_ret:.2f}%"
                r_sh = r_info.get("net_sharpe", r_info.get("sharpe", 0.0))
                r_mdd = r_info.get("net_max_drawdown", r_info.get("max_drawdown", 0.0))
                r_mdd_str = f"{r_mdd * 100.0:.2f}%" if abs(r_mdd) <= 1.0 else f"{r_mdd:.2f}%"
                regimes_section += f"- {r_name.capitalize()}: Return={r_ret_str}, Sharpe={r_sh:.2f}, Max Drawdown={r_mdd_str}\n"
    
    # Summary of transaction details (take the first 5 transactions)
    trade_summary = ""
    if trades:
        trade_summary = "\n [Transaction details sample]\n"
        for i, trade in enumerate(trades[:5]):
            trade_summary += f"- transaction{i+1}: {trade.get('symbol', 'N/A')} "
            trade_summary += f"{trade.get('entry_date', 'N/A')} -> {trade.get('exit_date', 'N/A')} "
            trade_summary += f"income: {trade.get('return_pct', 0):.1f}%\n"

    # Running logs and warning messages (important! Help identify the source of the problem)
    logs_section = ""
    if logs:
        logs_section = "\n [Backtest running log]\n"
        for log in logs:
            logs_section += f"- {log}\n"

    warnings_section = ""
    if warnings:
        warnings_section = "\n [⚠️ System warning (focus)]\n"
        for warn in warnings:
            warnings_section += f"- {warn}\n"

    # Strategy code summary (intercept key parts)
    code = strategy.get("code", "")
    code_summary = code[:500] + "..." if len(code) > 500 else code

    context = f"""
 [User original needs]
{user_description}

 [Strategy implementation]
```python
{code_summary}
```

 [Policy configuration]
{strategy.get('config', {})}

{result_summary}
{net_section}
{regimes_section}
{trade_summary}
{logs_section}
{warnings_section}

Based on the above information, please evaluate whether the strategy meets user needs, identify existing problems, and give optimization suggestions.
Pay special attention to the [System Warnings] section, these are potential problems automatically detected by the backtesting engine.
"""
    
    return context


async def optimize_strategy_based_on_evaluation(
    user_description: str,
    current_strategy: Dict[str, Any],
    evaluation_result: Dict[str, Any],
    backtest_result: Dict[str, Any],
    llm_client: Optional[UnifiedLLMClient] = None,
) -> Dict[str, Any]:
    """
    Optimize strategies based on evaluation results

    Args:
        user_description: User original needs
        current_strategy: current strategy (code + config) 
        evaluation_result: Assessment results
        backtest_result: Backtest results
        llm_client: LLM client

    Returns:
        Optimized strategy (code + config + optimization_summary) 
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config

        cfg = await get_coding_llm_config()
        if not cfg:
            raise ValueError("LLM is not configured and policy optimization cannot be performed")
        client = UnifiedLLMClient.from_config(cfg)

    # Build optimization context
    context = _build_optimization_context(
        user_description, current_strategy, evaluation_result, backtest_result
    )

    messages = [
        Message(role=MessageRole.SYSTEM, content=OPTIMIZE_SYSTEM),
        Message(role=MessageRole.USER, content=context),
    ]

    try:
        response = await client.achat(messages)
        result_text = (response.content or "").strip()

        # Parse JSON results
        import json
        optimized = json.loads(result_text)

        # Validate required fields
        required_fields = ["code", "config"]
        for field in required_fields:
            if field not in optimized:
                raise ValueError(f"Optimization results are missing required fields: {field}")

        return optimized

    except json.JSONDecodeError as e:
        logger.warning("Optimization result JSON parsing failed: %s", e)
        raise ValueError(f"Optimization result format error: {e}")
    except Exception as e:
        logger.exception("Strategy optimization failed")
        raise ValueError(f"Optimization failed: {e}")


def _build_optimization_context(
    user_description: str,
    current_strategy: Dict[str, Any],
    evaluation_result: Dict[str, Any],
    backtest_result: Dict[str, Any]
) -> str:
    """Build optimization context"""

    # Extract issues from assessment results
    issues = evaluation_result.get("issues", [])
    high_priority_issues = [issue for issue in issues if issue.get("severity") == "high"]

    issues_summary = ""
    if high_priority_issues:
        issues_summary = "\n [Issues that need to be resolved with priority]\n"
        for i, issue in enumerate(high_priority_issues):
            issues_summary += f"{i+1}. {issue.get('description', '')}\n"
            issues_summary += f"   Suggestions: {issue.get('suggestion', '')}\n"

    # Key indicators of backtest results
    summary = backtest_result.get("summary", {}) if "summary" in backtest_result else backtest_result
    performance_summary = f"""
 [Current performance]
- total revenue: {summary.get('total_return', 0):.1f}%
- winning rate: {summary.get('win_rate', 0):.1f}%
- maximum drawdown: {summary.get('max_drawdown_pct', 0):.1f}%
- Number of transactions: {summary.get('trade_count', 0)}
"""

    # Extract system warnings (important problem diagnostic information)
    warnings = backtest_result.get("warnings", [])
    warnings_section = ""
    if warnings:
        warnings_section = "\n [⚠️ Backtest engine warning (focus)]\n"
        for warn in warnings:
            warnings_section += f"- {warn}\n"

    context = f"""
 [User original needs]
{user_description}

 [Current strategy code]
```python
{current_strategy.get('code', '')}
```

 [Current policy configuration]
{current_strategy.get('config', {})}

{performance_summary}
{warnings_section}

 [Evaluation results]
- Overall rating: {evaluation_result.get('overall_score', 0)}/100
- Are you satisfied?: {'Yes' if evaluation_result.get('is_satisfactory') else 'No'}
- Optimization priority: {evaluation_result.get('optimization_priority', 'medium')}

{issues_summary}

 [Optimization goal]
{evaluation_result.get('next_steps', 'Improve strategy performance')}

Based on the above analysis, please optimize the strategy in a targeted manner, focusing on solving high-priority issues and system warnings.
"""

    return context


def should_optimize_strategy(evaluation_result: Dict[str, Any]) -> bool:
    """
    Determine whether an optimization strategy is needed

    Args:
        evaluation_result: Assessment results

    Returns:
        Does it need to be optimized?
    """
    # Optimization is required when the score is lower than 70 or there are high-priority issues
    score = evaluation_result.get("overall_score", 0)
    is_satisfactory = evaluation_result.get("is_satisfactory", False)
    optimization_priority = evaluation_result.get("optimization_priority", "none")

    return (
        score < 70 or
        not is_satisfactory or
        optimization_priority in ["high", "medium"]
    )
