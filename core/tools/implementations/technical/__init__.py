"""
Technical indicator calculation library

This is an independent technical indicator calculation library that provides purely functional indicator calculation functions.
It is not registered as a LangChain tool and can be called directly by other modules.

Supported indicators:
- MA (moving average)
- EMA (exponential moving average)
- MACD (Smoothed Moving Average Convergence and Divergence)
- RSI (Relative strength indicator, supports 3 calculation styles)
- BOLL (Bollinger Bands)
- ATR (average true volatility)
- KDJ (Stochastic)

Usage example:
    from core.tools.implementations.technical import ma, rsi, macd

    # Calculate MA
    ma_values = ma(df['close'], n=20)

    # Calculate RSI (international standard)
    rsi_values = rsi(df['close'], n=14, method='ema')

    # Calculate RSI (Chinese style)
    rsi_values = rsi(df['close'], n=14, method='china')

    # Calculate MACD
    macd_df = macd(df['close'], fast=12, slow=26, signal=9)
"""

from .indicators import (
    # Basic indicators
    ma,
    ema,
    macd,
    rsi,
    boll,
    atr,
    kdj,

    # Helper function
    compute_indicator,
    compute_many,
    last_values,
    add_all_indicators,

    # data class
    IndicatorSpec,
    SUPPORTED,
)

__all__ = [
    # Basic indicators
    "ma",
    "ema",
    "macd",
    "rsi",
    "boll",
    "atr",
    "kdj",

    # Helper function
    "compute_indicator",
    "compute_many",
    "last_values",
    "add_all_indicators",

    # data class
    "IndicatorSpec",
    "SUPPORTED",
]

