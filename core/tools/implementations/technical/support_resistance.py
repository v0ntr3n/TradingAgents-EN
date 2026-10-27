"""
Support pressure level calculation tool

Based on two methods: pivot points and historical price extremes, the support and pressure levels of stocks are automatically identified.
All calculations are based on purely mathematical rules and do not require the involvement of LLM.
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


def _calc_pivot_points(high: float, low: float, close: float, current_price: float) -> dict:
    """Calculate standard pivot points and support and resistance levels."""
    pivot = (high + low + close) / 3.0

    resistances = [
        {"level": "R1", "price": round(2 * pivot - low, 2)},
        {"level": "R2", "price": round(pivot + (high - low), 2)},
        {"level": "R3", "price": round(high + 2 * (pivot - low), 2)},
    ]
    # Mid-points
    r1_price = resistances[0]["price"]
    r2_price = resistances[1]["price"]
    resistances.append({"level": "R1-R2_MP", "price": round((r1_price + r2_price) / 2, 2)})

    supports = [
        {"level": "S1", "price": round(2 * pivot - high, 2)},
        {"level": "S2", "price": round(pivot - (high - low), 2)},
        {"level": "S3", "price": round(low - 2 * (high - pivot), 2)},
    ]
    s1_price = supports[0]["price"]
    s2_price = supports[1]["price"]
    supports.append({"level": "S1-S2_MP", "price": round((s1_price + s2_price) / 2, 2)})

    for item in resistances:
        item["distance_pct"] = round((item["price"] - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
    for item in supports:
        item["distance_pct"] = round((item["price"] - current_price) / current_price * 100, 2) if current_price > 0 else 0.0

    return {
        "pivot": round(pivot, 2),
        "resistances": resistances,
        "supports": supports,
    }


def _find_local_extrema(prices: np.ndarray, n_neighbors: int = 5) -> tuple:
    """Identify local extreme points——Peaks (resistance candidates) and troughs (support candidates)."""
    highs = np.array([_safe_float(row["high"]) or 0 for row in prices])
    lows = np.array([_safe_float(row["low"]) or 0 for row in prices])

    peak_indices = []
    trough_indices = []

    for i in range(n_neighbors, len(highs) - n_neighbors):
        is_peak = True
        is_trough = True
        for j in range(1, n_neighbors + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_peak = False
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_trough = False
        if is_peak:
            peak_indices.append(i)
        if is_trough:
            trough_indices.append(i)

    peak_levels = [float(highs[i]) for i in peak_indices]
    trough_levels = [float(lows[i]) for i in trough_indices]

    return peak_levels, trough_levels


def _cluster_levels(levels: list, threshold_pct: float = 0.02) -> list:
    """Price levels around clusters (pooled within threshold), sorted by number of hits."""
    if not levels:
        return []

    sorted_levels = sorted(set(round(level, 2) for level in levels))
    clusters = []
    current_cluster = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        if (level - current_cluster[-1]) / current_cluster[-1] < threshold_pct:
            current_cluster.append(level)
        else:
            clusters.append(current_cluster)
            current_cluster = [level]
    clusters.append(current_cluster)

    result = []
    for cluster in clusters:
        avg_price = round(sum(cluster) / len(cluster), 2)
        touches = len(cluster)
        if touches >= 3:
            strength = "very_strong"
        elif touches >= 2:
            strength = "strong"
        else:
            strength = "moderate"
        result.append({"price": avg_price, "touches": touches, "strength": strength})

    result.sort(key=lambda x: x["touches"], reverse=True)
    return result


def _calc_historical_levels(quotes: list, current_price: float) -> dict:
    """Calculate support and resistance levels based on historical price extremes."""
    prices_data = []
    for q in quotes:
        high_val = _safe_float(q.get("high"))
        low_val = _safe_float(q.get("low"))
        if high_val is not None and low_val is not None:
            prices_data.append({"high": high_val, "low": low_val})

    if len(prices_data) < 30:
        return {"resistances": [], "supports": [], "warnings": ["There are less than 30 pieces of historical data, and the reference value of the support and pressure level is limited."]}

    peak_levels, trough_levels = _find_local_extrema(prices_data, n_neighbors=5)

    resistance_clusters = _cluster_levels(peak_levels)
    support_clusters = _cluster_levels([-level for level in trough_levels])  # Negative sorting
    support_clusters_positive = [
        {"price": round(abs(item["price"]), 2), "touches": item["touches"], "strength": item["strength"]}
        for item in support_clusters
    ]

    # Take top 3
    top_resistances = resistance_clusters[:3]
    top_supports = support_clusters_positive[:3]

    # Remove supports above current price and resistances below
    top_resistances = [r for r in top_resistances if r["price"] > current_price * 1.005]
    top_supports = [s for s in top_supports if s["price"] < current_price * 0.995]

    for item in top_resistances:
        item["distance_pct"] = round((item["price"] - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
    for item in top_supports:
        item["distance_pct"] = round((item["price"] - current_price) / current_price * 100, 2) if current_price > 0 else 0.0

    return {"resistances": top_resistances, "supports": top_supports, "warnings": []}


# ============================================================
#  Tool: Support pressure level calculation
# ============================================================

@tool
@register_tool(
    tool_id="get_support_resistance_levels",
    name="支撑压力位计算",
    description="Calculate key support and pressure levels for stocks based on pivot point formulas and historical price extreme value clustering.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "support_resistance", "price_levels", "pivot"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["支撑压力位", "关键价格水平"],
    when_to_use="Use it when you need to identify the key support/pressure price range of a stock to assist in entry and exit decisions.",
    when_not_to_use="When there is insufficient data (less than 20 K lines), the results have limited reference value.",
    returns="Returns JSON, including symbol, current_price, date, pivot_points (pivot points), historical_levels (historical extreme value clustering), data_quality.",
    example="get_support_resistance_levels(symbol='600519', lookback_days=120, method='all')",
    related_tools=["get_candlestick_patterns", "get_crossover_signals", "get_pivot_points", "get_fibonacci_retracement"],
)
def get_support_resistance_levels(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 120"] = 120,
    method: Annotated[str, "Calculation method: pivot (pivot point), historical (historical extreme value clustering), all (calculate both)"] = "all",
) -> str:
    """Calculate stock support and resistance levels based on pivot point formulas and clustering of historical price extremes.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 120
        method: Calculation method, value "pivot" (pivot point) | "historical" (historical extreme value clustering) | "all" (Both are calculated), default "all"

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            pivot_points: Pivot point result (None when method does not contain pivot), subfield —
                pivot: pivot point price
                resistances: List of resistance levels, per element structure —
                    level: Resistance level identifier, value "R1" | "R2" | "R3" | "R1-R2_MP"
                    price: price
                    distance_pct: Percentage from current price
                supports: List of support bits, per element structure —
                    level: Support position identifier, value "S1" | "S2" | "S3" | "S1-S2_MP"
                    price: price
                    distance_pct: Percentage from current price
            historical_levels: Historical extreme value clustering results (None when method does not contain historical), subfield —
                resistances: List of resistance levels, per element structure —
                    price: price
                    touches: touches
                    strength: Strength, value "very_strong" | "strong" | "moderate"
                    distance_pct: Percentage from current price
                supports: Support bit list, the element structure is the same as resistances
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
                warnings: Warning message list
        Field returned on exception —
            status: "error"
            message: error message
            warnings: Optional, warning message list
    """
    try:
        end_date = _today()
        start_date = _days_ago(int(lookback_days) + 60)

        quotes = get_stock_daily_quotes(
            str(symbol), start_date, end_date, limit=int(lookback_days) + 100
        )

        warnings: list = []

        if not quotes or len(quotes) < 5:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足5条。", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        if len(quotes) < 20:
            warnings.append(f"K线数据仅 {len(quotes)} 条，不足20条，支撑压力位参考价值有限。")

        # Parse quotes into DataFrame for processing
        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")

        if len(df) < 5:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 5 valid OHLC data.", "warnings": warnings},
                ensure_ascii=False, indent=2, default=str,
            )

        latest = df.iloc[-1]
        current_price = float(latest["close"])
        latest_date = str(latest["trade_date"])

        chosen_method = str(method).strip().lower()
        if chosen_method not in ("pivot", "historical", "all"):
            chosen_method = "all"
            warnings.append(f"不支持的方法 '{method}'，已回退为 all。")

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price, 2),
            "date": latest_date,
            "pivot_points": None,
            "historical_levels": None,
            "data_quality": {
                "bars_analyzed": len(df),
                "warnings": warnings,
            },
        }

        # Pivot Points
        if chosen_method in ("pivot", "all"):
            # Use the most recent complete period (latest bar)
            last_high = float(latest["high"])
            last_low = float(latest["low"])
            last_close = float(latest["close"])
            pivot_result = _calc_pivot_points(last_high, last_low, last_close, current_price)
            result["pivot_points"] = pivot_result

        # Historical levels
        if chosen_method in ("historical", "all"):
            quotes_list = df.to_dict("records")
            hist_result = _calc_historical_levels(quotes_list, current_price)
            result["historical_levels"] = {
                "resistances": hist_result["resistances"],
                "supports": hist_result["supports"],
            }
            if hist_result.get("warnings"):
                result["data_quality"]["warnings"].extend(hist_result["warnings"])

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Support pressure level calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_support_resistance_levels",
]
