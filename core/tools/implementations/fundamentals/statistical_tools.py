"""Statistical toolset.

Provides 6 financial statistics tools:
1. get_correlation_matrix - correlation matrix
2. get_cointegration_test - cointegration test
3. get_rolling_regression - rolling regression
4. get_normality_test - Normality test
5. get_stationarity_test - Stationarity test
6. get_garch_volatility - GARCH Volatility modeling
"""

import datetime
import json
import logging
import math
from typing import Annotated, Any, Dict, List, Optional, Tuple

import numpy as np
from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes, get_latest_stock_price
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# ─── Helper function ──────────────────────────────────────────────────


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        numeric = float(str(value).strip())
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _dash_date(date_str: str) -> str:
    """Normalized dates are YYYY-MM-DD."""
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


def _try_get_benchmark_quotes(benchmark_symbol: str, start_date_obj: datetime.date,
                                end_date_obj: datetime.date, lookback_days: int) -> Any:
    """Get benchmark index quotes, use AKShare to get the bottom line when DB has no data."""
    quotes = get_stock_daily_quotes(
        benchmark_symbol, start_date=start_date_obj.isoformat(), end_date=end_date_obj.isoformat(),
        period="daily", limit=lookback_days + 60,
    )
    if quotes:
        return quotes
    # AKShare Keep everything in mind
    if benchmark_symbol in ("000300", "399300", "sh000300"):
        try:
            import akshare as ak
            import pandas as pd
            df = ak.stock_zh_index_daily(symbol="sh000300")
            # date The column is of datetime.date type, and is compared directly with date objects.
            sd = start_date_obj if isinstance(start_date_obj, datetime.date) else start_date_obj
            ed = end_date_obj if isinstance(end_date_obj, datetime.date) else end_date_obj
            df = df[df["date"] >= sd]
            df = df[df["date"] <= ed]
            records = []
            for _, row in df.iterrows():
                records.append({
                    "trade_date": str(row["date"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                })
            return records
        except Exception:
            return None
    return None


def _compute_daily_returns(quotes: List[Dict[str, Any]]) -> List[float]:
    """Calculate daily returns from daily record list."""
    closes = []
    for q in quotes:
        c = _to_float(q.get("close"))
        if c is not None and c > 0:
            closes.append(c)
    if len(closes) < 2:
        return []
    returns = []
    for i in range(1, len(closes)):
        returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return returns


def _fetch_quotes(symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Get the daily data for the last N days."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days + 30)  # Get more to make sure you have enough data
    return get_stock_daily_quotes(
        symbol,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        period="daily",
        limit=lookback_days + 60,
    )


def _safe_autocorr(series: List[float], lag: int = 1) -> Optional[float]:
    """Calculate the first-order autocorrelation coefficient."""
    if len(series) < lag + 2:
        return None
    arr = np.array(series)
    if np.std(arr[:-lag]) == 0 or np.std(arr[lag:]) == 0:
        return None
    return float(np.corrcoef(arr[:-lag], arr[lag:])[0, 1])


def _adf_test_simple(series: List[float]) -> Tuple[float, float]:
    """Simple ADF inspection.

    Regression of residual series Δε_t = ρ × ε_{t-1}, Inspect ρ Whether it is significantly negative.
    Use critical values from scipy.stats if available.

    Returns:
        (adf_statistic, p_value_simplified)
    """
    if len(series) < 4:
        return float("nan"), 1.0

    arr = np.array(series)
    y = np.diff(arr)  # Δε_t
    x = arr[:-1]      # ε_{t-1}

    if np.std(x) == 0:
        return float("nan"), 1.0

    # OLS: y = β * x + ε (without intercept for ADF on residuals)
    beta = np.sum(x * y) / np.sum(x ** 2)
    residuals = y - beta * x
    se = math.sqrt(np.sum(residuals ** 2) / (len(residuals) - 1))
    se_beta = se / math.sqrt(np.sum(x ** 2))

    if se_beta == 0:
        return float("nan"), 1.0

    adf_stat = beta / se_beta

    # Use scipy to check critical values
    try:
        from scipy import stats
        # ADF critical value approx. -3.43 (1%), -2.86 (5%), -2.57 (10%) - Sample size approx. 500
        # Estimate p-value using approximate t-distribution
        p_value = 2.0 * stats.t.cdf(adf_stat, df=len(residuals) - 1)
    except ImportError:
        # Manual estimation
        if adf_stat < -3.43:
            p_value = 0.01
        elif adf_stat < -2.86:
            p_value = 0.05
        elif adf_stat < -2.57:
            p_value = 0.10
        else:
            p_value = 0.50

    return float(adf_stat), float(p_value)


# ────────────────────────────────────────────────────────────────
# Tool 1: correlation matrix
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_correlation_matrix",
    name="相关性矩阵",
    description=(
        "Calculate the return correlation coefficient matrix between multiple stocks."
        "Supports three methods: Pearson, Spearman, and Kendall."
        "Automatically find high correlations (|r|>0.7) of stock pairs."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "correlation", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["多股票相关性分析", "组合分散化评估", "风险对冲配对识别"],
    when_to_use=(
        "When it is necessary to analyze the price linkage relationship between multiple stocks and construct a low-correlation investment portfolio,"
        "Or use when looking for hedging pairs. Suitable for quantitative analysis and risk management scenarios."
    ),
    when_not_to_use=(
        "Not suitable for single stock analysis; not suitable for causal analysis (correlation does not equal causation);"
        "When there is insufficient data (< 20 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing symbols, methods, bars_used,"
        "correlation_matrix (row list format), top_correlated_pairs (|r|>0.7 of high correlation pairs)."
    ),
    example="get_correlation_matrix(symbols='600519,000001,300750')",
    related_tools=[
        "get_cointegration_test",
        "get_rolling_regression",
    ],
)
def get_correlation_matrix(
    symbols: Annotated[str, "Multiple stock codes, separated by commas, such as '600519,000001,300750'"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (approximately 1 trading day year)"] = 252,
    method: Annotated[str, "Correlation coefficient method: pearson/spearman/kendall, default pearson"] = "pearson",
) -> str:
    """Calculate the return correlation matrix for multiple stocks.

    Args:
        symbols: Multiple stock symbols, separated by commas (e.g. "600519,000001,300750") 
        lookback_days: Number of days to look back (automatically truncated to 20-1000), default 252
        method: correlation coefficient method: "pearson" / "spearman" / "kendall", Default "pearson"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbols: list[str] List of actual stock symbols used
            method: actual method used
            bars_used: Number of return samples used after alignment
            correlation_matrix: list[dict] Correlation matrix, element structure——
                — symbol: Stock code
                — values: list[float] Correlation coefficient with each stock
            top_correlated_pairs: list[dict] Correlation coefficient absolute value > 0.7 Stock pairs (up to 20), element structure——
                — stock_a: stocks A
                — stock_b: stocks B
                — correlation: Correlation coefficient
                — strength: intensity: "strong positive correlation" | "strong negative correlation"
            data_quality: dict Data quality——
                — requested_symbols: Requested stock list
                — valid_symbols: Valid number of shares
                — returns_per_stock: The rate of return for each stock
                — note: Description
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(20, min(int(lookback_days), 1000))
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        if len(sym_list) < 2:
            return json.dumps(
                {"status": "error", "message": "至少需要 2 只股票"},
                ensure_ascii=False, indent=2, default=str,
            )

        method_map = {"pearson": "pearson", "spearman": "spearman", "kendall": "kendall"}
        corr_method = method_map.get(method, "pearson")

        # Get the daily line and return of each stock
        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        returns_by_symbol: Dict[str, List[float]] = {}
        dates_by_symbol: Dict[str, List[str]] = {}
        min_bars = float("inf")

        for sym in sym_list:
            quotes = get_stock_daily_quotes(
                sym,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                period="daily",
                limit=lookback_days + 60,
            )
            if not quotes or len(quotes) < 20:
                continue
            dates = []
            closes = []
            for q in quotes:
                c = _to_float(q.get("close"))
                d = str(q.get("trade_date", ""))
                if c is not None and c > 0 and d:
                    closes.append(c)
                    dates.append(d)
            if len(closes) < 20:
                continue
            rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            returns_by_symbol[sym] = rets
            dates_by_symbol[sym] = dates[1:]  # returns align with dates[1:]
            min_bars = min(min_bars, len(rets))

        if len(returns_by_symbol) < 2:
            return json.dumps(
                {"status": "error", "message": "At least 2 stocks with sufficient market data are required"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align to same length
        aligned_symbols = list(returns_by_symbol.keys())
        aligned_returns: Dict[str, List[float]] = {}
        for sym in aligned_symbols:
            aligned_returns[sym] = returns_by_symbol[sym][-min_bars:]

        # Build matrix
        n = len(aligned_symbols)
        matrix = [[0.0] * n for _ in range(n)]
        top_pairs = []

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                elif j > i:
                    xi = np.array(aligned_returns[aligned_symbols[i]])
                    xj = np.array(aligned_returns[aligned_symbols[j]])

                    if corr_method == "pearson":
                        r = float(np.corrcoef(xi, xj)[0, 1])
                    elif corr_method == "spearman":
                        from scipy.stats import spearmanr
                        r = float(spearmanr(xi, xj)[0])
                    elif corr_method == "kendall":
                        from scipy.stats import kendalltau
                        r = float(kendalltau(xi, xj)[0])
                    else:
                        r = float(np.corrcoef(xi, xj)[0, 1])

                    matrix[i][j] = round(r, 4)
                    matrix[j][i] = round(r, 4)

                    if abs(r) > 0.7:
                        top_pairs.append({
                            "stock_a": aligned_symbols[i],
                            "stock_b": aligned_symbols[j],
                            "correlation": round(r, 4),
                            "strength": "强正相关" if r > 0 else "强负相关",
                        })

        top_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        payload = {
            "symbols": aligned_symbols,
            "method": corr_method,
            "bars_used": min_bars,
            "correlation_matrix": [
                {"symbol": aligned_symbols[i], "values": matrix[i]}
                for i in range(n)
            ],
            "top_correlated_pairs": top_pairs[:20],
            "data_quality": {
                "requested_symbols": sym_list,
                "valid_symbols": len(aligned_symbols),
                "returns_per_stock": min_bars,
                "note": "Yield is calculated based on daily closing price. Spearman/Kendall requires scipy support.",
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Correlation matrix calculation failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 2: cointegration test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_cointegration_test",
    name="协整检验",
    description=(
        "Conduct a cointegration test on two stocks."
        "Using OLS regression y = α + β × x + ε, Perform an ADF stationarity test on the residuals,"
        "Determine whether there is a cointegration relationship and calculate the mean reversion half-life."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "cointegration", "pairs_trading", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["配对交易策略研究", "均值回归分析", "统计套利机会识别"],
    when_to_use=(
        "When it is necessary to judge whether there is a long-term equilibrium relationship between two stocks and prepare for a pair trading strategy,"
        "Or used when evaluating the mean reversion properties of a spread series."
    ),
    when_not_to_use=(
        "Not suitable for single stock analysis; at least about 60 trading days of data are required to be statistically significant;"
        "Not suitable for causality testing."
    ),
    returns=(
        "Returns a JSON string containing beta, alpha, hedge_ratio, adf_statistic,"
        "p_value, is_cointegrated, half_life, spread_series (the last 10 issues)."
    ),
    example="get_cointegration_test(symbol_x='600519', symbol_y='000858')",
    related_tools=[
        "get_correlation_matrix",
        "get_stationarity_test",
    ],
)
def get_cointegration_test(
    symbol_x: Annotated[str, "The first stock code, such as 600519"],
    symbol_y: Annotated[str, "The second stock code, such as 000858"],
    lookback_days: Annotated[int, "Number of days to look back, default 504 (about 2 years)"] = 504,
) -> str:
    """Conduct a cointegration test on two stocks.

    Args:
        symbol_x: The first stock code (such as "600519") 
        symbol_y: The second stock code (e.g. "000858") 
        lookback_days: Number of days to look back (automatically truncated to 60-2000), default 504

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol_x: First stock code
            symbol_y: Second stock code
            alpha: OLS regression intercept
            beta: OLS Regression slope (hedge ratio)
            hedge_ratio: Hedge Ratio (= beta) 
            adf_statistic: ADF test statistic
            p_value: ADF Test p-value
            is_cointegrated: Whether it is cointegrated (p<0.05) 
            half_life_days: Mean reversion half-life (days, None if cannot be calculated)
            current_z_score: current spread Z-Score
            spread_series: list[dict] Price difference sequence of the last 10 periods, element structure——
                — date: Date
                — spread: spread
            bars_used: Common trading days
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(60, min(int(lookback_days), 2000))

        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        quotes_x = get_stock_daily_quotes(
            symbol_x, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )
        quotes_y = get_stock_daily_quotes(
            symbol_y, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )

        if not quotes_x or not quotes_y:
            return json.dumps(
                {"status": "error", "message": "未能获取足够行情数据"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align by trade_date
        prices_x: Dict[str, float] = {}
        prices_y: Dict[str, float] = {}
        for q in quotes_x:
            d = str(q.get("trade_date", ""))
            c = _to_float(q.get("close"))
            if c and c > 0 and d:
                prices_x[d] = c
        for q in quotes_y:
            d = str(q.get("trade_date", ""))
            c = _to_float(q.get("close"))
            if c and c > 0 and d:
                prices_y[d] = c

        common_dates = sorted(set(prices_x.keys()) & set(prices_y.keys()))
        if len(common_dates) < 30:
            return json.dumps(
                {"status": "error", "message": f"共同交易日不足（仅 {len(common_dates)} 天）"},
                ensure_ascii=False, indent=2, default=str,
            )

        px = np.array([prices_x[d] for d in common_dates], dtype=float)
        py = np.array([prices_y[d] for d in common_dates], dtype=float)

        # OLS: y = α + β × x + ε
        X = np.vstack([np.ones(len(px)), px]).T
        beta_vec = np.linalg.lstsq(X, py, rcond=None)[0]
        alpha = float(beta_vec[0])
        beta = float(beta_vec[1])
        residuals = py - (alpha + beta * px)

        hedge_ratio = beta  # Hedge ratio = β

        # ADF Test residuals
        adf_stat, p_value = _adf_test_simple(residuals.tolist())
        is_cointegrated = p_value < 0.05

        # half life
        half_life: Optional[float] = None
        rho = _safe_autocorr(residuals.tolist(), lag=1)
        if rho is not None and 0 < rho < 1:
            half_life = round(-math.log(2) / math.log(rho), 2)

        # Spread series (last 10 periods)
        spread = py - beta * px  # spread = y - β × x
        spread_series = [
            {"date": common_dates[i], "spread": round(float(spread[i]), 4)}
            for i in range(max(0, len(spread) - 10), len(spread))
        ]

        current_spread = float(spread[-1]) if len(spread) > 0 else 0
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))
        z_score = (current_spread - spread_mean) / spread_std if spread_std > 0 else 0

        payload = {
            "symbol_x": symbol_x,
            "symbol_y": symbol_y,
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "hedge_ratio": round(hedge_ratio, 4),
            "adf_statistic": round(adf_stat, 4),
            "p_value": round(p_value, 4),
            "is_cointegrated": is_cointegrated,
            "half_life_days": half_life,
            "current_z_score": round(z_score, 4),
            "spread_series": spread_series,
            "bars_used": len(common_dates),
            "interpretation": (
                "The residual series is stationary (p<0.05) , There is a cointegration relationship" if is_cointegrated
                else "The residual sequence is non-stationary and there is no cointegration relationship."
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("协整检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 3: rolling regression
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_rolling_regression",
    name="滚动回归",
    description=(
        "Perform a rolling OLS regression on the stock s return relative to the benchmark index (default CSI 300),"
        "Calculate rolling beta, alpha, and R². Can be used to analyze beta stability."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["statistics", "beta", "rolling_regression", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["Beta 稳定性分析", "因子暴露时变性研究", "风险模型验证"],
    when_to_use=(
        "When you need to analyze whether a stock s beta changes over time, evaluate rolling alpha trends,"
        "or used when checking the stability of risk exposures relative to a baseline."
    ),
    when_not_to_use=(
        "Not suitable for single-period static beta calculation; insufficient data (< window+20 trading days) cannot be calculated."
    ),
    returns=(
        "Returns a JSON string, including rolling_beta (last 20 periods), rolling_alpha,"
        "rolling_r_squared、latest_beta、beta_stability。"
    ),
    example="get_rolling_regression(symbol='600519', benchmark_symbol='000300')",
    related_tools=[
        "get_correlation_matrix",
        "get_stationarity_test",
    ],
)
def get_rolling_regression(
    symbol: Annotated[str, "Stock code, such as 600519"],
    benchmark_symbol: Annotated[str, "Benchmark index code, default 000300 (CSI 300)"] = "000300",
    lookback_days: Annotated[int, "Total number of days to look back, default 504 (about 2 years)"] = 504,
    window: Annotated[int, "Rolling window size (number of trading days), default 60"] = 60,
) -> str:
    """Perform a rolling regression of individual stocks relative to a benchmark index.

    Args:
        symbol: Stock code (e.g. "600519") 
        benchmark_symbol: Benchmark index code, default "000300" (CSI 300)
        lookback_days: Total lookback days (automatically truncated to 100-2000), default 504
        window: Rolling window size (number of trading days, automatically truncated to 20 to lookback_days/2), default 60

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            benchmark: Benchmark index code
            window_days: rolling window size
            total_bars: total yield
            rolling_windows_computed: Calculated number of rolling windows
            latest_beta: Latest Beta Value
            latest_alpha: Latest Alpha value
            latest_r_squared: Latest R² value
            beta_stability: Beta Stability (standard deviation)
            beta_stability_interpretation: Beta Interpretation of stability: "stable" | "medium volatility" | "Highly volatile"
            rolling_series: list[dict] The last 20 rolling regression results, element structure——
                — beta: Beta value
                — alpha: Alpha value
                — r_squared: R² value
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(100, min(int(lookback_days), 2000))
        window = max(20, min(int(window), lookback_days // 2))

        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days + 30)

        quotes_stock = get_stock_daily_quotes(
            symbol, start_date=start.isoformat(), end_date=end.isoformat(),
            period="daily", limit=lookback_days + 60,
        )

        # Benchmark Index: 000300 Use AKShare to save money
        quotes_bm = _try_get_benchmark_quotes(benchmark_symbol, start, end, lookback_days)

        if not quotes_stock or not quotes_bm:
            return json.dumps(
                {"status": "error", "message": "未能获取足够行情数据"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Align closing price by date
        prices_s: Dict[str, float] = {}
        prices_b: Dict[str, float] = {}
        for q in quotes_stock:
            d = str(q.get("trade_date", ""))
            c = _to_float(q.get("close"))
            if c and c > 0 and d:
                prices_s[d] = c
        for q in quotes_bm:
            d = str(q.get("trade_date", ""))
            c = _to_float(q.get("close"))
            if c and c > 0 and d:
                prices_b[d] = c

        common_dates = sorted(set(prices_s.keys()) & set(prices_b.keys()))
        if len(common_dates) < window + 10:
            return json.dumps(
                {"status": "error", "message": f"共同交易日不足（仅 {len(common_dates)} 天，需要至少 {window + 10} 天）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ps_arr = np.array([prices_s[d] for d in common_dates], dtype=float)
        pb_arr = np.array([prices_b[d] for d in common_dates], dtype=float)

        # Yield
        ret_s = (ps_arr[1:] - ps_arr[:-1]) / ps_arr[:-1]
        ret_b = (pb_arr[1:] - pb_arr[:-1]) / pb_arr[:-1]

        # rolling regression
        rolling_beta = []
        rolling_alpha = []
        rolling_r2 = []

        for i in range(window, len(ret_s)):
            y = ret_s[i - window:i]
            x = ret_b[i - window:i]

            if np.std(x) == 0:
                continue

            X = np.vstack([np.ones(window), x]).T
            beta_vec = np.linalg.lstsq(X, y, rcond=None)[0]
            a = float(beta_vec[0])
            b = float(beta_vec[1])

            y_pred = a + b * x
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

            rolling_alpha.append(round(a, 6))
            rolling_beta.append(round(b, 4))
            rolling_r2.append(round(float(r2), 4))

        if not rolling_beta:
            return json.dumps(
                {"status": "error", "message": "滚动回归计算失败"},
                ensure_ascii=False, indent=2, default=str,
            )

        latest_beta = rolling_beta[-1]
        beta_std = float(np.std(rolling_beta)) if len(rolling_beta) > 1 else 0.0

        # Last 20 rolling values
        n_latest = min(20, len(rolling_beta))
        rolling_series = [
            {
                "beta": rolling_beta[-(n_latest - i)],
                "alpha": rolling_alpha[-(n_latest - i)],
                "r_squared": rolling_r2[-(n_latest - i)],
            }
            for i in range(n_latest - 1, -1, -1)
        ]

        payload = {
            "symbol": symbol,
            "benchmark": benchmark_symbol,
            "window_days": window,
            "total_bars": len(ret_s),
            "rolling_windows_computed": len(rolling_beta),
            "latest_beta": latest_beta,
            "latest_alpha": round(rolling_alpha[-1], 6),
            "latest_r_squared": round(rolling_r2[-1], 4),
            "beta_stability": round(beta_std, 4),
            "beta_stability_interpretation": (
                "稳定" if beta_std < 0.1
                else "中等波动" if beta_std < 0.3
                else "高度波动"
            ),
            "rolling_series": rolling_series,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("滚动回归失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 4: Normality test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_normality_test",
    name="正态性检验",
    description=(
        "Perform Jarque-Bera normality test on stock daily returns."
        "Calculate the skewness and kurtosis to determine whether the return distribution obeys the normal distribution."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "normality", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["收益率分布分析", "风险管理假设检验", "金融计量研究"],
    when_to_use=(
        "When it is necessary to test whether stock returns follow a normal distribution (an assumption of many risk models),"
        "Or used when analyzing the skewness and kurtosis characteristics of return distribution."
    ),
    when_not_to_use=(
        "Not suitable for single-day return calculation; insufficient data (< 30 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string, including jb_stat, p_value, is_normal,"
        "skewness、kurtosis、interpretation。"
    ),
    example="get_normality_test(symbol='600519')",
    related_tools=[
        "get_stationarity_test",
        "get_garch_volatility",
    ],
)
def get_normality_test(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (about 1 year)"] = 252,
) -> str:
    """Perform Jarque-Bera normality test on stock daily returns.

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 30-1000), default 252

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            jb_statistic: Jarque-Bera Statistics
            p_value: p value
            is_normal: Whether it obeys the normal distribution (p>0.05) 
            skewness: Skewness
            kurtosis: kurtosis
            excess_kurtosis: Excess kurtosis (kurtosis - 3)
            samples_used: Number of samples
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(30, min(int(lookback_days), 1000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"行情数据不足（仅 {len(quotes) if quotes else 0} 条）"},
                ensure_ascii=False, indent=2, default=str,
            )

        returns = _compute_daily_returns(quotes)
        if len(returns) < 30:
            return json.dumps(
                {"status": "error", "message": f"有效收益率数据不足（仅 {len(returns)} 个）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ret_arr = np.array(returns)
        n = len(ret_arr)
        skewness = float(np.mean((ret_arr - np.mean(ret_arr)) ** 3) / (np.std(ret_arr) ** 3 + 1e-10))
        kurtosis = float(np.mean((ret_arr - np.mean(ret_arr)) ** 4) / (np.std(ret_arr) ** 4 + 1e-10))

        # Jarque-Bera Inspect
        try:
            from scipy import stats
            jb_stat, p_value = stats.jarque_bera(ret_arr)
        except ImportError:
            # Manual calculation
            jb_stat = n / 6.0 * (skewness ** 2 + (kurtosis - 3) ** 2 / 4.0)
            from scipy.stats import chi2
            p_value = 1.0 - chi2.cdf(jb_stat, df=2)

        is_normal = p_value > 0.05

        # Interpretation
        if abs(skewness) < 0.5:
            skew_desc = "接近对称"
        elif skewness > 0:
            skew_desc = "Right skew (positive skew), there are more extreme values of positive returns"
        else:
            skew_desc = "Left skewed (negatively skewed), with more extreme values of negative returns"

        if abs(kurtosis - 3) < 0.5:
            kurt_desc = "接近正态峰度"
        elif kurtosis > 3:
            kurt_desc = f"尖峰（kurtosis={kurtosis:.2f}），厚尾分布"
        else:
            kurt_desc = f"低峰（kurtosis={kurtosis:.2f}），薄尾分布"

        payload = {
            "symbol": symbol,
            "jb_statistic": round(float(jb_stat), 4),
            "p_value": round(float(p_value), 4),
            "is_normal": is_normal,
            "skewness": round(float(skewness), 4),
            "kurtosis": round(float(kurtosis), 4),
            "excess_kurtosis": round(float(kurtosis - 3), 4),
            "samples_used": n,
            "interpretation": (
                f"收益率分布{'服从' if is_normal else '不服从'}正态分布 (p={'%.4f' % p_value})。"
                f" Skewness: {skew_desc}. kurtosis: {kurt_desc}. "
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("正态性检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 5: Stationarity test
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_stationarity_test",
    name="平稳性检验",
    description=(
        "Perform ADF (Augmented Dickey-Fuller) stationarity test on stock price series."
        "Determine whether the price series has a unit root (non-stationary)."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "stationarity", "adf", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["时间序列平稳性判断", "单位根检验", "建模前提验证"],
    when_to_use=(
        "When it is necessary to determine whether the stock price series is stationary (the premise assumption of many time series models),"
        "Or used when testing the existence of a unit root."
    ),
    when_not_to_use=(
        "Not suitable for return series (returns are usually stationary);"
        "Insufficient data (< 30 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing adf_statistic, p_value, is_stationary,"
        "critical_values, test_type and interpretation."
    ),
    example="get_stationarity_test(symbol='600519')",
    related_tools=[
        "get_normality_test",
        "get_cointegration_test",
    ],
)
def get_stationarity_test(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 252 (about 1 year)"] = 252,
    price_type: Annotated[str, "Price type: close/adjusted, default close"] = "close",
) -> str:
    """Perform ADF stationarity test on stock price series.

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 30-2000), default 252
        price_type: price type: "close" (closing price) or "adjusted" (rights after restoration), default "close"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            price_type: price type
            adf_statistic: ADF test statistic
            p_value: p value
            is_stationary: Is it stable (p<0.05) 
            critical_values: dict critical value——
                — "1%": 1% critical value
                — "5%": 5% critical value
                — "10%": 10% critical value
            test_type: Inspection type description
            samples_used: Number of samples
            interpretation: interpret text
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(30, min(int(lookback_days), 2000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": "行情数据不足"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Select price field based on price_type
        if price_type == "adjusted":
            fields = ["adj_close", "adj_close", "close"]
        else:
            fields = ["close"]

        prices = []
        for q in quotes:
            c = None
            for f in fields:
                c = _to_float(q.get(f))
                if c is not None and c > 0:
                    break
            if c is not None and c > 0:
                prices.append(c)

        if len(prices) < 30:
            return json.dumps(
                {"status": "error", "message": f"有效价格数据不足（仅 {len(prices)} 条）"},
                ensure_ascii=False, indent=2, default=str,
            )

        # ADF Inspect
        adf_stat, p_value = _adf_test_simple(prices)
        test_type = "ADF (Augmented Dickey-Fuller, simplified)"

        is_stationary = p_value < 0.05

        # critical value
        critical_values = {
            "1%": -3.43,
            "5%": -2.86,
            "10%": -2.57,
        }

        payload = {
            "symbol": symbol,
            "price_type": price_type,
            "adf_statistic": round(adf_stat, 4),
            "p_value": round(p_value, 4),
            "is_stationary": is_stationary,
            "critical_values": critical_values,
            "test_type": test_type,
            "samples_used": len(prices),
            "interpretation": (
                f"价格序列{'平稳（拒绝单位根假设）' if is_stationary else '非平稳（无法拒绝单位根假设）'}。"
                f" ADF Statistics = {adf_stat:.4f}, p value = {p_value:.4f}. "
                f" {'Note: Stock prices are usually non-stationary and may be stationary after differences or logarithms.' if not is_stationary else ''}"
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("平稳性检验失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


# ────────────────────────────────────────────────────────────────
# Tool 6: GARCH Volatility (EWMA simplified version)
# ────────────────────────────────────────────────────────────────


@tool
@register_tool(
    tool_id="get_garch_volatility",
    name="EWMA 条件波动率",
    description=(
        "Estimate the conditional volatility of a stock using the EWMA (exponentially weighted moving average) model."
        "Using RiskMetrics standard attenuation factors λ=0.94. "
        "Compare current volatility to long-term historical volatility."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["statistics", "volatility", "garch", "ewma", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["条件波动率估计", "风险度量（VaR 输入）", "波动率趋势分析"],
    when_to_use=(
        "When it is necessary to estimate the current conditional volatility level of a stock and compare volatility changes in different periods,"
        "Or used when providing volatility inputs to risk management models."
    ),
    when_not_to_use=(
        "Not suitable for directly predicting future volatility (EWMA is a simplified method);"
        "Insufficient data (< 60 trading days) results are unreliable."
    ),
    returns=(
        "Returns a JSON string containing current_volatility (annualized), long_term_vol,"
        "vol_ratio, volatility_series (The last 20 issues), method_note."
    ),
    example="get_garch_volatility(symbol='600519')",
    related_tools=[
        "get_normality_test",
        "get_stationarity_test",
    ],
)
def get_garch_volatility(
    symbol: Annotated[str, "A stock stock code, such as 600519"],
    lookback_days: Annotated[int, "Number of days to look back, default 504 (about 2 years)"] = 504,
    p: Annotated[int, "GARCH Lag order p, default 1 (fixed to EWMA in EWMA mode)"] = 1,
    q: Annotated[int, "ARCH Lag order q, default 1 (fixed to EWMA in EWMA mode)"] = 1,
) -> str:
    """Conditional volatility is estimated using EWMA (RiskMetrics standard).

    Args:
        symbol: A stock code (such as "600519") 
        lookback_days: Number of days to look back (automatically truncated to 60-2000), default 504
        p: GARCH Lag order p (current implementation is fixed to EWMA, parameters are retained), default 1
        q: ARCH Lag order q (current implementation is fixed to EWMA, parameters are retained), default 1

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Stock code
            model: Model ID (fixed to "EWMA (RiskMetrics, λ=0.94)") 
            current_volatility: Current Conditions Volatility (Annualized)
            long_term_historical_volatility: Long-term historical volatility (annualized)
            volatility_ratio: Current/Long-Term Volatility Ratio
            volatility_regime: volatility status: "High volatility (currently > long term × 1.2) " | "Low volatility (currently < long term × 0.8) " | "normal fluctuations"
            volatility_series: list[dict] Volatility series of the last 20 periods, element structure——
                — date: Date
                — daily_volatility: daily volatility
                — annualized_volatility: annualized volatility
            method_note: Method description
            bars_used: Number of return samples used
            message: Error message (only status="error" exist)
    """
    try:
        lookback_days = max(60, min(int(lookback_days), 2000))

        quotes = _fetch_quotes(symbol, lookback_days)
        if not quotes or len(quotes) < 60:
            return json.dumps(
                {"status": "error", "message": "行情数据不足"},
                ensure_ascii=False, indent=2, default=str,
            )

        returns = _compute_daily_returns(quotes)
        if len(returns) < 60:
            return json.dumps(
                {"status": "error", "message": f"有效收益率数据不足（仅 {len(returns)} 个）"},
                ensure_ascii=False, indent=2, default=str,
            )

        ret_arr = np.array(returns)

        # EWMA: σ²_t = λ × σ²_{t-1} + (1-λ) × r²_{t-1}
        lam = 0.94  # RiskMetrics Standard
        n = len(ret_arr)
        sigma2 = np.zeros(n)

        # Initialization: Use variance of first 10 returns
        sigma2[0] = np.var(ret_arr[:10]) if n >= 10 else np.var(ret_arr)

        for t in range(1, n):
            sigma2[t] = lam * sigma2[t - 1] + (1 - lam) * ret_arr[t - 1] ** 2

        sigma = np.sqrt(sigma2)

        # Annualized (assuming 252 trading days)
        annual_factor = math.sqrt(252)
        current_vol = float(sigma[-1] * annual_factor)
        long_term_vol = float(np.std(ret_arr) * annual_factor)

        # Volatility series (last 20 periods)
        vol_series = [
            {
                "date": str(quotes[min(i + 1, len(quotes) - 1)].get("trade_date", "")),
                "daily_volatility": round(float(sigma[i]), 6),
                "annualized_volatility": round(float(sigma[i] * annual_factor), 4),
            }
            for i in range(max(0, n - 20), n)
        ]

        vol_ratio = current_vol / long_term_vol if long_term_vol > 0 else 1.0

        payload = {
            "symbol": symbol,
            "model": "EWMA (RiskMetrics, λ=0.94)",
            "current_volatility": round(current_vol, 4),
            "long_term_historical_volatility": round(long_term_vol, 4),
            "volatility_ratio": round(vol_ratio, 4),
            "volatility_regime": (
                "High volatility (currently > long term × 1.2) " if vol_ratio > 1.2
                else "Low volatility (currently < long term × 0.8) " if vol_ratio < 0.8
                else "正常波动"
            ),
            "volatility_series": vol_series,
            "method_note": (
                "Using the RiskMetrics EWMA model (λ=0.94) Estimate conditional volatility."
                "annualization factor = sqrt(252). "
                "complete GARCH(p,q) A nonlinear optimization solution is required, and EWMA is used here as a simplified alternative."
            ),
            "bars_used": n,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("GARCH Volatility modeling failed: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = [
    "get_correlation_matrix",
    "get_cointegration_test",
    "get_rolling_regression",
    "get_normality_test",
    "get_stationarity_test",
    "get_garch_volatility",
]