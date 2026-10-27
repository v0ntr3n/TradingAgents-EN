"""
Fibonacci Retracement/Extension Tool

Automatically calculates Fibonacci retracement and extension levels based on recent highs and lows of price movements,
and evaluate the reach and support/resistance role of each price level in the current market.

All calculations are based on purely mathematical rules and do not require the involvement of LLM.
"""

import datetime
import json
import logging
from typing import Annotated, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

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


def _detect_trend(close_series: pd.Series) -> str:
    """Determine the trend direction based on the closing price changes of the most recent N/2 K lines."""
    n = len(close_series)
    half = max(1, n // 2)
    if close_series.iloc[-1] > close_series.iloc[-half]:
        return "up"
    else:
        return "down"


def _check_touched(
    level_price: float, high: pd.Series, low: pd.Series, bars: int = 5, tolerance: float = 0.005
) -> bool:
    """
    Checks whether the price in the most recent bars has touched a certain level.

    Args:
        level_price: price level
        high: highest price sequence
        low: lowest price sequence
        bars: Number of recent K-lines checked
        tolerance: Tolerance (ratio), default 0.5%

    Returns:
        bool: Whether touched
    """
    recent_high = high.iloc[-bars:]
    recent_low = low.iloc[-bars:]
    upper_bound = level_price * (1 + tolerance)
    lower_bound = level_price * (1 - tolerance)
    return bool((recent_high >= lower_bound).any() and (recent_low <= upper_bound).any())


def _detect_action(
    level_price: float, close: pd.Series, high: pd.Series, low: pd.Series, lookback: int = 10
) -> str:
    """
    Determine the effect of a certain price level on the latest lookback candlestick.

    If the price rebounds from this level (reverses after contact), it is considered support or resistance.
    If the price moves directly through this level, it is considered a breakout.

    Returns:
        "support", "resistance", "breakout", or ""
    """
    if lookback < 3:
        return ""

    recent_close = close.iloc[-lookback:]
    recent_high = high.iloc[-lookback:]
    recent_low = low.iloc[-lookback:]

    for i in range(2, lookback):
        # Check if it touches
        prev_high = recent_high.iloc[i - 1]
        prev_low = recent_low.iloc[i - 1]
        curr_close = recent_close.iloc[i]
        prev_close = recent_close.iloc[i - 1]

        upper = level_price * 1.005
        lower = level_price * 0.995

        touched_prev = prev_low <= upper and prev_high >= lower
        if not touched_prev:
            continue

        # Reverse judgment after contact
        if curr_close > prev_close * 1.01 and prev_close < level_price:
            return "support"
        elif curr_close < prev_close * 0.99 and prev_close > level_price:
            return "resistance"
        elif curr_close > prev_close * 1.02 and prev_close > level_price:
            return "breakout_above"
        elif curr_close < prev_close * 0.98 and prev_close < level_price:
            return "breakout_below"

    return ""


# ============================================================
#  Tool: Fibonacci retracements/extensions
# ============================================================

FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIB_EXTENSIONS = [1.272, 1.382, 1.618, 2.0, 2.618]


@tool
@register_tool(
    tool_id="get_fibonacci_retracement",
    name="斐波那契回调",
    description="Automatically calculate Fibonacci retracement and extension levels based on the highs and lows of recent price movements, assessing the support/resistance role of each price level.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "fibonacci"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["fibonacci_retracement", "fibonacci_extension", "price_targets"],
    when_to_use="Use when identifying potential price retracement support/resistance levels and trend extension targets. Suitable for market trends with clear trends.",
    when_not_to_use="When the market is volatile or there is no obvious trend, the reference value of Fibonacci levels is limited; it is unreliable when there is insufficient data (less than 30 K lines).",
    returns="Returns JSON, including symbol, current_price, trend, swing (high/low/range), retracement_levels (callback bit list), extension_levels (extension bit list), closest_level (most recent level), data_quality.",
    example="get_fibonacci_retracement(symbol='600519', lookback_days=120, trend_direction='auto', extension_levels=True)",
    related_tools=["get_support_resistance_levels", "get_chart_patterns", "get_fibonacci_extension"],
)
def get_fibonacci_retracement(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used to calculate the fluctuation range, the default 120"] = 120,
    trend_direction: Annotated[str, "Trend direction: up (uptrend callback), down (downtrend callback), auto (automatic identification)"] = "auto",
    extension_levels: Annotated[bool, "Whether to calculate extension bits (1.272, 1.382, 1.618, 2.0, 2.618)"] = False,
) -> str:
    """Calculate Fibonacci retracement and extension levels for a stock and evaluate the support/resistance role of each price level.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used to calculate the fluctuation range, the default 120
        trend_direction: Trend direction, value "up" (uptrend pullback) | "down" (downtrend pullback) | "auto" (automatic recognition), default "auto"
        extension_levels: Whether to calculate extension bits (1.272, 1.382, 1.618, 2.0, 2.618), default False

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            trend: The actual trend direction used, value "up" | "down"
            swing: Fluctuation interval, subfield —
                high: Highest price in range
                low: Lowest price in the range
                range: interval amplitude
            retracement_levels: callback bit list, per element structure —
                level: Fibonacci ratios (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
                price: Corresponding price
                distance_pct: Percentage from current price
                touched: whether touched
                action: optional, price action, value "bounce_above" | "breakout_above" | "breakout_below" (Only exists when touched)
            closest_level: The most recent level (same structure as retracement_levels element, with additional role field) —
                role: Price role, value "resistance" | "support" | "current"
            extension_levels: Optional, extension bit list (only extension_levels=True exist), element structure —
                level: Expansion ratio (1.272, 1.382, 1.618, 2.0, 2.618)
                price: Corresponding price
                distance_pct: Percentage from current price
                touched: whether touched
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 50)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 100)

        if not quotes or len(quotes) < 20:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足20条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 20:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 20 valid OHLC data."},
                ensure_ascii=False, indent=2, default=str,
            )

        latest = df.iloc[-1]
        current_price = float(latest["close"])
        latest_date = str(latest["trade_date"])

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Determine trend direction
        trend = str(trend_direction).strip().lower()
        if trend == "auto":
            trend = _detect_trend(close)
        elif trend not in ("up", "down"):
            trend = _detect_trend(close)

        # Calculate fluctuation range
        swing_high = float(high.max())
        swing_low = float(low.min())
        swing_range = swing_high - swing_low

        if swing_range <= 0:
            return json.dumps(
                {"status": "error", "message": f"{symbol} Abnormal price range (highest=lowest), Fibonacci levels cannot be calculated."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Calculate callback level
        if trend == "up":
            # Uptrend Retracement: Draw from Low to High
            retracement_levels = []
            for level in FIB_LEVELS:
                level_price = swing_high - level * swing_range
                touched = _check_touched(level_price, high, low, bars=5, tolerance=0.005)
                action = _detect_action(level_price, close, high, low, lookback=10) if touched else ""
                distance_pct = (level_price - current_price) / current_price * 100
                entry = {
                    "level": level,
                    "price": round(level_price, 2),
                    "distance_pct": round(distance_pct, 2),
                    "touched": touched,
                }
                if action:
                    entry["action"] = action
                retracement_levels.append(entry)

            # Extension bit (based on extending in the same direction)
            ext_levels = []
            if extension_levels:
                for ext in FIB_EXTENSIONS:
                    ext_price = swing_low + ext * swing_range
                    touched = _check_touched(ext_price, high, low, bars=5, tolerance=0.005)
                    distance_pct = (ext_price - current_price) / current_price * 100
                    entry = {
                        "level": ext,
                        "price": round(ext_price, 2),
                        "distance_pct": round(distance_pct, 2),
                        "touched": touched,
                    }
                    ext_levels.append(entry)

        else:
            # Downtrend Retracement: Draw from High to Low
            retracement_levels = []
            for level in FIB_LEVELS:
                level_price = swing_low + level * swing_range
                touched = _check_touched(level_price, high, low, bars=5, tolerance=0.005)
                action = _detect_action(level_price, close, high, low, lookback=10) if touched else ""
                distance_pct = (level_price - current_price) / current_price * 100
                entry = {
                    "level": level,
                    "price": round(level_price, 2),
                    "distance_pct": round(distance_pct, 2),
                    "touched": touched,
                }
                if action:
                    entry["action"] = action
                retracement_levels.append(entry)

            # Extension bit (based on extending in the same direction)
            ext_levels = []
            if extension_levels:
                for ext in FIB_EXTENSIONS:
                    ext_price = swing_high - ext * swing_range
                    touched = _check_touched(ext_price, high, low, bars=5, tolerance=0.005)
                    distance_pct = (ext_price - current_price) / current_price * 100
                    entry = {
                        "level": ext,
                        "price": round(ext_price, 2),
                        "distance_pct": round(distance_pct, 2),
                        "touched": touched,
                    }
                    ext_levels.append(entry)

        # recent level
        closest_level = min(
            retracement_levels,
            key=lambda x: abs(x["distance_pct"]),
        )

        # Determine the role of the nearest level
        if closest_level["price"] > current_price:
            closest_level["role"] = "resistance"
        elif closest_level["price"] < current_price:
            closest_level["role"] = "support"
        else:
            closest_level["role"] = "current"

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price, 2),
            "date": latest_date,
            "trend": trend,
            "swing": {
                "high": round(swing_high, 2),
                "low": round(swing_low, 2),
                "range": round(swing_range, 2),
            },
            "retracement_levels": retracement_levels,
            "closest_level": closest_level,
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        if extension_levels:
            result["extension_levels"] = ext_levels

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Fibonacci retracement/extension calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_fibonacci_retracement"]
