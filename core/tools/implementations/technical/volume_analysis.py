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