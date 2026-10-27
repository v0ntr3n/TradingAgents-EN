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


def _ema(close: pd.Series, n: int) -> pd.Series:
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
    dif = _ema(close, fast) - _ema(close, slow)
    dea = _ema(dif, signal)
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
