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


def _load_returns(symbol: str, lookback_days: int) -> Optional[np.ndarray]:
    """Get the daily return series of a single stock."""
    end_date = _today()
    start_date = _days_ago(int(lookback_days) * 2 + 50)
    quotes = get_stock_daily_quotes(
        str(symbol), start_date, end_date, limit=int(lookback_days) + 100
    )
    if not quotes:
        return None
    import pandas as pd
    df = pd.DataFrame(quotes)
    df["close"] = df["close"].apply(_safe_float)
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.dropna(subset=["close"]).sort_values("trade_date")
    df["return"] = df["close"].pct_change()
    df = df.dropna(subset=["return"])
    return df["return"].values


def _load_benchmark_returns(lookback_days: int = 252) -> Optional[np.ndarray]:
    """Obtain the benchmark index (CSI 300) return rate from the local DB, and use AKShare to cover it up if it fails."""
    import pandas as pd
    end = _today()
    start = _days_ago(lookback_days * 2 + 50)
    # Try first 000300
    quotes = get_stock_daily_quotes("000300", start, end, limit=lookback_days + 100)
    if quotes:
        df = pd.DataFrame(quotes)
        df["close"] = df["close"].apply(_safe_float)
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
            price = _safe_float(basic_info.get("close")) or _safe_float(basic_info.get("price")) or _safe_float(basic_info.get("latest_price"))
            if price is None:
                # Fallback: Get the latest closing price from the daily line
                end_date = _today()
                start_date = _days_ago(10)
                quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=5)
                if quotes:
                    price = _safe_float(quotes[-1].get("close"))
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
            price = _safe_float(basic_info.get("close")) or _safe_float(basic_info.get("price")) or _safe_float(basic_info.get("latest_price"))
            if price is None:
                end_date = _today()
                start_date = _days_ago(10)
                quotes = get_stock_daily_quotes(sym, start_date, end_date, limit=5)
                if quotes:
                    price = _safe_float(quotes[-1].get("close"))
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
        end_date = _today()
        start_date = _days_ago(ldays * 2 + 50)

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
                df["close"] = df["close"].apply(_safe_float)
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
                df["close"] = df["close"].apply(_safe_float)
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
        end_date = _today()
        start_date = _days_ago(ldays * 2 + 50)

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
                df["close"] = df["close"].apply(_safe_float)
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