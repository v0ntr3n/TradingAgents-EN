#!/usr/bin/env python3
"""
App Cache Read Adapter (TradingAgents -> app MongoDB collection)
- Basic information collection:stock_basic_info
- Quote collection:market_quotes

When ta_use_app_cache is enabled, it is used as the priority data source; the misses will continue to fall back to the directly connected data source from the upper layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

import pandas as pd
import logging

_logger = logging.getLogger('dataflows')

try:
    from tradingagents.config.database_manager import get_mongodb_client
except Exception:  # pragma: no cover - weak dependency
    get_mongodb_client = None  # type: ignore


BASICS_COLLECTION = "stock_basic_info"
QUOTES_COLLECTION = "market_quotes"


def get_basics_from_cache(stock_code: Optional[str] = None) -> Optional[Dict[str, Any] | List[Dict[str, Any]]]:
    """Read basic information from app s stock_basic_info."""
    if get_mongodb_client is None:
        return None
    client = get_mongodb_client()
    if not client:
        return None
    try:
        # The database name is taken from the DatabaseManager internal configuration
        db_name = None
        try:
            # Access DatabaseManager exposed configuration
            from tradingagents.config.database_manager import get_database_manager  # type: ignore
            db_name = get_database_manager().mongodb_config.get("database", "tradingagents")
        except Exception:
            db_name = "tradingagents"
        db = client[db_name]
        coll = db[BASICS_COLLECTION]
        if stock_code:
            code6 = str(stock_code).zfill(6)
            try:
                _logger.debug(f"[app_cache] Query basic information | db={db_name} coll={BASICS_COLLECTION} code={code6}")
            except Exception:
                pass
            # Query the symbol and code fields at the same time to ensure compatibility with old and new data formats
            doc = coll.find_one({"$or": [{"symbol": code6}, {"code": code6}]})
            if not doc:
                try:
                    _logger.debug(f"[app_cache] Basic information missed | db={db_name} coll={BASICS_COLLECTION} code={code6}, try etf_basic_info")
                except Exception:
                    pass
                # ETF/Fund code: Check everything etf_basic_info
                try:
                    etf_coll = db["etf_basic_info"]
                    doc = etf_coll.find_one({"$or": [{"symbol": code6}, {"code": code6}]})
                    if doc:
                        # Complete fields consistent with the stock_basic_info structure
                        doc.setdefault("area", "未知")
                        doc.setdefault("industry", "ETF基金")
                        doc.setdefault("market", "ETF")
                        doc.setdefault("list_date", "未知")
                except Exception as etf_e:
                    try:
                        _logger.debug(f"[app_cache] etf_basic_info Query exception: {etf_e}")
                    except Exception:
                        pass
            return doc or None
        else:
            cursor = coll.find({})
            docs = list(cursor)
            return docs or None
    except Exception as e:
        try:
            _logger.debug(f"[app_cache] Basic information reading exception (ignored): {e}")
        except Exception:
            pass
        return None


def get_market_quote_dataframe(symbol: str) -> Optional[pd.DataFrame]:
    """Read the latest snapshot of a single stock from the app s market_quotes and convert it into a DataFrame."""
    if get_mongodb_client is None:
        return None
    client = get_mongodb_client()
    if not client:
        return None
    try:
        # Get database
        from tradingagents.config.database_manager import get_database_manager  # type: ignore
        db_name = get_database_manager().mongodb_config.get("database", "tradingagents")
        db = client[db_name]
        coll = db[QUOTES_COLLECTION]
        code = str(symbol).zfill(6)
        try:
            _logger.debug(f"[app_cache] Check market prices | db={db_name} coll={QUOTES_COLLECTION} code={code}")
        except Exception:
            pass
        doc = coll.find_one({"code": code})
        if not doc:
            try:
                _logger.debug(f"[app_cache] The market misses | db={db_name} coll={QUOTES_COLLECTION} code={code}")
            except Exception:
                pass
            return None
        # Construct DataFrame, field alignment tushare standardized mapping
        row = {
            "code": code,
            "date": doc.get("trade_date"),  # YYYYMMDD
            "open": doc.get("open"),
            "high": doc.get("high"),
            "low": doc.get("low"),
            "close": doc.get("close"),
            "volume": doc.get("volume"),
            "amount": doc.get("amount"),
            "pct_chg": doc.get("pct_chg"),
            "change": None,
        }
        df = pd.DataFrame([row])
        return df
    except Exception as e:
        try:
            _logger.debug(f"[app_cache] Quote reading exception (ignored): {e}")
        except Exception:
            pass
        return None

