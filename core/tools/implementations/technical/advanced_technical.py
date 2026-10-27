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
            df[col] = df[col].apply(_safe_float)
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
        adx = _ema(dx, period_n)

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
            df[col] = df[col].apply(_safe_float)
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
            df[col] = df[col].apply(_safe_float)
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