#!/usr/bin/env python3
"""
CYQ Analyzer Skill - Chip distribution analysis tool

This package contains the core modules required for chip distribution analysis:
- cyq_analyzer: Chip distribution calculation and chart generation
- stock_cache_v3: Stock data caching system

Usage example:
    from scripts.cyq_analyzer import calculate_cyq, analyze_and_plot
    from scripts.stock_cache_v3 import get_stock_data, get_cache_stats
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__description__ = "Stock chip distribution analysis tool, supporting indicators such as profit margin, main cost area, chip concentration, etc."

# Optional: Export commonly used functions to facilitate external import
from .cyq_analyzer import calculate_cyq, analyze_and_plot, fetch_stock_data
from .stock_cache_v3 import get_stock_data, get_cache_stats, list_cached_stocks

__all__ = [
    # cyq_analyzer Export
    'calculate_cyq',
    'analyze_and_plot',
    'fetch_stock_data',
    # stock_cache_v3 Export
    'get_stock_data',
    'get_cache_stats',
    'list_cached_stocks'
]