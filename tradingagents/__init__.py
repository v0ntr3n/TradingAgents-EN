#!/usr/bin/env python3
"""
TradingAgents-CN Core trading agent library

This is a multi-agent-based stock research system that supports comprehensive research and analysis of A-shares, Hong Kong stocks and US stocks.
"""

__version__ = "1.0.0"
__author__ = "TradingAgents-CN"
__description__ = "TradingAgents-CN - Multi-agent stock research system for Chinese markets"

# Import core module
try:
    from .config import config_manager
    from .utils import logging_manager
except ImportError:
    # If the import fails, the basic functions of the module will not be affected.
    pass

__all__ = [
    "__version__",
    "__author__", 
    "__description__"
]