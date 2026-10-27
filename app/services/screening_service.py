from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Unified indicator library
from tradingagents.tools.analysis.indicators import IndicatorSpec, compute_many
# Unified multi-data source DF interface (downgraded by priority)
from tradingagents.dataflows.data_source_manager import get_data_source_manager
from tradingagents.dataflows.providers.china.fundamentals_snapshot import get_cn_fund_snapshot


from app.services.screening.eval_utils import (
    collect_fields_from_conditions as _collect_fields_from_conditions_util,
    evaluate_conditions as _evaluate_conditions_util,
    evaluate_fund_conditions as _evaluate_fund_conditions_util,
    safe_float as _safe_float_util,
)

# --- DSL constraint ---
ALLOWED_FIELDS = {
    # Original quotes (unified into lowercase columns)
    "open", "high", "low", "close", "vol", "amount",
    # derived
    "pct_chg",  # The day's increase or decrease
    # Indicators (fixed parameters)
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "dif", "dea", "macd_hist",
    "rsi14",
    "boll_mid", "boll_upper", "boll_lower",
    "atr14",
    "kdj_k", "kdj_d", "kdj_j",
    # Reserved: Fundamentals (subsequent implementation)
    "pe", "pb", "roe", "market_cap",
}

# Category: basic market field, technical indicator field, fundamental field
BASE_FIELDS = {"open", "high", "low", "close", "vol", "amount", "pct_chg"}
TECH_FIELDS = {
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "dif", "dea", "macd_hist",
    "rsi14",
    "boll_mid", "boll_upper", "boll_lower",
    "atr14",
    "kdj_k", "kdj_d", "kdj_j",
}
FUND_FIELDS = {"pe", "pb", "roe", "market_cap"}

ALLOWED_OPS = {">", "<", ">=", "<=", "==", "!=", "between", "cross_up", "cross_down"}


@dataclass
class ScreeningParams:
    market: str = "CN"
    date: Optional[str] = None  # YYYY-MM-DD, None=Last trading day
    adj: str = "qfq"  # Reserved parameters. The current implementation uses Tdx data and does not distinguish between restoration rights.
    limit: int = 50
    offset: int = 0
    order_by: Optional[List[Dict[str, str]]] = None  # [{field, direction}]


import logging
logger = logging.getLogger("agents")

class ScreeningService:
    def __init__(self):
        # Data sources are obtained through the unified DF interface and are not directly bound to specific sources.
        self.provider = None

    # --- public entrance ---
    def run(self, conditions: Dict[str, Any], params: ScreeningParams) -> Dict[str, Any]:
        symbols = self._get_universe()
        # In order to control the duration, first limit the sample size (later use batch/caching optimization)
        symbols = symbols[:120]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=220)
        end_s = end_date.strftime("%Y-%m-%d")
        start_s = start_date.strftime("%Y-%m-%d")

        results: List[Dict[str, Any]] = []

        # Analyze the fields involved in the conditions to determine whether technical indicators/markets are needed
        needed_fields = self._collect_fields_from_conditions(conditions)
        order_fields = {o.get("field") for o in (params.order_by or []) if o.get("field")}
        all_needed = set(needed_fields) | set(order_fields)
        need_tech = any(f in TECH_FIELDS for f in all_needed)
        need_base = any(f in BASE_FIELDS for f in all_needed) or need_tech
        need_fund = any(f in FUND_FIELDS for f in all_needed)

        for code in symbols:
            try:
                dfc = None
                last = None

                # If you need basic market conditions/technical indicators, take the K-line
                if need_base:
                    manager = get_data_source_manager()
                    df = manager.get_stock_dataframe(code, start_s, end_s)
                    if df is None or df.empty:
                        continue
                    # Uniformly listed in lowercase
                    dfu = df.rename(columns={
                        "Open": "open", "High": "high", "Low": "low", "Close": "close",
                        "Volume": "vol", "Amount": "amount"
                    }).copy()
                    # Calculate the derivation:pct_chg
                    if "close" in dfu.columns:
                        dfu["pct_chg"] = dfu["close"].pct_change() * 100.0

                    # Calculated only when technical indicators are required
                    if need_tech:
                        specs = [
                            IndicatorSpec("ma", {"n": 5}),
                            IndicatorSpec("ma", {"n": 10}),
                            IndicatorSpec("ma", {"n": 20}),
                            IndicatorSpec("ema", {"n": 12}),
                            IndicatorSpec("ema", {"n": 26}),
                            IndicatorSpec("macd"),
                            IndicatorSpec("rsi", {"n": 14}),
                            IndicatorSpec("boll", {"n": 20, "k": 2}),
                            IndicatorSpec("atr", {"n": 14}),
                            IndicatorSpec("kdj", {"n": 9, "m1": 3, "m2": 3}),
                        ]
                        dfc = compute_many(dfu, specs)
                    else:
                        dfc = dfu

                    last = dfc.iloc[-1]

                # Evaluation conditions (if the conditions are entirely fundamental and do not involve market/technical conditions, you can skip the K line here)
                passes = True
                if need_base:
                    passes = self._evaluate_conditions(dfc, conditions)
                elif need_fund and not need_base and not need_tech:
                    # Fundamental conditions only: Use fundamental snapshots to determine
                    snap = get_cn_fund_snapshot(code)
                    if not snap:
                        passes = False
                    else:
                        passes = self._evaluate_fund_conditions(snap, conditions)

                if passes:
                    item = {"code": code}
                    if last is not None:
                        item.update({
                            "close": self._safe_float(last.get("close")),
                            "pct_chg": self._safe_float(last.get("pct_chg")),
                            "amount": self._safe_float(last.get("amount")),
                            "ma20": self._safe_float(last.get("ma20")) if need_tech else None,
                            "rsi14": self._safe_float(last.get("rsi14")) if need_tech else None,
                            "kdj_k": self._safe_float(last.get("kdj_k")) if need_tech else None,
                            "kdj_d": self._safe_float(last.get("kdj_d")) if need_tech else None,
                            "kdj_j": self._safe_float(last.get("kdj_j")) if need_tech else None,
                            "dif": self._safe_float(last.get("dif")) if need_tech else None,
                            "dea": self._safe_float(last.get("dea")) if need_tech else None,
                            "macd_hist": self._safe_float(last.get("macd_hist")) if need_tech else None,
                        })
                    results.append(item)
            except Exception:
                continue

        total = len(results)
        # sort
        if params.order_by:
            for order in reversed(params.order_by):  # The latter has low priority
                f = order.get("field")
                d = order.get("direction", "desc").lower()
                if f in ALLOWED_FIELDS:
                    results.sort(key=lambda x: (x.get(f) is None, x.get(f)), reverse=(d == "desc"))

        # Pagination
        start = params.offset or 0
        end = start + (params.limit or 50)
        page_items = results[start:end]

        return {
            "total": total,
            "items": page_items,
        }
    def _evaluate_fund_conditions(self, snap: Dict[str, Any], node: Dict[str, Any]) -> bool:
        """Delegate fundamental condition evaluation to utils to keep service slim."""
        return _evaluate_fund_conditions_util(snap, node, FUND_FIELDS)


    def _collect_fields_from_conditions(self, node: Dict[str, Any]) -> List[str]:
        """Delegate field collection to utils."""
        return _collect_fields_from_conditions_util(node, ALLOWED_FIELDS)

    # --- Internal: DSL Assessment ---
    def _evaluate_conditions(self, df: pd.DataFrame, node: Dict[str, Any]) -> bool:
        """Delegate technical/base condition evaluation to utils."""
        return _evaluate_conditions_util(df, node, ALLOWED_FIELDS, ALLOWED_OPS)

    # --- Tools ---
    def _safe_float(self, v: Any) -> Optional[float]:
        """Delegate numeric coercion to utils."""
        return _safe_float_util(v)

    def _get_universe(self) -> List[str]:
        """Get the A-share code collection: Get all A-share stock codes from the MongoDB stock_basic_info collection"""
        try:
            from app.core.database import get_mongo_db

            db = get_mongo_db()
            collection = db.stock_basic_info

            # Query all A-share stock codes (compatible with different data structures)
            cursor = collection.find(
                {
                    "$or": [
                        {"market_info.market": "CN"},  # new data structure
                        {"category": "stock_cn"},      # old data structure
                        {"market": {"$in": ["主板", "创业板", "科创板", "北交所"]}}  # By market type
                    ]
                },
                {"code": 1, "_id": 0}
            )

            # Get all stock codes simultaneously
            codes = [doc.get("code") for doc in cursor if doc.get("code")]

            if codes:
                logger.info(f"📊 从 MongoDB 获取到 {len(codes)} 只A股股票")
                return codes
            else:
                # If the database is empty, return common stock codes as a guide
                logger.warning("⚠️ MongoDB No stock data found in, use the bottom stock list")
                return ["000001", "000002", "000858", "600519", "600036", "601318", "300750"]

        except Exception as e:
            logger.error(f"❌ Failed to get stock list from MongoDB: {e}")
            # Return common stock codes as a backup when exceptions occur
            return ["000001", "000002", "000858", "600519", "600036", "601318", "300750"]

