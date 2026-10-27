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
        end_date = _today()
        start_date = _days_ago(int(lookback_days) * 2 + 50)

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
        stock_df["close"] = stock_df["close"].apply(_safe_float)
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
            bench_df["close"] = bench_df["close"].apply(_safe_float)
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
        end_date = _today()
        start_date = _days_ago(int(lookback_days) * 2 + 50)

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
        df["close"] = df["close"].apply(_safe_float)
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
        end_date = _today()
        start_date = _days_ago(int(lookback_days) * 2 + 50)

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
        df["close"] = df["close"].apply(_safe_float)
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
            end_date = _today()
            start_date = _days_ago(int(lookback_days) * 2 + 50)
            quotes = get_stock_daily_quotes(str(symbol), start_date, end_date, limit=int(lookback_days) + 100)
            if not quotes:
                return json.dumps({"status": "error", "message": f"未获取到 {symbol} 的日线数据。"}, ensure_ascii=False, indent=2, default=str)

            df = pd.DataFrame(quotes)
            df["close"] = df["close"].apply(_safe_float)
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
