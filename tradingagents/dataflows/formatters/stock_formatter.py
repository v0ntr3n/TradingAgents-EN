"""Markdown table and summary statistics formatter for stock OHLCV DataFrames."""
from __future__ import annotations

import pandas as pd


class StockDataFormatter:
    """Format standardized stock DataFrames into concise Markdown tables for LLM agents."""

    @staticmethod
    def format_dataframe_summary(df: pd.DataFrame, symbol: str, max_rows: int = 10) -> str:
        """Format recent OHLCV rows and summary statistics as Markdown."""
        if df is None or df.empty:
            return f"No price data available for {symbol}."
        tail = df.tail(max_rows)
        lines = [f"### Market Data Summary for {symbol} ({len(df)} trading days)"]
        if "close" in df.columns:
            latest = float(df["close"].iloc[-1])
            high = float(df["close"].max())
            low = float(df["close"].min())
            lines.append(f"- Latest Close: {latest:.2f} | Period High: {high:.2f} | Period Low: {low:.2f}")
        lines.append("")
        lines.append(tail.to_string(index=False))
        return "\n".join(lines)
