#!/usr/bin/env python3
"""
Real-time news tool compatibility layer
To maintain backward compatibility, export functions from the news.realtime_news module
"""

from tradingagents.dataflows.news.realtime_news import (
    get_realtime_stock_news,
    RealtimeNewsAggregator,
    NewsItem
)

__all__ = [
    'get_realtime_stock_news',
    'RealtimeNewsAggregator',
    'NewsItem'
]

