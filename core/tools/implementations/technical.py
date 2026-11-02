from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['advanced_technical', 'candlestick_patterns', 'chart_patterns', 'crossover_signals', 'fibonacci_tools', 'indicators', 'support_resistance', 'volume_analysis']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === advanced_technical ===
"""
Advanced technical analysis tools

The following advanced technical analysis features are provided:
1. ADX trend strength (Average Directional Index)
2. MACD Deviation detection
3. RSI Deviation detection
4. Volume price divergence analysis

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

def _advanced_technical_safe_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _advanced_technical_ema(series: pd.Series, n: int) -> pd.Series:
    """指数移动平均"""
    return series.ewm(span=n, adjust=False).mean()


def _wilder_ema(series: pd.Series, n: int) -> pd.Series:
    """Wilder's Smooth EMA (α=1/n) """
    return series.ewm(alpha=1.0 / n, adjust=False).mean()


def _find_local_extrema_prices(
    series: pd.Series, order: int = 5
) -> tuple:
    """
    Detecting local extreme points in price series.

    Returns:
        (peak_indices, peak_values, trough_indices, trough_values)
    """
    peaks_mask = (series > series.shift(order)) & (series > series.shift(-order))
    troughs_mask = (series < series.shift(order)) & (series < series.shift(-order))

    peak_indices = series.index[peaks_mask].to_numpy()
    trough_indices = series.index[troughs_mask].to_numpy()

    peak_values = series.loc[peak_indices].to_numpy() if len(peak_indices) > 0 else np.array([])
    trough_values = series.loc[trough_indices].to_numpy() if len(trough_indices) > 0 else np.array([])

    return peak_indices, peak_values, trough_indices, trough_values


def _find_lowest_low(series: pd.Series, start_idx: int, end_idx: int) -> tuple:
    """Find the lowest value and corresponding index within the index range"""
    subset = series.iloc[start_idx:end_idx + 1]
    min_idx = subset.idxmin()
    return min_idx, float(subset.min())


def _find_highest_high(series: pd.Series, start_idx: int, end_idx: int) -> tuple:
    """Find the highest value and corresponding index within the index range"""
    subset = series.iloc[start_idx:end_idx + 1]
    max_idx = subset.idxmax()
    return max_idx, float(subset.max())


# ============================================================
#  Tool 1: ADX trend strength
# ============================================================

@tool
@register_tool(
    tool_id="get_adx_trend_strength",
    name="ADX 趋势强度分析",
    description="Calculate ADX (Average Trend Index) and ±DI, Evaluate the strength and direction of a stock s current trend.ADX>25=strong trend,20-25=trend development,<20=No trend.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "adx", "trend_strength"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["trend_strength_analysis", "adx_analysis"],
    when_to_use="Use it when you need to quantitatively judge the strength of the trend and distinguish between trends and volatile markets. Useful for confirming whether a trend is worth participating in.",
    when_not_to_use="When there is insufficient data (less than 30 K lines), the results are unreliable; it is not suitable for judging buying and selling points in sideways and volatile markets.",
    returns="Returns JSON containing latest_adx, plus_di, minus_di, trend_strength, trend_direction, adx_series, etc.",
    example="get_adx_trend_strength(symbol='600519', lookback_days=120, period=14)",
    related_tools=["get_macd_divergence", "get_crossover_signals"],
)
def get_adx_trend_strength(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of lookback days used to calculate ADX, default 120"] = 120,
    period: Annotated[int, "ADX Calculation period, default 14"] = 14,
) -> str:
    """Calculate ADX (Average Trend Index) and ±DI Indicator that evaluates the strength and direction of a stock s current trend.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of lookback days used to calculate ADX, default 120
        period: ADX Calculation period, default 14

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            latest_adx: Latest ADX value
            plus_di: Latest +DI value
            minus_di: Latest -DI value
            trend_strength: Trend strength, value "strong" | "moderate" | "weak"
            trend_direction: Trend direction, value "up" | "down" | "neutral"
            adx_trend: ADX change direction, value "rising" | "falling" | "unknown"
            adx_series: List of ADX values in the last 5 periods, element structure —
                date: transaction date
                adx: ADX value
            interpretation: Interpret information, subfields —
                adx_meanings: ADX Meaning text
                current_assessment: Current assessment text
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
                period: ADX Calculation cycle
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 60)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 100)

        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足30条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_advanced_technical_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 30 valid OHLC data."},
                ensure_ascii=False, indent=2, default=str,
            )

        high = df["high"]
        low = df["low"]
        close = df["close"]
        period_n = max(2, int(period))

        # 1. True Range (TR)
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)

        # 2. +DM and -DM
        prev_high = high.shift(1)
        prev_low = low.shift(1)

        up_move = high - prev_high
        down_move = prev_low - low

        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)

        plus_mask = (up_move > down_move) & (up_move > 0)
        minus_mask = (down_move > up_move) & (down_move > 0)

        plus_dm[plus_mask] = up_move[plus_mask]
        minus_dm[minus_mask] = down_move[minus_mask]

        # 3. Wilder's Smoothing
        smoothed_tr = _wilder_ema(tr, period_n)
        smoothed_plus_dm = _wilder_ema(plus_dm, period_n)
        smoothed_minus_dm = _wilder_ema(minus_dm, period_n)

        # 4. +DI and -DI
        plus_di = 100.0 * smoothed_plus_dm / smoothed_tr.replace(0, np.nan)
        minus_di = 100.0 * smoothed_minus_dm / smoothed_tr.replace(0, np.nan)

        # 5. DX
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)

        # 6. ADX = EMA of DX
        adx = _advanced_technical_ema(dx, period_n)

        # --- Get the latest value ---
        latest_idx = len(df) - 1
        latest_adx = float(adx.iloc[latest_idx]) if not pd.isna(adx.iloc[latest_idx]) else 0.0
        latest_plus_di = float(plus_di.iloc[latest_idx]) if not pd.isna(plus_di.iloc[latest_idx]) else 0.0
        latest_minus_di = float(minus_di.iloc[latest_idx]) if not pd.isna(minus_di.iloc[latest_idx]) else 0.0

        # Trend strength judgment
        if latest_adx > 25:
            trend_strength = "strong"
        elif latest_adx >= 20:
            trend_strength = "moderate"
        else:
            trend_strength = "weak"

        # Trend direction judgment
        if latest_plus_di > latest_minus_di:
            trend_direction = "up"
        elif latest_minus_di > latest_plus_di:
            trend_direction = "down"
        else:
            trend_direction = "neutral"

        # ADX Trend (the direction of recent changes)
        adx_values = adx.dropna()
        adx_trend = "unknown"
        if len(adx_values) >= 5:
            recent_adx = adx_values.iloc[-5:].values
            if recent_adx[-1] > recent_adx[0]:
                adx_trend = "rising"
            else:
                adx_trend = "falling"

        # ADX values for the last 5 periods
        recent_adx_series = []
        for i in range(max(0, latest_idx - 4), latest_idx + 1):
            val = float(adx.iloc[i]) if not pd.isna(adx.iloc[i]) else 0.0
            recent_adx_series.append({
                "date": str(df.iloc[i]["trade_date"]),
                "adx": round(val, 2),
            })

        result = {
            "symbol": str(symbol),
            "current_price": round(float(close.iloc[-1]), 2),
            "date": str(df.iloc[-1]["trade_date"]),
            "latest_adx": round(latest_adx, 2),
            "plus_di": round(latest_plus_di, 2),
            "minus_di": round(latest_minus_di, 2),
            "trend_strength": trend_strength,
            "trend_direction": trend_direction,
            "adx_trend": adx_trend,
            "adx_series": recent_adx_series,
            "interpretation": {
                "adx_meanings": (
                    "ADX>25=strong trend, 20-25=Trend developing, <20=Shock/no trend"
                ),
                "current_assessment": (
                    f"ADX={latest_adx:.1f}, The trend strength is [{trend_strength}] . "
                    f"{'ADX On the rise, the trend is strengthening.' if adx_trend == 'rising' else 'ADX Downtrend may be weakening.'}"
                    f" {'+DI > -DI, is an upward trend.' if trend_direction == 'up' else '-DI > +DI, is a downward trend.' if trend_direction == 'down' else 'The balance of long and short power.'}"
                ),
            },
            "data_quality": {
                "bars_analyzed": len(df),
                "period": period_n,
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("ADX 计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 2: MACD Deviation detection
# ============================================================

@tool
@register_tool(
    tool_id="get_macd_divergence",
    name="MACD 背离检测",
    description="Detect divergence signals between MACD and price. Alerts when price moves inconsistently with the MACD histogram.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "macd_divergence"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["MACD 背离检测", "背离分析"],
    when_to_use="Use when you need to identify trend failure and potential reversal signals. Suitable for assisting in determining the top/bottom area.",
    when_not_to_use="The detection reliability is insufficient when there is insufficient data (less than 50 K lines); there are many false signals in sideways oscillating markets.",
    returns="Returns JSON containing a list of divergences (each with type, date, strength, confirmation status, etc.) and an overall evaluation.",
    example="get_macd_divergence(symbol='600519', lookback_days=180)",
    related_tools=["get_rsi_divergence", "get_adx_trend_strength", "get_volume_price_divergence"],
)
def get_macd_divergence(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back for divergence detection, default 180"] = 180,
) -> str:
    """Detect divergence signals between MACD and price to identify trend exhaustion and potential reversal points.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back for divergence detection, default 180

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            divergences: Departure signal list, per element structure —
                type: Departure type, value "bearish" (top divergence) | "bullish" (bottom divergence)
                label: Chinese label, value "top divergence" | "bottom divergence"
                price_start_date: starting price date
                price_end_date: end price date
                price_start: starting price
                price_end: end price
                price_change_pct: price change %
                macd_start: Starting MACD bar value
                macd_end: End MACD bar value
                strength: signal strength, value "strong" | "moderate" | "weak"
                confirmation_status: Confirm status, get value "confirmed" | "pending"
            summary: Summary information, subfields —
                total_divergences: Total number of divergences
                bullish_count: Number of upward divergences
                bearish_count: Number of downside divergences
                strong_signals: Number of strong signals
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes
        from core.tools.implementations.technical import macd

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 60)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 100)

        if not quotes or len(quotes) < 50:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足50条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_advanced_technical_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 50:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 50 pieces of valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]

        # Calculate MACD
        macd_df = macd(close, fast=12, slow=26, signal=9)
        macd_hist = macd_df["macd_hist"]

        # Detect divergence
        divergences = []

        # Find local extreme points (price and MACD-Histogram)
        price_peaks, price_peak_vals, price_troughs, price_trough_vals = \
            _find_local_extrema_prices(close, order=5)

        macd_peaks, macd_peak_vals, macd_troughs, macd_trough_vals = \
            _find_local_extrema_prices(macd_hist, order=5)

        # --- Top Divergence Detection: Price Higher Highs, MACD Lower Highs ---
        if len(price_peaks) >= 2 and len(macd_peaks) >= 2:
            # Take the two most recent price peaks
            p1_idx, p1_price = price_peaks[-2], float(price_peak_vals[-2])
            p2_idx, p2_price = price_peaks[-1], float(price_peak_vals[-1])

            if p2_price > p1_price:
                # Find MACD peaks near price peaks
                macd_in_range = macd_peaks[(macd_peaks >= p1_idx) & (macd_peaks <= p2_idx)]
                if len(macd_in_range) >= 2:
                    m1_val = float(macd_hist.loc[macd_in_range[-2]])
                    m2_val = float(macd_hist.loc[macd_in_range[-1]])

                    if m2_val < m1_val:
                        # MACD column drop → top divergence
                        price_change_pct = (p2_price - p1_price) / p1_price * 100
                        hist_change_pct = (m2_val - m1_val) / max(abs(m1_val), 0.001) * 100
                        strength = "strong" if (abs(hist_change_pct) > 30) else "moderate" if (abs(hist_change_pct) > 15) else "weak"

                        # Confirmation status: Whether the callback has currently started
                        recent_close = close.iloc[-min(5, len(close)):].values
                        confirmation = "confirmed" if len(recent_close) >= 3 and recent_close[-1] < recent_close[0] else "pending"

                        divergences.append({
                            "type": "bearish",
                            "label": "顶背离",
                            "price_start_date": str(df.iloc[df.index.get_loc(p1_idx)]["trade_date"])[:10],
                            "price_end_date": str(df.iloc[df.index.get_loc(p2_idx)]["trade_date"])[:10],
                            "price_start": round(p1_price, 2),
                            "price_end": round(p2_price, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "macd_start": round(m1_val, 4),
                            "macd_end": round(m2_val, 4),
                            "strength": strength,
                            "confirmation_status": confirmation,
                        })

        # --- Bottom divergence detection: Price lower lows, MACD higher lows ---
        if len(price_troughs) >= 2 and len(macd_troughs) >= 2:
            t1_idx, t1_price = price_troughs[-2], float(price_trough_vals[-2])
            t2_idx, t2_price = price_troughs[-1], float(price_trough_vals[-1])

            if t2_price < t1_price:
                macd_in_range = macd_troughs[(macd_troughs >= t1_idx) & (macd_troughs <= t2_idx)]
                if len(macd_in_range) >= 2:
                    m1_val = float(macd_hist.loc[macd_in_range[-2]])
                    m2_val = float(macd_hist.loc[macd_in_range[-1]])

                    if m2_val > m1_val:
                        # MACD column rising → bottom divergence
                        price_change_pct = (t2_price - t1_price) / t1_price * 100
                        hist_change_pct = (m2_val - m1_val) / max(abs(m1_val), 0.001) * 100
                        strength = "strong" if (hist_change_pct > 30) else "moderate" if (hist_change_pct > 15) else "weak"

                        recent_close = close.iloc[-min(5, len(close)):].values
                        confirmation = "confirmed" if len(recent_close) >= 3 and recent_close[-1] > recent_close[0] else "pending"

                        divergences.append({
                            "type": "bullish",
                            "label": "底背离",
                            "price_start_date": str(df.iloc[df.index.get_loc(t1_idx)]["trade_date"])[:10],
                            "price_end_date": str(df.iloc[df.index.get_loc(t2_idx)]["trade_date"])[:10],
                            "price_start": round(t1_price, 2),
                            "price_end": round(t2_price, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "macd_start": round(m1_val, 4),
                            "macd_end": round(m2_val, 4),
                            "strength": strength,
                            "confirmation_status": confirmation,
                        })

        result = {
            "symbol": str(symbol),
            "current_price": round(float(close.iloc[-1]), 2),
            "date": str(df.iloc[-1]["trade_date"]),
            "divergences": divergences,
            "summary": {
                "total_divergences": len(divergences),
                "bullish_count": sum(1 for d in divergences if d["type"] == "bullish"),
                "bearish_count": sum(1 for d in divergences if d["type"] == "bearish"),
                "strong_signals": sum(1 for d in divergences if d["strength"] == "strong"),
            },
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("MACD Deviation detection failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 3: RSI Deviation detection
# ============================================================

@tool
@register_tool(
    tool_id="get_rsi_divergence",
    name="RSI 背离检测",
    description="Detect divergence signals between RSI and price. RSI signals are more reliable when there is divergence in the overbought/oversold zone.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "rsi_divergence"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["rsi_divergence_detection", "divergence_analysis"],
    when_to_use="Used when identifying potential reversal signals in overbought/oversold areas. RSI divergence combined with extreme areas has a stronger signal.",
    when_not_to_use="The detection reliability is insufficient when there is insufficient data (less than 50 K lines); there are many false signals in strong unilateral trends.",
    returns="Returns JSON containing a list of divergences (each with type, date, RSI value, strength, etc.) and an overall assessment.",
    example="get_rsi_divergence(symbol='600519', lookback_days=180, rsi_period=14)",
    related_tools=["get_macd_divergence", "get_volume_price_divergence"],
)
def get_rsi_divergence(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back for divergence detection, default 180"] = 180,
    rsi_period: Annotated[int, "RSI Calculation period, default 14"] = 14,
) -> str:
    """Detect divergence signals between RSI and price and identify potential reversal points in overbought/oversold areas.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back for divergence detection, default 180
        rsi_period: RSI Calculation period, default 14

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            latest_rsi: Latest RSI value
            rsi_zone: RSI area, value "overbought(>70)" | "oversold(<30)" | "Neutral"
            divergences: Departure signal list, per element structure —
                type: Departure type, value "bearish" (top divergence) | "bullish" (bottom divergence)
                label: Chinese label, value "RSI top divergence" | "RSI bottom divergence"
                price_start: starting price
                price_end: end price
                rsi_start: Starting RSI value
                rsi_end: end RSI value
                rsi_zone: RSI area, value "overbought zone" | "neutral zone" | "oversold zone"
                strength: signal strength, value "strong" | "moderate" | "weak"
            summary: Summary information, subfields —
                total_divergences: Total number of divergences
                bullish_count: Number of upward divergences
                bearish_count: Number of downside divergences
                strong_signals: Number of strong signals
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes
        from core.tools.implementations.technical import rsi

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 60)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 100)

        if not quotes or len(quotes) < 50:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足50条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_advanced_technical_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 50:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 50 pieces of valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]

        # Calculate RSI
        rsi_series = rsi(close, n=int(rsi_period), method="ema")

        divergences = []

        # Find local extreme points
        price_peaks, price_peak_vals, price_troughs, price_trough_vals = \
            _find_local_extrema_prices(close, order=5)

        rsi_peaks, rsi_peak_vals, rsi_troughs, rsi_trough_vals = \
            _find_local_extrema_prices(rsi_series, order=5)

        # --- RSI Top Divergence: Price higher highs, RSI lower highs ---
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            p1_idx, p1_price = price_peaks[-2], float(price_peak_vals[-2])
            p2_idx, p2_price = price_peaks[-1], float(price_peak_vals[-1])

            if p2_price > p1_price:
                rsi_in_range = rsi_peaks[(rsi_peaks >= p1_idx) & (rsi_peaks <= p2_idx)]
                if len(rsi_in_range) >= 2:
                    r1_val = float(rsi_series.loc[rsi_in_range[-2]])
                    r2_val = float(rsi_series.loc[rsi_in_range[-1]])

                    if r2_val < r1_val:
                        # RSI In extreme areas (>70) The signal is stronger when
                        in_overbought = r2_val > 70 or r1_val > 70
                        strength = "strong" if (in_overbought and (r1_val - r2_val) > 5) else "moderate" if (r1_val - r2_val) > 3 else "weak"

                        divergences.append({
                            "type": "bearish",
                            "label": "RSI顶背离",
                            "price_start": round(p1_price, 2),
                            "price_end": round(p2_price, 2),
                            "rsi_start": round(r1_val, 2),
                            "rsi_end": round(r2_val, 2),
                            "rsi_zone": "超买区" if in_overbought else "中性区",
                            "strength": strength,
                        })

        # --- RSI Bottom Divergence: Price lower lows, RSI higher lows ---
        if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
            t1_idx, t1_price = price_troughs[-2], float(price_trough_vals[-2])
            t2_idx, t2_price = price_troughs[-1], float(price_trough_vals[-1])

            if t2_price < t1_price:
                rsi_in_range = rsi_troughs[(rsi_troughs >= t1_idx) & (rsi_troughs <= t2_idx)]
                if len(rsi_in_range) >= 2:
                    r1_val = float(rsi_series.loc[rsi_in_range[-2]])
                    r2_val = float(rsi_series.loc[rsi_in_range[-1]])

                    if r2_val > r1_val:
                        in_oversold = r2_val < 30 or r1_val < 30
                        strength = "strong" if (in_oversold and (r2_val - r1_val) > 5) else "moderate" if (r2_val - r1_val) > 3 else "weak"

                        divergences.append({
                            "type": "bullish",
                            "label": "RSI底背离",
                            "price_start": round(t1_price, 2),
                            "price_end": round(t2_price, 2),
                            "rsi_start": round(r1_val, 2),
                            "rsi_end": round(r2_val, 2),
                            "rsi_zone": "超卖区" if in_oversold else "中性区",
                            "strength": strength,
                        })

        # Latest RSI value
        latest_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 0.0
        latest_close = float(close.iloc[-1])

        result = {
            "symbol": str(symbol),
            "current_price": round(latest_close, 2),
            "date": str(df.iloc[-1]["trade_date"]),
            "latest_rsi": round(latest_rsi, 2),
            "rsi_zone": "超买(>70)" if latest_rsi > 70 else "超卖(<30)" if latest_rsi < 30 else "中性",
            "divergences": divergences,
            "summary": {
                "total_divergences": len(divergences),
                "bullish_count": sum(1 for d in divergences if d["type"] == "bullish"),
                "bearish_count": sum(1 for d in divergences if d["type"] == "bearish"),
                "strong_signals": sum(1 for d in divergences if d["strength"] == "strong"),
            },
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("RSI Deviation detection failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 4: Volume price divergence analysis
# ============================================================

@tool
@register_tool(
    tool_id="get_volume_price_divergence",
    name="量价背离分析",
    description="Analyze the divergence between trading volume and price, and identify typical volume and price patterns such as stagnation on heavy volume, rising volume on shrinking volume, and falling volume on heavy volume.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "volume_price_divergence"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["量价分析", "背离分析"],
    when_to_use="Use when you need to assess the health of the volume-price relationship and identify potential reversals or continuation signals.",
    when_not_to_use="The results have limited reference value when there is insufficient data (less than 30 K lines); new stocks or stocks that are not actively traded are not applicable.",
    returns="Returns JSON, including current_status, divergence_bars_count, trend_alignment and recent volume and price scores.",
    example="get_volume_price_divergence(symbol='600519', lookback_days=120)",
    related_tools=["get_obv_analysis", "get_turnover_analysis"],
)
def get_volume_price_divergence(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used for volume and price analysis, default 120"] = 120,
) -> str:
    """Analyze the relationship between trading volume and price, detect volume and price divergence signals, and identify patterns such as sluggish growth in volume and rising volume in shrinkage.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used for volume and price analysis, default 120

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            current_status: Current volume and price status, value "bearish_divergence_detected" | "capitulation_detected" | "healthy_uptrend" | "mixed"
            divergence_bars_count: Volume price divergence K line quantity
            total_bars_analyzed: Total number of K lines analyzed
            divergence_ratio: Departure from K-line proportion
            trend_alignment: Trend consistency, value "aligned_bullish" | "aligned_bearish" | "bearish_divergence" | "potential_bottom" | "neutral" | "insufficient_data"
            recent_assessments: Recent volume and price evaluation list (last 10), each element structure —
                date: transaction date
                price_change_pct: price change %
                volume_ratio: Quantity ratio
                status: Single K-line status, value "healthy_uptrend" | "bearish_divergence" | "capitulation" | "low_interest" | "neutral"
            interpretation: Status interpretation, subfield —
                healthy_uptrend: Explanation of price increase and volume increase
                bearish_divergence: Explanation of price increase and volume decrease
                capitulation: Explanation of price drop and volume increase
                low_interest: Explanation of price drop and volume shrinkage
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
        start = (today - datetime.timedelta(days=int(lookback_days) + 30)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 60)

        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足30条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_advanced_technical_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close", "volume"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 30 valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        volume = df["volume"]

        # Calculate price changes and volume changes
        price_change = close.pct_change()
        volume_ma20 = volume.rolling(window=20, min_periods=5).mean()
        volume_ratio = volume / volume_ma20.replace(0, np.nan)

        # Volume and Price Score: Classify each K-line
        bar_assessments = []
        divergence_bars_count = 0

        for i in range(1, len(df)):
            p_chg = float(price_change.iloc[i]) if not pd.isna(price_change.iloc[i]) else 0.0
            v_ratio = float(volume_ratio.iloc[i]) if not pd.isna(volume_ratio.iloc[i]) else 1.0
            is_high_vol = v_ratio > 1.5
            is_low_vol = v_ratio < 0.5

            if p_chg > 0.01 and is_high_vol:
                status = "healthy_uptrend"
            elif p_chg > 0.01 and is_low_vol:
                status = "bearish_divergence"
                divergence_bars_count += 1
            elif p_chg < -0.01 and is_high_vol:
                status = "capitulation"
                divergence_bars_count += 1
            elif p_chg < -0.01 and is_low_vol:
                status = "low_interest"
            else:
                status = "neutral"

            bar_assessments.append({
                "date": str(df.iloc[i]["trade_date"])[:10],
                "price_change_pct": round(p_chg * 100, 2),
                "volume_ratio": round(v_ratio, 2),
                "status": status,
            })

        # Judgment of current status (last 3 K lines)
        recent_bars = bar_assessments[-min(3, len(bar_assessments)):]
        recent_statuses = [b["status"] for b in recent_bars]

        if "bearish_divergence" in recent_statuses:
            current_status = "bearish_divergence_detected"
        elif "capitulation" in recent_statuses:
            current_status = "capitulation_detected"
        elif recent_statuses.count("healthy_uptrend") >= 2:
            current_status = "healthy_uptrend"
        else:
            current_status = "mixed"

        # Trend consistency assessment
        recent_prices = close.iloc[-20:].values
        recent_volumes = volume.iloc[-20:].values
        if len(recent_prices) >= 10:
            price_trend = "up" if recent_prices[-1] > recent_prices[0] else "down"
            volume_trend = "up" if recent_volumes[-1] > recent_volumes[0] else "down"

            if price_trend == "up" and volume_trend == "up":
                trend_alignment = "aligned_bullish"
            elif price_trend == "down" and volume_trend == "down":
                trend_alignment = "aligned_bearish"
            elif price_trend == "up" and volume_trend == "down":
                trend_alignment = "bearish_divergence"
            elif price_trend == "down" and volume_trend == "up":
                trend_alignment = "potential_bottom"
            else:
                trend_alignment = "neutral"
        else:
            trend_alignment = "insufficient_data"

        result = {
            "symbol": str(symbol),
            "current_price": round(float(close.iloc[-1]), 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "current_status": current_status,
            "divergence_bars_count": divergence_bars_count,
            "total_bars_analyzed": len(bar_assessments),
            "divergence_ratio": round(divergence_bars_count / max(1, len(bar_assessments)), 4),
            "trend_alignment": trend_alignment,
            "recent_assessments": bar_assessments[-min(10, len(bar_assessments)):],
            "interpretation": {
                "healthy_uptrend": "The price increases and the volume increases, the upward trend is healthy",
                "bearish_divergence": "The price rises and the volume shrinks, and the upward momentum is exhausted (negative divergence signal)",
                "capitulation": "Price drops and volume increases, panic selling (possibly close to the bottom)",
                "low_interest": "Prices fell, volume shrank, and market attention was low",
            },
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("量价背离分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_adx_trend_strength",
    "get_macd_divergence",
    "get_rsi_divergence",
    "get_volume_price_divergence",
]

# === candlestick_patterns ===
"""
K Line shape recognition tool

provide 25+ Automatic recognition of classic K-line patterns, organized into three categories:
- Single K-line pattern (7 types)
- Double candlestick pattern (8 types)
- Three K-line patterns (10 types)

All patterns are based on purely mathematical rules and do not require LLM involvement.
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
#  Auxiliary calculation function
# ============================================================

def _body(row: pd.Series) -> float:
    """实体长度（绝对值）"""
    return abs(row["close"] - row["open"])


def _body_dir(row: pd.Series) -> int:
    """Entity direction:1=Yang line(green/bull), -1=negative line(red/bear), 0=Doji"""
    diff = row["close"] - row["open"]
    if diff > 0:
        return 1
    elif diff < 0:
        return -1
    return 0


def _upper_shadow(row: pd.Series) -> float:
    """上影线长度"""
    return row["high"] - max(row["open"], row["close"])


def _lower_shadow(row: pd.Series) -> float:
    """下影线长度"""
    return min(row["open"], row["close"]) - row["low"]


def _total_range(row: pd.Series) -> float:
    """K线全长"""
    return row["high"] - row["low"]


def _body_ratio(row: pd.Series, threshold: float = 0.1) -> bool:
    """Determine whether it is a small entity (entity/full length < threshold) """
    r = _total_range(row)
    if r == 0:
        return True
    return _body(row) / r < threshold


def _body_center(row: pd.Series) -> float:
    """实体中心位置"""
    return (row["open"] + row["close"]) / 2


def _trend(close_series: pd.Series, window: int = 5) -> str:
    """Determine short-term trends:up / down / sideways"""
    if len(close_series) < window:
        return "unknown"
    recent = close_series.iloc[-window:]
    ma = recent.mean()
    first_half = recent.iloc[: window // 2].mean() if window >= 2 else ma
    second_half = recent.iloc[window // 2 :].mean() if window >= 2 else ma
    if second_half > first_half * 1.005:
        return "up"
    elif second_half < first_half * 0.995:
        return "down"
    return "sideways"


def _gap_up(row1: pd.Series, row2: pd.Series) -> bool:
    """row2 Jump upward relative to row1"""
    return row2["low"] > row1["high"]


def _gap_down(row1: pd.Series, row2: pd.Series) -> bool:
    """row2 Gap downward relative to row1"""
    return row2["high"] < row1["low"]


def _engulfs(prev: pd.Series, curr: pd.Series) -> bool:
    """curr Whether to engulf the entity of prev"""
    prev_body_high = max(prev["open"], prev["close"])
    prev_body_low = min(prev["open"], prev["close"])
    curr_body_high = max(curr["open"], curr["close"])
    curr_body_low = min(curr["open"], curr["close"])
    return curr_body_high > prev_body_high and curr_body_low < prev_body_low


# ============================================================
#  Single K-line pattern
# ============================================================

def _pattern_doji(row: pd.Series) -> Optional[dict]:
    """Doji: The real body is extremely small, and the upper and lower shadows are long."""
    if _body_ratio(row, 0.03) and _total_range(row) > 0:
        upper = _upper_shadow(row)
        lower = _lower_shadow(row)
        if upper > 0 and lower > 0:
            return {"name": "十字星", "direction": "neutral", "confidence": 0.8}
        if upper > lower * 3 and lower == 0:
            return {"name": "墓碑十字", "direction": "bearish", "confidence": 0.75}
        if lower > upper * 3 and upper == 0:
            return {"name": "蜻蜓十字", "direction": "bullish", "confidence": 0.75}
        return {"name": "十字星", "direction": "neutral", "confidence": 0.6}
    return None


def _pattern_marubozu(row: pd.Series) -> Optional[dict]:
    """Bald head and bare feet: almost no shadow lines"""
    r = _total_range(row)
    if r == 0:
        return None
    body = _body(row)
    upper_s = _upper_shadow(row)
    lower_s = _lower_shadow(row)
    if body / r > 0.9 and upper_s / r < 0.05 and lower_s / r < 0.05:
        d = _body_dir(row)
        if d == 1:
            return {"name": "光头光脚阳线", "direction": "bullish", "confidence": 0.9}
        elif d == -1:
            return {"name": "光头光脚阴线", "direction": "bearish", "confidence": 0.9}
    return None


def _pattern_hammer(row: pd.Series, trend: str) -> Optional[dict]:
    """Hammer/hanging man: small real body at the top, long lower shadow"""
    r = _total_range(row)
    if r == 0:
        return None
    lower = _lower_shadow(row)
    upper = _upper_shadow(row)
    body = _body(row)
    # lower shadow ≥ 2 Double real body, upper shadow line ≤ 10% Entity
    if lower >= 2 * body and body > 0 and upper < body * 0.3:
        center = _body_center(row)
        # The real body is on the upper half of the K line
        if center > row["low"] + r * 0.6:
            if trend == "down":
                return {"name": "锤子线", "direction": "bullish", "confidence": 0.85}
            elif trend == "up":
                return {"name": "上吊线", "direction": "bearish", "confidence": 0.7}
            return {"name": "锤子线形态", "direction": "neutral", "confidence": 0.5}
    return None


def _pattern_inverted_hammer(row: pd.Series, trend: str) -> Optional[dict]:
    """Inverted Hammer/Shooting Star: Small real body at the bottom, long upper shadow"""
    r = _total_range(row)
    if r == 0:
        return None
    upper = _upper_shadow(row)
    lower = _lower_shadow(row)
    body = _body(row)
    # upper shadow line ≥ 2 Double real body, lower shadow ≤ 10% Entity
    if upper >= 2 * body and body > 0 and lower < body * 0.3:
        center = _body_center(row)
        # The entity is in the lower half of the K line
        if center < row["high"] - r * 0.6:
            if trend == "down":
                return {"name": "倒锤子", "direction": "bullish", "confidence": 0.75}
            elif trend == "up":
                return {"name": "射击之星", "direction": "bearish", "confidence": 0.85}
            return {"name": "倒锤子形态", "direction": "neutral", "confidence": 0.5}
    return None


def _pattern_spinning_top(row: pd.Series) -> Optional[dict]:
    """Spindle line: small real body, both upper and lower shadow lines"""
    r = _total_range(row)
    if r == 0:
        return None
    body = _body(row)
    upper = _upper_shadow(row)
    lower = _lower_shadow(row)
    if 0.05 < body / r < 0.4 and upper > body * 0.5 and lower > body * 0.5:
        return {"name": "纺锤线", "direction": "neutral", "confidence": 0.6}
    return None


def _pattern_belt_hold(row: pd.Series) -> Optional[dict]:
    """Belt catching line: bald yang line or barefoot yin line"""
    r = _total_range(row)
    if r == 0:
        return None
    body = _body(row)
    upper = _upper_shadow(row)
    lower = _lower_shadow(row)
    if body / r > 0.7:
        if upper / r < 0.05 and _body_dir(row) == 1:
            return {"name": "阳线捉腰带线", "direction": "bullish", "confidence": 0.7}
        if lower / r < 0.05 and _body_dir(row) == -1:
            return {"name": "阴线捉腰带线", "direction": "bearish", "confidence": 0.7}
    return None


# ============================================================
#  Double K-line pattern
# ============================================================

def _pattern_engulfing(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """吞没形态"""
    if _engulfs(prev, curr):
        prev_dir = _body_dir(prev)
        curr_dir = _body_dir(curr)
        if prev_dir == -1 and curr_dir == 1:
            return {"name": "阳线吞没", "direction": "bullish", "confidence": 0.85}
        elif prev_dir == 1 and curr_dir == -1:
            return {"name": "阴线吞没", "direction": "bearish", "confidence": 0.85}
    return None


def _pattern_piercing(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """刺透形态（阳线）"""
    if _body_dir(prev) == -1 and _body_dir(curr) == 1:
        prev_close = prev["close"]
        prev_open = prev["open"]
        curr_open = curr["open"]
        curr_close = curr["close"]
        prev_body_mid = (prev_open + prev_close) / 2
        # curr Opens below the prev real body and closes above the midpoint of the prev real body
        if curr_open < prev_close and curr_close > prev_body_mid and curr_close < prev_open:
            return {"name": "刺透形态", "direction": "bullish", "confidence": 0.8}
    return None


def _pattern_dark_cloud(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """乌云盖顶（阴线）"""
    if _body_dir(prev) == 1 and _body_dir(curr) == -1:
        prev_close = prev["close"]
        prev_open = prev["open"]
        curr_open = curr["open"]
        curr_close = curr["close"]
        prev_body_mid = (prev_open + prev_close) / 2
        # curr Opens above the prev entity and closes below the midpoint of the prev entity
        if curr_open > prev_close and curr_close < prev_body_mid and curr_close > prev_open:
            return {"name": "乌云盖顶", "direction": "bearish", "confidence": 0.8}
    return None


def _pattern_harami(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """Harami: the former is a large real body, and the latter is a small real body inside it."""
    if _engulfs(curr, prev):  # prev engulf curr = curr inside prev
        prev_body = _body(prev)
        curr_body = _body(curr)
        if prev_body > 0 and curr_body / prev_body < 0.5:
            prev_dir = _body_dir(prev)
            curr_dir = _body_dir(curr)
            if prev_dir == -1 and curr_dir == 1:
                return {"name": "阳线孕线", "direction": "bullish", "confidence": 0.7}
            elif prev_dir == -1 and curr_dir == -1:
                return {"name": "阳线孕线(阴)", "direction": "bullish", "confidence": 0.5}
            elif prev_dir == 1 and curr_dir == -1:
                return {"name": "阴线孕线", "direction": "bearish", "confidence": 0.7}
            elif prev_dir == 1 and curr_dir == 1:
                return {"name": "阴线孕线(阳)", "direction": "bearish", "confidence": 0.5}
    return None


def _pattern_harami_cross(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """Cross harami: The last one of the harami is the cross star"""
    if _engulfs(curr, prev) and _body_ratio(curr, 0.03):
        prev_dir = _body_dir(prev)
        if prev_dir == -1:
            return {"name": "阳线十字孕线", "direction": "bullish", "confidence": 0.8}
        elif prev_dir == 1:
            return {"name": "阴线十字孕线", "direction": "bearish", "confidence": 0.8}
    return None


def _pattern_tweezer(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """Flat top/flat bottom: the high and low points of the two K lines are almost the same"""
    r1 = _total_range(prev)
    r2 = _total_range(curr)
    avg_r = (r1 + r2) / 2
    if avg_r == 0:
        return None
    threshold = avg_r * 0.05
    prev_dir = _body_dir(prev)
    curr_dir = _body_dir(curr)

    # Flat bottom: low is similar
    if abs(prev["low"] - curr["low"]) < threshold:
        if prev_dir == -1 and curr_dir == 1:
            return {"name": "平底形态", "direction": "bullish", "confidence": 0.65}
    # Flat top: similar to high
    if abs(prev["high"] - curr["high"]) < threshold:
        if prev_dir == 1 and curr_dir == -1:
            return {"name": "平顶形态", "direction": "bearish", "confidence": 0.65}
    return None


def _pattern_kicking(prev: pd.Series, curr: pd.Series) -> Optional[dict]:
    """Counterattack line (dating line): two large opposite entities with similar opening points"""
    prev_body = _body(prev)
    curr_body = _body(curr)
    prev_r = _total_range(prev)
    curr_r = _total_range(curr)
    if prev_r == 0 or curr_r == 0:
        return None
    # Both roots are large entities
    if prev_body / prev_r < 0.6 or curr_body / curr_r < 0.6:
        return None
    prev_dir = _body_dir(prev)
    curr_dir = _body_dir(curr)
    if prev_dir == -1 and curr_dir == 1:
        if abs(prev["open"] - curr["open"]) < curr_body * 0.2:
            return {"name": "阳线反击线", "direction": "bullish", "confidence": 0.7}
    elif prev_dir == 1 and curr_dir == -1:
        if abs(prev["open"] - curr["open"]) < curr_body * 0.2:
            return {"name": "阴线反击线", "direction": "bearish", "confidence": 0.7}
    return None


# ============================================================
#  Three K-line pattern
# ============================================================

def _pattern_morning_star(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Morning Star: Yinxian → small entity(Gap low) → Yang line(Jump high and close more than halfway)"""
    if not (_body_dir(r1) == -1 and _body_dir(r3) == 1):
        return None
    r1_body_center = _body_center(r1)
    # r2 small entity + below r1
    if not (_body_ratio(r2, 0.4) and r2["high"] < r1_body_center):
        return None
    # r3 Closed above the midpoint of the r1 real body
    r1_body_mid = (r1["open"] + r1["close"]) / 2
    if r3["close"] > r1_body_mid:
        return {"name": "晨星", "direction": "bullish", "confidence": 0.85}
    return None


def _pattern_evening_star(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Evening Star: Yang Line → small entity(Jump high) → negative line(Gap low, close more than halfway)"""
    if not (_body_dir(r1) == 1 and _body_dir(r3) == -1):
        return None
    r1_body_center = _body_center(r1)
    # r2 small entity + above r1
    if not (_body_ratio(r2, 0.4) and r2["low"] > r1_body_center):
        return None
    # r3 Closed below the midpoint of the r1 real body
    r1_body_mid = (r1["open"] + r1["close"]) / 2
    if r3["close"] < r1_body_mid:
        return {"name": "黄昏之星", "direction": "bearish", "confidence": 0.85}
    return None


def _pattern_three_white_soldiers(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """three white soldiers(Red Soldier): Three consecutive positive lines of growth"""
    if not (_body_dir(r1) == 1 and _body_dir(r2) == 1 and _body_dir(r3) == 1):
        return None
    b1, b2, b3 = _body(r1), _body(r2), _body(r3)
    if b1 == 0 or b2 == 0:
        return None
    # Entity increment
    if not (b3 > b2 * 0.8 and b2 > b1 * 0.8):
        return None
    # closing price increment
    if not (r3["close"] > r2["close"] and r2["close"] > r1["close"]):
        return None
    # The upper shadow is shorter
    if _upper_shadow(r3) / b3 < 0.3:
        return {"name": "三白兵(红三兵)", "direction": "bullish", "confidence": 0.8}
    return None


def _pattern_three_black_crows(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Three crows: three continuously growing negative lines"""
    if not (_body_dir(r1) == -1 and _body_dir(r2) == -1 and _body_dir(r3) == -1):
        return None
    b1, b2, b3 = _body(r1), _body(r2), _body(r3)
    if b1 == 0 or b2 == 0:
        return None
    # Entity increment
    if not (b3 > b2 * 0.8 and b2 > b1 * 0.8):
        return None
    # Decreasing closing price
    if not (r3["close"] < r2["close"] and r2["close"] < r1["close"]):
        return None
    # The lower shadow is shorter
    if _lower_shadow(r3) / b3 < 0.3:
        return {"name": "三只乌鸦", "direction": "bearish", "confidence": 0.8}
    return None


def _pattern_three_inside_up(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Three inner rises: negative line → Yang line → Yangxian breakthrough"""
    if not (_body_dir(r1) == -1 and _engulfs(r2, r1) and _body_dir(r3) == 1):
        return None
    if r3["close"] > r1["open"]:
        return {"name": "三内升", "direction": "bullish", "confidence": 0.75}
    return None


def _pattern_three_inside_down(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Three inner declines: Yang line → vaginal pregnancy line → Yinxian fell below"""
    if not (_body_dir(r1) == 1 and _engulfs(r2, r1) and _body_dir(r3) == -1):
        return None
    if r3["close"] < r1["open"]:
        return {"name": "三内降", "direction": "bearish", "confidence": 0.75}
    return None


def _pattern_three_outside_up(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Three external rises: Yinxian → Yang swallows → Yang line confirmed"""
    if not (_body_dir(r1) == -1 and _engulfs(r1, r2) and _body_dir(r2) == 1):
        return None
    if _body_dir(r3) == 1 and r3["close"] > r2["close"]:
        return {"name": "三外升", "direction": "bullish", "confidence": 0.8}
    return None


def _pattern_three_outside_down(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Three outside drops: Yang line → Devoured by Yin → Yinxian confirmation"""
    if not (_body_dir(r1) == 1 and _engulfs(r1, r2) and _body_dir(r2) == -1):
        return None
    if _body_dir(r3) == -1 and r3["close"] < r2["close"]:
        return {"name": "三外降", "direction": "bearish", "confidence": 0.8}
    return None


def _pattern_abandoned_baby(r1: pd.Series, r2: pd.Series, r3: pd.Series) -> Optional[dict]:
    """Abandoned Baby Form: In Morning Star/Evening Star, r2 is a cross star with a gap."""
    if not _body_ratio(r2, 0.05):
        return None
    if _body_dir(r1) == -1 and _body_dir(r3) == 1:
        if _gap_down(r1, r2) and _gap_up(r2, r3):
            return {"name": "底部弃婴", "direction": "bullish", "confidence": 0.9}
    elif _body_dir(r1) == 1 and _body_dir(r3) == -1:
        if _gap_up(r1, r2) and _gap_down(r2, r3):
            return {"name": "顶部弃婴", "direction": "bearish", "confidence": 0.9}
    return None


# ============================================================
#  Four or more K-line patterns
# ============================================================

def _pattern_rising_window(df_window: pd.DataFrame) -> Optional[dict]:
    """Three rising methods: Yang line → Three small Yin lines are within the Yang line → Dayang line breakthrough"""
    if len(df_window) < 5:
        return None
    r1 = df_window.iloc[0]
    r5 = df_window.iloc[-1]
    if not (_body_dir(r1) == 1 and _body_dir(r5) == 1):
        return None
    r1_high = max(r1["open"], r1["close"])
    r1_low = min(r1["open"], r1["close"])
    # r2, r3, r4 All within the scope of the r1 entity
    for i in [1, 2, 3]:
        row = df_window.iloc[i]
        if _body_dir(row) >= 0:
            return None
        if row["high"] > r1_high or row["low"] < r1_low:
            return None
    if r5["close"] > r1_high:
        return {"name": "上升三法", "direction": "bullish", "confidence": 0.75}
    return None


def _pattern_falling_window(df_window: pd.DataFrame) -> Optional[dict]:
    """Three methods of descent: Yinxian → Three small positive lines are within the negative lines → The big Yinxian fell below"""
    if len(df_window) < 5:
        return None
    r1 = df_window.iloc[0]
    r5 = df_window.iloc[-1]
    if not (_body_dir(r1) == -1 and _body_dir(r5) == -1):
        return None
    r1_high = max(r1["open"], r1["close"])
    r1_low = min(r1["open"], r1["close"])
    for i in [1, 2, 3]:
        row = df_window.iloc[i]
        if _body_dir(row) <= 0:
            return None
        if row["high"] > r1_high or row["low"] < r1_low:
            return None
    if r5["close"] < r1_low:
        return {"name": "下降三法", "direction": "bearish", "confidence": 0.75}
    return None


# ============================================================
#  Tool registration and main function
# ============================================================

@tool
@register_tool(
    tool_id="get_candlestick_patterns",
    name="K线形态识别",
    description=(
        "Automatic identification based on OHLC data 25+ Classic K-line patterns, including cross star, hammer, engulfing,"
        "Morning Star/Evening Star, Three White Soldiers/Three Crows, etc. Returns structured JSON, including form name, direction,"
        "Confidence and date of occurrence."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["candlestick_patterns", "technical_pattern_recognition", "price_action"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["K线形态识别", "价格行为分析"],
    when_to_use=(
        "Use it when you need to identify K-line pattern signals (reversal signals/continuation signals)."
        "Suitable for short-term timing, entry/exit timing judgment, and reversal confirmation near support/pressure levels."
    ),
    when_not_to_use=(
        "Not suitable for those who need complete trend judgment (should be combined with trend analysis tools),"
        "It is not suitable for fundamental analysis and medium- and long-term valuation judgments."
        "Pattern recognition is only a probability signal and cannot replace comprehensive judgment."
    ),
    returns=(
        "Returns a JSON string, including patterns array, summary, data_info."
        "Each pattern contains date, name,direction(bullish/bearish/neutral), confidence(0-1). "
    ),
    example="get_candlestick_patterns(symbol='600519', lookback_days=60)",
    related_tools=[
        "get_technical_indicators",
        "get_technical_factor_bundle_tool",
        "get_stock_market_data_unified",
        "get_chart_patterns",
        "get_crossover_signals",
    ],
)
def get_candlestick_patterns(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 60"] = 60,
    trend_window: Annotated[int, "Trend judgment window (day), default 5"] = 5,
    min_confidence: Annotated[float, "minimum confidence threshold (0-1), Default 0.5"] = 0.5,
) -> str:
    """Identify K-line patterns and automatically identify them 25+ Classic K-line patterns (cross star, hammer, engulfing, morning star/evening star, etc.).

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 60
        trend_window: Trend judgment window (day), default 5
        min_confidence: minimum confidence threshold (0-1), Default 0.5

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            data_info: Data information, subfield —
                total_bars: K Total number of lines
                date_range: date range, subfield —
                    start: start date
                    end: end date
            patterns_found: The total number of patterns recognized
            summary: Summary statistics, subfields —
                bullish: Number of positive line patterns
                bearish: Number of negative line patterns
                neutral: Number of neutral forms
            patterns: Shape list, each element structure —
                date: transaction date
                index: K thread index
                name: Form name (e.g. "Doji", "hammer line", "Yangxian engulfed") 
                direction: direction, value "bullish" | "bearish" | "neutral"
                confidence: Confidence (0-1)
                close: Closing price of the day
        Field returned on exception —
            status: "no_data" | "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes

        data = get_stock_daily_quotes(
            symbol=symbol,
            start_date=(datetime.date.today() - datetime.timedelta(days=lookback_days + 30)).strftime("%Y%m%d"),
            end_date=datetime.date.today().strftime("%Y%m%d"),
            limit=lookback_days + 20,
        )
        if not data or len(data) < 10:
            return json.dumps(
                {"status": "no_data", "message": f"股票 {symbol} 数据不足，至少需要 10 个交易日数据"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(data)
        # Standardized column names
        col_map = {}
        for col in df.columns:
            low = col.lower().strip()
            if low in ("open", "开盘价", "开盘"):
                col_map[col] = "open"
            elif low in ("high", "最高价", "最高"):
                col_map[col] = "high"
            elif low in ("low", "最低价", "最低"):
                col_map[col] = "low"
            elif low in ("close", "收盘价", "收盘"):
                col_map[col] = "close"
            elif low in ("trade_date", "date", "日期"):
                col_map[col] = "date"
        df = df.rename(columns=col_map)

        required_cols = {"open", "high", "low", "close"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            return json.dumps(
                {"status": "error", "message": f"缺少必要列: {missing}，实际列: {list(df.columns)}"},
                ensure_ascii=False, indent=2, default=str,
            )

        # Sort by date
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        # Take the most recent lookback_days
        df = df.tail(lookback_days).copy()
        close_series = df["close"]

        patterns = []

        # Traverse each K line
        for i in range(len(df)):
            row = df.iloc[i]
            trend = _trend(close_series.iloc[: i + 1], trend_window) if i >= trend_window else "unknown"

            # Single root form
            for fn in [
                _pattern_doji,
                _pattern_marubozu,
                _pattern_spinning_top,
                _pattern_belt_hold,
            ]:
                result = fn(row)
                if result and result["confidence"] >= min_confidence:
                    _append_pattern(patterns, df, i, result)

            # Single root patterns that require trend context
            if trend != "unknown":
                for fn in [_pattern_hammer, _pattern_inverted_hammer]:
                    result = fn(row, trend)
                    if result and result["confidence"] >= min_confidence:
                        _append_pattern(patterns, df, i, result)

            # double root form
            if i >= 1:
                prev = df.iloc[i - 1]
                for fn in [
                    _pattern_engulfing,
                    _pattern_piercing,
                    _pattern_dark_cloud,
                    _pattern_harami,
                    _pattern_harami_cross,
                    _pattern_tweezer,
                    _pattern_kicking,
                ]:
                    result = fn(prev, row)
                    if result and result["confidence"] >= min_confidence:
                        _append_pattern(patterns, df, i, result)

            # three root pattern
            if i >= 2:
                r1, r2, r3 = df.iloc[i - 2], df.iloc[i - 1], row
                for fn in [
                    _pattern_morning_star,
                    _pattern_evening_star,
                    _pattern_three_white_soldiers,
                    _pattern_three_black_crows,
                    _pattern_three_inside_up,
                    _pattern_three_inside_down,
                    _pattern_three_outside_up,
                    _pattern_three_outside_down,
                    _pattern_abandoned_baby,
                ]:
                    result = fn(r1, r2, r3)
                    if result and result["confidence"] >= min_confidence:
                        _append_pattern(patterns, df, i, result)

            # Five root patterns (three methods of rising/falling)
            if i >= 4:
                window = df.iloc[i - 4 : i + 1]
                for fn in [_pattern_rising_window, _pattern_falling_window]:
                    result = fn(window)
                    if result and result["confidence"] >= min_confidence:
                        _append_pattern(patterns, df, i, result)

        # Statistical summary
        bullish_count = sum(1 for p in patterns if p["direction"] == "bullish")
        bearish_count = sum(1 for p in patterns if p["direction"] == "bearish")

        # Remove duplicates by date (only the same form on the same day with the highest confidence is retained)
        seen = {}
        for p in patterns:
            key = (p["date"], p["name"])
            if key not in seen or p["confidence"] > seen[key]["confidence"]:
                seen[key] = p
        patterns = sorted(seen.values(), key=lambda x: x["date"], reverse=True)

        payload = {
            "symbol": symbol,
            "data_info": {
                "total_bars": len(df),
                "date_range": {
                    "start": str(df.iloc[0].get("date", ""))[:10] if "date" in df.columns else "N/A",
                    "end": str(df.iloc[-1].get("date", ""))[:10] if "date" in df.columns else "N/A",
                },
            },
            "patterns_found": len(patterns),
            "summary": {
                "bullish": bullish_count,
                "bearish": bearish_count,
                "neutral": len(patterns) - bullish_count - bearish_count,
            },
            "patterns": patterns,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("K线形态识别失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": f"形态识别失败: {exc}"},
            ensure_ascii=False, indent=2, default=str,
        )


def _append_pattern(patterns: list, df: pd.DataFrame, idx: int, result: dict):
    """Auxiliary: Add recognized patterns to the patterns list"""
    date_str = ""
    if "date" in df.columns:
        date_str = str(df.iloc[idx]["date"])[:10]
    patterns.append({
        "date": date_str,
        "index": idx,
        "name": result["name"],
        "direction": result["direction"],
        "confidence": round(result["confidence"], 2),
        "close": float(df.iloc[idx]["close"]),
    })


__all__ = ["get_candlestick_patterns"]

# === chart_patterns ===
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

def _chart_patterns_safe_float(value) -> Optional[float]:
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
            df[col] = df[col].apply(_chart_patterns_safe_float)
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

# === crossover_signals ===
"""
Technical Indicator Cross Signal Detection Tool

Detects the following crossing signals:
1. Moving average golden cross/dead cross (MA5/10/20/60 combination)
2. MACD Golden Cross/Dead Cross + zero axis crossing
3. KDJ Golden Cross/Dead Cross + Overbought and oversold zone
4. Price-moving average crossover (breakout/breakthrough)

All signals are based on pure mathematical calculations without LLM involvement.
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

def _ma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(window=n, min_periods=n).mean()


def _crossover_signals_ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=n, adjust=False).mean()


def _cross_above(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """series_a Wear it on top series_b"""
    return (series_a > series_b) & (series_a.shift(1) <= series_b.shift(1))


def _cross_below(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """series_a Wear underneath series_b"""
    return (series_a < series_b) & (series_a.shift(1) >= series_b.shift(1))


# ============================================================
#  MACD Calculate
# ============================================================

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    dif = _crossover_signals_ema(close, fast) - _crossover_signals_ema(close, slow)
    dea = _crossover_signals_ema(dif, signal)
    hist = dif - dea
    return dif, dea, hist


# ============================================================
#  KDJ Calculate
# ============================================================

def _kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9):
    lowest = low.rolling(window=n, min_periods=n).min()
    highest = high.rolling(window=n, min_periods=n).max()
    rsv = (close - lowest) / (highest - lowest) * 100
    rsv = rsv.replace([np.inf, -np.inf], np.nan)

    k = pd.Series(np.nan, index=close.index)
    d = pd.Series(np.nan, index=close.index)
    last_k, last_d = 50.0, 50.0
    for i in range(len(close)):
        rv = rsv.iloc[i]
        if np.isnan(rv):
            continue
        curr_k = last_k * 2 / 3 + rv / 3
        curr_d = last_d * 2 / 3 + curr_k / 3
        k.iloc[i] = curr_k
        d.iloc[i] = curr_d
        last_k, last_d = curr_k, curr_d
    j = 3 * k - 2 * d
    return k, d, j


# ============================================================
#  Signal detection
# ============================================================

def _detect_ma_crossovers(df: pd.DataFrame) -> list[dict]:
    """检测均线金叉/死叉"""
    signals = []
    ma_pairs = [
        ("MA5", 5, "MA10", 10),
        ("MA5", 5, "MA20", 20),
        ("MA5", 5, "MA60", 60),
        ("MA10", 10, "MA20", 20),
        ("MA10", 10, "MA60", 60),
        ("MA20", 20, "MA60", 60),
    ]
    close = df["close"]

    # Precalculate all moving averages
    ma_cache = {}
    for _, n, _, _ in ma_pairs:
        if n not in ma_cache:
            ma_cache[n] = _ma(close, n)
    for _, _, _, n in ma_pairs:
        if n not in ma_cache:
            ma_cache[n] = _ma(close, n)

    for short_name, short_n, long_name, long_n in ma_pairs:
        short_ma = ma_cache[short_n]
        long_ma = ma_cache[long_n]

        golden = _cross_above(short_ma, long_ma)
        death = _cross_below(short_ma, long_ma)

        for idx in golden[golden].index:
            i = df.index.get_loc(idx)
            signals.append({
                "date": _get_date(df, i),
                "type": "MA金叉",
                "pair": f"{short_name}↗{long_name}",
                "direction": "bullish",
                "price": float(close.iloc[i]),
                "short_ma": round(float(short_ma.iloc[i]), 2),
                "long_ma": round(float(long_ma.iloc[i]), 2),
                "strength": _calc_strength(df, i, 20),
            })
        for idx in death[death].index:
            i = df.index.get_loc(idx)
            signals.append({
                "date": _get_date(df, i),
                "type": "MA死叉",
                "pair": f"{short_name}↘{long_name}",
                "direction": "bearish",
                "price": float(close.iloc[i]),
                "short_ma": round(float(short_ma.iloc[i]), 2),
                "long_ma": round(float(long_ma.iloc[i]), 2),
                "strength": _calc_strength(df, i, 20),
            })
    return signals


def _detect_macd_crossovers(df: pd.DataFrame) -> list[dict]:
    """Detect MACD Golden Cross/Dead Cross + zero axis crossing"""
    close = df["close"]
    dif, dea, hist = _macd(close)
    signals = []

    # MACD Golden Cross/Dead Cross (cross of DIF and DEA)
    golden = _cross_above(dif, dea)
    death = _cross_below(dif, dea)

    for idx in golden[golden].index:
        i = df.index.get_loc(idx)
        below_zero = dif.iloc[i] < 0
        signals.append({
            "date": _get_date(df, i),
            "type": "MACD金叉" + ("(零轴下)" if below_zero else "(零轴上)"),
            "pair": "DIF↗DEA",
            "direction": "bullish",
            "price": float(close.iloc[i]),
            "dif": round(float(dif.iloc[i]), 4),
            "dea": round(float(dea.iloc[i]), 4),
            "hist": round(float(hist.iloc[i]), 4),
            "zero_position": "below" if below_zero else "above",
            "strength": _calc_strength(df, i, 20),
        })
    for idx in death[death].index:
        i = df.index.get_loc(idx)
        above_zero = dif.iloc[i] > 0
        signals.append({
            "date": _get_date(df, i),
            "type": "MACD死叉" + ("(零轴上)" if above_zero else "(零轴下)"),
            "pair": "DIF↘DEA",
            "direction": "bearish",
            "price": float(close.iloc[i]),
            "dif": round(float(dif.iloc[i]), 4),
            "dea": round(float(dea.iloc[i]), 4),
            "hist": round(float(hist.iloc[i]), 4),
            "zero_position": "above" if above_zero else "below",
            "strength": _calc_strength(df, i, 20),
        })

    # DIF zero axis crossing
    zero_up = _cross_above(dif, pd.Series(0, index=dif.index))
    zero_down = _cross_below(dif, pd.Series(0, index=dif.index))
    for idx in zero_up[zero_up].index:
        i = df.index.get_loc(idx)
        signals.append({
            "date": _get_date(df, i),
            "type": "DIF零轴穿越(上穿)",
            "pair": "DIF↗0",
            "direction": "bullish",
            "price": float(close.iloc[i]),
            "dif": round(float(dif.iloc[i]), 4),
            "strength": _calc_strength(df, i, 20),
        })
    for idx in zero_down[zero_down].index:
        i = df.index.get_loc(idx)
        signals.append({
            "date": _get_date(df, i),
            "type": "DIF零轴穿越(下穿)",
            "pair": "DIF↘0",
            "direction": "bearish",
            "price": float(close.iloc[i]),
            "dif": round(float(dif.iloc[i]), 4),
            "strength": _calc_strength(df, i, 20),
        })
    return signals


def _detect_kdj_crossovers(df: pd.DataFrame) -> list[dict]:
    """Detect KDJ golden cross/dead cross + Overbought and oversold zone"""
    k, d, j = _kdj(df["high"], df["low"], df["close"])
    close = df["close"]
    signals = []

    golden = _cross_above(k, d)
    death = _cross_below(k, d)

    for idx in golden[golden].index:
        i = df.index.get_loc(idx)
        k_val = float(k.iloc[i])
        zone = "超卖区(<20)" if k_val < 20 else ("中性区" if k_val < 80 else "超买区(>80)")
        signals.append({
            "date": _get_date(df, i),
            "type": "KDJ金叉",
            "pair": "K↗D",
            "direction": "bullish",
            "price": float(close.iloc[i]),
            "k": round(k_val, 2),
            "d": round(float(d.iloc[i]), 2),
            "j": round(float(j.iloc[i]), 2) if not np.isnan(j.iloc[i]) else None,
            "zone": zone,
            "strength": _calc_strength(df, i, 20),
        })
    for idx in death[death].index:
        i = df.index.get_loc(idx)
        k_val = float(k.iloc[i])
        zone = "超买区(>80)" if k_val > 80 else ("中性区" if k_val > 20 else "超卖区(<20)")
        signals.append({
            "date": _get_date(df, i),
            "type": "KDJ死叉",
            "pair": "K↘D",
            "direction": "bearish",
            "price": float(close.iloc[i]),
            "k": round(k_val, 2),
            "d": round(float(d.iloc[i]), 2),
            "j": round(float(j.iloc[i]), 2) if not np.isnan(j.iloc[i]) else None,
            "zone": zone,
            "strength": _calc_strength(df, i, 20),
        })
    return signals


def _detect_price_ma_crossovers(df: pd.DataFrame) -> list[dict]:
    """检测价格突破/跌破均线"""
    close = df["close"]
    signals = []

    for n, name in [(5, "MA5"), (10, "MA10"), (20, "MA20"), (60, "MA60")]:
        ma = _ma(close, n)
        break_up = _cross_above(close, ma)
        break_down = _cross_below(close, ma)

        for idx in break_up[break_up].index:
            i = df.index.get_loc(idx)
            signals.append({
                "date": _get_date(df, i),
                "type": f"价格突破{name}",
                "pair": f"Price↗{name}",
                "direction": "bullish",
                "price": float(close.iloc[i]),
                "ma": round(float(ma.iloc[i]), 2),
                "strength": _calc_strength(df, i, 20),
            })
        for idx in break_down[break_down].index:
            i = df.index.get_loc(idx)
            signals.append({
                "date": _get_date(df, i),
                "type": f"价格跌破{name}",
                "pair": f"Price↘{name}",
                "direction": "bearish",
                "price": float(close.iloc[i]),
                "ma": round(float(ma.iloc[i]), 2),
                "strength": _calc_strength(df, i, 20),
            })
    return signals


def _detect_ma_alignment(df: pd.DataFrame) -> dict:
    """检测当前均线多空排列状态"""
    close = df["close"]
    if len(close) < 60:
        return {"status": "insufficient_data"}

    ma5 = _ma(close, 5).iloc[-1]
    ma10 = _ma(close, 10).iloc[-1]
    ma20 = _ma(close, 20).iloc[-1]
    ma60 = _ma(close, 60).iloc[-1]

    if pd.isna(ma60):
        return {"status": "insufficient_data"}

    # Upward ranking: short term MA > long term MA
    if ma5 > ma10 > ma20 > ma60:
        return {
            "status": "上行排列",
            "direction": "bullish",
            "mas": {"MA5": round(float(ma5), 2), "MA10": round(float(ma10), 2),
                    "MA20": round(float(ma20), 2), "MA60": round(float(ma60), 2)},
        }
    # Downward ranking: short term MA < long term MA
    elif ma5 < ma10 < ma20 < ma60:
        return {
            "status": "下行排列",
            "direction": "bearish",
            "mas": {"MA5": round(float(ma5), 2), "MA10": round(float(ma10), 2),
                    "MA20": round(float(ma20), 2), "MA60": round(float(ma60), 2)},
        }
    else:
        # bonding/interweaving
        return {
            "status": "均线交织",
            "direction": "neutral",
            "mas": {"MA5": round(float(ma5), 2), "MA10": round(float(ma10), 2),
                    "MA20": round(float(ma20), 2), "MA60": round(float(ma60), 2)},
            "note": "The moving averages do not form a unified arrangement and may be in a period of shock or trend transition.",
        }


# ============================================================
#  Helper function
# ============================================================

def _get_date(df: pd.DataFrame, idx: int) -> str:
    if "date" in df.columns:
        return str(df.iloc[idx]["date"])[:10]
    idx_val = df.index[idx]
    if hasattr(idx_val, "strftime"):
        return idx_val.strftime("%Y-%m-%d")
    return str(idx_val)


def _calc_strength(df: pd.DataFrame, idx: int, window: int = 20) -> str:
    """Calculate the trend strength of the crossover signal (based on subsequent price changes)"""
    close = df["close"]
    if idx >= len(close) - 3:
        return "unknown"
    # Prices rise and fall 3 days after the crossover
    future_return = (close.iloc[min(idx + 3, len(close) - 1)] / close.iloc[idx] - 1) * 100
    if abs(future_return) > 3:
        return "strong" if future_return > 0 else "strong_reverse"
    elif abs(future_return) > 1:
        return "moderate"
    return "weak"


# ============================================================
#  Tool registration and main function
# ============================================================

@tool
@register_tool(
    tool_id="get_crossover_signals",
    name="技术指标交叉信号检测",
    description=(
        "Detect the golden cross/dead cross signals of common technical indicators such as moving average, MACD, KDJ and so on."
        "Covers 12 types of moving average pair crossovers, MACD golden crosses and dead crosses+Zero axis crossing, KDJ golden cross and dead cross+Overbought and oversold zones."
        "Outputs structured JSON containing signal type, direction, strength, and date of occurrence."
        "Here s signal It refers to technical trading signals generated by price/indicator intersections, not financial fraud signals, risk event signals, emotional signals or Agent capability gaps."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["crossover_signals", "golden_cross", "death_cross", "technical_signals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["金叉信号检测", "死叉信号检测", "趋势信号检测"],
    when_to_use=(
        "Use it when you need to identify golden cross/death cross signals, moving average breakthrough/breakdown, and MACD/KDJ crossover signals."
        "Suitable for trend confirmation, buying and selling signal assistance, and moving average arrangement judgment."
    ),
    when_not_to_use=(
        "Not suitable as a basis for trading decisions alone (should be combined with other tools)."
        "Not suitable for identifying candlestick patterns (get_candlestick_patterns should be used)."
        "Not used for financial statement anomalies, cash flow risk, announcement event risk, market sentiment or Agent capability gap analysis."
        "Not suitable for fundamental analysis."
    ),
    returns=(
        "Returns a JSON string, including the signals array, ma_alignment, and summary."
        "Each signal contains date, type, direction, price, strength, etc."
    ),
    example="get_crossover_signals(symbol='600519', lookback_days=120)",
    related_tools=[
        "get_candlestick_patterns",
        "get_technical_indicators",
        "get_technical_factor_bundle_tool",
        "get_support_resistance_levels",
        "get_adx_trend_strength",
    ],
)
def get_crossover_signals(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 120"] = 120,
    signal_types: Annotated[str, "Signal types, comma separated, default all. Optional: ma, macd, kdj, price_ma"] = "all",
) -> str:
    """Detect technical indicator cross signals, covering moving average golden cross/dead cross, MACD golden cross/dead cross+Zero axis crossing, KDJ golden fork/death fork+Overbought and oversold zones, price/moving average crossing.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 120
        signal_types: Signal type filtering, comma separated, value "ma" | "macd" | "kdj" | "price_ma" | "all", Default "all"

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            data_info: Data information, subfield —
                total_bars: K Total number of lines
                date_range: date range, subfield —
                    start: start date
                    end: end date
            signals_found: Total number of signals detected
            summary: Summary statistics, subfields —
                bullish: Number of uplink signals
                bearish: Number of downlink signals
            ma_alignment: Moving average arrangement status, subfield —
                status: Arrangement status, value "Arrange in ascending order" | "descending order" | "Moving average crossover" | "insufficient_data"
                direction: direction, value "bullish" | "bearish" | "neutral" (This field is not available when there is insufficient data)
                mas: Each moving average value, subfield — MA5, MA10, MA20, MA60
                note: Optional, status description text (only "Moving average crossover" exist)
            latest_signals: List of the last 20 signals, each element structure —
                date: Signal occurrence date
                type: Signal type, with values such as "MA golden fork" | "MA Sicha" | "MACD golden fork(on zero axis)" | "MACD golden fork(below zero axis)" | "MACD Sicha(on zero axis)" | "MACD Sicha(below zero axis)" | "DIF zero axis crossing(Wear it on top)" | "DIF zero axis crossing(Wear underneath)" | "KDJ golden fork" | "KDJ Sicha" | "The price is high MA{N}" | "Price drops MA{N}"
                pair: Signal pairing identifier, such as "MA5↗MA10", "DIF↗DEA", "K↗D", "DIF↗0"
                direction: direction, value "bullish" | "bearish"
                price: The closing price when the signal occurs
                strength: Signal strength (0-1)
                 (Additional fields vary by signal type: short_ma, long_ma, dif, dea, hist, zero_position, k, d, j, ma_value, zone)
        Field returned on exception —
            status: "no_data" | "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes

        data = get_stock_daily_quotes(
            symbol=symbol,
            start_date=(datetime.date.today() - datetime.timedelta(days=lookback_days + 60)).strftime("%Y%m%d"),
            end_date=datetime.date.today().strftime("%Y%m%d"),
            limit=lookback_days + 60,
        )
        if not data or len(data) < 30:
            return json.dumps(
                {"status": "no_data", "message": f"股票 {symbol} 数据不足，至少需要 30 个交易日"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(data)
        col_map = {}
        for col in df.columns:
            low = col.lower().strip()
            if low in ("open", "开盘价", "开盘"):
                col_map[col] = "open"
            elif low in ("high", "最高价", "最高"):
                col_map[col] = "high"
            elif low in ("low", "最低价", "最低"):
                col_map[col] = "low"
            elif low in ("close", "收盘价", "收盘"):
                col_map[col] = "close"
            elif low in ("trade_date", "date", "日期"):
                col_map[col] = "date"
        df = df.rename(columns=col_map)

        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return json.dumps(
                {"status": "error", "message": f"缺少必要列: {required - set(df.columns)}"},
                ensure_ascii=False, indent=2, default=str,
            )

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
        df = df.tail(lookback_days).copy()

        # Select signal type
        types = [t.strip().lower() for t in signal_types.split(",")]
        detect_all = "all" in types

        signals = []
        if detect_all or "ma" in types:
            signals.extend(_detect_ma_crossovers(df))
        if detect_all or "macd" in types:
            signals.extend(_detect_macd_crossovers(df))
        if detect_all or "kdj" in types:
            signals.extend(_detect_kdj_crossovers(df))
        if detect_all or "price_ma" in types:
            signals.extend(_detect_price_ma_crossovers(df))

        # Sort by date (newest first)
        signals.sort(key=lambda s: s["date"], reverse=True)

        # moving average arrangement
        ma_alignment = _detect_ma_alignment(df)

        bullish = sum(1 for s in signals if s["direction"] == "bullish")
        bearish = sum(1 for s in signals if s["direction"] == "bearish")

        payload = {
            "symbol": symbol,
            "data_info": {
                "total_bars": len(df),
                "date_range": {
                    "start": _get_date(df, 0),
                    "end": _get_date(df, len(df) - 1),
                },
            },
            "signals_found": len(signals),
            "summary": {
                "bullish": bullish,
                "bearish": bearish,
            },
            "ma_alignment": ma_alignment,
            "latest_signals": signals[:20],  # Last 20
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("交叉信号检测失败: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": f"信号检测失败: {exc}"},
            ensure_ascii=False, indent=2, default=str,
        )


__all__ = ["get_crossover_signals"]

# === fibonacci_tools ===
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

def _fibonacci_tools_safe_float(value) -> Optional[float]:
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
            df[col] = df[col].apply(_fibonacci_tools_safe_float)
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

# === indicators ===

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    params: Optional[Dict[str, Any]] = None


SUPPORTED = {"ma", "ema", "macd", "rsi", "boll", "atr", "kdj"}


def _require_cols(df: pd.DataFrame, cols: Iterable[str]):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame缺少必要列: {missing}, 现有列: {list(df.columns)[:10]}...")


def ma(close: pd.Series, n: int, min_periods: int = None) -> pd.Series:
    """
    Calculate Moving Average

    Args:
        close: closing price sequence
        n: cycle
        min_periods: The minimum number of periods, the default is 1 (it is also allowed to be calculated when there is insufficient data in the previous period)

    Returns:
        moving average series
    """
    if min_periods is None:
        min_periods = 1  # Defaults to 1, consistent with existing code
    return close.rolling(window=int(n), min_periods=min_periods).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """
    Calculate Exponential Moving Average

    Args:
        close: closing price sequence
        n: cycle

    Returns:
        exponential moving average series
    """
    return close.ewm(span=int(n), adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calculate MACD indicator (Moving Average Convergence Divergence)

    Args:
        close: closing price sequence
        fast: Fast line cycle, default 12
        slow: Slow line period, default 26
        signal: Signal line period, default 9

    Returns:
        contains dif, dea, macd_hist of DataFrame
        - dif: Difference between fast line and slow line (DIF)
        - dea: DIF signal line (DEA)
        - macd_hist: MACD Histogram (DIF - DEA)
    """
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=int(signal), adjust=False).mean()
    hist = dif - dea
    return pd.DataFrame({"dif": dif, "dea": dea, "macd_hist": hist})


def rsi(close: pd.Series, n: int = 14, method: str = 'ema') -> pd.Series:
    """
    Calculate RSI indicator (Relative Strength Index)

    Args:
        close: closing price sequence
        n: Period, default 14
        method: Calculation method
            - 'ema': Exponential moving average (international standard,Wilder's method)
            - 'sma': simple moving average
            - 'china': Chinese style SMA (flush/tongda letter style)

    Returns:
        RSI Sequence (0-100)

    Description:
        - 'ema': Use ewm(alpha=1/n, adjust=False), Suitable for international market
        - 'sma': Use rolling(window=n).mean(), simple moving average
        - 'china': Use ewm(com=n-1, adjust=True), Consistent with Flush/Tongdaxin
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    if method == 'ema':
        # International standards:Wilder's exponential moving average
        avg_gain = gain.ewm(alpha=1 / float(n), adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / float(n), adjust=False).mean()
    elif method == 'sma':
        # simple moving average
        avg_gain = gain.rolling(window=int(n), min_periods=1).mean()
        avg_loss = loss.rolling(window=int(n), min_periods=1).mean()
    elif method == 'china':
        # Chinese SMA: Flush/Tongdaxin style
        # SMA(X, N, 1) = ewm(com=N-1, adjust=True).mean()
        # Reference:https://blog.csdn.net/u011218867/article/details/117427927
        avg_gain = gain.ewm(com=int(n) - 1, adjust=True).mean()
        avg_loss = loss.ewm(com=int(n) - 1, adjust=True).mean()
    else:
        raise ValueError(f"不支持的RSI计算方法: {method}，支持的方法: 'ema', 'sma', 'china'")

    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def boll(close: pd.Series, n: int = 20, k: float = 2.0, min_periods: int = None) -> pd.DataFrame:
    """
    Calculate Bollinger Bands indicator

    Args:
        close: closing price sequence
        n: Period, default 20
        k: Standard deviation multiple, default 2.0
        min_periods: The minimum number of periods, the default is 1 (it is also allowed to be calculated when there is insufficient data in the previous period)

    Returns:
        contains boll_mid, boll_upper, boll_lower of DataFrame
        - boll_mid: Medium track (n-day moving average)
        - boll_upper: Upper rail (middle rail) + k times the standard deviation)
        - boll_lower: Lower rail (middle rail - k times standard deviation)
    """
    if min_periods is None:
        min_periods = 1  # Defaults to 1, consistent with existing code
    mid = close.rolling(window=int(n), min_periods=min_periods).mean()
    std = close.rolling(window=int(n), min_periods=min_periods).std()
    upper = mid + k * std
    lower = mid - k * std
    return pd.DataFrame({"boll_mid": mid, "boll_upper": upper, "boll_lower": lower})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Calculate the ATR (Average True Range, average true range) indicator to measure price volatility.

    Args:
        high: highest price sequence
        low: lowest price sequence
        close: closing price sequence
        n: Calculation period, default 14

    Returns:
        pd.Series: ATR Series (n-day moving average of true volatility), the first n-1 values are NaN
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=int(n), min_periods=int(n)).mean()


def kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """Calculate the KDJ stochastic indicator for determining overbought, oversold and short-term buy and sell signals.

    Args:
        high: highest price sequence
        low: lowest price sequence
        close: closing price sequence
        n: RSV Calculation period, default 9
        m1: K Value smoothing coefficient, default 3
        m2: D Value smoothing coefficient, default 3

    Returns:
        pd.DataFrame: DataFrame containing three lines of KDJ, column descriptions —
            kdj_k: K Value (m1 daily smoothing of RSV)
            kdj_d: D value (m2 daily smoothing of K values)
            kdj_j: J value(3*K - 2*D, highest sensitivity)
    """
    lowest_low = low.rolling(window=int(n), min_periods=int(n)).min()
    highest_high = high.rolling(window=int(n), min_periods=int(n)).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    # Handle division by zero and start NaN
    rsv = rsv.replace([np.inf, -np.inf], np.nan)

    # Recurse according to the classical formula (initialization 50)
    k = pd.Series(np.nan, index=close.index)
    d = pd.Series(np.nan, index=close.index)
    alpha_k = 1 / float(m1)
    alpha_d = 1 / float(m2)
    last_k = 50.0
    last_d = 50.0
    for i in range(len(close)):
        rv = rsv.iloc[i]
        if np.isnan(rv):
            k.iloc[i] = np.nan
            d.iloc[i] = np.nan
            continue
        curr_k = (1 - alpha_k) * last_k + alpha_k * rv
        curr_d = (1 - alpha_d) * last_d + alpha_d * curr_k
        k.iloc[i] = curr_k
        d.iloc[i] = curr_d
        last_k, last_d = curr_k, curr_d
    j = 3 * k - 2 * d
    return pd.DataFrame({"kdj_k": k, "kdj_d": d, "kdj_j": j})


def compute_indicator(df: pd.DataFrame, spec: IndicatorSpec) -> pd.DataFrame:
    """Calculate a single technical indicator on a DataFrame based on the IndicatorSpec and append the result column.

    Supported indicator names: ma, ema, macd, rsi, boll, atr, kdj.

    Args:
        df: DataFrame containing price data (required columns, such as close, high, low)
        spec: IndicatorSpec Object, name is the indicator name, params is the parameter dictionary
            ma/ema: n or period (default 20)
            macd: fast/slow/signal (Default 12/26/9)
            rsi: n or period (default 14)
            boll: n (Default 20), k (default 2.0)
            atr: n (Default 14)
            kdj: n (Default 9), m1 (default 3), m2 (default 3)

    Returns:
        pd.DataFrame: Copy of original DataFrame, appended indicator result columns, column naming rules —
            ma{N}: moving average
            ema{N}: exponential moving average
            dif, dea, macd_hist: MACD indicator
            rsi{N}: RSI indicator
            boll_mid, boll_upper, boll_lower: Bollinger Bands
            atr{N}: ATR indicator
            kdj_k, kdj_d, kdj_j: KDJ indicator

    Raises:
        ValueError: Thrown when the indicator name is not supported or a required column is missing
    """
    name = spec.name.lower()
    params = spec.params or {}
    out = df.copy()

    if name == "ma":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 20)))
        out[f"ma{n}"] = ma(df["close"], n)
        return out

    if name == "ema":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 20)))
        out[f"ema{n}"] = ema(df["close"], n)
        return out

    if name == "macd":
        _require_cols(df, ["close"])
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        macd_df = macd(df["close"], fast=fast, slow=slow, signal=signal)
        for c in macd_df.columns:
            out[c] = macd_df[c]
        return out

    if name == "rsi":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 14)))
        out[f"rsi{n}"] = rsi(df["close"], n)
        return out

    if name == "boll":
        _require_cols(df, ["close"])
        n = int(params.get("n", 20))
        k = float(params.get("k", 2.0))
        boll_df = boll(df["close"], n=n, k=k)
        for c in boll_df.columns:
            out[c] = boll_df[c]
        return out

    if name == "atr":
        _require_cols(df, ["high", "low", "close"])
        n = int(params.get("n", 14))
        out[f"atr{n}"] = atr(df["high"], df["low"], df["close"], n=n)
        return out

    if name == "kdj":
        _require_cols(df, ["high", "low", "close"])
        n = int(params.get("n", 9))
        m1 = int(params.get("m1", 3))
        m2 = int(params.get("m2", 3))
        kdj_df = kdj(df["high"], df["low"], df["close"], n=n, m1=m1, m2=m2)
        for c in kdj_df.columns:
            out[c] = kdj_df[c]
        return out

    raise ValueError(f"不支持的指标: {name}")


def compute_many(df: pd.DataFrame, specs: List[IndicatorSpec]) -> pd.DataFrame:
    """Calculate multiple technical indicators in batches, press (name, params) After deduplication, the result columns are merged in sequence.

    Args:
        df: DataFrame containing price data (required columns, such as close, high, low)
        specs: IndicatorSpec List, each element describes an indicator to be calculated

    Returns:
        pd.DataFrame: A copy of the original DataFrame, appended with all deduplicated indicator result columns;
            If specs is empty, returns a copy of the original DataFrame
    """
    if not specs:
        return df.copy()
    # Rough deduplication (press name+sorted(params)) 
    def key(s: IndicatorSpec):
        p = s.params or {}
        items = tuple(sorted(p.items()))
        return (s.name.lower(), items)

    unique_specs: List[IndicatorSpec] = []
    seen = set()
    for s in specs:
        k = key(s)
        if k not in seen:
            seen.add(k)
            unique_specs.append(s)

    out = df.copy()
    for s in unique_specs:
        out = compute_indicator(out, s)
    return out


def last_values(df: pd.DataFrame, columns: List[str]) -> Dict[str, Any]:
    """Extracts the last row (latest) value of the specified column in the DataFrame, returning None if missing or NaN.

    Args:
        df: data DataFrame
        columns: List of column names to be extracted

    Returns:
        Dict[str, Any]: Dictionary, key is the column name, value is the value of the last row of the column;
            If df is empty, the column does not exist or the value is NaN, the corresponding value is None
    """
    if df.empty:
        return {c: None for c in columns}
    last = df.iloc[-1]
    return {c: (None if c not in df.columns else (None if pd.isna(last.get(c)) else last.get(c))) for c in columns}


def add_all_indicators(df: pd.DataFrame, close_col: str = 'close',
                       high_col: str = 'high', low_col: str = 'low',
                       rsi_style: str = 'international') -> pd.DataFrame:
    """
    Add all common technical indicators to DataFrame

    This is a unified technical indicator calculation function used to replace repeated calculation codes in each data source module.

    Args:
        df: Contains price data DataFrame
        close_col: Closing price column name, default'close'
        high_col: Highest price column name, default'high' (Reserved, not used yet)
        low_col: Lowest price column name, default'low' (Reserved, not used yet)
        rsi_style: RSI computational style
            - 'international': International standard (RSI14, using EMA)
            - 'china': Chinese style (RSI6/12/24 + RSI14, Using Chinese SMA)

    Returns:
        DataFrame with technical indicator column added (modified in place)

    Added metric columns:
        - ma5, ma10, ma20, ma60: moving average
        - rsi: RSI Indicator (14th, international standard)
        - rsi6, rsi12, rsi24: RSI indicator (Chinese style, only if rsi_style='china' time)
        - rsi14: RSI Indicator (14-day, simple moving average, only if rsi_style='china' time)
        - macd_dif, macd_dea, macd: MACD indicator
        - boll_mid, boll_upper, boll_lower: Bollinger Bands

    Example:
        >>> df = pd.DataFrame({'close': [100, 101, 102, 103, 104]})
        >>> df = add_all_indicators(df)
        >>> print(df[['close', 'ma5', 'rsi']].tail())
        >>>
        >>> # Chinese style
        >>> df = add_all_indicators(df, rsi_style='china')
        >>> print(df[['close', 'rsi6', 'rsi12', 'rsi24']].tail())
    """
    # Check necessary columns
    if close_col not in df.columns:
        raise ValueError(f"DataFrame Missing closing price column: {close_col}")

    # Calculate the moving average (MA5, MA10, MA20, MA60) 
    df['ma5'] = ma(df[close_col], 5, min_periods=1)
    df['ma10'] = ma(df[close_col], 10, min_periods=1)
    df['ma20'] = ma(df[close_col], 20, min_periods=1)
    df['ma60'] = ma(df[close_col], 60, min_periods=1)

    # Calculate RSI indicator
    if rsi_style == 'china':
        # Chinese style:RSI6, RSI12, RSI24 (Using Chinese SMA)
        df['rsi6'] = rsi(df[close_col], 6, method='china')
        df['rsi12'] = rsi(df[close_col], 12, method='china')
        df['rsi24'] = rsi(df[close_col], 24, method='china')
        # Keep RSI14 as international standard reference (using simple moving average)
        df['rsi14'] = rsi(df[close_col], 14, method='sma')
        # For compatibility, also add 'rsi' column (points to rsi12)
        df['rsi'] = df['rsi12']
    else:
        # International Standard: RSI14 (using EMA)
        df['rsi'] = rsi(df[close_col], 14, method='ema')

    # Calculate MACD
    macd_df = macd(df[close_col], fast=12, slow=26, signal=9)
    df['macd_dif'] = macd_df['dif']
    df['macd_dea'] = macd_df['dea']
    df['macd'] = macd_df['macd_hist'] * 2  # Note: This is multiplied by 2 to be consistent with Tong Da Xin/Flush

    # Calculate Bollinger Bands (20th day, 2 times standard deviation)
    boll_df = boll(df[close_col], n=20, k=2.0, min_periods=1)
    df['boll_mid'] = boll_df['boll_mid']
    df['boll_upper'] = boll_df['boll_upper']
    df['boll_lower'] = boll_df['boll_lower']

    return df


# === support_resistance ===
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

def _support_resistance_safe_float(value) -> Optional[float]:
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
    highs = np.array([_support_resistance_safe_float(row["high"]) or 0 for row in prices])
    lows = np.array([_support_resistance_safe_float(row["low"]) or 0 for row in prices])

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
        high_val = _support_resistance_safe_float(q.get("high"))
        low_val = _support_resistance_safe_float(q.get("low"))
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
            df[col] = df[col].apply(_support_resistance_safe_float)
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

# === volume_analysis ===
"""
Volume Analysis Tool

The following trading volume analysis functions are provided:
1. VWAP (Volume weighted average price)
2. OBV (Energy Tide Indicator)
3. Turnover rate analysis
4. Pivot point calculation
5. Volume distribution
6. Fibonacci Extension

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


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


# ============================================================
#  Tool 5: VWAP (Volume weighted average price)
# ============================================================

@tool
@register_tool(
    tool_id="get_vwap",
    name="VWAP 成交量加权均价",
    description="Calculate VWAP (Volume Weighted Average Price) and the multi-period VWAP trend to evaluate how far the current price deviates from VWAP.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "vwap"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["vwap_analysis", "volume_weighted_price"],
    when_to_use="Use it when you need to evaluate the deviation of the current price from the average transaction price and identify buying and selling pressure.",
    when_not_to_use="The results are unreliable when there is insufficient data (less than 20 K lines); it is not suitable for minute-level short-term trading.",
    returns="Return JSON, including latest_vwap, current_close, deviation_pct, vwap_trend (5d/20d).",
    example="get_vwap(symbol='600519', lookback_days=60)",
    related_tools=["get_obv_analysis", "get_turnover_analysis", "get_volume_profile"],
)
def get_vwap(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back for VWAP calculation, default 60"] = 60,
) -> str:
    """Calculate VWAP (Volume Weighted Average Price) and the multi-period VWAP trend to evaluate how far the current price deviates from VWAP.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back for VWAP calculation, default 60

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_close: latest closing price
            date: Latest trading day
            latest_vwap: Latest VWAP value
            deviation_pct: Percent deviation of current price from VWAP
            position: Price position relative to VWAP, value "above_vwap" | "below_vwap" | "at_vwap"
            vwap_trend: Multi-Period VWAP Trend, Subfield —
                vwap_5d: 5 day VWAP
                vwap_20d: 20 day VWAP
            interpretation: interpret text
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
        start = (today - datetime.timedelta(days=int(lookback_days) + 30)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 60)

        if not quotes or len(quotes) < 20:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足20条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close", "volume"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 20:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 20 valid data items."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # typical price = (high + low + receive) / 3
        typical_price = (high + low + close) / 3.0

        # day VWAP
        vwap = (typical_price * volume).cumsum() / volume.cumsum().replace(0, np.nan)

        # Rolling VWAP: 5th and 20th
        def _rolling_vwap(tp: pd.Series, vol: pd.Series, n: int) -> pd.Series:
            cum_pv = (tp * vol).rolling(window=n, min_periods=n).sum()
            cum_v = vol.rolling(window=n, min_periods=n).sum()
            return cum_pv / cum_v.replace(0, np.nan)

        vwap_5 = _rolling_vwap(typical_price, volume, 5)
        vwap_20 = _rolling_vwap(typical_price, volume, 20)

        latest_idx = len(df) - 1
        latest_vwap = float(vwap.iloc[latest_idx]) if not pd.isna(vwap.iloc[latest_idx]) else 0.0
        latest_close = float(close.iloc[-1])
        deviation_pct = ((latest_close - latest_vwap) / latest_vwap * 100) if latest_vwap > 0 else 0.0

        vwap_5_val = float(vwap_5.iloc[latest_idx]) if not pd.isna(vwap_5.iloc[latest_idx]) else 0.0
        vwap_20_val = float(vwap_20.iloc[latest_idx]) if not pd.isna(vwap_20.iloc[latest_idx]) else 0.0

        result = {
            "symbol": str(symbol),
            "current_close": round(latest_close, 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "latest_vwap": round(latest_vwap, 2),
            "deviation_pct": round(deviation_pct, 2),
            "position": "above_vwap" if latest_close > latest_vwap else "below_vwap" if latest_close < latest_vwap else "at_vwap",
            "vwap_trend": {
                "vwap_5d": round(vwap_5_val, 2),
                "vwap_20d": round(vwap_20_val, 2),
            },
            "interpretation": (
                f"当前价格 {latest_close:.2f}，"
                f"VWAP {latest_vwap:.2f}，"
                f"deviate {deviation_pct:+.2f}%. "
                f" {'The price is higher than VWAP, and buyer power prevails.' if latest_close > latest_vwap else 'The price is lower than VWAP and seller power prevails.'}"
            ),
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("VWAP Calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 6: OBV (Energy Tide Indicator)
# ============================================================

@tool
@register_tool(
    tool_id="get_obv_analysis",
    name="OBV 能量潮分析",
    description="Calculate OBV (Power Wave indicator) and detect OBV trends and divergence signals from price.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "obv", "volume_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["obv_analysis", "volume_divergence"],
    when_to_use="It is used when it is necessary to verify the reliability of the price trend through trading volume and detect the deviation between volume and price.",
    when_not_to_use="Results are unreliable when there is insufficient data (less than 30 candlesticks); not suitable for stocks that are not actively traded.",
    returns="Returns JSON, including latest_obv, obv_trend, divergence_signal, obv_data (the latest 5 issues).",
    example="get_obv_analysis(symbol='600519', lookback_days=120)",
    related_tools=["get_vwap", "get_volume_price_divergence", "get_turnover_analysis"],
)
def get_obv_analysis(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back for OBV calculation, default 120"] = 120,
) -> str:
    """Calculate OBV (On-Balance Volume, energy tide indicator) and detect OBV trends and divergence signals from price.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back for OBV calculation, default 120

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            latest_obv: Latest OBV value
            obv_trend: OBV trend, value "up" | "down" | "neutral"
            divergence_signal: Divergence signal, value "bearish" | "bullish" | "none"
            obv_data: OBV data list of the last 5 periods, each element structure —
                date: transaction date
                close: closing price
                obv: OBV value
            interpretation: Interpret information, subfields —
                obv_up: OBV rising explanation
                obv_down: OBV Descent instructions
                bearish_divergence: Downside divergence explanation
                bullish_divergence: Upward divergence explanation
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
        start = (today - datetime.timedelta(days=int(lookback_days) + 30)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 60)

        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足30条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close", "volume"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 30 valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        volume = df["volume"]

        # Calculate OBV
        obv = pd.Series(0.0, index=df.index)
        obv_vals = [0.0]
        for i in range(1, len(df)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv_vals.append(obv_vals[-1] + volume.iloc[i])
            elif close.iloc[i] < close.iloc[i - 1]:
                obv_vals.append(obv_vals[-1] - volume.iloc[i])
            else:
                obv_vals.append(obv_vals[-1])
        obv = pd.Series(obv_vals, index=df.index)

        # OBV moving average
        obv_ma20 = obv.rolling(window=20, min_periods=10).mean()
        obv_ma50 = obv.rolling(window=50, min_periods=20).mean()

        # OBV Trend judgment
        latest_idx = len(df) - 1
        ma20_val = float(obv_ma20.iloc[latest_idx]) if not pd.isna(obv_ma20.iloc[latest_idx]) else 0.0
        ma50_val = float(obv_ma50.iloc[latest_idx]) if not pd.isna(obv_ma50.iloc[latest_idx]) else 0.0

        if ma20_val > ma50_val:
            obv_trend = "up"
        elif ma20_val < ma50_val:
            obv_trend = "down"
        else:
            obv_trend = "neutral"

        # OBV Detection of divergence from price
        divergence_signal = "none"

        # Check the trend of the last 20 candlesticks
        recent_close = close.iloc[-20:]
        recent_obv = obv.iloc[-20:]

        if len(recent_close) >= 10:
            close_start = float(recent_close.iloc[0])
            close_end = float(recent_close.iloc[-1])
            obv_start = float(recent_obv.iloc[0])
            obv_end = float(recent_obv.iloc[-1])

            price_up = close_end > close_start * 1.02
            price_down = close_end < close_start * 0.98
            obv_up = obv_end > obv_start * 1.02
            obv_down = obv_end < obv_start * 0.98

            if price_up and (not obv_up or obv_down):
                divergence_signal = "bearish"
            elif price_down and (not obv_down or obv_up):
                divergence_signal = "bullish"

        # Latest OBV value
        latest_obv = float(obv.iloc[latest_idx])

        # Last 5 issues OBV
        obv_data = []
        for i in range(max(0, latest_idx - 4), latest_idx + 1):
            obv_data.append({
                "date": str(df.iloc[i]["trade_date"])[:10],
                "close": round(float(close.iloc[i]), 2),
                "obv": round(float(obv.iloc[i]), 2),
            })

        result = {
            "symbol": str(symbol),
            "current_price": round(float(close.iloc[-1]), 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "latest_obv": round(latest_obv, 2),
            "obv_trend": obv_trend,
            "divergence_signal": divergence_signal,
            "obv_data": obv_data,
            "interpretation": {
                "obv_up": "OBV Up, volume supports uptrend",
                "obv_down": "OBV Down, volume supports downtrend",
                "bearish_divergence": "Price rises but OBV falls/stalls, rise lacks volume support (negative divergence signal)",
                "bullish_divergence": "Price falls but OBV rises/stabilizes, decline lacks volume support (positive divergence signal)",
            },
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("OBV 分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 7: Turnover rate analysis
# ============================================================

@tool
@register_tool(
    tool_id="get_turnover_analysis",
    name="换手率分析",
    description="Calculate the historical average turnover rate of stocks, detect abnormal volume increase/shrinkage signals, and evaluate the changing trend of trading activity.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "turnover", "volume_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["换手率分析", "异常放量/缩量"],
    when_to_use="Use it when you need to evaluate stock trading activity, detect abnormal volume increase/shrinkage, and analyze chip exchange situations.",
    when_not_to_use="There is insufficient data for new stocks listed less than 30 days ago; there is no data for periods of trading suspension.",
    returns="Returns JSON containing avg_turnover, current_turnover, abnormal_days_count, turnover_trend.",
    example="get_turnover_analysis(symbol='600519', lookback_days=120)",
    related_tools=["get_obv_analysis", "get_volume_price_divergence"],
)
def get_turnover_analysis(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used for turnover rate analysis, default 120"] = 120,
) -> str:
    """Analyze the stock turnover rate, calculate the historical average turnover rate, detect abnormal volume increase/shrinkage signals, and evaluate the changing trend of trading activity.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used for turnover rate analysis, default 120

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            has_shares_info: Whether to obtain the total equity information (if False, the turnover rate field is None, and the transaction volume is used for approximate estimation)
            avg_turnover: Average turnover rate (percentage), when there is no total share capital None
            current_turnover: Current turnover rate (percentage), when there is no total share capital None
            abnormal_days_count: Abnormal volume days
            abnormal_days: Abnormal volume day list (last 5 items), each element structure —
                date: transaction date
                volume: Volume
                volume_ratio: Quantity ratio
            turnover_trend: Turnover rate trend, value "increasing" | "decreasing" | "stable"
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes, get_stock_basic_info

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 30)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 60)

        if not quotes or len(quotes) < 20:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足20条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close", "volume"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 20:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 20 valid data items."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        volume = df["volume"]

        # Get total share capital
        basic_info = get_stock_basic_info(str(symbol))
        total_shares = None
        if basic_info:
            total_shares = (
                _safe_float(basic_info.get("total_shares"))
                or _safe_float(basic_info.get("total_share"))
                or _safe_float(basic_info.get("total_mv"))
            )

        if total_shares is None or total_shares <= 0:
            # If total equity information is not available, use turnover to approximate turnover rate
            turnover_series = pd.Series([0.0] * len(df), index=df.index)
            for i in range(1, len(df)):
                vol_value = float(volume.iloc[i]) if not pd.isna(volume.iloc[i]) else 0
                turnover_series.iloc[i] = vol_value / (vol_value + 1e-10)
            has_shares_info = False
        else:
            has_shares_info = True
            # turnover rate = Trading volume/total equity
            turnover_series = volume / total_shares * 100.0

        # Calculate average turnover rate
        avg_turnover = float(turnover_series.iloc[1:].mean()) if len(df) > 1 else 0.0
        current_turnover = float(turnover_series.iloc[-1]) if not pd.isna(turnover_series.iloc[-1]) else 0.0

        # Detect abnormal volume (>2x mean)
        mean_vol = float(volume.iloc[1:].mean()) if len(df) > 1 else 0.0
        abnormal_days = []
        for i in range(1, len(df)):
            v = float(volume.iloc[i]) if not pd.isna(volume.iloc[i]) else 0.0
            if mean_vol > 0 and v > mean_vol * 2:
                abnormal_days.append({
                    "date": str(df.iloc[i]["trade_date"])[:10],
                    "volume": round(v, 2),
                    "volume_ratio": round(v / mean_vol, 2),
                })

        # Turnover trend (judged by MA5 and MA20)
        turnover_ma5 = turnover_series.rolling(window=5, min_periods=3).mean()
        turnover_ma20 = turnover_series.rolling(window=20, min_periods=10).mean()

        ma5_val = float(turnover_ma5.iloc[-1]) if not pd.isna(turnover_ma5.iloc[-1]) else 0.0
        ma20_val = float(turnover_ma20.iloc[-1]) if not pd.isna(turnover_ma20.iloc[-1]) else 0.0

        if ma5_val > ma20_val * 1.1:
            turnover_trend = "increasing"
        elif ma5_val < ma20_val * 0.9:
            turnover_trend = "decreasing"
        else:
            turnover_trend = "stable"

        result = {
            "symbol": str(symbol),
            "current_price": round(float(close.iloc[-1]), 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "has_shares_info": has_shares_info,
            "avg_turnover": round(avg_turnover, 4) if has_shares_info else None,
            "current_turnover": round(current_turnover, 4) if has_shares_info else None,
            "abnormal_days_count": len(abnormal_days),
            "abnormal_days": abnormal_days[-5:] if abnormal_days else [],
            "turnover_trend": turnover_trend,
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("换手率分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 8: pivot point (Pivot Points)
# ============================================================

@tool
@register_tool(
    tool_id="get_pivot_points",
    name="枢轴点计算",
    description="Calculate key support/resistance levels based on the classic pivot point formula and Fibonacci pivot point formula to provide a reference for intraday research.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "pivot_points"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["pivot_points_calculation", "intraday_levels"],
    when_to_use="Use it when you need to calculate key support and resistance levels within the day, and set reference for risk attention and return attention.",
    when_not_to_use="It cannot be calculated when there is insufficient data (less than 2 K lines); it is not suitable for long-term analysis at the non-daily level.",
    returns="Returns JSON, including classic and fibonacci two sets of pivot points (PP/R1-3/S1-3) and current prices.",
    example="get_pivot_points(symbol='600519', lookback_days=30)",
    related_tools=["get_support_resistance_levels", "get_fibonacci_extension"],
)
def get_pivot_points(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back for pivot point calculation, default 30"] = 30,
) -> str:
    """Calculate classic pivot points and Fibonacci pivot points to provide support/resistance reference for intraday research.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back for pivot point calculation, default 30

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            reference_bar: Reference K line (previous one), subfield —
                date: Reference K line date
                high: highest price
                low: lowest price
                close: closing price
            classic: Classic pivot points, the value of each level is {price, distance_pct}, key include —
                pp: pivot point
                r1, r2, r3: resistance level 1/2/3
                s1, s2, s3: support level 1/2/3
            fibonacci: Fibonacci pivot points, subfields —
                pp: pivot point
                resistances: Resistance level dictionary, key is "r_{level}" (level Values 0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0), the value is {price, distance_pct}
                supports: Support bit dictionary, key is "s_{level}" (level Same as above), the value is {price, distance_pct}
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
        start = (today - datetime.timedelta(days=int(lookback_days) + 10)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 20)

        if not quotes or len(quotes) < 2:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足2条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 2:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 2 valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        latest = df.iloc[-1]
        current_price = float(latest["close"])

        # The most recent complete K-line
        if len(df) >= 2:
            ref_bar = df.iloc[-2]  # Use the previous one to calculate
        else:
            ref_bar = df.iloc[-1]

        high = float(ref_bar["high"])
        low = float(ref_bar["low"])
        close = float(ref_bar["close"])
        ref_date = str(ref_bar["trade_date"])[:10]

        # --- classic pivot point ---
        pp = (high + low + close) / 3.0

        classic = {
            "pp": round(pp, 2),
            "r1": round(2 * pp - low, 2),
            "r2": round(pp + (high - low), 2),
            "r3": round(high + 2 * (pp - low), 2),
            "s1": round(2 * pp - high, 2),
            "s2": round(pp - (high - low), 2),
            "s3": round(low - 2 * (high - pp), 2),
        }

        classic_with_dist = {}
        for k, v in classic.items():
            dist = round((v - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
            classic_with_dist[k] = {"price": v, "distance_pct": dist}

        # --- Fibonacci Pivot Points ---
        fib_levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        fib_pivot = pp
        fib_range = high - low

        fib_resistances = {}
        fib_supports = {}

        for level in fib_levels:
            # resistance = PP + level * range
            r_price = fib_pivot + level * fib_range
            r_dist = round((r_price - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
            fib_resistances[f"r_{level}"] = {"price": round(r_price, 2), "distance_pct": r_dist}

            # support = PP - level * range
            s_price = fib_pivot - level * fib_range
            s_dist = round((s_price - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
            fib_supports[f"s_{level}"] = {"price": round(s_price, 2), "distance_pct": s_dist}

        fibonacci = {
            "pp": round(fib_pivot, 2),
            "resistances": fib_resistances,
            "supports": fib_supports,
        }

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price, 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "reference_bar": {
                "date": ref_date,
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
            },
            "classic": classic_with_dist,
            "fibonacci": fibonacci,
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("枢轴点计算失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 9: Volume distribution (Volume Profile)
# ============================================================

@tool
@register_tool(
    tool_id="get_volume_profile",
    name="成交量分布分析",
    description="Calculate volume distribution, identify POC (point of control) and value area, and evaluate the position of the current price in the value area.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "volume_profile"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["成交量分布分析", "POC 控制点识别"],
    when_to_use="Use it when you need to identify the price range with the most intensive transactions and determine the fair value area. Suitable for large cycle trend judgment.",
    when_not_to_use="The distribution is unreliable when there is insufficient data (less than 20 K lines); it is not suitable for short-term high-frequency trading.",
    returns="Returns JSON containing poc_price, value_area_high, value_area_low, current_position_relative_to_va, distribution_profile.",
    example="get_volume_profile(symbol='600519', lookback_days=60, price_bins=20)",
    related_tools=["get_support_resistance_levels", "get_vwap"],
)
def get_volume_profile(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used for volume distribution calculation, default 60"] = 60,
    price_bins: Annotated[int, "Price range bin quantity, default 20"] = 20,
) -> str:
    """Calculate the volume profile (Volume Profile), identify POC (point of control) and value area, and evaluate the position of the current price in the value area.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used for volume distribution calculation, default 60
        price_bins: Price range bin quantity, default 20

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            poc_price: POC (control point) price
            poc_volume: POC Volume
            poc_volume_pct: POC Transaction volume ratio (percentage)
            value_area_high: upper edge of value area
            value_area_low: Lower edge of value area
            value_area_width: value area width
            current_position_relative_to_va: The position of the current price relative to the value area, the value "above_va" | "below_va" | "within_va"
            distribution_profile: List of distribution profiles (up to 20 bins), per element structure —
                price_level: Price level (bundling center)
                price_low: Lower edge of bin
                price_high: Top edge of dividing box
                volume: Volume
                volume_pct: Transaction volume ratio (percentage)
                is_poc: Is it POC
                in_value_area: Is it within the value area?
            data_quality: Data quality, subfield —
                bars_analyzed: Number of candlesticks analyzed
                price_bins: Actual number of bins
        Field returned on exception —
            status: "error"
            message: error message
    """
    try:
        from core.skill_runtime.data_access import get_stock_daily_quotes

        today = datetime.date.today()
        end = today.strftime("%Y%m%d")
        start = (today - datetime.timedelta(days=int(lookback_days) + 20)).strftime("%Y%m%d")
        quotes = get_stock_daily_quotes(str(symbol), start, end, limit=int(lookback_days) + 40)

        if not quotes or len(quotes) < 20:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足20条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close", "volume"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 20:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 20 valid data items."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Determine price range
        price_min = float(low.min())
        price_max = float(high.max())
        price_range = price_max - price_min

        if price_range <= 0:
            return json.dumps(
                {"status": "error", "message": "The price range is abnormal and the volume distribution cannot be calculated."},
                ensure_ascii=False, indent=2, default=str,
            )

        n_bins = max(5, min(50, int(price_bins)))
        bin_width = price_range / n_bins

        # Create price bins
        bin_edges = [price_min + i * bin_width for i in range(n_bins + 1)]
        bin_centers = [(bin_edges[i] + bin_edges[i + 1]) / 2.0 for i in range(n_bins)]
        bin_volume = [0.0] * n_bins

        # Assign volume to individual price bins
        for i in range(len(df)):
            bar_high = float(high.iloc[i])
            bar_low = float(low.iloc[i])
            bar_volume = float(volume.iloc[i])

            if bar_high <= bar_low or bar_volume <= 0:
                continue

            for j in range(n_bins):
                bin_top = bin_edges[j + 1]
                bin_bottom = bin_edges[j]

                # Calculate overlapping intervals
                overlap_low = max(bar_low, bin_bottom)
                overlap_high = min(bar_high, bin_top)

                if overlap_high > overlap_low:
                    overlap_pct = (overlap_high - overlap_low) / (bar_high - bar_low)
                    bin_volume[j] += bar_volume * overlap_pct

        # Find the POC (the price level with the highest volume)
        poc_idx = int(np.argmax(bin_volume))
        poc_price = round(bin_centers[poc_idx], 2)
        poc_volume = round(bin_volume[poc_idx], 2)

        # Value Zone: Find the price range that contains 70% of the volume
        total_volume = sum(bin_volume)
        if total_volume <= 0:
            return json.dumps(
                {"status": "error", "message": "The trading volume data is abnormal."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Expand from POC to both sides
        sorted_indices = sorted(
            range(n_bins),
            key=lambda x: bin_volume[x],
            reverse=True,
        )

        target_vol = total_volume * 0.7
        accumulated_vol = 0.0
        value_area_bins = []

        for idx in sorted_indices:
            if accumulated_vol >= target_vol:
                break
            value_area_bins.append(idx)
            accumulated_vol += bin_volume[idx]

        if value_area_bins:
            va_low_idx = min(value_area_bins)
            va_high_idx = max(value_area_bins)
            value_area_low = round(bin_edges[va_low_idx], 2)
            value_area_high = round(bin_edges[va_high_idx + 1], 2)
        else:
            value_area_low = round(price_min, 2)
            value_area_high = round(price_max, 2)

        current_price_val = float(close.iloc[-1])
        if current_price_val > value_area_high:
            current_position = "above_va"
        elif current_price_val < value_area_low:
            current_position = "below_va"
        else:
            current_position = "within_va"

        # Distribution overview
        distribution_profile = []
        for j in range(n_bins):
            vol_pct = (bin_volume[j] / total_volume * 100) if total_volume > 0 else 0
            distribution_profile.append({
                "price_level": round(bin_centers[j], 2),
                "price_low": round(bin_edges[j], 2),
                "price_high": round(bin_edges[j + 1], 2),
                "volume": round(bin_volume[j], 2),
                "volume_pct": round(vol_pct, 2),
                "is_poc": j == poc_idx,
                "in_value_area": j in value_area_bins,
            })

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price_val, 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "poc_price": poc_price,
            "poc_volume": poc_volume,
            "poc_volume_pct": round(poc_volume / total_volume * 100, 2) if total_volume > 0 else 0,
            "value_area_high": value_area_high,
            "value_area_low": value_area_low,
            "value_area_width": round(value_area_high - value_area_low, 2),
            "current_position_relative_to_va": current_position,
            "distribution_profile": distribution_profile[:20] if len(distribution_profile) > 20 else distribution_profile,
            "data_quality": {
                "bars_analyzed": len(df),
                "price_bins": n_bins,
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Volume distribution calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


# ============================================================
#  Tool 10: Fibonacci Extension
# ============================================================

@tool
@register_tool(
    tool_id="get_fibonacci_extension",
    name="斐波那契扩展",
    description="Fibonacci extension targets are calculated based on recent price movements (high to low or low to high) to provide a reference for potential price targets.",
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_analysis", "fibonacci_extension"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["斐波那契扩展", "价格目标位"],
    when_to_use="Use it when you need to find potential expansion price levels in trending markets and set a profit focus reference.",
    when_not_to_use="The reference value of the expansion position in the volatile market is limited; when the data is insufficient (less than 30 K lines), the results are unreliable.",
    returns="Returns JSON, including swing_analysis, extension_prices (each level), current_proximity.",
    example="get_fibonacci_extension(symbol='600519', lookback_days=120, extension_levels='1.272,1.382,1.618,2.0,2.618')",
    related_tools=["get_fibonacci_retracement", "get_pivot_points"],
)
def get_fibonacci_extension(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "The number of days to look back is used to identify fluctuation ranges, the default 120"] = 120,
    extension_levels: Annotated[str, "Expansion levels, comma separated, default 1.272,1.382,1.618,2.0,2.618"] = "1.272,1.382,1.618,2.0,2.618",
) -> str:
    """Calculate Fibonacci extension targets to calculate potential price targets based on recent price movements (high to low or low to high).

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: The number of days to look back is used to identify fluctuation ranges, the default 120
        extension_levels: Expansion levels, comma separated, default "1.272,1.382,1.618,2.0,2.618"

    Returns:
        str: JSON String, returns field description normally——
            symbol: Stock code
            current_price: latest closing price
            date: Latest trading day
            trend: Current trend direction, value "up" | "down"
            swing_analysis: Fluctuation Analysis, Subfield —
                swing_type: Fluctuation type, value "rising fluctuations" | "downtrend"
                start_price: Fluctuation starting price
                end_price: Fluctuation end price
                swing_range: Fluctuation range
            extension_prices: Extended bitlist, per-element structure —
                level: Expansion ratio (such as 1.272, 1.382, 1.618, 2.0, 2.618)
                price: Extension bit price
                distance_pct: Percentage from current price
            current_proximity: Recent extension bit information, subfield —
                closest_level: Recent expansion ratio
                closest_price: Recent expansion price
                distance_pct: Percentage from current price
                role: Price role, value "resistance" | "support"
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

        if not quotes or len(quotes) < 30:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据，或数据不足30条。"},
                ensure_ascii=False, indent=2, default=str,
            )

        df = pd.DataFrame(quotes)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].apply(_safe_float)
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.dropna(subset=["high", "low", "close"]).sort_values("trade_date")
        df = df.reset_index(drop=True)

        if len(df) < 30:
            return json.dumps(
                {"status": "error", "message": f"{symbol} There are less than 30 valid data."},
                ensure_ascii=False, indent=2, default=str,
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # parse extension level
        levels = []
        for s in extension_levels.split(","):
            s = s.strip()
            try:
                val = float(s)
                if val > 0:
                    levels.append(val)
            except (ValueError, TypeError):
                continue

        if not levels:
            levels = [1.272, 1.382, 1.618, 2.0, 2.618]

        current_price = float(close.iloc[-1])

        # Find recent significant fluctuations (use the most recent half of the data to find high and low points)
        half_len = max(20, len(df) // 2)
        recent = df.iloc[-half_len:]

        swing_high = float(recent["high"].max())
        swing_low = float(recent["low"].min())
        swing_high_idx = recent["high"].idxmax()
        swing_low_idx = recent["low"].idxmin()

        # Determine the current trend direction: price changes of the recent N K lines
        recent_close_vals = close.iloc[-min(20, len(close)):]
        trend = "up" if float(recent_close_vals.iloc[-1]) > float(recent_close_vals.iloc[0]) else "down"

        # Determine the direction of the wave
        if swing_low_idx < swing_high_idx:
            # Low points first, high points last → rising fluctuations
            swing_type = "low_to_high"
            swing_start_price = swing_low
            swing_end_price = swing_high
            swing_range = swing_high - swing_low
            direction = "up"
        else:
            # High points first, low points last → downtrend
            swing_type = "high_to_low"
            swing_start_price = swing_high
            swing_end_price = swing_low
            swing_range = swing_high - swing_low
            direction = "down"

        if swing_range <= 0:
            return json.dumps(
                {"status": "error", "message": "The price fluctuation range is abnormal and the extension level cannot be calculated."},
                ensure_ascii=False, indent=2, default=str,
            )

        # Calculate extension price
        extension_prices = []
        for level in levels:
            if direction == "up":
                # Rising expansion: extending from the starting point to the end point
                ext_price = swing_start_price + level * swing_range
            else:
                # Descending expansion: extending from the starting point to the end point
                ext_price = swing_start_price - level * swing_range

            # The distance percentage from the current price to the extension level
            if direction == "up":
                distance_pct = (ext_price - current_price) / current_price * 100 if current_price > 0 else 0.0
            else:
                distance_pct = (current_price - ext_price) / current_price * 100 if current_price > 0 else 0.0

            extension_prices.append({
                "level": level,
                "price": round(ext_price, 2),
                "distance_pct": round(distance_pct, 2),
            })

        # Find the nearest extension bit
        if extension_prices:
            closest = min(extension_prices, key=lambda x: abs(x["distance_pct"]))
            current_proximity = {
                "closest_level": closest["level"],
                "closest_price": closest["price"],
                "distance_pct": closest["distance_pct"],
                "role": "resistance" if closest["price"] > current_price else "support",
            }
        else:
            current_proximity = None

        result = {
            "symbol": str(symbol),
            "current_price": round(current_price, 2),
            "date": str(df.iloc[-1]["trade_date"])[:10],
            "trend": trend,
            "swing_analysis": {
                "swing_type": "上升波动" if direction == "up" else "下降波动",
                "start_price": round(swing_start_price, 2),
                "end_price": round(swing_end_price, 2),
                "swing_range": round(swing_range, 2),
            },
            "extension_prices": extension_prices,
            "current_proximity": current_proximity,
            "data_quality": {
                "bars_analyzed": len(df),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Fibonacci extension calculation failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_vwap",
    "get_obv_analysis",
    "get_turnover_analysis",
    "get_pivot_points",
    "get_volume_profile",
    "get_fibonacci_extension",
]

