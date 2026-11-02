from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['extended_performance', 'performance_metrics', 'quant_tools']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === extended_performance ===
"""
Expanded Portfolio Performance Metrics Tool

Provides Sortino Ratio, Treynor Ratio, Information Ratio, Calmar Ratio, Jensen Alpha,
Professional portfolio performance analysis functions such as stress testing, scenario analysis, Brinson attribution, and industry attribution.
All indicators are based on purely mathematical calculations without the involvement of LLM.
"""

import json
import logging
import math
from datetime import datetime, timedelta
from typing import Annotated, Optional, Any, List

import numpy as np
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes, get_stock_basic_info
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ============================================================
#  Helper function
# ============================================================

def _extended_performance_safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _extended_performance_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _extended_performance_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


def _load_returns(symbol: str, lookback_days: int) -> Optional[np.ndarray]:
    """Get the daily return series of a single stock."""
    end_date = _extended_performance_today()
    start_date = _extended_performance_days_ago(int(lookback_days) * 2 + 50)
    quotes = get_stock_daily_quotes(
        str(symbol), start_date, end_date, limit=int(lookback_days) + 100
    )
    if not quotes:
        return None
    import pandas as pd
    df = pd.DataFrame(quotes)
    df["close"] = df["close"].apply(_extended_performance_safe_float)
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.dropna(subset=["close"]).sort_values("trade_date")
    df["return"] = df["close"].pct_change()
    df = df.dropna(subset=["return"])
    return df["return"].values


def _load_benchmark_returns(lookback_days: int = 252) -> Optional[np.ndarray]:
    """Obtain the benchmark index (CSI 300) return rate from the local DB, and use AKShare to cover it up if it fails."""
    import pandas as pd
    end = _extended_performance_today()
    start = _extended_performance_days_ago(lookback_days * 2 + 50)
    # Try first 000300
    quotes = get_stock_daily_quotes("000300", start, end, limit=lookback_days + 100)
    if quotes:
        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_extended_performance_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        return df["return"].dropna().values
    # DB No data, use AKShare to find out
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df = df.sort_values("date")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"]).tail(lookback_days)
        return df["return"].values
    except Exception:
        return None


def _annualized_return(returns: np.ndarray) -> float:
    n = len(returns)
    if n == 0:
        return 0.0
    cumulative = float(np.prod(1 + returns))
    return cumulative ** (252.0 / n) - 1


def _max_drawdown_from_returns(returns: np.ndarray) -> float:
    cumulative = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - peak) / peak
    return float(np.min(drawdown))


def _parse_symbols_weights(symbols_str: str, weights_str: Optional[str] = None):
    """Parse the symbol and weight strings and return (symbols_list, weights_list_or_equal)."""
    sym_list = [s.strip() for s in str(symbols_str).split(",") if s.strip()]
    if weights_str:
        w_list = [float(w.strip()) for w in str(weights_str).split(",") if w.strip()]
        # If the number of weights is inconsistent with the number of symbols, fall back to equal weighting.
        if len(w_list) != len(sym_list):
            w_list = [1.0 / len(sym_list)] * len(sym_list)
        else:
            total = sum(w_list)
            if total > 0:
                w_list = [w / total for w in w_list]
    else:
        w_list = [1.0 / len(sym_list)] * len(sym_list) if sym_list else []
    return sym_list, w_list


# ============================================================
#  Tool 1: Sortino Ratio
# ============================================================

@tool
@register_tool(
    tool_id="get_sortino_ratio",
    name="Sortino 比率",
    description="Calculate the Sortino Ratio, a measure of downside risk-adjusted returns, returning annualized returns, downside volatility, Sortino Ratio, target return, and sample size for evaluating asset returns",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["sortino_ratio", "downside_risk_adjusted_return"],
    when_to_use="Use when you need to evaluate the risk-adjusted return of an asset and wish to penalize only downside volatility rather than overall volatility.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), the indicator has limited reference value.",
    returns="Returns JSON, including sortino_ratio, downward_deviation, annualized_return, excess_return.",
    example="get_sortino_ratio(symbol='600519', lookback_days=252, risk_free_rate=0.025)",
    related_tools=["get_sharpe_ratio", "get_calmar_ratio"],
)
def get_sortino_ratio(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    risk_free_rate: Annotated[float, "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
    target_return: Annotated[float, "Target rate of return, default 0.0"] = 0.0,
) -> str:
    """Calculate the Sortino ratio. Only negative return deviation (downside deviation) is used as a risk measure to measure the excess return per unit of downside risk.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)
        target_return: Target rate of return (MAR), default 0.0

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            sortino_ratio: Annualized Sortino ratio (None if not computable)
            downside_deviation: annualized downward bias
            annualized_return: annualized rate of return
            excess_return: Annualized excess return (annualized return – risk-free interest rate)
            risk_free_rate: The actual risk-free rate used
            target_return: Actual target rate of return used
            data_points: Effective rate of return sample number
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025
        target = float(target_return)
        returns = _load_returns(str(symbol), int(lookback_days))

        if returns is None or len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 足够的历史数据（需要至少30个交易日）。"},
                ensure_ascii=False, indent=2, default=str,
            )

        # annualized rate of return
        ann_return = _annualized_return(returns)

        # excess return (Rp - Rf)
        excess_return = ann_return - rf

        # Downside deviation: the standard deviation of the return below target_return
        downside_returns = returns[returns < target]
        if len(downside_returns) >= 2:
            downside_deviation = float(np.std(downside_returns, ddof=1)) * np.sqrt(252)
        elif len(downside_returns) == 1:
            downside_deviation = float(np.std(downside_returns, ddof=0)) * np.sqrt(252)
        else:
            downside_deviation = 0.0

        # Sortino Ratio
        if downside_deviation > 0:
            sortino_ratio = excess_return / downside_deviation
        else:
            sortino_ratio = None if excess_return == 0 else (float("inf") if excess_return > 0 else float("-inf"))

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "sortino_ratio": float(round(sortino_ratio, 4)) if sortino_ratio is not None and np.isfinite(sortino_ratio) else None,
            "downside_deviation": float(round(downside_deviation, 6)),
            "annualized_return": float(round(ann_return, 6)),
            "excess_return": float(round(excess_return, 6)),
            "risk_free_rate": rf,
            "target_return": target,
            "data_points": len(returns),
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Sortino Ratio calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 2: Treynor Ratio
# ============================================================

@tool
@register_tool(
    tool_id="get_treynor_ratio",
    name="Treynor 比率",
    description="Calculate the Treynor Ratio, which measures the excess return per unit of systematic risk, returning the excess return, Beta, Treynor Ratio, risk-free rate, and sample interval",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["treynor_ratio", "systematic_risk_adjusted_return"],
    when_to_use="Used when it is necessary to evaluate the excess return performance of an asset relative to systemic risk.",
    when_not_to_use="The indicator is not available when there is insufficient data or beta cannot be calculated.",
    returns="Returns JSON containing treynor_ratio, beta, annualized_return, excess_return.",
    example="get_treynor_ratio(symbol='600519', lookback_days=252, risk_free_rate=0.025)",
    related_tools=["get_beta_calculation", "get_sortino_ratio"],
)
def get_treynor_ratio(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    risk_free_rate: Annotated[float, "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
) -> str:
    """Calculate the Treynor ratio. Beta measures systemic risk and measures the excess return per unit of systemic risk.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            treynor_ratio: Treynor Ratio (None if not computable)
            beta: Beta coefficient relative to CSI 300 (reverts to 1.0 when Beta calculation fails)
            annualized_return: annualized rate of return
            excess_return: annualized excess return
            risk_free_rate: The actual risk-free rate used
            data_points: Effective rate of return sample number
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025
        ldays = int(lookback_days)

        returns = _load_returns(sym, ldays)
        if returns is None or len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 足够的历史数据（需要至少30个交易日）。"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Get from get_beta_calculation Beta
        from core.tools.registry import ToolRegistry as _TR
        _reg = _TR()
        beta_raw = _reg.get_function('get_beta_calculation')
        beta_result_str = beta_raw(symbol=sym, benchmark="000300", lookback_days=ldays)
        beta_result = json.loads(beta_result_str)

        if beta_result.get("status") == "error":
            warnings.append(f"Beta 计算异常: {beta_result.get('message')}")
            beta = 1.0
        else:
            beta = beta_result.get("beta", 1.0)
            if beta_result.get("warnings"):
                warnings.extend(beta_result.get("warnings"))

        if beta == 0:
            return json.dumps(
                {"status": "error", "message": "Beta is zero, the Treynor ratio cannot be calculated."},
                ensure_ascii=False, indent=2, default=str,
            )

        # annualized rate of return
        ann_return = _annualized_return(returns)
        excess_return = ann_return - rf
        treynor_ratio = excess_return / beta

        payload = {
            "status": "success",
            "symbol": sym,
            "treynor_ratio": float(round(treynor_ratio, 6)) if np.isfinite(treynor_ratio) else None,
            "beta": float(round(beta, 4)),
            "annualized_return": float(round(ann_return, 6)),
            "excess_return": float(round(excess_return, 6)),
            "risk_free_rate": rf,
            "data_points": len(returns),
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Treynor Ratio calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 3: information ratio
# ============================================================

@tool
@register_tool(
    tool_id="get_information_ratio",
    name="信息比率",
    description="Calculate the information ratio (Information Ratio), which measures the ratio of excess return and tracking error of a portfolio relative to the benchmark index.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["information_ratio", "active_management"],
    when_to_use="Used when it is necessary to evaluate active management capabilities and measure the stability of excess returns relative to a benchmark.",
    when_not_to_use="When the data is insufficient and the tracking error cannot be reliably calculated, the indicator has limited reference value.",
    returns="Return JSON, including information_ratio, tracking_error, excess_return.",
    example="get_information_ratio(symbol='600519', benchmark_symbol='000300', lookback_days=252)",
    related_tools=["get_sortino_ratio", "get_treynor_ratio"],
)
def get_information_ratio(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    benchmark_symbol: Annotated[str, "Benchmark index code, default 000300 (CSI 300)"] = "000300",
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Calculate the information ratio. Measures the ratio of excess return to tracking error of a portfolio relative to the benchmark.

    Args:
        symbol: A stock code, such as 600519,000001
        benchmark_symbol: Benchmark index code, default "000300" (CSI 300)
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            benchmark_symbol: Actual benchmark code used
            information_ratio: information ratio
            tracking_error: annualized tracking error
            excess_return: annualized excess return
            data_points: Number of samples actually used for alignment
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        bench = str(benchmark_symbol)
        ldays = int(lookback_days)

        stock_returns = _load_returns(sym, ldays)

        # Benchmark Index: 000300 Use AKShare to save money
        if bench in ("000300", "399300", "sh000300"):
            benchmark_returns = _load_benchmark_returns(ldays)
        else:
            benchmark_returns = _load_returns(bench, ldays)

        if stock_returns is None or len(stock_returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 足够的历史数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        if benchmark_returns is None or len(benchmark_returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到基准 {bench} 足够的历史数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Alignment length (whichever is shorter)
        min_len = min(len(stock_returns), len(benchmark_returns))
        stock_r = stock_returns[-min_len:]
        bench_r = benchmark_returns[-min_len:]

        # excess return series
        excess_series = stock_r - bench_r
        excess_return = float(np.mean(excess_series) * 252)
        tracking_error = float(np.std(excess_series, ddof=1) * np.sqrt(252))

        if tracking_error > 0:
            information_ratio = excess_return / tracking_error
        else:
            information_ratio = 0.0

        payload = {
            "status": "success",
            "symbol": sym,
            "benchmark_symbol": bench,
            "information_ratio": float(round(information_ratio, 4)),
            "tracking_error": float(round(tracking_error, 6)),
            "excess_return": float(round(excess_return, 6)),
            "data_points": min_len,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("信息比率计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 4: Calmar Ratio
# ============================================================

@tool
@register_tool(
    tool_id="get_calmar_ratio",
    name="Calmar 比率",
    description="Calculate the Calmar ratio, which measures the ratio of annualized return to maximum drawdown. Returns annualized return, maximum drawdown, Calmar ratio and drawdown range, reflecting asset drawdown-adjusted returns.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["calmar_ratio", "drawdown_adjusted_return"],
    when_to_use="Used when it is necessary to evaluate an asset s ability to recover returns after experiencing a maximum drawdown.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), the indicator has limited reference value.",
    returns="Returns JSON, including calmar_ratio, annualized_return, max_drawdown.",
    example="get_calmar_ratio(symbol='600519', lookback_days=252)",
    related_tools=["get_sortino_ratio", "get_sharpe_ratio"],
)
def get_calmar_ratio(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Calculate the Calmar ratio. The ratio of annualized return to maximum drawdown (in absolute terms), which measures drawdown-adjusted returns.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            calmar_ratio: Calmar Ratio (None when maximum drawdown is 0)
            annualized_return: annualized rate of return
            max_drawdown: Maximum drawdown (negative number)
            data_points: Effective rate of return sample number
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        ldays = int(lookback_days)

        returns = _load_returns(sym, ldays)
        if returns is None or len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 足够的历史数据（需要至少30个交易日）。"},
                ensure_ascii=False, indent=2, default=str,
            )

        ann_return = _annualized_return(returns)
        max_dd = _max_drawdown_from_returns(returns)

        if max_dd < 0 and abs(max_dd) > 0:
            calmar_ratio = ann_return / abs(max_dd)
        else:
            calmar_ratio = None

        payload = {
            "status": "success",
            "symbol": sym,
            "calmar_ratio": float(round(calmar_ratio, 4)) if calmar_ratio is not None and np.isfinite(calmar_ratio) else None,
            "annualized_return": float(round(ann_return, 6)),
            "max_drawdown": float(round(max_dd, 6)),
            "data_points": len(returns),
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Calmar Ratio calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 5: Jensen Alpha
# ============================================================

@tool
@register_tool(
    tool_id="get_jensen_alpha",
    name="Jensen Alpha",
    description="Calculate Jensen Alpha, which measures the difference between a portfolio s actual return and the CAPM model s expected return.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["jensen_alpha", "excess_return_attribution"],
    when_to_use="It is used when it is necessary to evaluate the excess return capability of a fund manager or asset and determine whether the return exceeds market risk compensation.",
    when_not_to_use="The indicator is not available when there is insufficient data or beta cannot be calculated.",
    returns="Returns JSON, containing jensen_alpha, beta, expected_return, actual_return.",
    example="get_jensen_alpha(symbol='600519', lookback_days=252, risk_free_rate=0.025)",
    related_tools=["get_beta_calculation", "get_treynor_ratio"],
)
def get_jensen_alpha(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    risk_free_rate: Annotated[float, "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
) -> str:
    """Calculate Jensen Alpha. Based on the CAPM model, the difference between the actual return and the expected return of the portfolio is measured.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            jensen_alpha: Jensen Alpha (Actual Returns - CAPM Expected Returns)
            beta: Beta coefficient relative to CSI 300
            expected_return: CAPM expected return
            actual_return: actual annualized return
            market_return: Base annualized return
            risk_free_rate: The actual risk-free rate used
            data_points: Number of samples actually used for alignment
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025
        ldays = int(lookback_days)

        returns = _load_returns(sym, ldays)
        if returns is None or len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 足够的历史数据（需要至少30个交易日）。"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Get the market rate of return (CSI 300, AKShare)
        market_returns = _load_benchmark_returns(ldays)
        if market_returns is None or len(market_returns) < 30:
            return json.dumps(
                {"status": "error", "message": "Not enough historical data for the benchmark index (000300) was obtained to calculate Jensen Alpha."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Alignment
        min_len = min(len(returns), len(market_returns))
        stock_r = returns[-min_len:]
        mkt_r = market_returns[-min_len:]

        # Calculate Beta
        cov = np.cov(stock_r, mkt_r)
        mkt_var = np.var(mkt_r, ddof=1)
        if mkt_var == 0:
            return json.dumps(
                {"status": "error", "message": "The benchmark index variance is zero and beta cannot be calculated."},
                ensure_ascii=False, indent=2, default=str,
            )
        beta = cov[0, 1] / mkt_var

        # annualized rate of return
        actual_return = _annualized_return(stock_r)
        market_return = _annualized_return(mkt_r)

        # CAPM expected return: E(R) = Rf + beta * (Rm - Rf)
        expected_return = rf + beta * (market_return - rf)

        # Jensen Alpha
        jensen_alpha = actual_return - expected_return

        payload = {
            "status": "success",
            "symbol": sym,
            "jensen_alpha": float(round(jensen_alpha, 6)),
            "beta": float(round(beta, 4)),
            "expected_return": float(round(expected_return, 6)),
            "actual_return": float(round(actual_return, 6)),
            "market_return": float(round(market_return, 6)),
            "risk_free_rate": rf,
            "data_points": min_len,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Jensen Alpha Calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 6: Portfolio stress testing
# ============================================================

@tool
@register_tool(
    tool_id="get_portfolio_stress_test",
    name="投资组合压力测试",
    description="Conduct historical scenario stress tests on investment portfolios to simulate the impact of extreme market scenarios such as the 2008 financial crisis, the 2015 stock market crash, the 2020 epidemic, and the 2022 adjustment.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "stress_testing"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["stress_test", "scenario_analysis"],
    when_to_use="Used when there is a need to evaluate a portfolio s potential losses under extreme market conditions.",
    when_not_to_use="Stress testing cannot be conducted when the current price or fundamental information of the stock is not available.",
    returns="Returns JSON containing current_value, scenarios (name of each scenario, total return, impact amount).",
    example="get_portfolio_stress_test(symbols='600519,000001,300750', weights='0.4,0.3,0.3')",
    related_tools=["get_scenario_analysis", "get_var_calculation"],
)
def get_portfolio_stress_test(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as '600519,000001,300750'"],
    weights: Annotated[Optional[str], "List of weights, separated by commas, such as '0.4,0.3,0.3', No transfer will result in equal rights"] = None,
) -> str:
    """Stress test portfolios. Simulate the impact of extreme scenarios such as the 2008 financial crisis, the 2015 stock market crash, the 2020 epidemic, and the 2022 adjustment.

    Args:
        symbols: List of stock symbols, separated by commas, such as "600519,000001,300750"
        weights: List of weights, separated by commas, such as "0.4,0.3,0.3"; Equal weight when None;
            When the number of weights is inconsistent with symbols, it will fall back to equal weighting; the weights will be normalized.

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            current_value: Total current value of the portfolio (by weight × price aggregation)
            num_assets: Asset quantity
            assets: list[dict], Asset list, element structure——
                — symbol: Stock code
                — weight: Normalized weight
                — price: Current price (use an assumed price of 100.0 when missing)
            scenarios: list[dict], Scenario results, element structure——
                — name: scene name ("2008 financial crisis" / "2015 stock market crash" / "2020 Impact of the epidemic" / "2022 market adjustment") 
                — description: Scenario description
                — shock: Scenario shock magnitude (e.g. -0.50)
                — total_return: total portfolio return
                — impact: Impact amount
                — remaining_value: residual value
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym_list, w_list = _parse_symbols_weights(str(symbols), weights)

        if not sym_list:
            return json.dumps(
                {"status": "error", "message": "At least one ticker symbol is required."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Get current prices and underlying information
        current_prices = {}
        for sym in sym_list:
            basic_info = get_stock_basic_info(sym) or {}
            # Try to get the latest price from basic information
            price = _extended_performance_safe_float(basic_info.get("close")) or _extended_performance_safe_float(basic_info.get("price")) or _extended_performance_safe_float(basic_info.get("latest_price"))
            if price is None:
                # Fallback: Get the latest closing price from the daily line
                end_date = _extended_performance_today()
                start_date = _extended_performance_days_ago(10)
                quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=5)
                if quotes:
                    price = _extended_performance_safe_float(quotes[-1].get("close"))
            if price is not None:
                current_prices[sym] = price
            else:
                warnings.append(f"无法获取 {sym} 的当前价格，使用假设价格 100。")
                current_prices[sym] = 100.0

        # Calculate the total current value of the portfolio (assuming each stock holds 1 unit or by weight)
        # Use normalized weights and prices
        total_value = sum(w_list[i] * current_prices[sym_list[i]] for i in range(len(sym_list)))

        # Four historical stress scenarios
        scenarios_config = [
            {"name": "2008 金融危机", "shock": -0.50, "description": "2008 During the global financial crisis, markets fell by approx.50%"},
            {"name": "2015 股灾", "shock": -0.40, "description": "2015 China s stock market crash in 2016, the market fell by about 40%"},
            {"name": "2020 疫情冲击", "shock": -0.30, "description": "2020 Impacted by the COVID-19 epidemic in 2019, the market fell by approximately 30%"},
            {"name": "2022 市场调整", "shock": -0.20, "description": "2022 The market adjusted in 2018, falling by approximately 20%"},
        ]

        scenario_results = []
        for sc in scenarios_config:
            shock = sc["shock"]
            # Simplification: all assets receive the same shock
            portfolio_return = shock
            impact = total_value * shock

            scenario_results.append({
                "name": sc["name"],
                "description": sc["description"],
                "shock": shock,
                "total_return": float(round(portfolio_return, 4)),
                "impact": float(round(impact, 2)),
                "remaining_value": float(round(total_value + impact, 2)),
            })

        payload = {
            "status": "success",
            "current_value": float(round(total_value, 2)),
            "num_assets": len(sym_list),
            "assets": [{"symbol": sym_list[i], "weight": float(round(w_list[i], 4)), "price": float(round(current_prices[sym_list[i]], 2))} for i in range(len(sym_list))],
            "scenarios": scenario_results,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("压力测试失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 7: Scenario analysis
# ============================================================

@tool
@register_tool(
    tool_id="get_scenario_analysis",
    name="情景分析",
    description="Conduct custom scenario analysis on the investment portfolio, calculate the overall impact of the portfolio based on the rise and fall of each asset specified by the user, and return changes in market value, profit and loss, new weights and risk indicators of the portfolio under each scenario",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "scenario_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["custom_scenario_analysis", "what_if_analysis"],
    when_to_use="Use when you need to simulate the impact of custom market scenarios on your portfolio.",
    when_not_to_use="The scenario JSON cannot be parsed when it is not properly formatted.",
    returns="Returns JSON containing base_value, scenario_results (name of each scenario, total value after shock, total return, details).",
    example="get_scenario_analysis(symbols='600519,000001', weights='0.5,0.5', scenarios='[{\"name\":\"bull market\",\"shocks\":{\"600519\":0.2,\"000001\":0.1}}]')",
    related_tools=["get_portfolio_stress_test"],
)
def get_scenario_analysis(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as '600519,000001'"],
    weights: Annotated[Optional[str], "List of weights, separated by commas, such as '0.5,0.5', No transfer will result in equal rights"] = None,
    scenarios: Annotated[str, "Scenario JSON string in the format [{\"name\": \"scene name\", \"shocks\": {\"600519\": -0.1, \"000001\": 0.05}}]"] = "[]",
) -> str:
    """Perform custom scenario analysis on your portfolio. The overall impact of the portfolio is calculated based on the rise and fall of each asset specified by the user.

    Args:
        symbols: List of stock symbols, separated by commas, such as "600519,000001"
        weights: List of weights, separated by commas, such as "0.5,0.5"; Equal weight when None; weights will be normalized
        scenarios: Context JSON string, default "[]"; 
            The format is [{"name": "scene name", "shocks": {"600519": -0.1, "000001": 0.05}}]

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            base_value: Portfolio base total value
            num_assets: Asset quantity
            num_scenarios: The number of scenarios obtained by analysis
            scenario_results: list[dict], Scenario results, element structure——
                — name: scene name
                — total_return: total portfolio return
                — post_value: Total post-shock portfolio value
                — impact: Impact amount
                — asset_details: list[dict], Asset details, element structure——
                    — symbol: Stock code
                    — weight: weight
                    — shock: The magnitude of the asset s impact
                    — contribution: Contribution to portfolio returns
                    — value_change: Change in asset value
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym_list, w_list = _parse_symbols_weights(str(symbols), weights)

        if not sym_list:
            return json.dumps(
                {"status": "error", "message": "At least one ticker symbol is required."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Get current price
        current_prices = {}
        for sym in sym_list:
            basic_info = get_stock_basic_info(sym) or {}
            price = _extended_performance_safe_float(basic_info.get("close")) or _extended_performance_safe_float(basic_info.get("price")) or _extended_performance_safe_float(basic_info.get("latest_price"))
            if price is None:
                end_date = _extended_performance_today()
                start_date = _extended_performance_days_ago(10)
                quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=5)
                if quotes:
                    price = _extended_performance_safe_float(quotes[-1].get("close"))
            if price is not None:
                current_prices[sym] = price
            else:
                warnings.append(f"无法获取 {sym} 的当前价格，使用假设价格 100。")
                current_prices[sym] = 100.0

        base_value = sum(w_list[i] * current_prices[sym_list[i]] for i in range(len(sym_list)))

        # Analyze the situation
        try:
            parsed_scenarios = json.loads(str(scenarios))
            if not isinstance(parsed_scenarios, list):
                parsed_scenarios = [parsed_scenarios]
        except (json.JSONDecodeError, TypeError):
            return json.dumps(
                {"status": "error", "message": "Scenario JSON is not in the correct format, please provide a valid JSON array."},
                ensure_ascii=False, indent=2, default=str,
            )

        scenario_results = []
        for scenario in parsed_scenarios:
            name = scenario.get("name", "未命名情景")
            shocks = scenario.get("shocks", {})

            total_impact = 0.0
            asset_details = []
            for i, sym in enumerate(sym_list):
                shock = float(shocks.get(sym, 0.0))
                weight = w_list[i]
                contribution = weight * shock
                total_impact += contribution

                asset_value_change = current_prices[sym] * shock
                asset_details.append({
                    "symbol": sym,
                    "weight": float(round(weight, 4)),
                    "shock": shock,
                    "contribution": float(round(contribution, 6)),
                    "value_change": float(round(asset_value_change, 2)),
                })

            post_value = base_value * (1 + total_impact)
            scenario_results.append({
                "name": name,
                "total_return": float(round(total_impact, 6)),
                "post_value": float(round(post_value, 2)),
                "impact": float(round(base_value * total_impact, 2)),
                "asset_details": asset_details,
            })

        payload = {
            "status": "success",
            "base_value": float(round(base_value, 2)),
            "num_assets": len(sym_list),
            "num_scenarios": len(scenario_results),
            "scenario_results": scenario_results,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("情景分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 8: Brinson attribution
# ============================================================

@tool
@register_tool(
    tool_id="get_brinson_attribution",
    name="Brinson 归因分析",
    description="Use the Brinson model to perform performance attribution on the portfolio, decompose the sources of excess returns, and return allocation effects, stock selection effects, interaction effects, industry contributions, and excess return decompositions",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["performance_attribution", "portfolio_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["brinson_attribution", "performance_decomposition"],
    when_to_use="It is used when it is necessary to analyze the sources of excess returns of a portfolio and distinguish the contributions of allocation decisions and stock selection decisions.",
    when_not_to_use="Attribution results may be incomplete when insufficient data or industry classification information is unavailable.",
    returns="Returns JSON, including allocation_effect, selection_effect, interaction_effect, total_excess_return.",
    example="get_brinson_attribution(symbols='600519,000001,300750', benchmark_symbols='000300,399001,399006')",
    related_tools=["get_sector_attribution", "get_factor_attribution"],
)
def get_brinson_attribution(
    symbols: Annotated[str, "List of portfolio ticker symbols, separated by commas, e.g. '600519,000001,300750'"],
    benchmark_symbols: Annotated[str, "List of benchmark index codes, comma separated, default '000300,399001,399006' (CSI 300, Shenzhen Component Index, GEM Index)"] = "000300,399001,399006",
) -> str:
    """Perform Brinson performance attribution on portfolios. Decompose excess returns into allocation effects, stock selection effects and interaction effects.

    Args:
        symbols: List of portfolio ticker symbols, separated by commas, e.g. "600519,000001,300750"
        benchmark_symbols: List of benchmark index codes, comma separated, default "000300,399001,399006"
             (CSI 300, Shenzhen Component Index, GEM Index)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            allocation_effect: allocation effect
            selection_effect: stock picking effect
            interaction_effect: interaction effect
            total_excess_return: Total excess return (portfolio - benchmark)
            portfolio_return: Portfolio annualized return
            benchmark_return: Base annualized return
            portfolio_assets: list[str], Combined stock code list
            benchmark_assets: list[str], Benchmark Index Code List
            industry_breakdown: dict, Industry breakdown——
                — portfolio: dict[str, dict], Combine various industries——
                    — <Industry name>: {weight: weight, return: Industry income}
                — benchmark: dict[str, dict], Benchmark various industries——
                    — <Industry name>: {weight: weight, return: Industry income}
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym_list = [s.strip() for s in str(symbols).split(",") if s.strip()]
        bench_list = [s.strip() for s in str(benchmark_symbols).split(",") if s.strip()]

        if not sym_list:
            return json.dumps(
                {"status": "error", "message": "At least one portfolio ticker is required."},
                ensure_ascii=False, indent=2, default=str,
            )

        if not bench_list:
            bench_list = ["000300", "399001", "399006"]

        ldays = 252
        end_date = _extended_performance_today()
        start_date = _extended_performance_days_ago(ldays * 2 + 50)

        # Get the industry classification and return rate of each stock in the portfolio
        portfolio_sectors = {}
        portfolio_returns = {}
        for sym in sym_list:
            basic_info = get_stock_basic_info(sym) or {}
            industry = str(basic_info.get("industry", basic_info.get("sector", "未知")))
            if industry in ("None", "", "未知"):
                industry = "未知"
            portfolio_sectors[sym] = industry

            quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=ldays + 50)
            if quotes:
                import pandas as pd
                df = pd.DataFrame(quotes)
                df["close"] = df["close"].apply(_extended_performance_safe_float)
                df = df.dropna(subset=["close"]).sort_values("trade_date")
                df["return"] = df["close"].pct_change()
                df = df.dropna(subset=["return"])
                if len(df) >= 20:
                    portfolio_returns[sym] = float(np.mean(df["return"].values) * 252)
                else:
                    portfolio_returns[sym] = 0.0
                    warnings.append(f"{sym} Insufficient data, return rate set to 0.")
            else:
                portfolio_returns[sym] = 0.0
                warnings.append(f"无法获取 {sym} 的日线数据，收益率设为 0。")

        # Get the industry classification and return rate of the benchmark index
        benchmark_sectors = {}
        benchmark_returns = {}
        for bench in bench_list:
            basic_info = get_stock_basic_info(bench) or {}
            industry = str(basic_info.get("industry", basic_info.get("sector", "基准")))
            if industry in ("None", "", "未知"):
                industry = "基准"
            benchmark_sectors[bench] = industry

            quotes = get_stock_daily_quotes(bench, start_date, end_date, limit=ldays + 50)
            if quotes:
                import pandas as pd
                df = pd.DataFrame(quotes)
                df["close"] = df["close"].apply(_extended_performance_safe_float)
                df = df.dropna(subset=["close"]).sort_values("trade_date")
                df["return"] = df["close"].pct_change()
                df = df.dropna(subset=["return"])
                if len(df) >= 20:
                    benchmark_returns[bench] = float(np.mean(df["return"].values) * 252)
                else:
                    benchmark_returns[bench] = 0.0
            else:
                benchmark_returns[bench] = 0.0

        # Simplified Brinson Attribution
        # Equal weight assumption
        port_weight = 1.0 / len(sym_list)
        bench_weight = 1.0 / len(bench_list)

        # total portfolio return
        port_total_return = sum(portfolio_returns.get(sym, 0.0) for sym in sym_list) / len(sym_list)
        # Benchmark total return
        bench_total_return = sum(benchmark_returns.get(b, 0.0) for b in bench_list) / len(bench_list)

        # allocation effect: Differences in allocation weights across industries * Benchmark industry returns
        allocation_effect = 0.0
        selection_effect = 0.0
        interaction_effect = 0.0

        # Group by industry
        port_industry_weights = {}
        port_industry_returns = {}
        for sym in sym_list:
            ind = portfolio_sectors.get(sym, "未知")
            port_industry_weights[ind] = port_industry_weights.get(ind, 0.0) + port_weight
            port_industry_returns[ind] = port_industry_returns.get(ind, 0.0) + portfolio_returns.get(sym, 0.0) * port_weight

        bench_industry_weights = {}
        bench_industry_returns = {}
        for bench in bench_list:
            ind = benchmark_sectors.get(bench, "基准")
            bench_industry_weights[ind] = bench_industry_weights.get(ind, 0.0) + bench_weight
            bench_industry_returns[ind] = bench_industry_returns.get(ind, 0.0) + benchmark_returns.get(bench, 0.0) * bench_weight

        all_industries = set(list(port_industry_weights.keys()) + list(bench_industry_weights.keys()))
        for ind in all_industries:
            pw = port_industry_weights.get(ind, 0.0)
            bw = bench_industry_weights.get(ind, 0.0)
            pr = port_industry_returns.get(ind, 0.0)
            br = bench_industry_returns.get(ind, 0.0)

            allocation_effect += (pw - bw) * br
            selection_effect += bw * (pr - br)
            interaction_effect += (pw - bw) * (pr - br)

        total_excess_return = port_total_return - bench_total_return

        payload = {
            "status": "success",
            "allocation_effect": float(round(allocation_effect, 6)),
            "selection_effect": float(round(selection_effect, 6)),
            "interaction_effect": float(round(interaction_effect, 6)),
            "total_excess_return": float(round(total_excess_return, 6)),
            "portfolio_return": float(round(port_total_return, 6)),
            "benchmark_return": float(round(bench_total_return, 6)),
            "portfolio_assets": sym_list,
            "benchmark_assets": bench_list,
            "industry_breakdown": {
                "portfolio": {k: {"weight": float(round(v, 4)), "return": float(round(port_industry_returns.get(k, 0.0), 6))} for k, v in port_industry_weights.items()},
                "benchmark": {k: {"weight": float(round(v, 4)), "return": float(round(bench_industry_returns.get(k, 0.0), 6))} for k, v in bench_industry_weights.items()},
            },
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Brinson Attribution analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 9: Industry attribution
# ============================================================

@tool
@register_tool(
    tool_id="get_sector_attribution",
    name="行业归因分析",
    description="Calculate the income contribution of each stock in the investment portfolio by industry classification, and return structured attribution reports such as industry weight, rate of return, contribution proportion, asset quantity and detailed list",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["performance_attribution", "sector_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["sector_attribution", "industry_contribution"],
    when_to_use="Used when it is necessary to analyze the contribution of each industry in the portfolio to total returns.",
    when_not_to_use="Attribution cannot be completed when the industry classification information of the stock cannot be obtained.",
    returns="Returns JSON, containing a list of sector_contributions (name, weight, rate of return, contribution of each industry).",
    example="get_sector_attribution(symbols='600519,000001,300750,002415,601318')",
    related_tools=["get_brinson_attribution", "get_factor_attribution"],
)
def get_sector_attribution(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as '600519,000001,300750'"],
) -> str:
    """Conduct industry attribution analysis on portfolios. Calculate the contribution of each industry to the total return of the portfolio by industry classification.

    Args:
        symbols: List of stock symbols, separated by commas, such as "600519,000001,300750"

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            portfolio_return: Portfolio annualized return
            num_sectors: Number of industries
            num_assets: Asset quantity
            sector_contributions: list[dict], Arranged in descending order by industry revenue, element structure——
                — sector: Industry name
                — weight: Industry weight
                — return: Industry Weighted Returns
                — contribution_pct: Revenue contribution percentage
                — num_assets: Number of assets in the industry
                — assets: list[dict], List of assets in the industry——
                    — symbol: Stock code
                    — return: annualized income
                    — weight: weight
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym_list = [s.strip() for s in str(symbols).split(",") if s.strip()]

        if not sym_list:
            return json.dumps(
                {"status": "error", "message": "At least one ticker symbol is required."},
                ensure_ascii=False, indent=2, default=str,
            )

        ldays = 252
        end_date = _extended_performance_today()
        start_date = _extended_performance_days_ago(ldays * 2 + 50)

        # Get industry information and returns for each stock
        sector_data = {}  # sector -> {total_return, weight, symbols}
        total_weight = 1.0 / len(sym_list)

        for sym in sym_list:
            basic_info = get_stock_basic_info(sym) or {}
            industry = str(basic_info.get("industry", basic_info.get("sector", "未知")))
            if industry in ("None", "", "未知"):
                industry = "未知"

            # Get rate of return
            quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=ldays + 50)
            stock_return = 0.0
            if quotes:
                import pandas as pd
                df = pd.DataFrame(quotes)
                df["close"] = df["close"].apply(_extended_performance_safe_float)
                df = df.dropna(subset=["close"]).sort_values("trade_date")
                df["return"] = df["close"].pct_change()
                df = df.dropna(subset=["return"])
                if len(df) >= 20:
                    stock_return = float(np.mean(df["return"].values) * 252)
                else:
                    warnings.append(f"{sym} Insufficient data, return rate set to 0.")
            else:
                warnings.append(f"无法获取 {sym} 的日线数据，收益率设为 0。")

            if industry not in sector_data:
                sector_data[industry] = {
                    "total_return": 0.0,
                    "total_weight": 0.0,
                    "assets": [],
                }
            sector_data[industry]["total_return"] += stock_return * total_weight
            sector_data[industry]["total_weight"] += total_weight
            sector_data[industry]["assets"].append({
                "symbol": sym,
                "return": float(round(stock_return, 6)),
                "weight": float(round(total_weight, 4)),
            })

        portfolio_return = sum(sd["total_return"] for sd in sector_data.values())

        sector_contributions = []
        for sector_name, data in sorted(sector_data.items(), key=lambda x: x[1]["total_return"], reverse=True):
            contribution_pct = (data["total_return"] / portfolio_return * 100) if portfolio_return != 0 else 0.0
            sector_contributions.append({
                "sector": sector_name,
                "weight": float(round(data["total_weight"], 4)),
                "return": float(round(data["total_return"], 6)),
                "contribution_pct": float(round(contribution_pct, 2)),
                "num_assets": len(data["assets"]),
                "assets": data["assets"],
            })

        payload = {
            "status": "success",
            "portfolio_return": float(round(portfolio_return, 6)),
            "num_sectors": len(sector_contributions),
            "num_assets": len(sym_list),
            "sector_contributions": sector_contributions,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("行业归因分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_sortino_ratio",
    "get_treynor_ratio",
    "get_information_ratio",
    "get_calmar_ratio",
    "get_jensen_alpha",
    "get_portfolio_stress_test",
    "get_scenario_analysis",
    "get_brinson_attribution",
    "get_sector_attribution",
]

# === performance_metrics ===
"""
Portfolio Performance Metrics Tool

Provides professional portfolio performance indicator calculations such as Beta coefficient, Sharpe ratio, VaR value at risk, etc.
All indicators are based on purely mathematical calculations without the involvement of LLM.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ============================================================
#  Helper function
# ============================================================

def _performance_metrics_safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _performance_metrics_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _performance_metrics_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


# ============================================================
#  Tool 1: Beta Coefficient calculation
# ============================================================

@tool
@register_tool(
    tool_id="get_beta_calculation",
    name="Beta 系数计算",
    description="Calculate the Beta, Alpha, and R² and correlation coefficients, returning regression statistics, residual analysis, and data point information used to measure systemic risk exposure",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["beta_calculation", "systematic_risk"],
    when_to_use="Used when it is necessary to measure the systemic risk exposure of an individual stock relative to the broader market, or to assess the co-movement of a stock with a benchmark.",
    when_not_to_use="Returns a warning when there is insufficient data (less than 30 trading days) or when baseline data is missing and cannot be rolled back.",
    returns="Returns JSON containing symbol, beta, alpha_annualized, r_squared, correlation, data_points, period_days, warnings.",
    example="get_beta_calculation(symbol='600519', benchmark='000300', lookback_days=252)",
    related_tools=["get_sharpe_ratio", "get_var_calculation"],
)
def get_beta_calculation(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    benchmark: Annotated[Optional[str], "Benchmark index code, default 000300 (CSI 300)"] = "000300",
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Calculate the beta coefficient of an individual stock relative to a benchmark index. Also gives Alpha,R², Regression indicators such as correlation coefficients measure systemic risk exposure.

    Args:
        symbol: A stock code, such as 600519,000001
        benchmark: Benchmark index code, default "000300" (CSI 300)
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            beta: Beta Coefficient (fallback to 1.0 when baseline is missing or variance is 0)
            alpha_annualized: Annualized Alpha (None if baseline is not available)
            r_squared: coefficient of determination R² (None if the baseline is not available)
            correlation: Correlation coefficient (None if benchmark is not available)
            data_points: The actual number of effective rate of return samples used
            period_days: Add ginseng lookback_days
            benchmark: Actual benchmark code used
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        end_date = _performance_metrics_today()
        start_date = _performance_metrics_days_ago(int(lookback_days) * 2 + 50)

        stock_quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(lookback_days) + 100
        )
        benchmark_quotes = get_stock_daily_quotes(
            str(benchmark), start_date, end_date, limit=int(lookback_days) + 100
        )

        warnings: list = []

        if not stock_quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据。", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        stock_df = pd.DataFrame(stock_quotes)
        stock_df["close"] = stock_df["close"].apply(_performance_metrics_safe_float)
        stock_df["trade_date"] = stock_df["trade_date"].astype(str)
        stock_df = stock_df.dropna(subset=["close"]).sort_values("trade_date")
        stock_df["return"] = stock_df["close"].pct_change()
        stock_df = stock_df.dropna(subset=["return"])

        if len(stock_df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} The effective return data is less than 30 trading days, so beta cannot be reliably calculated.",
                 "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        # Process benchmark data
        no_benchmark = False
        if not benchmark_quotes:
            warnings.append(f"未获取到基准指数 {benchmark} 的日线数据，使用市场默认 beta=1.0。")
            no_benchmark = True
        else:
            bench_df = pd.DataFrame(benchmark_quotes)
            bench_df["close"] = bench_df["close"].apply(_performance_metrics_safe_float)
            bench_df["trade_date"] = bench_df["trade_date"].astype(str)
            bench_df = bench_df.dropna(subset=["close"]).sort_values("trade_date")
            bench_df["return"] = bench_df["close"].pct_change()
            bench_df = bench_df.dropna(subset=["return"])

            if len(bench_df) < 20:
                warnings.append(f"基准指数 {benchmark} 有效收益率数据不足20个交易日，使用市场默认 beta=1.0。")
                no_benchmark = True

        if no_benchmark:
            payload = {
                "status": "success",
                "symbol": str(symbol),
                "beta": 1.0,
                "alpha_annualized": None,
                "r_squared": None,
                "correlation": None,
                "data_points": len(stock_df),
                "period_days": int(lookback_days),
                "benchmark": str(benchmark),
                "warnings": warnings,
            }
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        # Align dates
        merged = pd.merge(
            stock_df[["trade_date", "return"]],
            bench_df[["trade_date", "return"]],
            on="trade_date",
            how="inner",
            suffixes=("_stock", "_bench"),
        )

        if len(merged) < 30:
            warnings.append(f"股票与基准重叠交易日仅 {len(merged)} 天，不足30天，结果参考价值有限。")

        stock_returns = merged["return_stock"]
        bench_returns = merged["return_bench"]

        # Beta = Cov(stock, bench) / Var(bench)
        cov_matrix = np.cov(stock_returns, bench_returns)
        bench_var = np.var(bench_returns, ddof=1)

        if bench_var == 0:
            payload = {
                "status": "success",
                "symbol": str(symbol),
                "beta": 1.0,
                "alpha_annualized": None,
                "r_squared": None,
                "correlation": None,
                "data_points": len(merged),
                "period_days": int(lookback_days),
                "benchmark": str(benchmark),
                "warnings": warnings + ["The benchmark return variance is zero and beta cannot be calculated."],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        beta = cov_matrix[0, 1] / bench_var if len(cov_matrix) > 1 else float(np.cov(stock_returns, bench_returns)[0, 1] / bench_var)

        # Alpha (annualized)
        alpha_daily = stock_returns.mean() - beta * bench_returns.mean()
        alpha_annualized = alpha_daily * 252

        # Correlation
        correlation = float(np.corrcoef(stock_returns, bench_returns)[0, 1])

        # R²
        r_squared = float(correlation ** 2)

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "beta": float(round(beta, 4)),
            "alpha_annualized": float(round(alpha_annualized, 6)),
            "r_squared": float(round(r_squared, 4)),
            "correlation": float(round(correlation, 4)),
            "data_points": len(merged),
            "period_days": int(lookback_days),
            "benchmark": str(benchmark),
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Beta Coefficient calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 2: Sharpe ratio
# ============================================================

@tool
@register_tool(
    tool_id="get_sharpe_ratio",
    name="夏普比率",
    description="Calculate comprehensive risk-adjusted return indicators and return Sharpe ratio, Sortino ratio, Kalmar ratio, annualized return, volatility, maximum drawdown and other comprehensive indicators for evaluating risk returns",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "performance"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["risk_adjusted_return", "performance_evaluation"],
    when_to_use="Use when you need to evaluate the risk-adjusted return of a stock or compare the risk-return characteristics of different assets.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), the indicator has limited reference value.",
    returns="Returns JSON containing sharpe_ratio, sortino_ratio, calmar_ratio, annual_return, annual_volatility, max_drawdown, data_points, interpretation.",
    example="get_sharpe_ratio(symbol='600519', risk_free_rate=0.025, lookback_days=252)",
    related_tools=["get_beta_calculation", "get_var_calculation"],
)
def get_sharpe_ratio(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    risk_free_rate: Annotated[Optional[float], "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Calculate a comprehensive risk-adjusted return metric. Including Sharpe, Sortino, and Kalmar ratios, as well as annualized returns, annualized volatility, and maximum drawdowns.

    Args:
        symbol: A stock code, such as 600519,000001
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            sharpe_ratio: Annualized Sharpe ratio (None if not computable)
            sortino_ratio: Annualized Sortino Ratio (None if there are insufficient downside samples)
            calmar_ratio: Kalmar Ratio (None when maximum drawdown is 0)
            annual_return: annualized rate of return
            annual_volatility: annualized volatility
            max_drawdown: Maximum drawdown (negative number)
            risk_free_rate: The actual risk-free rate used
            data_points: Effective rate of return sample number
            interpretation: Risk-adjusted return evaluation copy
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        end_date = _performance_metrics_today()
        start_date = _performance_metrics_days_ago(int(lookback_days) * 2 + 50)

        quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(lookback_days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_performance_metrics_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        returns = df["return"].values
        close_prices = df["close"].values

        if len(returns) < 30:
            warnings.append(f"有效收益率数据仅 {len(returns)} 天，不足30天，指标参考价值有限。")

        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025
        daily_rf = rf / 252

        excess_returns = returns - daily_rf
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)

        # Sharpe ratio (annualized)
        if std_excess > 0:
            sharpe_ratio = (mean_excess / std_excess) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0 if mean_excess == 0 else float("inf") if mean_excess > 0 else float("-inf")

        # Sortino ratio (using downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) >= 2:
            downside_std = np.std(downside_returns, ddof=1)
            sortino_ratio = (mean_excess / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
        else:
            sortino_ratio = None

        # Annual return
        cumulative_return = (1 + returns).prod()
        n_days = len(returns)
        annual_return = cumulative_return ** (252 / n_days) - 1

        # Annual volatility
        annual_volatility = std_excess * np.sqrt(252)

        # Max drawdown
        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        max_drawdown = float(np.min(drawdown))

        # Calmar ratio
        if max_drawdown < 0 and abs(max_drawdown) > 0:
            calmar_ratio = annual_return / abs(max_drawdown)
        else:
            calmar_ratio = None

        # Interpretation
        if sharpe_ratio > 2:
            interpretation = "Excellent — Excellent risk-adjusted returns"
        elif sharpe_ratio > 1:
            interpretation = "good — Better risk-adjusted returns"
        elif sharpe_ratio > 0.5:
            interpretation = "Average — Moderate risk-adjusted returns"
        elif sharpe_ratio > 0:
            interpretation = "Poor — Risk-adjusted returns are low"
        else:
            interpretation = "Poor — Returns did not beat the risk-free rate"

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "sharpe_ratio": float(round(sharpe_ratio, 4)) if np.isfinite(sharpe_ratio) else None,
            "sortino_ratio": float(round(sortino_ratio, 4)) if sortino_ratio is not None and np.isfinite(sortino_ratio) else None,
            "calmar_ratio": float(round(calmar_ratio, 4)) if calmar_ratio is not None and np.isfinite(calmar_ratio) else None,
            "annual_return": float(round(annual_return, 6)),
            "annual_volatility": float(round(annual_volatility, 6)),
            "max_drawdown": float(round(max_drawdown, 6)),
            "risk_free_rate": rf,
            "data_points": len(returns),
            "interpretation": interpretation,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("夏普比率计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 3: VaR Value at Risk Calculation
# ============================================================

@tool
@register_tool(
    tool_id="get_var_calculation",
    name="VaR 风险价值计算",
    description="Calculate VaR (value at risk) and CVaR (conditional value at risk/expected loss) for historical simulation and parametric methods, supporting daily and annualized output.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["risk_analysis", "downside_risk"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["var_calculation", "tail_risk", "risk_management"],
    when_to_use="Used when you need to quantify lower tail risk and estimate the maximum possible loss at a given confidence level.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), VaR has limited reference value.",
    returns="Returns JSON, containing method, confidence, var_daily, var_annual, cvar_daily, cvar_annual, data_points, interpretation.",
    example="get_var_calculation(symbol='600519', confidence=0.95, lookback_days=252, method='historical')",
    related_tools=["get_beta_calculation", "get_sharpe_ratio"],
)
def get_var_calculation(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    confidence: Annotated[float, "Confidence level, default 0.95"] = 0.95,
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    method: Annotated[str, "Calculation method: historical (historical simulation method) or parametric (parametric method)"] = "historical",
) -> str:
    """Calculate VaR value at risk. Calculate daily/annualized VaR and CVaR (expected loss) based on historical simulation or parametric methods.

    Args:
        symbol: A stock code, such as 600519,000001
        confidence: Confidence level, default 0.95
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        method: Calculation method, default "historical"; Optional "historical" (historical simulation method) or "parametric" (parametric method),
            Illegal values will fall back to "historical"

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            method: The calculation method actually used,"historical" or "parametric"
            confidence: The confidence level actually used (clipped to [0.5, 0.999]) 
            var_daily: Daily VaR (negative number indicates loss)
            var_annual: annualized VaR
            cvar_daily: Daily CVaR / expected loss
            cvar_annual: Annualized CVaR / expected loss
            data_points: Effective rate of return sample number
            interpretation: Risk level evaluation copy (None in scipy missing retry scenario)
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        end_date = _performance_metrics_today()
        start_date = _performance_metrics_days_ago(int(lookback_days) * 2 + 50)

        quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(lookback_days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        warnings: list = []

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_performance_metrics_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        returns = df["return"].values

        if len(returns) < 30:
            warnings.append(f"有效收益率数据仅 {len(returns)} 天，不足30天，VaR 参考价值有限。")

        conf = float(confidence)
        cl = max(0.5, min(0.999, conf))
        alpha = 1.0 - cl
        chosen_method = str(method).strip().lower()

        if chosen_method not in ("historical", "parametric"):
            chosen_method = "historical"
            warnings.append(f"不支持的方法 '{method}'，已回退为 historical。")

        # Historical VaR
        hist_var_daily = float(np.percentile(returns, alpha * 100))

        # Historical CVaR (Expected Shortfall)
        tail_returns = returns[returns <= hist_var_daily]
        if len(tail_returns) > 0:
            hist_cvar_daily = float(np.mean(tail_returns))
        else:
            hist_cvar_daily = hist_var_daily

        # Parametric VaR
        from scipy.stats import norm as scipy_norm

        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)
        z_score = scipy_norm.ppf(alpha)  # negative for alpha < 0.5
        param_var_daily = mu + z_score * sigma

        # Parametric CVaR
        param_cvar_daily = mu - sigma * scipy_norm.pdf(z_score) / alpha

        # Annualize (square root of time rule)
        sqrt252 = np.sqrt(252)

        if chosen_method == "historical":
            var_daily = hist_var_daily
            var_annual = hist_var_daily * sqrt252
            cvar_daily = hist_cvar_daily
            cvar_annual = hist_cvar_daily * sqrt252
        else:
            var_daily = param_var_daily
            var_annual = param_var_daily * sqrt252
            cvar_daily = param_cvar_daily
            cvar_annual = param_cvar_daily * sqrt252

        # Interpretation
        var_pct = abs(var_daily) * 100
        if var_pct > 6:
            interpretation = "extremely high risk — Daily VaR exceeds 6%"
        elif var_pct > 4:
            interpretation = "high risk — Daily VaR is between 4%-6%"
        elif var_pct > 2:
            interpretation = "medium risk — Daily VaR is between 2%-4%"
        elif var_pct > 1:
            interpretation = "low risk — Daily VaR is between 1%-2%"
        else:
            interpretation = "Very low risk — Daily VaR is lower than 1%"

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "method": chosen_method,
            "confidence": cl,
            "var_daily": float(round(var_daily, 6)),
            "var_annual": float(round(var_annual, 6)),
            "cvar_daily": float(round(cvar_daily, 6)),
            "cvar_annual": float(round(cvar_annual, 6)),
            "data_points": len(returns),
            "interpretation": interpretation,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except ImportError:
        logger.warning("scipy Not installed, VaR parameter method is not available, fallback to historical simulation method.")
        # Retry history-only simulation method
        try:
            end_date = _performance_metrics_today()
            start_date = _performance_metrics_days_ago(int(lookback_days) * 2 + 50)
            quotes = get_stock_daily_quotes(str(symbol), start_date, end_date, limit=int(lookback_days) + 100)
            if not quotes:
                return json.dumps({"status": "error", "message": f"未获取到 {symbol} 的日线数据。"}, ensure_ascii=False, indent=2, default=str)

            df = pd.DataFrame(quotes)
            df["close"] = df["close"].apply(_performance_metrics_safe_float)
            df["trade_date"] = df["trade_date"].astype(str)
            df = df.dropna(subset=["close"]).sort_values("trade_date")
            df["return"] = df["close"].pct_change()
            df = df.dropna(subset=["return"])
            returns = df["return"].values
            conf = float(confidence)
            cl = max(0.5, min(0.999, conf))
            alpha = 1.0 - cl
            var_daily = float(np.percentile(returns, alpha * 100))
            tail_returns = returns[returns <= var_daily]
            cvar_daily = float(np.mean(tail_returns)) if len(tail_returns) > 0 else var_daily
            sqrt252 = np.sqrt(252)
            payload = {
                "status": "success",
                "symbol": str(symbol),
                "method": "historical",
                "confidence": cl,
                "var_daily": float(round(var_daily, 6)),
                "var_annual": float(round(var_daily * sqrt252, 6)),
                "cvar_daily": float(round(cvar_daily, 6)),
                "cvar_annual": float(round(cvar_daily * sqrt252, 6)),
                "data_points": len(returns),
                "interpretation": None,
                "warnings": ["scipy Not installed, only historical simulation method is supported."],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except Exception as exc2:
            logger.error("VaR 计算失败: %s", exc2, exc_info=True)
            return json.dumps({"status": "error", "message": str(exc2)}, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("VaR 计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_beta_calculation",
    "get_sharpe_ratio",
    "get_var_calculation",
]

# === quant_tools ===
"""
Portfolio Quantitative Analysis Tools

Provides professional quantitative analysis functions such as efficient frontier, Monte Carlo simulation, and factor attribution.
All calculations are based on purely mathematical methods without the involvement of LLM.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes, get_stock_basic_info
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ============================================================
#  Helper function
# ============================================================

def _safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


def _load_returns_for_symbol(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """Get the return series of a single stock."""
    end_date = _today()
    start_date = _days_ago(int(lookback_days) * 2 + 50)
    quotes = get_stock_daily_quotes(
        str(symbol), start_date, end_date, limit=int(lookback_days) + 100
    )
    if not quotes:
        return None
    df = pd.DataFrame(quotes)
    df["close"] = df["close"].apply(_safe_float)
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.dropna(subset=["close"]).sort_values("trade_date")
    df["return"] = df["close"].pct_change()
    df = df.dropna(subset=["return"])
    df["symbol"] = str(symbol)
    return df[["trade_date", "return", "symbol"]]


# ============================================================
#  Tool 1: efficient frontier
# ============================================================

@tool
@register_tool(
    tool_id="get_efficient_frontier",
    name="有效前沿分析",
    description="Based on the Markowitz mean-variance model, calculate the efficient frontier curve of the investment portfolio, the maximum Sharpe ratio portfolio (cut point portfolio) and the minimum volatility portfolio.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["portfolio_analysis", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["efficient_frontier", "portfolio_optimization"],
    when_to_use="Use it when you need to analyze the risk-return characteristics of a multi-asset portfolio and find the optimal asset allocation ratio.",
    when_not_to_use="It cannot be calculated when there is insufficient data (at least 2 stocks with valid data and each of at least 30 trading days are required).",
    returns="Returns JSON, containing max_sharpe (return, volatility, Sharpe ratio, weight), min_vol (return, volatility, weight), frontier_points, portfolio_stats.",
    example="get_efficient_frontier(symbols='600519,000001,300750', lookback_days=252, risk_free_rate=0.025, num_portfolios=5000)",
    related_tools=["get_monte_carlo_simulation", "get_sharpe_ratio"],
)
def get_efficient_frontier(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as '600519,000001,300750'"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
    risk_free_rate: Annotated[float, "Risk-free interest rate, default 0.025 (2.5%)"] = 0.025,
    num_portfolios: Annotated[int, "Number of combinations for Monte Carlo simulation, default 5000"] = 5000,
) -> str:
    """Calculate the portfolio efficient frontier. Based on the Markowitz mean-variance model, the maximum Sharpe combination, the minimum fluctuation combination and the frontier curve are given.

    Args:
        symbols: List of stock symbols, separated by commas, such as "600519,000001,300750" (At least 2)
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)
        risk_free_rate: Risk-free interest rate, default 0.025 (2.5%)
        num_portfolios: Number of random combinations for Monte Carlo simulation, default 5000

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            max_sharpe: dict, Maximum Sharpe Ratio Combination——
                — return: annualized income
                — volatility: annualized volatility
                — sharpe_ratio: Sharpe ratio
                — weights: dict[str, float], Weight of each stock
            min_vol: dict, minimum volatility portfolio——
                — return: annualized income
                — volatility: annualized volatility
                — weights: dict[str, float], Weight of each stock
            frontier_points: list[dict], Efficient frontier curve point, element structure——
                — return: target income
                — volatility: Corresponds to the minimum volatility
            portfolio_stats: dict, Combination statistics——
                — num_assets: Number of assets
                — valid_symbols: list[str], The actual valid stock symbol used
                — num_portfolios_simulated: Number of simulation combinations
                — overlapping_trading_days: Number of overlapping trading days
                — risk_free_rate: risk-free rate
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        symbol_list = [s.strip() for s in str(symbols).split(",") if s.strip()]
        if len(symbol_list) < 2:
            return json.dumps(
                {"status": "error", "message": "At least 2 stocks are required for efficient frontier analysis."},
                ensure_ascii=False, indent=2, default=str,
            )

        rf = float(risk_free_rate) if risk_free_rate is not None else 0.025

        # Obtain the return data of each stock and merge it
        returns_dfs = []
        valid_symbols = []
        for sym in symbol_list:
            df = _load_returns_for_symbol(sym, int(lookback_days))
            if df is not None and len(df) >= 30:
                returns_dfs.append(df.rename(columns={"return": sym})[[sym, "trade_date"]])
                valid_symbols.append(sym)
            else:
                warnings.append(f"{sym} Insufficient data (requires at least 30 trading days), excluded.")

        if len(valid_symbols) < 2:
            return json.dumps(
                {"status": "error", "message": "There are less than 2 stocks with at least data, so efficient frontier analysis cannot be performed.", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        # Consolidated return data
        merged = returns_dfs[0]
        for df in returns_dfs[1:]:
            merged = pd.merge(merged, df, on="trade_date", how="inner")
        merged = merged.dropna()
        merged = merged.set_index("trade_date")

        if len(merged) < 20:
            return json.dumps(
                {"status": "error", "message": f"股票间重叠交易日仅 {len(merged)} 天，不足20天。", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        returns_matrix = merged.values
        n_assets = len(valid_symbols)
        mean_returns = np.mean(returns_matrix, axis=0)
        cov_matrix = np.cov(returns_matrix, rowvar=False)

        # Monte Carlo simulation of random combinations
        np.random.seed(42)
        results = np.zeros((3, int(num_portfolios)))
        weights_record = []

        for i in range(int(num_portfolios)):
            weights = np.random.random(n_assets)
            weights = weights / np.sum(weights)
            weights_record.append(weights)

            port_return = np.sum(mean_returns * weights) * 252
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
            sharpe = (port_return - rf) / port_vol if port_vol > 0 else 0

            results[0, i] = port_return
            results[1, i] = port_vol
            results[2, i] = sharpe

        # Maximum Sharpe Ratio Combination
        max_sharpe_idx = np.argmax(results[2])
        max_sharpe_weights = weights_record[max_sharpe_idx]
        max_sharpe_portfolio = {
            "return": float(round(results[0, max_sharpe_idx], 6)),
            "volatility": float(round(results[1, max_sharpe_idx], 6)),
            "sharpe_ratio": float(round(results[2, max_sharpe_idx], 4)),
            "weights": {sym: float(round(w, 6)) for sym, w in zip(valid_symbols, max_sharpe_weights)},
        }

        # minimum volatility portfolio
        min_vol_idx = np.argmin(results[1])
        min_vol_weights = weights_record[min_vol_idx]
        min_vol_portfolio = {
            "return": float(round(results[0, min_vol_idx], 6)),
            "volatility": float(round(results[1, min_vol_idx], 6)),
            "weights": {sym: float(round(w, 6)) for sym, w in zip(valid_symbols, min_vol_weights)},
        }

        # Efficient frontier curve (try using scipy.optimize to calculate the theoretical frontier)
        frontier_points = []
        try:
            from scipy.optimize import minimize

            def portfolio_stats(weights):
                weights = np.array(weights)
                port_return = np.sum(mean_returns * weights) * 252
                port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
                return port_return, port_vol

            constraints = {"type": "eq", "fun": lambda x: np.sum(x) - 1}
            bounds = tuple((0, 1) for _ in range(n_assets))

            target_returns = np.linspace(
                min_vol_portfolio["return"],
                max(results[0]) * 0.95,
                50,
            )

            for target in target_returns:
                cons = [constraints, {"type": "eq", "fun": lambda x, t=target: np.sum(mean_returns * x) * 252 - t}]
                init_guess = np.array([1.0 / n_assets] * n_assets)
                result = minimize(
                    lambda w: np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))) * np.sqrt(252),
                    init_guess,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=cons,
                )
                if result.success:
                    opt_weights = result.x
                    opt_vol = np.sqrt(np.dot(opt_weights.T, np.dot(cov_matrix, opt_weights))) * np.sqrt(252)
                    frontier_points.append({
                        "return": float(round(target, 6)),
                        "volatility": float(round(opt_vol, 6)),
                    })
        except ImportError:
            # scipy Not available, uses front point from Monte Carlo simulation results
            # Sort by volatility and take the Pareto optimal of each return interval
            df_results = pd.DataFrame({
                "return": results[0],
                "volatility": results[1],
            }).sort_values("volatility")
            best_by_return = {}
            for _, row in df_results.iterrows():
                ret_key = round(row["return"], 4)
                if ret_key not in best_by_return or row["volatility"] < best_by_return[ret_key]["volatility"]:
                    best_by_return[ret_key] = {"return": row["return"], "volatility": row["volatility"]}
            frontier_points = sorted(best_by_return.values(), key=lambda x: x["return"])
            warnings.append("scipy Uninstalled, approximate results of the efficient frontier using Monte Carlo simulations.")

        # Combined statistical summary
        portfolio_stats_data = {
            "num_assets": n_assets,
            "valid_symbols": valid_symbols,
            "num_portfolios_simulated": int(num_portfolios),
            "overlapping_trading_days": len(merged),
            "risk_free_rate": rf,
        }

        payload = {
            "status": "success",
            "max_sharpe": max_sharpe_portfolio,
            "min_vol": min_vol_portfolio,
            "frontier_points": frontier_points,
            "portfolio_stats": portfolio_stats_data,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("有效前沿分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 2: Monte Carlo simulation
# ============================================================

@tool
@register_tool(
    tool_id="get_monte_carlo_simulation",
    name="蒙特卡洛模拟",
    description="Carry out Monte Carlo price path simulation for a single stock based on the geometric Brownian motion model, and return the simulation path, terminal value distribution, VaR, CVaR, expected return and confidence interval, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["portfolio_analysis", "risk_management"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["price_simulation", "monte_carlo"],
    when_to_use="It is used when it is necessary to evaluate the possible distribution range of future stock prices or to measure risk.",
    when_not_to_use="When there is insufficient data (less than 30 trading days), the simulation results have limited reference value.",
    returns="Returns JSON, including parameters, simulation_count, stats (median, p5, p95, mean, std, prob_loss), sample_paths, current_price.",
    example="get_monte_carlo_simulation(symbol='600519', days=252, simulations=1000)",
    related_tools=["get_efficient_frontier", "get_var_calculation"],
)
def get_monte_carlo_simulation(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    days: Annotated[int, "Number of simulated trading days, default 252 (about 1 year)"] = 252,
    simulations: Annotated[int, "Number of simulation paths, default 1000"] = 1000,
    mu: Annotated[Optional[float], "Annualized rate of return expectations, if not specified, estimate from historical data"] = None,
    sigma: Annotated[Optional[float], "Annualized volatility, if not passed, it is estimated from historical data."] = None,
) -> str:
    """Monte Carlo price simulation based on geometric Brownian motion. Predict future price distribution and risk indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        days: Number of trading days to simulate, default 252 (approximately 1 year)
        simulations: Number of simulation paths, default 1000 (actual will be limited to 10000)
        mu: Annualized rate of return expectation; estimated from historical data when None
        sigma: Annualized volatility; estimated from historical data when None

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            current_price: Current price (simulation starting point)
            parameters: dict, Simulation parameters——
                — mu_annual: Annualized rate of return expectations
                — sigma_annual: annualized volatility
                — mu_source: "user_provided" | "estimated"
                — sigma_source: "user_provided" | "estimated"
                — days: Simulated trading days
            simulation_count: Actual number of simulation paths
            stats: dict, final price statistics——
                — median: median
                — mean: mean
                — std: standard deviation
                — p5: 5 Quantile
                — p95: 95 Quantile
                — prob_loss: Probability of loss (the proportion of the final price lower than the current price)
                — min: minimum value
                — max: maximum value
            sample_paths: list[dict], Sample paths (up to 100), element structure——
                — simulation_id: Analog number
                — final_price: final price
                — path: list[float], daily price series
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        end_date = _today()
        start_date = _days_ago(int(days) * 2 + 50)

        quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        returns = df["return"].values
        current_price = float(df["close"].iloc[-1])

        if len(returns) < 30:
            warnings.append(f"有效收益率数据仅 {len(returns)} 天，不足30天，模拟结果参考价值有限。")

        # estimated parameters
        estimated_mu = float(np.mean(returns) * 252) if mu is None else float(mu)
        estimated_sigma = float(np.std(returns, ddof=1) * np.sqrt(252)) if sigma is None else float(sigma)

        if estimated_sigma <= 0:
            return json.dumps(
                {"status": "error", "message": "Volatility is estimated to be zero and cannot be simulated."},
                ensure_ascii=False, indent=2, default=str,
            )

        n_days = int(days)
        n_sim = min(int(simulations), 10000)  # Limit the maximum number of simulations
        dt = 1.0 / 252

        # Monte Carlo simulation
        np.random.seed(42)
        random_matrix = np.random.standard_normal((n_days, n_sim))

        # Geometric Brownian motion:S_t = S_0 * exp((mu - 0.5*sigma^2)*t + sigma * sqrt(t) * Z)
        drift = (estimated_mu - 0.5 * estimated_sigma ** 2) * dt
        diffusion = estimated_sigma * np.sqrt(dt) * random_matrix
        price_paths = np.exp(np.cumsum(drift + diffusion, axis=0))
        price_paths = current_price * price_paths

        # final price array
        final_prices = price_paths[-1, :]

        # Statistical indicators
        median_price = float(np.median(final_prices))
        p5_price = float(np.percentile(final_prices, 5))
        p95_price = float(np.percentile(final_prices, 95))
        mean_price = float(np.mean(final_prices))
        std_price = float(np.std(final_prices, ddof=1))
        prob_loss = float(np.mean(final_prices < current_price))

        # Extract sample paths (up to 100 for display)
        sample_indices = np.linspace(0, n_sim - 1, min(100, n_sim), dtype=int)
        sample_paths_list = []
        for idx in sample_indices:
            path = price_paths[:, idx]
            sample_paths_list.append({
                "simulation_id": int(idx),
                "final_price": float(round(path[-1], 3)),
                "path": [float(round(p, 3)) for p in path],
            })

        payload = {
            "status": "success",
            "symbol": str(symbol),
            "current_price": float(round(current_price, 3)),
            "parameters": {
                "mu_annual": float(round(estimated_mu, 6)),
                "sigma_annual": float(round(estimated_sigma, 6)),
                "mu_source": "user_provided" if mu is not None else "estimated",
                "sigma_source": "user_provided" if sigma is not None else "estimated",
                "days": n_days,
            },
            "simulation_count": n_sim,
            "stats": {
                "median": float(round(median_price, 3)),
                "mean": float(round(mean_price, 3)),
                "std": float(round(std_price, 3)),
                "p5": float(round(p5_price, 3)),
                "p95": float(round(p95_price, 3)),
                "prob_loss": float(round(prob_loss, 6)),
                "min": float(round(float(np.min(final_prices)), 3)),
                "max": float(round(float(np.max(final_prices)), 3)),
            },
            "sample_paths": sample_paths_list,
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("蒙特卡洛模拟失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 3: factor attribution
# ============================================================

@tool
@register_tool(
    tool_id="get_factor_attribution",
    name="因子归因分析",
    description="Perform simplified factor attribution analysis on individual stocks and calculate Alpha, Beta,R² and market factor explanation, return factor contribution, residual income and attribution conclusions, and identify income sources.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["factor_analysis", "risk_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["factor_attribution", "return_decomposition"],
    when_to_use="Use it when you need to analyze the source of returns of individual stocks and distinguish between Alpha (excess returns) and Beta (market returns).",
    when_not_to_use="Analytical results are limited when there is insufficient data (less than 30 trading days) or market portfolio data is missing.",
    returns="Returns JSON containing factor_model, alpha, beta, r_squared, explained_by_market_pct, stock_specific_pct, data_quality.",
    example="get_factor_attribution(symbol='600519', lookback_days=252)",
    related_tools=["get_beta_calculation", "get_efficient_frontier"],
)
def get_factor_attribution(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of trading days to look back, default is 252 (approximately 1 year)"] = 252,
) -> str:
    """Perform simplified factor attribution analysis on individual stocks. Based on the single-factor CAPM model to decompose Alpha, Beta,R² and market interpretability.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of trading days to look back, default is 252 (about 1 year)

    Returns:
        str: JSON String, field description——
            status: "success" | "error"
            symbol: Underlying stock code
            factor_model: factor model name,"single_factor_capm" or "single_factor_simplified"
            alpha: Annualized Alpha (0.0 in simplified model)
            beta: Beta Coefficient (1.0 under simplified model)
            r_squared: coefficient of determination R² (None in the simplified model)
            explained_by_market_pct: Market factor explanation percentage (None in simplified model)
            stock_specific_pct: The percentage of individual stock idiosyncratic returns (None in the simplified model)
            annualized_return: annualized income
            annualized_volatility: annualized volatility
            residual_std: Residual standard deviation (returned for full CAPM model only)
            skewness: Skewness
            kurtosis: kurtosis
            pe_ttm: Rolling price-to-earnings ratio (None when basic information is missing)
            pb: Price-to-book ratio (None when basic information is missing)
            data_quality: dict, Data quality——
                — return_data_points: Return sample number
                — overlapping_days: Number of trading days overlapped with benchmark (full model only)
                — has_benchmark: Are there any benchmarks available?
                — benchmark_symbol: Base code ("000300") 
            warnings: list[str], Alarm information generated during the process
            message: When status is "error" error description when
    """
    try:
        warnings: list = []
        sym = str(symbol)
        end_date = _today()
        start_date = _days_ago(int(lookback_days) * 2 + 50)

        # Get basic information
        basic_info = get_stock_basic_info(sym) or {}

        # Get daily data
        quotes = get_stock_daily_quotes(
            sym, start_date, end_date, limit=int(lookback_days) + 100
        )

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {sym} 的日线数据。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["close"]).sort_values("trade_date")
        df["return"] = df["close"].pct_change()
        df = df.dropna(subset=["return"])

        stock_returns = df["return"].values

        if len(stock_returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"{sym} The effective return data is less than 30 trading days, and factor attribution cannot be reliably performed.",
                 "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        # Constructing Market Portfolio Agents: Using Own Earnings + Other available data
        # Try to get CSI 300 (000300) as market benchmark
        market_symbol = "000300"
        market_quotes = get_stock_daily_quotes(
            market_symbol, start_date, end_date, limit=int(lookback_days) + 100
        )

        use_market_proxy = False
        if market_quotes and len(market_quotes) > 20:
            mkt_df = pd.DataFrame(market_quotes)
            mkt_df["close"] = mkt_df["close"].apply(_safe_float)
            mkt_df["trade_date"] = mkt_df["trade_date"].astype(str)
            mkt_df = mkt_df.dropna(subset=["close"]).sort_values("trade_date")
            mkt_df["return"] = mkt_df["close"].pct_change()
            mkt_df = mkt_df.dropna(subset=["return"])

            # Align dates
            merged = pd.merge(
                df[["trade_date", "return"]],
                mkt_df[["trade_date", "return"]],
                on="trade_date",
                how="inner",
                suffixes=("_stock", "_market"),
            )

            if len(merged) >= 30:
                stock_r = merged["return_stock"].values
                market_r = merged["return_market"].values
                use_market_proxy = True
        else:
            warnings.append(f"未获取到基准指数 {market_symbol} 数据。")

        if not use_market_proxy:
            # Unable to obtain market benchmark, use simplified model
            # Using the stock's own return as a market proxy,beta=1
            payload = {
                "status": "success",
                "symbol": sym,
                "factor_model": "single_factor_simplified",
                "alpha": 0.0,
                "beta": 1.0,
                "r_squared": None,
                "explained_by_market_pct": None,
                "stock_specific_pct": None,
                "annualized_return": float(round(float(np.mean(stock_returns) * 252), 6)),
                "annualized_volatility": float(round(float(np.std(stock_returns, ddof=1) * np.sqrt(252)), 6)),
                "skewness": float(round(float(pd.Series(stock_returns).skew()), 4)),
                "kurtosis": float(round(float(pd.Series(stock_returns).kurtosis()), 4)),
                "pe_ttm": _safe_float(basic_info.get("pe_ttm")),
                "pb": _safe_float(basic_info.get("pb")),
                "data_quality": {
                    "return_data_points": len(stock_returns),
                    "has_benchmark": False,
                    "benchmark_symbol": market_symbol,
                },
                "warnings": warnings + ["Without benchmark index data, a simplified model is used (beta=1.0) . "],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        # OLS Return:stock_return = alpha + beta * market_return + epsilon
        X = np.column_stack([np.ones(len(market_r)), market_r])
        y = stock_r

        try:
            coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return json.dumps(
                {"status": "error", "message": "OLS Regression calculation failed."},
                ensure_ascii=False, indent=2, default=str,
            )

        alpha_daily = coeffs[0]
        beta = coeffs[1]

        # annualized Alpha
        alpha_annualized = alpha_daily * 252

        # R²
        y_pred = X @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # market interpretability
        market_contribution = beta * market_r
        total_explained = y_pred - alpha_daily  # exclude alpha
        explained_by_market = np.var(market_contribution, ddof=1)
        total_return_var = np.var(y, ddof=1)
        if total_return_var > 0:
            explained_by_market_pct = explained_by_market / total_return_var * 100
            stock_specific_pct = (1.0 - r_squared) * 100
        else:
            explained_by_market_pct = 0.0
            stock_specific_pct = 0.0

        # statistical characteristics
        residuals = y - y_pred
        annualized_return = float(np.mean(stock_returns) * 252)
        annualized_vol = float(np.std(stock_returns, ddof=1) * np.sqrt(252))

        payload = {
            "status": "success",
            "symbol": sym,
            "factor_model": "single_factor_capm",
            "alpha": float(round(alpha_annualized, 6)),
            "beta": float(round(beta, 4)),
            "r_squared": float(round(r_squared, 4)),
            "explained_by_market_pct": float(round(explained_by_market_pct, 2)),
            "stock_specific_pct": float(round(stock_specific_pct, 2)),
            "annualized_return": float(round(annualized_return, 6)),
            "annualized_volatility": float(round(annualized_vol, 6)),
            "residual_std": float(round(float(np.std(residuals, ddof=1)), 6)),
            "skewness": float(round(float(pd.Series(stock_returns).skew()), 4)),
            "kurtosis": float(round(float(pd.Series(stock_returns).kurtosis()), 4)),
            "pe_ttm": _safe_float(basic_info.get("pe_ttm")),
            "pb": _safe_float(basic_info.get("pb")),
            "data_quality": {
                "return_data_points": len(stock_returns),
                "overlapping_days": len(market_r),
                "has_benchmark": True,
                "benchmark_symbol": market_symbol,
            },
            "warnings": warnings,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("因子归因分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_efficient_frontier", "get_monte_carlo_simulation", "get_factor_attribution"]

