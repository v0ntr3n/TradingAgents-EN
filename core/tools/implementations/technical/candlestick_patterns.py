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
