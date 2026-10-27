"""
Basic data synchronization sub-package: encapsulates blocking calls and processing functions related to synchronization of basic stock information.
- utils.py: Blocking retrieval function with Tushare (stock list, latest trading day, daily basic data)
- processing.py: Shared document building/metric handling functions
"""
from .utils import (
    fetch_stock_basic_df,
    find_latest_trade_date,
    fetch_daily_basic_mv_map,
    fetch_latest_roe_map,
)
from .processing import add_financial_metrics

