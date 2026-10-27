from __future__ import annotations

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

