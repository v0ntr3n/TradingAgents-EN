"""
Classic technical form recognition tool

Based on OHLC data, the following five major categories of classic technology forms are automatically identified:
- Head and shoulders top/bottom (Head and Shoulders)
- Double top/double bottom (Double Top/Bottom)
- triangular state (Triangle: Ascending/Descending/Symmetrical)
- flag/pennant (Flag/Pennant)
- channel (Channel)

All patterns are detected based on purely mathematical rules without the involvement of LLM.
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


def _find_peaks_and_troughs(
    high: pd.Series, low: pd.Series, n: int = 5
) -> tuple:
    """
    Use N-neighbor comparison method to detect local extreme points.

    Returns:
        (peak_indices, trough_indices) are the index arrays of the local highest and lowest points respectively.
    """
    # Peak value: higher than N neighbors on the left and right
    peak_mask = (high > high.shift(n)) & (high > high.shift(-n))
    # Valley value: lower than N neighbors on the left and right
    trough_mask = (low < low.shift(n)) & (low < low.shift(-n))

    peak_indices = high.index[peak_mask].to_numpy()
    trough_indices = low.index[trough_mask].to_numpy()

    return peak_indices, trough_indices


def _filter_consecutive_extrema(indices: np.ndarray, prices: pd.Series) -> list:
    """
    Filter consecutive extreme points and only retain the most extreme one within each local window.
    If the distance between two extreme points is less than 3 K lines, the one with the more extreme price will be retained.
    """
    if len(indices) < 2:
        return list(indices)

    filtered = [indices[0]]
    for i in range(1, len(indices)):
        idx = indices[i]
        prev_idx = filtered[-1]
        if abs(idx - prev_idx) < 3:
            # Reserve the more extreme prices
            if abs(prices.loc[idx]) > abs(prices.loc[prev_idx]):
                filtered[-1] = idx
        else:
            filtered.append(idx)
    return filtered


def _detect_head_shoulders(
    peaks: np.ndarray, peak_prices: np.ndarray, volumes: pd.Series
) -> list:
    """
    Detect the head and shoulders pattern.

    Conditions:
    1. Find 3 consecutive peaks: left shoulder < head > right shoulder
    2. The head is higher than the left and right shoulders > 3%
    3. Difference in height between left and right shoulders < 3%
    4. Volume decreases from left to right
    """
    results = []
    for i in range(len(peaks) - 2):
        ls_idx, h_idx, rs_idx = peaks[i], peaks[i + 1], peaks[i + 2]
        ls_price, head_price, rs_price = (
            peak_prices[i],
            peak_prices[i + 1],
            peak_prices[i + 2],
        )

        # Head higher than shoulders > 3%
        if head_price <= ls_price * 1.03 or head_price <= rs_price * 1.03:
            continue
        # Difference in height between shoulders < 3%
        shoulder_diff = abs(ls_price - rs_price) / max(ls_price, rs_price)
        if shoulder_diff >= 0.03:
            continue

        # Decreasing trading volume
        ls_vol = volumes.iloc[ls_idx]
        h_vol = volumes.iloc[h_idx]
        rs_vol = volumes.iloc[rs_idx]
        if h_vol > ls_vol or rs_vol > h_vol:
            continue

        # Neckline = Connect the valley between the left and right shoulders
        # Simple approximation: use the average of the two shoulder prices as the neckline
        neckline = (ls_price + rs_price) / 2.0
        results.append({
            "pattern": "head_and_shoulders_top",
            "type": "top",
            "left_shoulder_price": round(ls_price, 2),
            "head_price": round(head_price, 2),
            "right_shoulder_price": round(rs_price, 2),
            "neckline": round(neckline, 2),
            "break_down_target": round(neckline - (head_price - neckline), 2),
            "confidence": "high" if shoulder_diff < 0.015 else "medium",
        })
    return results


def _detect_inverse_head_shoulders(
    troughs: np.ndarray, trough_prices: np.ndarray, volumes: pd.Series
) -> list:
    """
    Detect the head and shoulders bottom pattern (inverted head and shoulders).
    """
    results = []
    for i in range(len(troughs) - 2):
        ls_idx, h_idx, rs_idx = troughs[i], troughs[i + 1], troughs[i + 2]
        ls_price, head_price, rs_price = (
            trough_prices[i],
            trough_prices[i + 1],
            trough_prices[i + 2],
        )

        # Head lower than shoulders > 3%
        if head_price >= ls_price * 0.97 or head_price >= rs_price * 0.97:
            continue
        # Difference between shoulders < 3%
        shoulder_diff = abs(ls_price - rs_price) / max(abs(ls_price), abs(rs_price))
        if shoulder_diff >= 0.03:
            continue

        # The trading volume increases at the top and then shrinks (the volume characteristics of the bottom form are opposite)
        results.append({
            "pattern": "head_and_shoulders_bottom",
            "type": "bottom",
            "left_shoulder_price": round(ls_price, 2),
            "head_price": round(head_price, 2),
            "right_shoulder_price": round(rs_price, 2),
            "neckline": round((ls_price + rs_price) / 2.0, 2),
            "break_up_target": round((ls_price + rs_price) / 2.0 + abs((ls_price + rs_price) / 2.0 - head_price), 2),
            "confidence": "high" if shoulder_diff < 0.015 else "medium",
        })
    return results


def _detect_double_top(
    peaks: np.ndarray, peak_prices: np.ndarray, low_series: pd.Series
) -> list:
    """
    Detecting a double top pattern.

    Conditions:
    1. Both peaks are at similar levels (difference < 3%) 
    2. distance between peaks > 10 Root K line
    3. There is a clear valley between the two peaks
    """
    results = []
    for i in range(len(peaks) - 1):
        p1_idx, p2_idx = peaks[i], peaks[i + 1]
        p1_price, p2_price = peak_prices[i], peak_prices[i + 1]

        # The prices of the two peaks are close (the difference < 3%) 
        diff = abs(p1_price - p2_price) / max(p1_price, p2_price)
        if diff >= 0.03:
            continue

        # distance > 10 Root K line
        bar_distance = abs(p2_idx - p1_idx)
        if bar_distance <= 10:
            continue

        # the valley between two peaks
        valley = low_series.loc[int(p1_idx):int(p2_idx)].min()

        results.append({
            "pattern": "double_top",
            "type": "top",
            "peak1_price": round(p1_price, 2),
            "peak2_price": round(p2_price, 2),
            "valley_price": round(float(valley), 2),
            "neckline": round(float(valley), 2),
            "break_down_target": round(float(valley) - (p1_price - float(valley)), 2),
            "bar_distance": int(bar_distance),
            "confidence": "high" if diff < 0.015 else "medium",
        })
    return results


def _detect_double_bottom(
    troughs: np.ndarray, trough_prices: np.ndarray, high_series: pd.Series
) -> list:
    """
    Detecting a double bottom pattern.
    """
    results = []
    for i in range(len(troughs) - 1):
        t1_idx, t2_idx = troughs[i], troughs[i + 1]
        t1_price, t2_price = trough_prices[i], trough_prices[i + 1]

        diff = abs(t1_price - t2_price) / max(abs(t1_price), abs(t2_price))
        if diff >= 0.03:
            continue

        bar_distance = abs(t2_idx - t1_idx)
        if bar_distance <= 10:
            continue

        peak = high_series.loc[int(t1_idx):int(t2_idx)].max()

        results.append({
            "pattern": "double_bottom",
            "type": "bottom",
            "trough1_price": round(t1_price, 2),
            "trough2_price": round(t2_price, 2),
            "neckline": round(float(peak), 2),
            "break_up_target": round(float(peak) + (float(peak) - t1_price), 2),
            "bar_distance": int(bar_distance),
            "confidence": "high" if diff < 0.015 else "medium",
        })
    return results


def _detect_triangles(
    peaks: np.ndarray, peak_prices: np.ndarray,
    troughs: np.ndarray, trough_prices: np.ndarray,
) -> list:
    """
    Detect triangle states.

    Take the nearest set of peak-trough sequences and check convergence using linear regression.
    """
    results = []

    if len(peaks) < 3 or len(troughs) < 3:
        return results

    # Take the last 10 peaks and valleys
    recent_peaks = peaks[-10:]
    recent_peak_prices = peak_prices[-10:]
    recent_troughs = troughs[-10:]
    recent_trough_prices = trough_prices[-10:]

    if len(recent_peaks) >= 3 and len(recent_troughs) >= 3:
        # Examining the Ascending Triangle: Higher Bottoms + horizontal peak
        trough_slope = np.polyfit(
            range(len(recent_troughs)), recent_trough_prices, 1
        )[0]
        peak_slope = np.polyfit(
            range(len(recent_peaks)), recent_peak_prices, 1
        )[0]

        # Normalized slope (relative to price level)
        avg_price = (np.mean(recent_peak_prices) + np.mean(recent_trough_prices)) / 2.0
        trough_slope_norm = trough_slope / avg_price * 100 if avg_price > 0 else 0
        peak_slope_norm = peak_slope / avg_price * 100 if avg_price > 0 else 0
        peak_slope_abs = abs(peak_slope_norm)
        trough_slope_abs = abs(trough_slope_norm)

        # Symmetrical triangle: peak falling + valley rising
        if peak_slope_norm < -0.05 and trough_slope_norm > 0.05:
            convergence = trough_slope_norm - peak_slope_norm
            if convergence > 0.2:
                apex_bar = len(recent_troughs) + (
                    (recent_trough_prices[-1] - recent_peak_prices[-1])
                    / (peak_slope - trough_slope)
                    if abs(peak_slope - trough_slope) > 1e-8 else 50
                )
                results.append({
                    "pattern": "symmetrical_triangle",
                    "type": "neutral",
                    "peak_trend_slope_pct": round(peak_slope_norm, 3),
                    "trough_trend_slope_pct": round(trough_slope_norm, 3),
                    "bars_to_apex": max(0, int(apex_bar)),
                    "confidence": "medium",
                })
        # Ascending Triangle: Valley Ascending + peak level
        elif trough_slope_norm > 0.05 and peak_slope_abs < 0.1:
            results.append({
                "pattern": "ascending_triangle",
                "type": "bullish",
                "peak_trend_slope_pct": round(peak_slope_norm, 3),
                "trough_trend_slope_pct": round(trough_slope_norm, 3),
                "confidence": "medium",
            })
        # Descending Triangle: Peak Descending + trough level
        elif peak_slope_norm < -0.05 and trough_slope_abs < 0.1:
            results.append({
                "pattern": "descending_triangle",
                "type": "bearish",
                "peak_trend_slope_pct": round(peak_slope_norm, 3),
                "trough_trend_slope_pct": round(trough_slope_norm, 3),
                "confidence": "medium",
            })

    return results


def _detect_flag_pennant(
    df: pd.DataFrame, high: pd.Series, low: pd.Series, close: pd.Series
) -> list:
    """
    Detect flag and pennant patterns.

    Flag shape: There is a sharp rise/fall (flagpole) first, and then it enters a parallel channel consolidation that is opposite to the trend.
    Pennant: There is a flagpole first, and then it enters convergence (volume decreases).
    """
    results = []
    n = len(df)
    if n < 40:
        return results

    # Take the latest 40 K lines
    recent_high = high.iloc[-40:]
    recent_low = low.iloc[-40:]
    recent_close = close.iloc[-40:]

    # Testing Flagpoles: Top 10 Moves in the Past 40
    returns_10 = recent_close.pct_change(10).dropna()
    if len(returns_10) < 5:
        return results

    max_idx = returns_10.idxmax()
    min_idx = returns_10.idxmin()

    max_ret = returns_10.loc[max_idx]
    min_ret = returns_10.loc[min_idx]

    # If the maximum increase > 15%, There may be a rising flag
    if max_ret > 0.15:
        # Trend characteristics behind the flagpole
        pole_end_pos = recent_high.index.get_loc(max_idx)
        if pole_end_pos < len(recent_high) - 10:
            consolidation_high = recent_high.iloc[pole_end_pos + 1:]
            consolidation_low = recent_low.iloc[pole_end_pos + 1:]
            if len(consolidation_high) >= 10:
                # Consolidation range: range of high points and low points < 10%
                consol_range = (consolidation_high.max() - consolidation_low.min()) / consolidation_low.min()
                if consol_range < 0.10:
                    results.append({
                        "pattern": "bull_flag",
                        "type": "bullish",
                        "pole_move_pct": round(float(max_ret) * 100, 2),
                        "consolidation_days": len(consolidation_high),
                        "consolidation_range_pct": round(float(consol_range) * 100, 2),
                        "confidence": "medium",
                    })

    # If the maximum decline > 15%, There may be a falling flag
    if abs(min_ret) > 0.15:
        pole_end_pos = recent_low.index.get_loc(min_idx)
        if pole_end_pos < len(recent_low) - 10:
            consolidation_high = recent_high.iloc[pole_end_pos + 1:]
            consolidation_low = recent_low.iloc[pole_end_pos + 1:]
            if len(consolidation_high) >= 10:
                consol_range = (consolidation_high.max() - consolidation_low.min()) / consolidation_low.min()
                if consol_range < 0.10:
                    results.append({
                        "pattern": "bear_flag",
                        "type": "bearish",
                        "pole_move_pct": round(float(min_ret) * 100, 2),
                        "consolidation_days": len(consolidation_high),
                        "consolidation_range_pct": round(float(consol_range) * 100, 2),
                        "confidence": "medium",
                    })

    return results


def _detect_channel(
    peaks: np.ndarray, peak_prices: np.ndarray,
    troughs: np.ndarray, trough_prices: np.ndarray,
    high: pd.Series, low: pd.Series,
) -> list:
    """
    Detect channel patterns (parallel support and resistance lines).
    """
    results = []

    if len(peaks) < 3 or len(troughs) < 3:
        return results

    recent_peaks = peaks[-6:]
    recent_peak_prices = peak_prices[-6:]
    recent_troughs = troughs[-6:]
    recent_trough_prices = trough_prices[-6:]

    if len(recent_peaks) >= 3 and len(recent_troughs) >= 3:
        # Use linear regression to fit the upper and lower tracks of the channel
        peak_slope, peak_intercept = np.polyfit(
            np.array([float(i) for i in range(len(recent_peaks))]),
            recent_peak_prices, 1
        )
        trough_slope, trough_intercept = np.polyfit(
            np.array([float(i) for i in range(len(recent_troughs))]),
            recent_trough_prices, 1
        )

        avg_price = (np.mean(recent_peak_prices) + np.mean(recent_trough_prices)) / 2.0
        slope_diff_pct = abs(peak_slope - trough_slope) / avg_price * 100 if avg_price > 0 else 0

        # The slopes of the upper and lower rails are close (parallel), and the channel width is reasonable
        if slope_diff_pct < 0.5:
            channel_height = (recent_peak_prices[-1] - recent_trough_prices[-1]) / recent_trough_prices[-1] * 100
            if 2 < channel_height < 30:
                direction = "up" if peak_slope > 0 else ("down" if peak_slope < 0 else "horizontal")
                results.append({
                    "pattern": "channel",
                    "type": "horizontal" if direction == "horizontal" else f"{direction}trend_channel",
                    "channel_height_pct": round(channel_height, 2),
                    "resistance_slope": round(float(peak_slope), 4),
                    "support_slope": round(float(trough_slope), 4),
                    "current_resistance": round(float(peak_intercept + peak_slope * (len(recent_peaks) - 1)), 2),
                    "current_support": round(float(trough_intercept + trough_slope * (len(recent_troughs) - 1)), 2),
                    "confidence": "medium",
                })

    return results


# ============================================================
#  Tool: Classic technology form recognition
# ============================================================

@tool
@register_tool(
    tool_id="get_chart_patterns",
    name="经典技术形态识别",
    description=(
        "Based on OHLC data, five classic technical forms are automatically identified: head and shoulders top/bottom, double top/double bottom, triangle, flag, and channel."
        "Here s Pattern/Gap/Graphic It belongs to the context of K-line price technical analysis and is not used for Agent workshop capability gap, tool gap, data missing or financial gap analysis."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "chart_patterns"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["chart_pattern_recognition", "technical_patterns"],
    when_to_use="Use it when you need to automatically identify classic technical patterns (head and shoulders, double tops, triangles, etc.) and price graphic structures in stock K-line charts.",
    when_not_to_use="The detection reliability is insufficient when there is insufficient data (less than 60 K-lines); it is not suitable for time-sharing or minute-level data; it is not used for Agent workshop capability gap, data gap, financial risk gap or cash flow/valuation analysis.",
    returns="Returns JSON, including symbol, current_price, date, patterns list (each pattern includes type, price, and confidence), and data_quality.",
    example="get_chart_patterns(symbol='600519', lookback_days=180, pattern_types='all')",
    related_tools=["get_support_resistance_levels", "get_candlestick_patterns", "get_fibonacci_retracement", "get_fibonacci_extension"],
)
def get_chart_patterns(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used for pattern recognition, default 180"] = 180,
    pattern_types: Annotated[str, "Filter by pattern type, separated by commas:head_shoulders,double_top_bottom,triangle,flag,channel,all"] = "all",
) -> str:
    """Identify the classic technical forms of stocks and automatically identify five major types of forms: head and shoulders top/bottom, double top/double bottom, triangle, flag, and channel.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used for pattern recognition, default 180
        pattern_types: Pattern type filtering, comma separated, value "head_shoulders" | "double_top_bottom" | "triangle" | "flag" | "channel" | "all", Default "all"

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            patterns: Form list, the structure of each element varies depending on the form, public fields —
                pattern: Form name, with values such as "head_and_shoulders_top" | "head_and_shoulders_bottom" | "double_top" | "double_bottom" | "symmetrical_triangle" | "ascending_triangle" | "descending_triangle" | "bull_flag" | "bear_flag" | "channel"
                type: Form subtype/direction, with values such as "top" | "bottom" | "bullish" | "bearish" | "neutral" | "horizontal" | "uptrend_channel" | "downtrend_channel"
                confidence: Confidence, value "high" | "medium"
                 (Additional fields vary depending on the form, such as left_shoulder_price, head_price, right_shoulder_price, neckline, break_down_target, break_up_target, peak1_price, peak2_price, valley_price, trough1_price, trough2_price, bar_distance, peak_trend_sl ope_pct, trough_trend_slope_pct, bars_to_apex, pole_move_pct, consolidation_days, consolidation_range_pct, channel_height_pct, resistance_slope, support_slope, current_resistance, current_support)
            note: Optional, description text when no pattern is detected
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
                peaks_detected: Number of peaks detected
                troughs_detected: Number of valleys detected
                patterns_found: number of detected forms
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

        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足30条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 30 valid OHLC data."},
                ensure_ascii=False, indent=2, default=str,
            )

        latest = df.iloc[-1]
        current_price = float(latest["close"])
        latest_date = str(latest["trade_date"])

        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)

        # Peak and valley detection
        peak_indices, trough_indices = _find_peaks_and_troughs(high, low, n=5)
        peak_prices = high.loc[peak_indices].to_numpy() if len(peak_indices) > 0 else np.array([])
        trough_prices = low.loc[trough_indices].to_numpy() if len(trough_indices) > 0 else np.array([])

        # Filter continuous extreme values
        peak_indices = np.array(_filter_consecutive_extrema(peak_indices, high), dtype=int)
        trough_indices = np.array(_filter_consecutive_extrema(trough_indices, low), dtype=int)
        peak_prices = high.iloc[peak_indices].to_numpy() if len(peak_indices) > 0 else np.array([])
        trough_prices = low.iloc[trough_indices].to_numpy() if len(trough_indices) > 0 else np.array([])

        patterns_found = []
        types_to_check = [t.strip() for t in str(pattern_types).lower().split(",")]

        # 1. Head and shoulders top/bottom
        if "all" in types_to_check or "head_shoulders" in types_to_check:
            if len(peak_indices) >= 3:
                patterns_found.extend(
                    _detect_head_shoulders(peak_indices, peak_prices, volume)
                )
            if len(trough_indices) >= 3:
                patterns_found.extend(
                    _detect_inverse_head_shoulders(trough_indices, trough_prices, volume)
                )

        # 2. Double top/double bottom
        if "all" in types_to_check or "double_top_bottom" in types_to_check:
            if len(peak_indices) >= 2:
                patterns_found.extend(
                    _detect_double_top(peak_indices, peak_prices, low)
                )
            if len(trough_indices) >= 2:
                patterns_found.extend(
                    _detect_double_bottom(trough_indices, trough_prices, high)
                )

        # 3. triangular state
        if "all" in types_to_check or "triangle" in types_to_check:
            patterns_found.extend(
                _detect_triangles(peak_indices, peak_prices, trough_indices, trough_prices)
            )

        # 4. flag/pennant
        if "all" in types_to_check or "flag" in types_to_check:
            patterns_found.extend(
                _detect_flag_pennant(df, high, low, close)
            )

        # 5. channel
        if "all" in types_to_check or "channel" in types_to_check:
            patterns_found.extend(
                _detect_channel(peak_indices, peak_prices, trough_indices, trough_prices, high, low)
            )

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price, 2),
            "date": latest_date,
            "patterns": patterns_found,
            "data_quality": {
                "bars_analyzed": len(df),
                "peaks_detected": len(peak_indices),
                "troughs_detected": len(trough_indices),
                "patterns_found": len(patterns_found),
            },
        }

        if not patterns_found:
            result["note"] = "No classic technical patterns that clearly comply with the rules were detected. There are no obvious head-and-shoulders, double top/bottom, triangle, flag, or channel structures within the current price range."

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Classic technical form recognition fails: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_chart_patterns"]
