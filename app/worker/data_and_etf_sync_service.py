from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['etf_sync_service', 'financial_data_sync_service', 'financial_data_sync_task', 'news_data_sync_service', 'favorites_sync_task', 'watchlist_analysis_task']:
    _sys.modules[f"app.worker.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === etf_sync_service.py ===
"""
ETF Data synchronization service

Use the project s unified data source configuration (get_enabled_data_sources_async) to try synchronization in order of priority.
The one with the highest priority is called first, and ends if the synchronization is successful; if it fails, the next priority is tried.
- etf_basic_info: ETF Basic information (code, name, scale, tracking index, etc.)
- etf_daily_quotes: ETF Daily market price
"""

import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Dict, Any, List, Optional, Callable

from app.core.config import settings
from app.core.database import get_mongo_db
from app.core.data_source_priority import get_enabled_data_sources_async
from app.services.data_sources.qmt_adapter import QMTAdapter

logger = logging.getLogger(__name__)

# Collection name (consistent with design document)
ETF_BASIC_INFO_COLLECTION = "etf_basic_info"
ETF_DAILY_QUOTES_COLLECTION = "etf_daily_quotes"
DEFAULT_SOURCE_PRIORITY = ["akshare"]  # Default value when unified configuration fails to obtain
ETF_FULL_SYNC_FALLBACK_START = "19900101"

ETF_SH_PREFIXES = ("50", "51", "52", "56", "58")
ETF_SZ_PREFIXES = ("15", "16", "18")
ETF_BJ_PREFIXES = ("89",)  # North Exchange ETF prefix


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "--", "None", "nan", "NaN"}
    return False


def _coalesce(*values):
    for value in values:
        if not _is_missing(value):
            return value
    return None


def _safe_float(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace("%", "")
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_date_text(value: Any) -> Optional[str]:
    if _is_missing(value):
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 10:
        return text[:10].replace("/", "-")
    return text or None


def _calculate_nav_change(latest_unit_nav: Optional[float], previous_unit_nav: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if latest_unit_nav is None or previous_unit_nav in (None, 0):
        return None, None
    try:
        change_value = round(float(latest_unit_nav) - float(previous_unit_nav), 4)
        growth_rate = round(change_value / float(previous_unit_nav) * 100, 4)
        return change_value, growth_rate
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None


def _needs_tushare_backfill(existing: Optional[Dict[str, Any]]) -> bool:
    if not existing:
        return False
    required_fields = ("unit_nav", "accum_nav", "latest_nav_date", "fund_share", "fund_share_date")
    return any(_is_missing(existing.get(field)) for field in required_fields)


def _normalize_etf_code(s: str) -> str:
    """Standardized ETF symbols are 6 digits"""
    if not s:
        return ""
    digits = "".join(c for c in str(s) if c.isdigit())
    return digits.zfill(6)[-6:] if digits and len(digits) <= 6 else (digits[-6:] if digits else "")


def _get_full_symbol(code: str) -> str:
    """Generate complete code based on code prefix"""
    if not code or len(code) != 6:
        return ""
    if code.startswith(ETF_SH_PREFIXES):
        return f"{code}.SH"
    if code.startswith(ETF_SZ_PREFIXES):
        return f"{code}.SZ"
    if code.startswith(ETF_BJ_PREFIXES):
        return f"{code}.BJ"
    return f"{code}.SH"


def _etf_sync_service_is_etf_code(code: str) -> bool:
    return bool(code) and len(code) == 6 and code.startswith(ETF_SH_PREFIXES + ETF_SZ_PREFIXES + ETF_BJ_PREFIXES)


def _normalize_source_name(name: str) -> str:
    """Normalize data source names to lowercase (e.g. AKShare -> akshare) """
    return str(name or "").strip().lower()


def _fetch_etf_spot_list_akshare() -> List[Dict[str, Any]]:
    """Get the ETF real-time price list from AKShare (blocking call)"""
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return []

        code_col = "code" if "code" in df.columns else "Fund code"
        name_col = "Name" if "Name" in df.columns else "Fund name"

        rows = []
        for _, r in df.iterrows():
            raw_code = str(r.get(code_col, "")).strip()
            code = _normalize_etf_code(raw_code)
            if not code or len(code) != 6:
                continue
            if not _etf_sync_service_is_etf_code(code):
                continue

            full_symbol = _get_full_symbol(code)
            rows.append({
                "code": code,
                "name": str(r.get(name_col, r.get("基金名称", ""))),
                "full_symbol": full_symbol,
                "latest_price": r.get("最新价", r.get("最新-单位净值", r.get("当前-单位净值"))),
                "change_pct": r.get("涨跌幅", r.get("增长率")),
                "volume": r.get("成交量"),
                "amount": r.get("成交额"),
                "fund_scale": r.get("规模"),
                "track_index": r.get("跟踪指数", ""),
                "fund_type": r.get("基金类型", ""),
            })
        return rows
    except Exception as e:
        logger.warning(f"AKShare fund_etf_spot_em Failed to obtain: {e}")
        return []


def _fetch_etf_valuation_map_akshare() -> Dict[str, Dict[str, Any]]:
    """Obtain ETF net value, discount and premium, and redemption status mapping from AKShare."""
    try:
        import akshare as ak

        valuation_df = ak.fund_etf_fund_daily_em()
        if valuation_df is None or valuation_df.empty:
            return {}

        code_col = "Fund code" if "Fund code" in valuation_df.columns else "code"
        valuation_df["code_clean"] = valuation_df[code_col].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
        unit_nav_col = next((col for col in valuation_df.columns if str(col).endswith("net unit value")), None)
        accum_nav_col = next((col for col in valuation_df.columns if str(col).endswith("Cumulative net worth")), None)

        result: Dict[str, Dict[str, Any]] = {}
        for _, row in valuation_df.iterrows():
            code = _normalize_etf_code(row.get("code_clean"))
            if not _etf_sync_service_is_etf_code(code):
                continue
            result[code] = {
                "unit_nav": row.get(unit_nav_col) if unit_nav_col else None,
                "accum_nav": row.get(accum_nav_col) if accum_nav_col else None,
                "nav_change_value": row.get("增长值"),
                "nav_growth_rate": row.get("增长率"),
                "market_price": row.get("市价"),
                "premium_discount_rate": row.get("折价率"),
                "fund_type": row.get("类型"),
            }

        return result
    except Exception as e:
        logger.warning(f"AKShare ETF Failed to obtain valuation mapping: {e}")
        return {}


def _get_tushare_pro_api():
    """Get Tushare pro_api (reuse singleton to avoid repeated connections)"""
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
        provider = get_tushare_provider()
        if provider and provider.api:
            return provider.api
    except Exception as e:
        logger.warning(f"Tushare Connection failed: {e}")
    return None


def _fetch_etf_spot_list_tushare() -> List[Dict[str, Any]]:
    """from Tushare fund_basic(market='E') Get the ETF basic information list (blocking call)"""
    pro = _get_tushare_pro_api()
    if pro is None:
        return []
    try:
        df = pro.fund_basic(market="E", status="L")
        if df is None or df.empty:
            return []

        rows = []
        for _, r in df.iterrows():
            ts_code = str(r.get("ts_code", "")).strip()
            code = _normalize_etf_code(ts_code)
            if not code or len(code) != 6:
                continue
            if not _etf_sync_service_is_etf_code(code):
                continue

            full_symbol = ts_code if "." in ts_code else _get_full_symbol(code)
            rows.append({
                "code": code,
                "name": str(r.get("name", "")),
                "full_symbol": full_symbol,
                "latest_price": None,
                "change_pct": None,
                "volume": None,
                "amount": None,
                "fund_scale": r.get("issue_amount"),
                "track_index": str(r.get("benchmark", "") or ""),
                "fund_type": str(r.get("fund_type", "ETF") or "ETF"),
                "management": r.get("management"),
                "custodian": r.get("custodian"),
                "management_fee": r.get("m_fee"),
                "custodian_fee": r.get("c_fee"),
                "found_date": r.get("found_date"),
                "list_date": r.get("list_date"),
                "issue_date": r.get("issue_date"),
                "due_date": r.get("due_date"),
                "invest_type": r.get("invest_type"),
                "status": r.get("status"),
                "min_amount": r.get("min_amount"),
                "purchase_start_date": r.get("purc_startdate"),
                "redemption_start_date": r.get("redm_startdate"),
            })
        return rows
    except Exception as e:
        logger.warning(f"Tushare fund_basic Failed to obtain: {e}")
        return []


def _fetch_etf_nav_map_tushare(target_codes: Optional[set[str]] = None, recent_days: int = 15) -> Dict[str, Dict[str, Any]]:
    """Get the latest net worth mapping of ETFs in batches from Tushare fund_nav."""
    pro = _get_tushare_pro_api()
    if pro is None:
        return {}

    try:
        records_by_code: Dict[str, List[Dict[str, Any]]] = {}
        pending_codes = set(target_codes or [])
        end_dt = datetime.now()

        for offset in range(recent_days):
            nav_date = (end_dt - timedelta(days=offset)).strftime("%Y%m%d")
            df = pro.fund_nav(nav_date=nav_date, market="E")
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", "")).strip()
                code = _normalize_etf_code(ts_code)
                if not _etf_sync_service_is_etf_code(code):
                    continue
                if pending_codes and code not in pending_codes:
                    continue

                bucket = records_by_code.setdefault(code, [])
                if len(bucket) < 2:
                    bucket.append(row.to_dict())

            if pending_codes and all(len(records_by_code.get(code, [])) >= 2 for code in pending_codes):
                break

        result: Dict[str, Dict[str, Any]] = {}
        for code, rows in records_by_code.items():
            rows.sort(
                key=lambda item: (
                    str(item.get("nav_date") or ""),
                    str(item.get("ann_date") or "")
                ),
                reverse=True
            )
            latest = rows[0]
            previous = rows[1] if len(rows) > 1 else None

            latest_unit_nav = _safe_float(latest.get("unit_nav"))
            previous_unit_nav = _safe_float(previous.get("unit_nav")) if previous else None
            nav_change_value, nav_growth_rate = _calculate_nav_change(latest_unit_nav, previous_unit_nav)

            result[code] = {
                "unit_nav": latest_unit_nav,
                "accum_nav": _safe_float(latest.get("accum_nav")),
                "latest_nav_date": _normalize_date_text(latest.get("nav_date")),
                "latest_nav_ann_date": _normalize_date_text(latest.get("ann_date")),
                "accum_div": _safe_float(latest.get("accum_div")),
                "net_asset": _safe_float(latest.get("net_asset")),
                "total_netasset": _safe_float(latest.get("total_netasset")),
                "adj_nav": _safe_float(latest.get("adj_nav")),
                "nav_change_value": nav_change_value,
                "nav_growth_rate": nav_growth_rate,
            }

        return result
    except Exception as e:
        logger.warning(f"Tushare fund_nav Failed to obtain: {e}")
        return {}


def _fetch_etf_share_map_tushare(target_codes: Optional[set[str]] = None, recent_days: int = 30) -> Dict[str, Dict[str, Any]]:
    """Get ETF latest share mapping in bulk from Tushare fund_share."""
    pro = _get_tushare_pro_api()
    if pro is None:
        return {}

    try:
        target_codes = set(target_codes or [])
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=recent_days)
        rows: List[Dict[str, Any]] = []

        for market in ("SH", "SZ", "BJ"):
            df = pro.fund_share(
                market=market,
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d")
            )
            if df is None or df.empty:
                continue
            rows.extend(df.to_dict("records"))

        if not rows:
            return {}

        latest_by_code: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ts_code = str(row.get("ts_code", "")).strip()
            code = _normalize_etf_code(ts_code)
            if not _etf_sync_service_is_etf_code(code):
                continue
            if target_codes and code not in target_codes:
                continue

            existing = latest_by_code.get(code)
            trade_date = str(row.get("trade_date") or "")
            if not existing or trade_date > str(existing.get("trade_date") or ""):
                latest_by_code[code] = row

        return {
            code: {
                "fund_share": _safe_float(row.get("fd_share")),
                "fund_share_date": _normalize_date_text(row.get("trade_date")),
            }
            for code, row in latest_by_code.items()
        }
    except Exception as e:
        logger.warning(f"Tushare fund_share Failed to obtain: {e}")
        return {}


def _fetch_etf_hist_tushare(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Get the historical daily line of a single ETF from Tushare fund_daily (blocking call)"""
    pro = _get_tushare_pro_api()
    if pro is None:
        return []
    try:
        code = _normalize_etf_code(symbol)
        if not code:
            return []
        ts_code = _get_full_symbol(code)
        if not ts_code:
            ts_code = f"{code}.SH"

        df = pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []

        full_symbol = _get_full_symbol(code)
        records = []
        for _, r in df.iterrows():
            trade_date = r.get("trade_date")
            if trade_date is None:
                continue
            trade_date = str(trade_date)
            if len(trade_date) == 8:
                trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

            vol = r.get("vol")
            amt = r.get("amount")
            if amt is not None and amt != "":
                try:
                    amt = float(amt) * 1000
                except (TypeError, ValueError):
                    pass

            records.append({
                "symbol": code,
                "code": code,
                "full_symbol": full_symbol,
                "trade_date": trade_date,
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "close": r.get("close"),
                "volume": vol,
                "amount": amt,
                "pct_chg": r.get("pct_chg"),
                "data_source": "tushare",
            })
        return records
    except Exception as e:
        logger.warning(f"Tushare fund_daily {symbol} Failed to obtain: {e}")
        return []


def _fetch_etf_hist_akshare(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Get the historical daily line of a single ETF from AKShare (blocking call)"""
    try:
        import akshare as ak
        code = _normalize_etf_code(symbol)
        if not code:
            return []
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []

        # Column names are compatible: date/date, opening/open, closing/close, highest/high, lowest/low, trading volume/volume, trading amount/amount, price increase or decrease
        date_col = "Date" if "Date" in df.columns else "date"
        open_col = "Open" if "Open" in df.columns else "open"
        high_col = "highest" if "highest" in df.columns else "high"
        low_col = "lowest" if "lowest" in df.columns else "low"
        close_col = "close" if "close" in df.columns else "close"
        vol_col = "Volume" if "Volume" in df.columns else "volume"
        amt_col = "Turnover" if "Turnover" in df.columns else "amount"
        pct_col = "Increase or decrease" if "Increase or decrease" in df.columns else "growth rate"
        nav_col = "net unit value" if "net unit value" in df.columns else None
        accum_col = "Cumulative net worth" if "Cumulative net worth" in df.columns else None

        records = []
        full_symbol = _get_full_symbol(code)
        for _, r in df.iterrows():
            trade_date = r.get(date_col)
            if trade_date is None:
                continue
            if hasattr(trade_date, "strftime"):
                trade_date = trade_date.strftime("%Y-%m-%d")
            else:
                trade_date = str(trade_date)[:10].replace("/", "-")

            rec = {
                "symbol": code,
                "code": code,  # Consistent with stock_daily_quotes, convenient for UnifiedStockService query
                "full_symbol": full_symbol,
                "trade_date": trade_date,
                "open": r.get(open_col),
                "high": r.get(high_col),
                "low": r.get(low_col),
                "close": r.get(close_col),
                "volume": r.get(vol_col),
                "amount": r.get(amt_col),
                "pct_chg": r.get(pct_col),
                "data_source": "akshare",  # Overridden by sync method by actual source
            }
            if nav_col and nav_col in r:
                rec["unit_nav"] = r.get(nav_col)
            if accum_col and accum_col in r:
                rec["accum_nav"] = r.get(accum_col)
            records.append(rec)
        return records
    except Exception as e:
        logger.warning(f"AKShare fund_etf_hist_em {symbol} Failed to obtain: {e}")
        return []


def _fetch_etf_spot_list_qmt() -> List[Dict[str, Any]]:
    """Get underlying ETF information and near real-time snapshots from QMT"""
    try:
        adapter = QMTAdapter()
        if not adapter.is_available():
            return []

        df = adapter.get_etf_list()
        if df is None or df.empty:
            return []

        quotes = adapter.get_realtime_quotes() or {}
        rows = []
        for _, r in df.iterrows():
            code = _normalize_etf_code(r.get("code") or r.get("symbol") or "")
            if not _etf_sync_service_is_etf_code(code):
                continue
            quote = quotes.get(code, {})
            rows.append({
                "code": code,
                "name": str(r.get("name", "") or code),
                "full_symbol": str(r.get("ts_code", "") or _get_full_symbol(code)),
                "latest_price": quote.get("close"),
                "change_pct": quote.get("pct_chg"),
                "volume": None,
                "amount": quote.get("amount"),
                "fund_scale": None,
                "track_index": "",
                "fund_type": str(r.get("fund_type", "ETF") or "ETF"),
            })
        return rows
    except Exception as e:
        logger.warning(f"QMT ETF Failed to get list: {e}")
        return []


def _fetch_etf_hist_qmt(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Get the historical daily line of a single ETF from QMT"""
    try:
        adapter = QMTAdapter()
        if not adapter.is_available():
            return []

        code = _normalize_etf_code(symbol)
        if not _etf_sync_service_is_etf_code(code):
            return []

        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        limit = max((end_dt - start_dt).days + 5, 30)
        items = adapter.get_kline(code, period="day", limit=limit)
        if not items:
            return []

        records = []
        previous_close = None
        for item in items:
            trade_date = str(item.get("date") or item.get("time") or "")
            if not trade_date:
                continue
            if len(trade_date) >= 10:
                normalized_date = trade_date[:10].replace("/", "-")
            elif len(trade_date) == 8 and trade_date.isdigit():
                normalized_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            else:
                normalized_date = trade_date

            compact_date = normalized_date.replace("-", "")
            if compact_date < start_date or compact_date > end_date:
                continue

            close_value = item.get("close")
            record = {
                "symbol": code,
                "code": code,
                "full_symbol": _get_full_symbol(code),
                "trade_date": normalized_date,
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": close_value,
                "volume": item.get("volume"),
                "amount": item.get("amount"),
                "pct_chg": None,
                "data_source": "qmt",
            }

            if previous_close not in (None, 0) and close_value is not None:
                try:
                    record["pct_chg"] = round((float(close_value) - float(previous_close)) / float(previous_close) * 100, 4)
                except (TypeError, ValueError, ZeroDivisionError):
                    record["pct_chg"] = None

            previous_close = close_value if close_value is not None else previous_close
            records.append(record)
        return records
    except Exception as e:
        logger.warning(f"QMT ETF Failed to obtain historical daily line {symbol}: {e}")
        return []


# Data source and fetcher mapping (extensible to Tushare, etc.)
_FETCH_BASIC: Dict[str, Callable] = {
    "akshare": _fetch_etf_spot_list_akshare,
    "tushare": _fetch_etf_spot_list_tushare,
    "qmt": _fetch_etf_spot_list_qmt,
}
_FETCH_HIST: Dict[str, Callable[[str, str, str], List[Dict[str, Any]]]] = {
    "akshare": _fetch_etf_hist_akshare,
    "tushare": _fetch_etf_hist_tushare,
    "qmt": _fetch_etf_hist_qmt,
}


class EtfSyncService:
    """ETF Data synchronization service (try in order according to data source priority)"""

    def __init__(self):
        self.db = None
        self.batch_size = 50
        self.rate_limit_delay = 0.3
        self.item_timeout_seconds = settings.ETF_SYNC_ITEM_TIMEOUT_SECONDS

    @staticmethod
    def _find_index_name(index_info: Dict[str, Any], keys: List[tuple[str, int]]) -> Optional[str]:
        expected_keys = tuple(keys)
        for index_name, spec in index_info.items():
            if tuple(spec.get("key", [])) == expected_keys:
                return index_name
        return None

    async def _find_duplicate_key_sample(self, collection, keys: List[tuple[str, int]]) -> Optional[Dict[str, Any]]:
        group_id = {field: f"${field}" for field, _ in keys}
        duplicates = await collection.aggregate(
            [
                {"$group": {"_id": group_id, "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 1},
            ]
        ).to_list(length=1)
        return duplicates[0] if duplicates else None

    async def _ensure_unique_index(self, collection, collection_name: str, keys: List[tuple[str, int]]) -> None:
        index_info = await collection.index_information()
        index_name = self._find_index_name(index_info, keys)

        if index_name and index_info[index_name].get("unique"):
            return

        duplicate_sample = await self._find_duplicate_key_sample(collection, keys)
        if duplicate_sample:
            logger.warning(
                f"⚠️ {collection_name} Duplicate data exists and the unique index cannot be upgraded temporarily.: "
                f"keys={list(duplicate_sample.get('_id', {}).items())}, count={duplicate_sample.get('count')}"
            )
            return

        if index_name:
            await collection.drop_index(index_name)
            logger.info(
                f"🧹 Removed {collection_name} The old non-unique index is ready to be upgraded to a unique index: {index_name}"
            )

        await collection.create_index(keys, unique=True, background=True)
        logger.info(f"✅ secured {collection_name} unique index: {keys}")

    async def _ensure_indexes(self):
        """Ensure ETF fundamentals and daily aggregation have key indexes."""
        try:
            if self.db is None:
                self.db = get_mongo_db()

            basic_collection = self.db[ETF_BASIC_INFO_COLLECTION]
            daily_collection = self.db[ETF_DAILY_QUOTES_COLLECTION]

            logger.info("📊 Check and create ETF collection index...")

            await self._ensure_unique_index(
                basic_collection,
                ETF_BASIC_INFO_COLLECTION,
                [("code", 1), ("source", 1)],
            )
            await basic_collection.create_index([("code", 1)], background=True)

            await self._ensure_unique_index(
                daily_collection,
                ETF_DAILY_QUOTES_COLLECTION,
                [("code", 1), ("trade_date", -1)],
            )
            await daily_collection.create_index([("symbol", 1), ("trade_date", -1)], background=True)

            logger.info("✅ ETF Collection index check completed")
        except Exception as e:
            logger.warning(f"⚠️ ETF Collection index check/creation failed (without blocking the main process): {e}")

    @staticmethod
    def _calculate_stage_progress(stage_start: int, stage_end: int, processed_items: int, total_items: int) -> int:
        """Calculate the overall progress according to stage intervals to ensure that the progress increases monotonically."""
        stage_start = max(0, min(100, stage_start))
        stage_end = max(stage_start, min(100, stage_end))
        if total_items <= 0:
            return stage_start

        ratio = min(max(processed_items / total_items, 0.0), 1.0)
        return int(round(stage_start + (stage_end - stage_start) * ratio))

    async def _report_job_progress(
        self,
        job_id: Optional[str],
        progress: int,
        message: str,
        *,
        current_item: Optional[str] = None,
        total_items: Optional[int] = None,
        processed_items: Optional[int] = None,
    ) -> None:
        """Write back the progress to the scheduling execution history for the front end to display the progress/current operation/remaining time."""
        if not job_id:
            return

        try:
            from app.services.scheduler_service import TaskCancelledException, update_job_progress

            await update_job_progress(
                job_id=job_id,
                progress=max(0, min(100, progress)),
                message=message,
                current_item=current_item,
                total_items=total_items,
                processed_items=processed_items,
            )
        except TaskCancelledException:
            raise
        except Exception as e:
            logger.debug(f"ETF Synchronization progress writeback failed (does not affect the main process): {e}")

    @staticmethod
    def _build_sync_result(basic_stats: Dict[str, Any], daily_stats: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Flatten ETF phased results and be compatible with scheduler completion statistics."""
        daily_total = int(daily_stats.get("total_processed") or 0)
        basic_total = int(basic_stats.get("total_processed") or 0)
        total_processed = daily_total or basic_total

        if daily_total > 0:
            error_count = int(daily_stats.get("error_count") or 0)
        else:
            error_count = int(basic_stats.get("error_count") or 0)

        success_count = max(total_processed - error_count, 0)

        errors = list(basic_stats.get("errors") or []) + list(daily_stats.get("errors") or [])

        return {
            "basic_info": basic_stats,
            "daily_quotes": daily_stats,
            "data_source_used": source,
            "total_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "skipped_count": int(basic_stats.get("skipped_count") or 0),
            "records_inserted": int(daily_stats.get("records_inserted") or 0),
            "errors": errors,
        }

    @staticmethod
    def _to_compact_date(value: Any) -> Optional[str]:
        normalized = _normalize_date_text(value)
        if not normalized:
            return None
        try:
            return datetime.strptime(normalized, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return None

    @staticmethod
    def _get_initial_full_sync_date(basic_doc: Optional[Dict[str, Any]]) -> Optional[str]:
        if not basic_doc:
            return None

        for field in ("list_date", "found_date", "issue_date"):
            compact_date = EtfSyncService._to_compact_date(basic_doc.get(field))
            if compact_date:
                return compact_date

        return None

    async def _resolve_daily_sync_window(
        self,
        code: str,
        source: str,
        fallback_days: int,
        force_update: bool,
        *,
        basic_doc: Optional[Dict[str, Any]] = None,
        smart_incremental: bool = False,
    ) -> tuple[str, str, str]:
        """Determine the ETF daily synchronization window: the first full amount, and subsequent increments based on the latest date in the library."""
        end_dt = datetime.now()
        end_date = end_dt.strftime("%Y%m%d")

        if force_update or not smart_incremental:
            start_dt = end_dt - timedelta(days=fallback_days)
            return start_dt.strftime("%Y%m%d"), end_date, f"Sync recent by specified window {fallback_days} day"

        collection = self.db[ETF_DAILY_QUOTES_COLLECTION]
        latest_doc = await collection.find_one(
            {"symbol": code},
            {"trade_date": 1, "_id": 0},
            sort=[("trade_date", -1)]
        )
        latest_trade_date = _normalize_date_text((latest_doc or {}).get("trade_date"))
        if latest_trade_date:
            try:
                next_dt = datetime.strptime(latest_trade_date, "%Y-%m-%d") + timedelta(days=1)
                return next_dt.strftime("%Y%m%d"), end_date, f"Incremental completion (latest entry into database {latest_trade_date}) "
            except ValueError:
                logger.debug(f"ETF {code} The latest trade_date parsing failed and fell back to the full starting point.: {latest_trade_date}")

        initial_start_date = self._get_initial_full_sync_date(basic_doc)

        if not initial_start_date and basic_doc is None:
            basic_doc = await self.db[ETF_BASIC_INFO_COLLECTION].find_one(
                {"code": code, "source": source},
                {"list_date": 1, "found_date": 1, "issue_date": 1, "_id": 0}
            )
            initial_start_date = self._get_initial_full_sync_date(basic_doc)

        if not initial_start_date:
            basic_doc = await self.db[ETF_BASIC_INFO_COLLECTION].find_one(
                {"code": code},
                {"list_date": 1, "found_date": 1, "issue_date": 1, "_id": 0}
            )
            initial_start_date = self._get_initial_full_sync_date(basic_doc)

        if initial_start_date:
            return initial_start_date, end_date, f"First full amount (from {initial_start_date[:4]}-{initial_start_date[4:6]}-{initial_start_date[6:8]} start)"

        return ETF_FULL_SYNC_FALLBACK_START, end_date, "Full volume for the first time (lacking the launch date, using the full historical starting point)"

    async def initialize(self):
        """Initialize database connection"""
        self.db = get_mongo_db()
        await self._ensure_indexes()
        logger.info("✅ ETF Synchronization service initialization completed")

    async def _get_source_priority(self) -> List[str]:
        """Use the unified data source configuration of the project (a_shares, ETF and A-shares are in the same market), exclude local and return according to priority"""
        try:
            enabled = await get_enabled_data_sources_async("a_shares")
            # Exclude local (local is the reading library, synchronization requires calling external API)
            raw = [s for s in enabled if s and s.lower() != "local"]
            # Only keep ETF-synced data sources and normalize to lowercase
            priority = [_normalize_source_name(p) for p in raw if _normalize_source_name(p) in _FETCH_BASIC]
            if priority:
                logger.info(f"📊 [ETF sync] Data source priority (unified configuration): {priority}")
                return priority
        except Exception as e:
            logger.warning(f"⚠️ [ETF sync] Failed to obtain unified data source configuration: {e}")
        logger.info(f"📊 [ETF sync] Use default data source: {DEFAULT_SOURCE_PRIORITY}")
        return DEFAULT_SOURCE_PRIORITY

    async def _sync_basic_by_source(
        self,
        source: str,
        force_update: bool,
        symbols: Optional[List[str]] = None,
        job_id: Optional[str] = None,
        stage_start: int = 5,
        stage_end: int = 45,
    ) -> Dict[str, Any]:
        """Synchronize ETF basic information according to specified data source"""
        if self.db is None:
            await self.initialize()
        fetch_fn = _FETCH_BASIC.get(source)
        if not fetch_fn:
            return {"total_processed": 0, "success_count": 0, "error_count": 1, "errors": [{"error": f"Unimplemented data source: {source}"}]}

        stats = {"total_processed": 0, "success_count": 0, "error_count": 0, "skipped_count": 0, "start_time": datetime.utcnow(), "end_time": None, "duration": 0, "errors": [], "data_source": source}

        try:
            loop = asyncio.get_running_loop()
            rows = await loop.run_in_executor(None, fetch_fn)
            if symbols:
                normalized_symbols = {_normalize_etf_code(symbol) for symbol in symbols if _normalize_etf_code(symbol)}
                rows = [row for row in rows if row.get("code") in normalized_symbols]
            valuation_map = {}
            share_map = {}
            if source == "akshare":
                valuation_map = await loop.run_in_executor(None, _fetch_etf_valuation_map_akshare)
            elif source == "tushare":
                target_codes = {row["code"] for row in rows if row.get("code")}
                valuation_map = await loop.run_in_executor(None, partial(_fetch_etf_nav_map_tushare, target_codes, 15))
                share_map = await loop.run_in_executor(None, partial(_fetch_etf_share_map_tushare, target_codes, 30))
            if not rows:
                await self._report_job_progress(
                    job_id,
                    stage_start,
                    f"ETF basic information was not obtained ({source.upper()}) , Try other data sources",
                    current_item=source.upper(),
                )
                logger.warning(f"⚠️ [{source}] No ETF list obtained")
                return stats

            stats["total_processed"] = len(rows)
            logger.info(f"📊 [{source}] Get {len(rows)} Only ETF basic information")
            await self._report_job_progress(
                job_id,
                stage_start,
                f"Synchronizing ETF basic information ({source.upper()}) ",
                total_items=len(rows),
                processed_items=0,
            )

            collection = self.db[ETF_BASIC_INFO_COLLECTION]
            now = datetime.utcnow()

            for index, r in enumerate(rows, start=1):
                try:
                    code = r["code"]
                    existing = None
                    skip_item = False
                    if not force_update:
                        existing = await collection.find_one({"code": code, "source": source})
                        if existing and self._is_fresh(existing.get("updated_at"), hours=24):
                            if source == "tushare" and _needs_tushare_backfill(existing):
                                logger.info(f"🔄 [{source}] ETF {code} The basic information is newer but the net worth/share field is missing, so backfill is performed.")
                            else:
                                stats["skipped_count"] += 1
                                skip_item = True

                    if not skip_item:
                        valuation = valuation_map.get(code, {})
                        share_info = share_map.get(code, {})
                        existing_doc = existing or {}

                        doc = {
                            "code": code,
                            "symbol": code,
                            "name": r.get("name", ""),
                            "full_symbol": r.get("full_symbol", _get_full_symbol(code)),
                            "fund_type": _coalesce(r.get("fund_type"), valuation.get("fund_type"), "ETF"),
                            "fund_scale": r.get("fund_scale"),
                            "track_index": r.get("track_index", ""),
                            "management": r.get("management"),
                            "custodian": r.get("custodian"),
                            "management_fee": r.get("management_fee"),
                            "custodian_fee": r.get("custodian_fee"),
                            "found_date": r.get("found_date"),
                            "list_date": r.get("list_date"),
                            "issue_date": r.get("issue_date"),
                            "due_date": r.get("due_date"),
                            "invest_type": r.get("invest_type"),
                            "status": r.get("status"),
                            "min_amount": r.get("min_amount"),
                            "purchase_start_date": r.get("purchase_start_date"),
                            "redemption_start_date": r.get("redemption_start_date"),
                            "unit_nav": _coalesce(valuation.get("unit_nav"), existing_doc.get("unit_nav")),
                            "accum_nav": _coalesce(valuation.get("accum_nav"), existing_doc.get("accum_nav")),
                            "nav_change_value": _coalesce(valuation.get("nav_change_value"), existing_doc.get("nav_change_value")),
                            "nav_growth_rate": _coalesce(valuation.get("nav_growth_rate"), existing_doc.get("nav_growth_rate")),
                            "market_price": _coalesce(valuation.get("market_price"), existing_doc.get("market_price")),
                            "premium_discount_rate": _coalesce(valuation.get("premium_discount_rate"), existing_doc.get("premium_discount_rate")),
                            "latest_nav_date": _coalesce(valuation.get("latest_nav_date"), existing_doc.get("latest_nav_date")),
                            "latest_nav_ann_date": _coalesce(valuation.get("latest_nav_ann_date"), existing_doc.get("latest_nav_ann_date")),
                            "accum_div": _coalesce(valuation.get("accum_div"), existing_doc.get("accum_div")),
                            "net_asset": _coalesce(valuation.get("net_asset"), existing_doc.get("net_asset")),
                            "total_netasset": _coalesce(valuation.get("total_netasset"), existing_doc.get("total_netasset")),
                            "adj_nav": _coalesce(valuation.get("adj_nav"), existing_doc.get("adj_nav")),
                            "fund_share": _coalesce(share_info.get("fund_share"), existing_doc.get("fund_share")),
                            "fund_share_date": _coalesce(share_info.get("fund_share_date"), existing_doc.get("fund_share_date")),
                            "purchase_status": _coalesce(valuation.get("purchase_status"), existing_doc.get("purchase_status")),
                            "redemption_status": _coalesce(valuation.get("redemption_status"), existing_doc.get("redemption_status")),
                            "source": source,
                            "updated_at": now,
                        }
                        await collection.update_one({"code": code, "source": source}, {"$set": doc}, upsert=True)
                        stats["success_count"] += 1
                except Exception as e:
                    stats["error_count"] += 1
                    stats["errors"].append({"code": r.get("code", "?"), "error": str(e)})

                if index == 1 or index == len(rows) or index % 10 == 0:
                    current_code = r.get("code", "?")
                    current_name = str(r.get("name") or "").strip()
                    current_item = f"{current_code} {current_name}".strip()
                    await self._report_job_progress(
                        job_id,
                        self._calculate_stage_progress(stage_start, stage_end, index, len(rows)),
                        f"Synchronizing ETF basic information ({source.upper()}) ",
                        current_item=current_item,
                        total_items=len(rows),
                        processed_items=index,
                    )
                await asyncio.sleep(self.rate_limit_delay / 10)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            logger.info(f"🎉 [{source}] ETF Basic information synchronization completed: success {stats['success_count']}, skip {stats['skipped_count']}, Error {stats['error_count']}")
        except Exception as e:
            from app.services.scheduler_service import TaskCancelledException

            if isinstance(e, TaskCancelledException):
                raise
            logger.error(f"❌ [{source}] ETF Basic information synchronization failed: {e}", exc_info=True)
            stats["errors"].append({"error": str(e), "context": "sync_etf_basic_info"})

        return stats

    async def _sync_daily_by_source(
        self,
        source: str,
        symbols: Optional[List[str]],
        days: int,
        force_update: bool,
        job_id: Optional[str] = None,
        stage_start: int = 50,
        stage_end: int = 95,
        smart_incremental: bool = False,
    ) -> Dict[str, Any]:
        """Synchronize ETF daily lines according to specified data source"""
        if self.db is None:
            await self.initialize()
        fetch_fn = _FETCH_HIST.get(source)
        if not fetch_fn:
            return {"total_processed": 0, "success_count": 0, "records_inserted": 0, "errors": [{"error": f"Unimplemented data source: {source}"}]}

        stats = {"total_processed": 0, "success_count": 0, "error_count": 0, "records_inserted": 0, "start_time": datetime.utcnow(), "end_time": None, "duration": 0, "errors": [], "data_source": source}

        try:
            if symbols:
                code_entries = []
                for symbol in symbols:
                    normalized = _normalize_etf_code(symbol)
                    if normalized:
                        code_entries.append({"code": normalized})
            else:
                cursor = self.db[ETF_BASIC_INFO_COLLECTION].find(
                    {"source": source},
                    {"code": 1, "name": 1, "list_date": 1, "found_date": 1, "issue_date": 1, "_id": 0}
                )
                code_entries = [d async for d in cursor if d.get("code")]

            if not code_entries:
                await self._report_job_progress(
                    job_id,
                    stage_start,
                    f"No syncable ETF daily ticker found ({source.upper()}) ",
                    current_item=source.upper(),
                )
                logger.warning(f"⚠️ [{source}] No ETF ticker to sync")
                return stats

            stats["total_processed"] = len(code_entries)
            if smart_incremental and not force_update:
                sync_scope_message = "Full quantity for the first time, subsequent increments based on the latest storage date"
            else:
                sync_scope_message = f"Sync recent by specified window {days} day"

            logger.info(f"📊 [{source}] Start syncing {len(code_entries)} Only daily data for ETFs ({sync_scope_message}) ")
            await self._report_job_progress(
                job_id,
                stage_start,
                f"Synchronizing ETF daily line ({source.upper()}) ",
                total_items=len(code_entries),
                processed_items=0,
            )

            collection = self.db[ETF_DAILY_QUOTES_COLLECTION]
            loop = asyncio.get_running_loop()

            for i, code_entry in enumerate(code_entries, start=1):
                code = code_entry["code"]
                current_name = str(code_entry.get("name") or "").strip()
                try:
                    start_date, end_date, sync_window_desc = await self._resolve_daily_sync_window(
                        code,
                        source,
                        days,
                        force_update,
                        basic_doc=code_entry,
                        smart_incremental=smart_incremental,
                    )

                    fetch_started_at = loop.time()
                    if start_date > end_date:
                        logger.info(
                            f"🌐 [{source}] Skip web scraping: code={code}, name={current_name or '-'}, "
                            f"reason=Sync window is empty, start_date={start_date}, end_date={end_date}"
                        )
                        records = []
                    else:
                        logger.info(
                            f"🌐 [{source}] Start grabbing ETF daily lines: code={code}, name={current_name or '-'}, "
                            f"start_date={start_date}, end_date={end_date}"
                        )
                        records = await asyncio.wait_for(
                            loop.run_in_executor(None, partial(fetch_fn, code, start_date, end_date)),
                            timeout=self.item_timeout_seconds,
                        )
                        fetch_elapsed = loop.time() - fetch_started_at
                        logger.info(
                            f"🌐 [{source}] Fetching completed: code={code}, records={len(records)}, "
                            f"elapsed={fetch_elapsed:.2f}s"
                        )
                    if not records:
                        inserted = 0
                        logger.info(
                            f"💾 [{source}] Skip database writes: code={code}, name={current_name or '-'}, records=0"
                        )
                    else:
                        from pymongo import UpdateOne

                        written_count = 0
                        updated_count = 0
                        skipped_existing = 0
                        write_started_at = loop.time()
                        write_timestamp = datetime.utcnow()
                        logger.info(
                            f"💾 [{source}] Start writing ETF daily line: code={code}, name={current_name or '-'}, "
                            f"records={len(records)}, force_update={force_update}"
                        )

                        existing_trade_dates = set()
                        existing_query_code = records[0].get("code") or code
                        record_trade_dates = [rec.get("trade_date") for rec in records if rec.get("trade_date") is not None]
                        if record_trade_dates:
                            existing_cursor = collection.find(
                                {"code": existing_query_code, "trade_date": {"$in": record_trade_dates}},
                                {"trade_date": 1, "_id": 0},
                            )
                            async for existing_doc in existing_cursor:
                                existing_trade_dates.add(existing_doc.get("trade_date"))

                        known_trade_dates = set(existing_trade_dates)
                        bulk_operations = []
                        bulk_batch_size = 200

                        for rec in records:
                            rec["data_source"] = source
                            record_code = rec.get("code") or rec.get("symbol") or code
                            rec["code"] = record_code
                            trade_date = rec.get("trade_date")
                            key = {"code": record_code, "trade_date": trade_date}
                            record_exists = trade_date in known_trade_dates

                            if not force_update and record_exists:
                                skipped_existing += 1
                                logger.info(
                                    f"💾 [{source}] Skip existing daily lines: code={record_code}, "
                                    f"trade_date={trade_date}, action=skip_existing"
                                )
                                continue

                            known_trade_dates.add(trade_date)
                            bulk_operations.append(
                                UpdateOne(
                                    key,
                                    {"$set": {**rec, "updated_at": write_timestamp}},
                                    upsert=True,
                                )
                            )

                            action = "updated" if record_exists else "inserted"
                            if action == "updated":
                                updated_count += 1
                            written_count += 1
                            logger.info(
                                f"💾 [{source}] Write daily record: code={record_code}, "
                                f"trade_date={trade_date}, action={action}"
                            )

                            if len(bulk_operations) >= bulk_batch_size:
                                await collection.bulk_write(bulk_operations, ordered=False)
                                bulk_operations = []

                        if bulk_operations:
                            await collection.bulk_write(bulk_operations, ordered=False)

                        write_elapsed = loop.time() - write_started_at
                        logger.info(
                            f"💾 [{source}] Writing completed: code={code}, inserted={written_count}, "
                            f"updated={updated_count}, skipped_existing={skipped_existing}, elapsed={write_elapsed:.2f}s"
                        )

                        stats["records_inserted"] += written_count

                    stats["success_count"] += 1

                    if i % 20 == 0:
                        logger.info(f"📈 [{source}] ETF Daily synchronization progress: {i}/{len(code_entries)}")
                except asyncio.TimeoutError:
                    stats["error_count"] += 1
                    timeout_message = f"Fetch timeout (>{self.item_timeout_seconds}s) "
                    stats["errors"].append({"code": code, "error": timeout_message})
                    sync_window_desc = timeout_message
                    logger.warning(
                        f"⏰ [{source}] ETF Daily crawl timeout: code={code}, "
                        f"timeout={self.item_timeout_seconds}s, start_date={start_date}, end_date={end_date}"
                    )
                except Exception as e:
                    stats["error_count"] += 1
                    stats["errors"].append({"code": code, "error": str(e)})
                    sync_window_desc = "Sync failed"

                if i == 1 or i == len(code_entries) or i % 10 == 0:
                    current_item = f"{code} {current_name}".strip()
                    if sync_window_desc:
                        current_item = f"{current_item} | {sync_window_desc}" if current_item else sync_window_desc
                    await self._report_job_progress(
                        job_id,
                        self._calculate_stage_progress(stage_start, stage_end, i, len(code_entries)),
                        f"Synchronizing ETF daily line ({source.upper()}) ",
                        current_item=current_item,
                        total_items=len(code_entries),
                        processed_items=i,
                    )

                await asyncio.sleep(self.rate_limit_delay)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            logger.info(f"🎉 [{source}] ETF Daily synchronization completed: {stats['success_count']}/{len(code_entries)} only, Insert {stats['records_inserted']} Article")
        except Exception as e:
            from app.services.scheduler_service import TaskCancelledException

            if isinstance(e, TaskCancelledException):
                raise
            logger.error(f"❌ [{source}] ETF Daily synchronization failed: {e}", exc_info=True)
            stats["errors"].append({"error": str(e), "context": "sync_etf_daily_quotes"})

        return stats

    async def sync_all(self, force_update: bool = False, days: int = 30, job_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Full synchronization: Try in order according to the priority of the data source. The one with the highest priority is called first. If the synchronization is successful, it will end. If it fails, the next priority will be tried.
        """
        if self.db is None:
            await self.initialize()

        priority = await self._get_source_priority()
        valid_sources = [source for source in priority if source in _FETCH_BASIC]
        last_error = None

        await self._report_job_progress(job_id, 1, "Start syncing ETF data...")

        if not valid_sources:
            return {
                "basic_info": {"total_processed": 0, "errors": [{"error": "No available ETF data source found"}]},
                "daily_quotes": {"records_inserted": 0, "total_processed": 0},
                "data_source_used": None,
                "total_processed": 0,
                "success_count": 0,
                "error_count": 1,
                "errors": [{"error": "No available ETF data source found"}],
            }

        total_sources = len(valid_sources)

        for index, source in enumerate(valid_sources):
            slot_start = 5 + int(90 * index / total_sources)
            slot_end = 5 + int(90 * (index + 1) / total_sources)
            slot_end = max(slot_start + 1, min(95, slot_end))
            basic_end = min(slot_end - 1, slot_start + max(1, int((slot_end - slot_start) * 0.45)))
            daily_start = min(slot_end, basic_end + 1)

            logger.info(f"🔄 [ETF sync] try data source: {source}")
            await self._report_job_progress(
                job_id,
                slot_start,
                f"Prepare to sync ETF data ({source.upper()}) ",
                current_item=source.upper(),
            )

            try:
                from app.services.scheduler_service import TaskCancelledException

                basic_stats = await self._sync_basic_by_source(
                    source,
                    force_update,
                    job_id=job_id,
                    stage_start=slot_start,
                    stage_end=basic_end,
                )

                # Basic information synchronization is successful: just get the data (total_processed > 0) 
                if basic_stats.get("total_processed", 0) > 0:
                    # Once the current data source gets the ETF list, the current task will directly use the data source to complete daily synchronization and return.
                    # Subsequent data sources will not be tried again; therefore, the daily phase should cover the completion interval of all tasks, rather than staying at the upper limit of the current slot.
                    daily_stats = await self._sync_daily_by_source(
                        source,
                        None,
                        days,
                        force_update,
                        job_id=job_id,
                        stage_start=daily_start,
                        stage_end=95,
                        smart_incremental=True,
                    )
                    result = self._build_sync_result(basic_stats, daily_stats, source)
                    await self._report_job_progress(
                        job_id,
                        99,
                        f"ETF Data synchronization is about to be completed ({source.upper()}) ",
                        current_item=source.upper(),
                        total_items=result.get("total_processed") or None,
                        processed_items=result.get("total_processed") or None,
                    )
                    logger.info(f"✅ [ETF sync] data source {source} Synchronization completed")
                    return result
                else:
                    last_error = basic_stats.get("errors", [{"error": "No ETF list obtained"}])
                    await self._report_job_progress(
                        job_id,
                        slot_end,
                        f"data source {source.upper()} No ETF data was obtained, try the next data source",
                        current_item=source.upper(),
                    )
                    logger.warning(f"⚠️ [ETF sync] data source {source} No data was obtained, try the next priority")
            except TaskCancelledException:
                raise
            except Exception as e:
                last_error = str(e)
                await self._report_job_progress(
                    job_id,
                    slot_end,
                    f"data source {source.upper()} Failed, try next data source",
                    current_item=source.upper(),
                )
                logger.warning(f"⚠️ [ETF sync] data source {source} failed: {e}, Try next priority")

        logger.error(f"❌ [ETF sync] All data sources fail with the final error: {last_error}")
        return {
            "basic_info": {"total_processed": 0, "errors": [{"error": str(last_error)}]},
            "daily_quotes": {"records_inserted": 0},
            "data_source_used": None,
            "total_processed": 0,
            "success_count": 0,
            "error_count": 1,
            "errors": [{"error": str(last_error)}],
        }

    async def sync_symbols(
        self,
        symbols: List[str],
        force_update: bool = False,
        days: int = 30,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronize fundamental information and daily data by specified ETF code."""
        if self.db is None:
            await self.initialize()

        normalized_symbols = sorted(
            {
                normalized
                for normalized in (_normalize_etf_code(symbol) for symbol in (symbols or []))
                if _etf_sync_service_is_etf_code(normalized)
            }
        )

        if not normalized_symbols:
            return {
                "basic_info": {"total_processed": 0, "errors": [{"error": "No valid ETF code provided"}]},
                "daily_quotes": {"records_inserted": 0, "total_processed": 0},
                "data_source_used": None,
                "total_processed": 0,
                "success_count": 0,
                "error_count": 1,
                "errors": [{"error": "No valid ETF code provided"}],
                "requested_symbols": [],
            }

        priority = await self._get_source_priority()
        valid_sources = [source for source in priority if source in _FETCH_BASIC]
        last_error = None

        await self._report_job_progress(
            job_id,
            1,
            "Start synchronizing specified ETF data...",
            total_items=len(normalized_symbols),
            processed_items=0,
        )

        if not valid_sources:
            return {
                "basic_info": {"total_processed": 0, "errors": [{"error": "No available ETF data source found"}]},
                "daily_quotes": {"records_inserted": 0, "total_processed": 0},
                "data_source_used": None,
                "total_processed": 0,
                "success_count": 0,
                "error_count": 1,
                "errors": [{"error": "No available ETF data source found"}],
                "requested_symbols": normalized_symbols,
            }

        for source in valid_sources:
            logger.info(f"🔄 [ETF sync] Try to specify code synchronization, data source: {source}, Quantity: {len(normalized_symbols)}")
            await self._report_job_progress(
                job_id,
                5,
                f"Prepare to synchronize specified ETF data ({source.upper()}) ",
                current_item=source.upper(),
                total_items=len(normalized_symbols),
                processed_items=0,
            )

            try:
                basic_stats = await self._sync_basic_by_source(
                    source,
                    force_update,
                    symbols=normalized_symbols,
                    job_id=job_id,
                    stage_start=5,
                    stage_end=45,
                )

                if basic_stats.get("total_processed", 0) > 0:
                    daily_stats = await self._sync_daily_by_source(
                        source,
                        normalized_symbols,
                        days,
                        force_update,
                        job_id=job_id,
                        stage_start=50,
                        stage_end=95,
                        smart_incremental=True,
                    )
                    result = self._build_sync_result(basic_stats, daily_stats, source)
                    result["requested_symbols"] = normalized_symbols
                    return result

                last_error = basic_stats.get("errors", [{"error": "No ETF list obtained"}])
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ [ETF sync] Synchronization failed for specified ETF: source={source}, error={e}")

        logger.error(f"❌ [ETF sync] Specified ETF synchronization failed with final error: {last_error}")
        return {
            "basic_info": {"total_processed": 0, "errors": [{"error": str(last_error)}]},
            "daily_quotes": {"records_inserted": 0, "total_processed": 0},
            "data_source_used": None,
            "total_processed": 0,
            "success_count": 0,
            "error_count": 1,
            "errors": [{"error": str(last_error)}],
            "requested_symbols": normalized_symbols,
        }

    def _is_fresh(self, updated_at: Any, hours: int = 24) -> bool:
        """Check if the data has been updated within the specified hour"""
        if not updated_at:
            return False
        try:
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated_at.tzinfo:
                updated_at = updated_at.replace(tzinfo=None)
            return (datetime.utcnow() - updated_at).total_seconds() < hours * 3600
        except Exception:
            return False


_etf_sync_service: Optional[EtfSyncService] = None


async def get_etf_sync_service() -> EtfSyncService:
    """Get ETF synchronization service singleton"""
    global _etf_sync_service
    if _etf_sync_service is None:
        _etf_sync_service = EtfSyncService()
        await _etf_sync_service.initialize()
    return _etf_sync_service


async def run_etf_sync(force_update: bool = False, days: int = 30, job_id: str = None) -> Dict[str, Any]:
    """Run ETF full volume synchronization (for APScheduler or API call)"""
    try:
        service = await get_etf_sync_service()
        result = await service.sync_all(force_update=force_update, days=days, job_id=job_id)
        if job_id:
            try:
                from app.services.scheduler_service import mark_job_completed
                await mark_job_completed(job_id, result)
            except Exception:
                pass
        return result
    except Exception as e:
        from app.services.scheduler_service import TaskCancelledException

        if isinstance(e, TaskCancelledException):
            logger.info("ℹ️ ETF The synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        logger.error(f"❌ ETF Sync failed: {e}", exc_info=True)
        if job_id:
            try:
                from app.services.scheduler_service import mark_job_completed
                await mark_job_completed(job_id, {}, str(e))
            except Exception:
                pass
        raise

# === financial_data_sync_service.py ===
#!/usr/bin/env python3
"""
Financial data synchronization service
Unified management of financial data synchronization from three data sources
"""
import asyncio
import logging
import time
import threading
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.core.database import create_isolated_async_mongo_binding, get_mongo_db
from app.services.financial_data_service import get_financial_data_service
from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
from tradingagents.dataflows.providers.china.baostock import get_baostock_provider

logger = logging.getLogger(__name__)


@dataclass
class FinancialSyncStats:
    """Financial data synchronization statistics"""
    total_symbols: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_symbols": self.total_symbols,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "success_rate": round(self.success_count / max(self.total_symbols, 1) * 100, 2),
            "errors": self.errors[:10]  # Only return the first 10 errors
        }


class FinancialDataSyncService:
    """Financial data synchronization service"""
    
    def __init__(self):
        self.db = None
        self.financial_service = None
        self.providers = {}
        
    async def initialize(self):
        """Initialize service"""
        try:
            self.db = get_mongo_db()
            self.financial_service = await get_financial_data_service()
            
            # Initialize data source provider
            self.providers = {
                "tushare": get_tushare_provider(),
                "akshare": get_akshare_provider(),
                "baostock": get_baostock_provider()
            }
            
            logger.info("✅ Financial data synchronization service initialization successful")
            
        except Exception as e:
            logger.error(f"❌ Financial data synchronization service initialization failed: {e}")
            raise
    
    async def sync_financial_data(
        self,
        symbols: List[str] = None,
        data_sources: List[str] = None,
        report_types: List[str] = None,
        batch_size: int = 50,
        delay_seconds: float = 1.0,
        job_id: str = None,
        rate_limit_per_minute: int = 80,  # 🔥 Rate Limit: Maximum number of calls per minute
        _resume_from_index: int = None  # 🔥 Resume execution: from which position to continue (number of stocks processed)
    ) -> Dict[str, FinancialSyncStats]:
        """
        Synchronize financial data (using thread pool)
        
        Args:
            symbols: Stock code list, None means synchronize all stocks
            data_sources: Data source list ["tushare", "akshare", "baostock"]
            report_types: List of report types ["quarterly", "annual"]
            batch_size: Batch size (deprecated for compatibility)
            delay_seconds: API Call deferral (deprecated, retaining compatibility)
            job_id: Task ID, used for progress tracking
            
        Returns:
            Synchronized statistical results of each data source
        """
        if self.db is None:
            await self.initialize()
        
        # Default parameters
        if data_sources is None:
            data_sources = ["tushare", "akshare", "baostock"]
        if report_types is None:
            report_types = ["quarterly", "annual"]
        
        logger.info(f"🔄 Start financial data synchronization (thread pool mode): data source={data_sources}, Report type filter={report_types}")
        
        # Get a list of stocks
        if symbols is None:
            symbols = await self._get_stock_symbols()
        
        if not symbols:
            logger.warning("⚠️ No stocks found to sync")
            return {}
        
        logger.info(f"📊 Prepare to sync {len(symbols)} Financial data for only stocks")
        
        # Perform synchronization for each data source
        results = {}
        
        # 🔥 Process each data source in parallel using a unified thread pool service
        # Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        tasks = []
        for data_source in data_sources:
            if data_source not in self.providers:
                logger.warning(f"⚠️ Unsupported data source: {data_source}")
                continue
            
            # 🔥 Create concurrent tasks: Use the unified thread pool service to perform synchronization of each data source
            # 🔥 Use the original job_id instead of the modified job_id so that progress updates will be updated to the correct execution record
            data_source_job_id = job_id if job_id else f"financial_{data_source}"
            
            # 🔥 Create wrapper method with data source as closure variable (use default parameters to ensure proper capture)
            def create_sync_wrapper(ds, syms, rpts, jid, rate_limit):
                """Create wrapper methods to ensure variables are captured correctly"""
                async def sync_data_source_wrapper(**kwargs):
                    """Wrapper method for unifying thread pool service calls"""
                    return await self._sync_source_financial_data_serial_async(
                        data_source=ds,
                        symbols=syms,
                        report_types=rpts,
                        job_id=jid,
                        rate_limit_per_minute=rate_limit,
                        resume_from_index=kwargs.get("resume_from_index")
                    )
                return sync_data_source_wrapper
            
            sync_data_source_wrapper = create_sync_wrapper(
                data_source, symbols, report_types, data_source_job_id, rate_limit_per_minute
            )
            
            # 🔥 Execute using unified thread pool service
            task = unified_service.execute_sync_method(
                sync_method=sync_data_source_wrapper,
                method_kwargs={},
                job_id=data_source_job_id,
                rate_limit_per_minute=rate_limit_per_minute,
                resume_from_index=_resume_from_index
            )
            tasks.append((data_source, task))
        
        # Execute synchronization tasks for all data sources in parallel
        if tasks:
            logger.info(f"🚀 Start parallel synchronization {len(tasks)} financial data from data sources: {[ds for ds, _ in tasks]}")
            
            # Parallel execution using asyncio.gather
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True
            )
            
            # Processing results
            for i, ((data_source, _), task_result) in enumerate(zip(tasks, task_results)):
                if isinstance(task_result, Exception):
                    logger.error(f"❌ {data_source} Financial data synchronization failed: {task_result}", exc_info=True)
                    # Creation of statistics failed
                    failed_stats = FinancialSyncStats()
                    failed_stats.total_symbols = len(symbols) if symbols else 0
                    failed_stats.error_count = failed_stats.total_symbols
                    failed_stats.errors.append({
                        "error": str(task_result),
                        "data_source": data_source
                    })
                    results[data_source] = failed_stats
                elif not task_result.success:
                    # Unified service returns failure result
                    logger.error(f"❌ {data_source} Financial data synchronization failed: {task_result.error}")
                    failed_stats = FinancialSyncStats()
                    failed_stats.total_symbols = len(symbols) if symbols else 0
                    failed_stats.error_count = failed_stats.total_symbols
                    failed_stats.errors.append({
                        "error": task_result.error or "unknown error",
                        "data_source": data_source
                    })
                    results[data_source] = failed_stats
                else:
                    # success
                    result = task_result.result
                    results[data_source] = result
                    logger.info(f"✅ {data_source} Financial data synchronization completed: "
                               f"success {result.success_count}/{result.total_symbols} "
                               f"({result.success_count/max(result.total_symbols,1)*100:.1f}%)")
        else:
            logger.warning("⚠️ No data source available for financial data synchronization")
        
        return results
    
    async def _sync_source_financial_data_serial_async(
        self,
        data_source: str,
        symbols: List[str],
        report_types: List[str],
        job_id: str,
        rate_limit_per_minute: int,
        resume_from_index: int = None  # 🔥 Resume execution: where to continue from
    ) -> FinancialSyncStats:
        """
        Serial synchronization of financial data from a single data source (asynchronous version, runs in a thread of the thread pool)
        """
        provider = self.providers[data_source]
        
        # Check data source availability
        if not provider.is_available():
            logger.warning(f"⚠️ {data_source} Data source is not available")
            stats = FinancialSyncStats()
            stats.total_symbols = len(symbols)
            stats.skipped_count = len(symbols)
            return stats
        
        # Calculate latency (make sure you don't exceed the rate limit)
        # For example: 80 times/minute = 60/80 = 0.75 seconds/times
        delay_between_calls = 60.0 / rate_limit_per_minute if rate_limit_per_minute > 0 else 0.5
        
        # 🔥 Save the original stock total (used for progress calculations)
        original_total_symbols = len(symbols)
        
        # 🔥 If a restore location is specified, skip processed stocks
        start_index = resume_from_index if resume_from_index is not None and resume_from_index > 0 else 0
        if start_index > 0:
            logger.info(f"🔄 [{data_source}] Resume execution: from section {start_index} stocks start (processed {start_index}/{original_total_symbols}) ")
            # Skip processed stocks
            symbols = symbols[start_index:]
            if not symbols:
                logger.warning(f"⚠️ [{data_source}] All stocks have been processed, no need to continue synchronization")
                stats = FinancialSyncStats()
                stats.total_symbols = original_total_symbols
                stats.success_count = start_index
                return stats
        
        logger.info(f"🔧 [{data_source}] Serial sync configuration: Number of shares remaining={len(symbols)}, Total number of shares={original_total_symbols}, "
                   f"rate limit={rate_limit_per_minute}times/minute, "
                   f"delay={delay_between_calls:.2f}seconds/request, "
                   f"starting position={start_index}")
        
        # Initialize statistics
        stats = FinancialSyncStats()
        stats.total_symbols = original_total_symbols  # 🔥 Total number of shares (including processed)
        stats.start_time = datetime.now(timezone.utc)
        
        # 🔥 Create a new service instance in a thread in the thread pool (to avoid event loop conflicts)
        # Create an independent asynchronous database connection using the current thread's event loop
        from app.services.financial_data_service import FinancialDataService

        mongo_client, mongo_db = create_isolated_async_mongo_binding()
        
        # Create a new service instance, using the database connection of the current thread's event loop
        financial_service = FinancialDataService()
        financial_service.db = mongo_db
        
        # Make sure the index exists (asynchronously, executed in the event loop of the current thread)
        try:
            collection = financial_service.db[financial_service.collection_name]
            # Create index (asynchronous operation)
            await collection.create_indexes([
                # Composite unique index
                [("symbol", 1), ("report_period", 1), ("data_source", 1)],
                # Other indexes
                [("symbol", 1)],
                [("report_period", -1)],
                [("data_source", 1)]
            ])
        except Exception as e:
            logger.debug(f"Index creation check: {e}")  # Index may already exist, ignore error
        
        # Process each stock serially
        processed_count = start_index  # 🔥 Count from recovery position
        try:
            for i, symbol in enumerate(symbols):
                # 🔥 Check if the task should be stopped (by querying the database)
                try:
                    # 🔥 Check if the task was canceled (checked at the beginning of each loop)
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected, task canceled, sync stopped (job_id={job_id})")
                        # Update progress to current progress
                        try:
                            from app.services.scheduler_service import update_job_progress, TaskCancelledException
                            # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                            total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                            progress_int = int((processed_count / total_items) * 100) if total_items > 0 else 0
                            progress_int = min(progress_int, 100)
                            await update_job_progress(
                                job_id=job_id,
                                progress=progress_int,
                                current_item=f"[{data_source}] {symbol}",
                                total_items=total_items,
                                processed_items=processed_count,
                                message=f"[{data_source}] The task has been canceled by the user"
                            )
                        except TaskCancelledException:
                            # If update_job_progress also detects cancellation, exit directly
                            logger.warning(f"🛑 [{data_source}] update_job_progress Cancellation request also detected, stop immediately")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Update progress failed: {e}")
                        break

                    # 🔥 Rate limiting: wait before calling API (cancellation is also checked during wait)
                    if delay_between_calls > 0:
                        # Wait in segments, checking cancellation status every 0.5 seconds
                        wait_time = 0
                        check_interval = 0.5
                        while wait_time < delay_between_calls:
                            await asyncio.sleep(min(check_interval, delay_between_calls - wait_time))
                            wait_time += check_interval
                            # Check cancellation status
                            should_stop = await self._should_stop_sync(job_id)
                            if should_stop:
                                logger.warning(f"🛑 [{data_source}] Cancellation request detected while waiting, sync stopped (job_id={job_id})")
                                # Update progress and exit the loop
                                try:
                                    from app.services.scheduler_service import update_job_progress
                                    # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                                    total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                                    progress_int = int((processed_count / total_items) * 100) if total_items > 0 else 0
                                    progress_int = min(progress_int, 100)
                                    await update_job_progress(
                                        job_id=job_id,
                                        progress=progress_int,
                                        current_item=f"[{data_source}] {symbol}",
                                        total_items=total_items,
                                        processed_items=processed_count,
                                        message=f"[{data_source}] The task has been canceled by the user"
                                    )
                                except Exception as e:
                                    logger.warning(f"⚠️ Update progress failed: {e}")
                                break

                    # 🔥 Before syncing stock data, check again for cancellation flag (prevents receiving cancellation request during sync)
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected before sync, sync stopped (job_id={job_id})")
                        break

                    # Synchronize financial data for individual stocks
                    success = await self._sync_symbol_financial_data_async(
                        symbol=symbol,
                        data_source=data_source,
                        provider=provider,
                        report_types=report_types,
                        financial_service=financial_service
                    )

                    if success:
                        stats.success_count += 1
                    else:
                        stats.skipped_count += 1

                    processed_count += 1

                    # 🔥 After the sync is complete, check again for the cancellation flag
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected after sync, sync stopped (job_id={job_id})")
                        break

                    # 🔥 Update progress every time 1 stock is processed or completed (more frequent updates)
                    # Calculate progress percentage: ensure that even small progress is displayed correctly (at least 1% is displayed)
                    # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                    total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                    if total_items > 0:
                        progress_float = (processed_count / total_items) * 100
                        # 🔥 If the progress is greater than 0 but less than 1%, display at least 1% to avoid displaying 0%
                        if progress_float > 0 and progress_float < 1:
                            progress_int = 1
                        else:
                            progress_int = int(round(progress_float))
                        # Make sure not to exceed 100%
                        progress_int = min(progress_int, 100)
                    else:
                        progress_int = 0

                    # update_job_progress is an independent asynchronous function
                    try:
                        from app.services.scheduler_service import update_job_progress, TaskCancelledException
                        # 🔥 Logging progress update calls (for debugging)
                        logger.debug(f"📊 [{data_source}] Prepare to update progress: job_id={job_id}, progress={progress_int}%, "
                                   f"processed={processed_count}/{total_items}, current_item={symbol}")

                        await update_job_progress(
                            job_id=job_id,
                            progress=progress_int,  # Use whole number percentages
                            current_item=f"[{data_source}] {symbol}",  # 🔥 Mark the data source in current_item
                            total_items=total_items,  # 🔥 Use the total number of shares (including those processed)
                            processed_items=processed_count,
                            message=f"[{data_source}] Synchronizing: {symbol} ({processed_count}/{total_items})"  # 🔥 Mark the data source and total number of stocks in the message
                        )

                        # 🔥 Record detailed logs every 10 stocks to avoid excessive logs
                        if processed_count % 10 == 0 or (i + 1) == len(symbols):
                            logger.info(f"📊 [{data_source}] Progress updated successfully: {processed_count}/{total_items} "
                                       f"({progress_int}%), success={stats.success_count}, skip={stats.skipped_count}")
                    except TaskCancelledException as cancel_error:
                        # 🔥 If a cancellation request is received, stop the task immediately
                        logger.warning(f"🛑 [{data_source}] Received cancellation request (via update_job_progress), stopped synchronization: {cancel_error}")
                        # 🔥 Set a flag to ensure the loop exits
                        should_stop = True
                        # 🔥 Break out of the loop immediately
                        break
                    except Exception as progress_error:
                        # 🔥 Check if it is a cancellation related exception (maybe other forms of cancellation exception)
                        error_msg = str(progress_error)
                        error_type = type(progress_error).__name__
                        logger.warning(f"🔍 [{data_source}] Progress update exception type: {error_type}, news: {error_msg}")

                        error_lower = error_msg.lower()
                        if "Cancel" in error_lower or "cancel" in error_lower or "cancelled" in error_lower or "TaskCancelledException" in error_type:
                            logger.warning(f"🛑 [{data_source}] A cancellation-related exception was detected during progress update and synchronization was stopped.: {progress_error}")
                            break
                        # 🔥 Failure in progress update should not affect the main process, but needs to be logged
                        logger.error(f"❌ [{data_source}] Progress update failed: job_id={job_id}, error={progress_error}", exc_info=True)
                        # Log errors every 10 stocks to avoid excessive logs
                        if processed_count % 10 == 0:
                            logger.warning(f"⚠️ [{data_source}] Progress update fails, but execution continues: {progress_error}")

                except Exception as e:
                    # 🔥 Check if it is a cancellation related exception
                    error_msg = str(e)
                    error_type = type(e).__name__
                    error_lower = error_msg.lower()

                    # 🔥 Check if it is TaskCancelledException or its subclass
                    from app.services.scheduler_service import TaskCancelledException
                    if isinstance(e, TaskCancelledException):
                        logger.warning(f"🛑 [{data_source}] TaskCancelledException detected, synchronization stopped: {error_msg}")
                        break

                    # 🔥 Check whether the exception type name or message contains cancellation-related keywords
                    if "Cancel" in error_lower or "cancel" in error_lower or "cancelled" in error_lower or "TaskCancelledException" in error_type:
                        logger.warning(f"🛑 [{data_source}] Cancellation related exception detected, synchronization stopped: Type={error_type}, news={error_msg}")
                        break

                    stats.error_count += 1
                    stats.errors.append({
                        "symbol": symbol,
                        "error": error_msg,
                        "data_source": data_source
                    })
                    logger.error(f"❌ [{data_source}] {symbol} Financial data synchronization failed: {error_msg}")
                    processed_count += 1
        finally:
            try:
                mongo_client.close()
            except Exception as close_error:
                logger.warning(f"⚠️ [{data_source}] Failed to close in-thread MongoDB client: {close_error}")
        
        # 🔥 Check if the task is stopped due to cancellation
        was_cancelled = False
        try:
            should_stop = await self._should_stop_sync(job_id)
            if should_stop:
                was_cancelled = True
                logger.warning(f"🛑 [{data_source}] The task is stopped due to cancellation and the status will be updated to cancelled (job_id={job_id})")
        except Exception as e:
            logger.warning(f"⚠️ [{data_source}] Checking cancellation status failed: {e}")
        
        # Complete statistics
        stats.end_time = datetime.now(timezone.utc)
        stats.duration = (stats.end_time - stats.start_time).total_seconds()
        
        # 🔥 If the task is canceled, the updated status is cancelled
        if was_cancelled:
            try:
                # Use a synchronous way to update the state (because in the thread pool thread, the event loop may be closed)
                from pymongo import MongoClient
                from app.core.config import settings
                sync_client = MongoClient(settings.MONGO_URI)
                sync_db = sync_client[settings.MONGODB_DATABASE]
                try:
                    # Extract original job_id
                    original_job_id = job_id
                    for ds in ["tushare", "akshare", "baostock"]:
                        if job_id.endswith(f"_{ds}"):
                            original_job_id = job_id[:-len(f"_{ds}")]
                            break
                    
                    # Update all related execution records to canceled status
                    update_result = sync_db.scheduler_executions.update_many(
                        {
                            "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                            "status": "running"
                        },
                        {
                            "$set": {
                                "status": "cancelled",
                                "error_message": f"[{data_source}] The task has been canceled by the user",
                                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
                            }
                        }
                    )
                    logger.info(f"✅ [{data_source}] updated {update_result.modified_count} The execution record status is cancelled (job_id={job_id})")
                    
                    # 🔥 Also update the status in the Redis cache
                    try:
                        from app.core.redis_client import RedisKeys
                        from app.core.database import get_redis_sync_client
                        import json
                        redis_sync_client = get_redis_sync_client()
                        if redis_sync_client:
                            progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=original_job_id)
                            # Get current progress data
                            progress_data_str = redis_sync_client.get(progress_key)
                            if progress_data_str:
                                progress_data = json.loads(progress_data_str)
                                progress_data["status"] = "cancelled"
                                progress_data["message"] = f"[{data_source}] The task has been canceled by the user"
                                redis_sync_client.setex(
                                    progress_key,
                                    86400,  # 24 hour expires
                                    json.dumps(progress_data, ensure_ascii=False)
                                )
                                logger.info(f"✅ [{data_source}] The updated Redis cache status is cancelled")
                    except Exception as redis_error:
                        logger.warning(f"⚠️ [{data_source}] Failed to update Redis cache: {redis_error}")
                finally:
                    sync_client.close()
            except Exception as e:
                logger.error(f"❌ [{data_source}] Failed to update task status to canceled: {e}", exc_info=True)
        
        logger.info(f"✅ [{data_source}] Financial data synchronization completed: "
                   f"success={stats.success_count}, failed={stats.error_count}, "
                   f"skip={stats.skipped_count}, Time consuming={stats.duration:.2f}seconds, "
                   f"Cancel={was_cancelled}")
        
        return stats
    
    async def _should_stop_sync(self, job_id: str) -> bool:
        """
        Check if the task should be stopped
        
        Args:
            job_id: Task ID (may be a modified job_id, such as tushare_financial_sync_tushare)
            
        Returns:
            If the task should be stopped, return True
        """
        try:
            # 🔥 Extract the original job_id (if the job_id is tushare_financial_sync_tushare, the original is tushare_financial_sync)
            # Check if job_id ends with data source name (tushare, akshare, baostock)
            original_job_id = job_id
            for data_source in ["tushare", "akshare", "baostock"]:
                if job_id.endswith(f"_{data_source}"):
                    original_job_id = job_id[:-len(f"_{data_source}")]
                    break
            
            # 🔥 Use synchronous MongoDB client queries (to avoid event loop conflicts)
            from pymongo import MongoClient
            from app.core.config import settings
            
            def query_execution():
                sync_client = MongoClient(settings.MONGO_URI)
                sync_db = sync_client[settings.MONGODB_DATABASE]
                try:
                    # 🔥 Only query the currently running tasks (running status), do not query old records in suspended status
                    # Because the suspended record may be an old task that was canceled before, it should not affect the new task
                    query = {
                        "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                        "status": "running"  # 🔥 Only query the running status and ignore the suspended status
                    }
                    execution = sync_db.scheduler_executions.find_one(
                        query,
                        sort=[("started_at", -1)]
                    )
                    
                    # 🔥 If an execution record is found, check whether it is the execution record of the current task.
                    # By checking the timestamp, if the execution record was created within the last minute, it is considered to be the current task.
                    if execution:
                        from datetime import datetime, timedelta
                        execution_time = execution.get("started_at") or execution.get("timestamp") or execution.get("scheduled_time")
                        if execution_time:
                            # If it is a datetime object, compare directly; if it is a string, it needs to be converted
                            if isinstance(execution_time, str):
                                try:
                                    execution_time = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
                                except Exception:
                                    execution_time = None
                            
                            if execution_time:
                                time_diff = (datetime.now() - execution_time.replace(tzinfo=None)).total_seconds()
                                # If the execution record exceeds 5 minutes, it is considered an old task and the cancellation mark is not checked.
                                if time_diff > 300:  # 5 minutes
                                    logger.debug(f"🔍 The execution record is too old ({time_diff:.0f}seconds ago), ignoring unmark checks")
                                    return None
                    
                    return execution
                finally:
                    sync_client.close()
            
            # 🔥 Execute synchronous query using current event loop
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    execution = await loop.run_in_executor(None, query_execution)
                else:
                    # If the event loop is closed, use synchronous query directly
                    execution = query_execution()
            except RuntimeError:
                # No event loop, use synchronous query directly
                execution = query_execution()
            
            if execution:
                execution_id = str(execution.get("_id", ""))
                execution_job_id = execution.get("job_id", "")
                cancel_requested = execution.get("cancel_requested", False)
                execution_status = execution.get("status", "")
                
                # 🔥 INFO level logs are only output when cancellation or exception status is detected, and DEBUG level is used for normal checks.
                if cancel_requested or execution_status in ["failed", "cancelled"]:
                    logger.info(f"🔍 Check task status: job_id={job_id}, original_job_id={original_job_id}, "
                               f"record found: execution_id={execution_id}, execution_job_id={execution_job_id}, "
                               f"cancel_requested={cancel_requested}, status={execution_status}")
                else:
                    # Use DEBUG level during normal inspection to reduce log output
                    logger.debug(f"🔍 Check task status: job_id={job_id}, original_job_id={original_job_id}, "
                               f"record found: execution_id={execution_id}, execution_job_id={execution_job_id}, "
                               f"cancel_requested={cancel_requested}, status={execution_status}")
                
                # Check if canceled
                if cancel_requested:
                    logger.warning(f"🛑 Cancellation request detected: job_id={job_id}, original_job_id={original_job_id}, "
                                 f"execution_id={execution_id}, execution_job_id={execution_job_id}")
                    return True
                
                # Check if status is failed or canceled
                if execution_status in ["failed", "cancelled"]:
                    logger.warning(f"🛑 The detected task status is {execution_status}: job_id={job_id}, "
                                 f"original_job_id={original_job_id}, execution_job_id={execution_job_id}")
                    return True
            else:
                # 🔥 If no execution record is found, log
                logger.debug(f"⚠️ Execution record not found: job_id={job_id}, original_job_id={original_job_id}")
            
            return False
        except RuntimeError as e:
            # 🔥 Catching event loop related errors
            if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                logger.warning(f"⚠️ Event loop closed, task status check skipped: {job_id}")
                return False
            logger.error(f"❌ Checking task status failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Checking task status failed: {e}")
            return False
    
    async def _sync_symbol_financial_data_async(
        self,
        symbol: str,
        data_source: str,
        provider: Any,
        report_types: List[str],
        financial_service: Any
    ) -> bool:
        """
        Synchronize financial data for a single stock (asynchronous version)
        """
        try:
            # 🔥 Check if the event loop has been closed
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    logger.warning(f"⚠️ {symbol} Event loop is closed, unable to get financial data ({data_source})")
                    return False
            except RuntimeError:
                logger.warning(f"⚠️ {symbol} Unable to obtain event loop, may be closed ({data_source})")
                return False
            
            # Get financial data
            financial_data = await provider.get_financial_data(symbol)
            
            if not financial_data:
                logger.debug(f"⚠️ {symbol} No financial data ({data_source})")
                return False
            
            saved_count = 0
            try:
                saved_count = await financial_service.save_financial_data(
                    symbol=symbol,
                    financial_data=financial_data,
                    data_source=data_source,
                )
            except RuntimeError as e:
                # 🔥 Catching event loop shutdown errors
                if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                    logger.warning(f"⚠️ {symbol} Event loop closed while saving financial data ({data_source}): {e}")
                    return False
                raise
            
            return saved_count > 0
            
        except RuntimeError as e:
            # 🔥 Catching event loop related errors
            if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                logger.warning(f"⚠️ {symbol} Event loop closed while synchronizing financial data ({data_source}): {e}")
                return False
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
        except Exception as e:
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
    
    async def _sync_source_financial_data(
        self,
        data_source: str,
        symbols: List[str],
        report_types: List[str],
        batch_size: int,
        delay_seconds: float
    ) -> FinancialSyncStats:
        """Synchronize financial data from a single data source"""
        stats = FinancialSyncStats()
        stats.total_symbols = len(symbols)
        stats.start_time = datetime.now(timezone.utc)
        
        provider = self.providers[data_source]
        
        # Check data source availability
        if not provider.is_available():
            logger.warning(f"⚠️ {data_source} Data source is not available")
            stats.skipped_count = len(symbols)
            stats.end_time = datetime.now(timezone.utc)
            return stats
        
        # Process stocks in batches
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            
            logger.info(f"📈 {data_source} process batch {i//batch_size + 1}: "
                       f"{len(batch_symbols)} only stocks")
            
            # Concurrent processing of stocks within batches
            tasks = []
            for symbol in batch_symbols:
                task = self._sync_symbol_financial_data(
                    symbol=symbol,
                    data_source=data_source,
                    provider=provider,
                    report_types=report_types
                )
                tasks.append(task)
            
            # Execute concurrent tasks
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Statistics batch results
            for j, result in enumerate(batch_results):
                symbol = batch_symbols[j]
                
                if isinstance(result, Exception):
                    stats.error_count += 1
                    stats.errors.append({
                        "symbol": symbol,
                        "data_source": data_source,
                        "error": str(result),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    logger.error(f"❌ {symbol} Financial data synchronization failed ({data_source}): {result}")
                elif result:
                    stats.success_count += 1
                    logger.debug(f"✅ {symbol} Financial data synchronization successful ({data_source})")
                else:
                    stats.skipped_count += 1
                    logger.debug(f"⏭️ {symbol} Financial data skipped ({data_source})")
            
            # API Current limiting delay
            if i + batch_size < len(symbols):
                await asyncio.sleep(delay_seconds)
        
        stats.end_time = datetime.now(timezone.utc)
        stats.duration = (stats.end_time - stats.start_time).total_seconds()
        
        return stats
    
    async def _sync_symbol_financial_data(
        self,
        symbol: str,
        data_source: str,
        provider: Any,
        report_types: List[str]
    ) -> bool:
        """Synchronize financial data for individual stocks"""
        try:
            # Get financial data
            financial_data = await provider.get_financial_data(symbol)
            
            if not financial_data:
                logger.debug(f"⚠️ {symbol} No financial data ({data_source})")
                return False
            
            saved_count = await self.financial_service.save_financial_data(
                symbol=symbol,
                financial_data=financial_data,
                data_source=data_source,
            )
            
            return saved_count > 0
            
        except Exception as e:
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
    
    async def _get_stock_symbols(self) -> List[str]:
        """Get a list of stock symbols (remove duplicates)"""
        try:
            # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
            # Because the same stock may come from multiple data sources (tushare, akshare, baostock), there will be duplicate records
            pipeline = [
                {
                    "$match": {
                        "$or": [
                            {"market_info.market": "CN"},  # new data structure
                            {"category": "stock_cn"},      # old data structure
                            {"market": {"$in": ["motherboard", "GEM", "Science and Technology Innovation Board", "Beijing Exchange"]}}  # By market type
                        ]
                    }
                },
                {
                    "$group": {
                        "_id": "$code"  # Group by stock code to remove duplicates
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "code": "$_id"
                    }
                }
            ]
            cursor = self.db.stock_basic_info.aggregate(pipeline)
            symbols = [doc["code"] async for doc in cursor]
            logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stock codes (duplication removed)")

            return symbols

        except Exception as e:
            logger.error(f"❌ Failed to get list of stock symbols: {e}")
            return []
    
    async def get_sync_statistics(self) -> Dict[str, Any]:
        """Get sync statistics"""
        try:
            if self.financial_service is None:
                await self.initialize()
            
            return await self.financial_service.get_financial_statistics()
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain synchronization statistics: {e}")
            return {}
    
    async def sync_single_stock(
        self,
        symbol: str,
        data_sources: List[str] = None
    ) -> Dict[str, bool]:
        """Synchronize financial data for individual stocks"""
        if self.db is None:
            await self.initialize()
        
        if data_sources is None:
            data_sources = ["tushare", "akshare", "baostock"]
        
        results = {}
        
        for data_source in data_sources:
            if data_source not in self.providers:
                results[data_source] = False
                continue
            
            try:
                provider = self.providers[data_source]
                
                if not provider.is_available():
                    results[data_source] = False
                    continue
                
                result = await self._sync_symbol_financial_data(
                    symbol=symbol,
                    data_source=data_source,
                    provider=provider,
                    report_types=["quarterly"]
                )
                
                results[data_source] = result
                
            except Exception as e:
                logger.error(f"❌ {symbol} Single stock financial data synchronization failed ({data_source}): {e}")
                results[data_source] = False
        
        return results


# Global service instance
_financial_sync_service = None


async def get_financial_sync_service() -> FinancialDataSyncService:
    """Obtain financial data synchronization service instance"""
    global _financial_sync_service
    if _financial_sync_service is None:
        _financial_sync_service = FinancialDataSyncService()
        await _financial_sync_service.initialize()
    return _financial_sync_service

# === financial_data_sync_task.py ===
#!/usr/bin/env python3
"""
Financial data synchronization task (scheduler entrance)

Use a unified financial data synchronization service to support thread pool parallel processing
"""
import logging
from typing import Dict, Any
from app.services.scheduler_service import mark_job_completed, TaskCancelledException

logger = logging.getLogger(__name__)


async def run_financial_data_sync(**kwargs):
    """
    APScheduler Task: Unified financial data synchronization (using thread pool)
    
    Supports parallel synchronization of multiple data sources and uses thread pools to achieve true parallel processing
    """
    job_id = kwargs.get("job_id", "financial_data_sync")
    
    logger.info(f"🚀 [Financial data synchronization] Start task (job_id={job_id})")
    
    # 🔥 Ordinary manual triggering also needs to check whether there are any unfinished tasks, and it will only be skipped if it is forced to execute.
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    
    if not force_execute:
        # 🔥 Check whether there is already an instance running (normal manual triggering also checks)
        from app.worker.tushare_sync_service import _check_task_running
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if force_execute:
            logger.info("🔧 [APScheduler] Force execution, skip concurrency checks")
    
    try:
        # Get a unified financial data synchronization service
        service = await get_financial_sync_service()
        
        # Get parameters from kwargs
        data_sources = kwargs.get("data_sources", ["tushare", "akshare", "baostock"])
        report_types = kwargs.get("report_types", ["quarterly", "annual"])
        symbols = kwargs.get("symbols", None)  # None Indicates synchronization of all stocks
        
        # Perform synchronization (using thread pool)
        results = await service.sync_financial_data(
            symbols=symbols,
            data_sources=data_sources,
            report_types=report_types,
            job_id=job_id
        )
        
        # Statistics overall results
        total_success = sum(stats.success_count for stats in results.values())
        total_symbols = sum(stats.total_symbols for stats in results.values())
        total_errors = sum(stats.error_count for stats in results.values())
        
        # Mark task complete
        try:
            stats_dict = {
                "total_processed": total_symbols,
                "success_count": total_success,
                "error_count": total_errors,
                "errors": []
            }
            
            # Collect all errors
            for source, stats in results.items():
                if stats.errors:
                    stats_dict["errors"].extend([
                        {"data_source": source, **error} 
                        for error in stats.errors[:5]  # Maximum 5 errors per data source
                    ])
            
            await mark_job_completed(job_id, stats_dict)
        except Exception as e:
            logger.warning(f"⚠️ Failed to update task completion status: {e}")
        
        logger.info(f"✅ [Financial data synchronization] Mission accomplished: job_id={job_id}, "
                   f"success={total_success}/{total_symbols}, failed={total_errors}")
        
        return {
            "success": True,
            "job_id": job_id,
            "total_symbols": total_symbols,
            "success_count": total_success,
            "error_count": total_errors,
            "results": {source: stats.to_dict() for source, stats in results.items()}
        }
        
    except TaskCancelledException:
        logger.info(f"ℹ️ [Financial data synchronization] The task has been canceled by the user: job_id={job_id}")
        return {"cancelled": True, "message": "The task has been canceled by the user"}
    except Exception as e:
        logger.error(f"❌ [Financial data synchronization] Task failed: job_id={job_id}, error={e}", exc_info=True)
        
        # Mark task as failed
        try:
            await mark_job_completed(
                job_id=job_id,
                error_message=f"Financial data synchronization failed: {str(e)}"
            )
        except Exception as mark_error:
            logger.warning(f"⚠️ Mark task failed status failed: {mark_error}")
        
        raise

# === news_data_sync_service.py ===
"""
News data synchronization service
Support news data synchronization and sentiment analysis from multiple data sources
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from app.services.news_data_service import get_news_data_service
from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
from tradingagents.dataflows.news.realtime_news import RealtimeNewsAggregator

logger = logging.getLogger(__name__)


@dataclass
class NewsSyncStats:
    """News synchronization statistics"""
    total_processed: int = 0
    successful_saves: int = 0
    failed_saves: int = 0
    duplicate_skipped: int = 0
    sources_used: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        """Synchronization time (seconds)"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """success rate"""
        if self.total_processed == 0:
            return 0.0
        return (self.successful_saves / self.total_processed) * 100


class NewsDataSyncService:
    """News data synchronization service"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._news_service = None
        self._tushare_provider = None
        self._akshare_provider = None
        self._realtime_aggregator = None
    
    async def _get_news_service(self):
        """Get news data service"""
        if self._news_service is None:
            self._news_service = await get_news_data_service()
        return self._news_service
    
    async def _get_tushare_provider(self):
        """Get Tushare Provider"""
        if self._tushare_provider is None:
            self._tushare_provider = get_tushare_provider()
            await self._tushare_provider.connect()
        return self._tushare_provider
    
    async def _get_tushare_provider(self):
        """Get Tushare Provider"""
        if self._tushare_provider is None:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            self._tushare_provider = get_tushare_provider()
            await self._tushare_provider.connect()
        return self._tushare_provider

    async def _get_akshare_provider(self):
        """Get AKShare provider"""
        if self._akshare_provider is None:
            self._akshare_provider = get_akshare_provider()
            await self._akshare_provider.connect()
        return self._akshare_provider
    
    async def _get_realtime_aggregator(self):
        """Get real-time news aggregator"""
        if self._realtime_aggregator is None:
            self._realtime_aggregator = RealtimeNewsAggregator()
        return self._realtime_aggregator
    
    async def sync_stock_news(
        self,
        symbol: str,
        data_sources: List[str] = None,
        hours_back: int = 24,
        max_news_per_source: int = 50
    ) -> NewsSyncStats:
        """
        Synchronize news data of a single stock
        
        Args:
            symbol: Stock code
            data_sources: List of data sources, all available sources are used by default
            hours_back: Lookback hours
            max_news_per_source: Maximum number of news per data source
            
        Returns:
            Sync statistics
        """
        stats = NewsSyncStats()
        
        try:
            self.logger.info(f"📰 Start syncing stock news: {symbol}")
            
            if data_sources is None:
                data_sources = ["tushare", "akshare", "realtime"]
            
            news_service = await self._get_news_service()
            all_news = []
            
            # 🔥 Optimization: Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
            # The same data source is still serial internally (to avoid API current limiting)
            import asyncio
            
            tasks = []
            task_sources = []
            
            # Create concurrent tasks
            if "tushare" in data_sources:
                task = self._sync_tushare_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("tushare")
            
            if "akshare" in data_sources:
                task = self._sync_akshare_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("akshare")
            
            if "realtime" in data_sources:
                task = self._sync_realtime_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("realtime")
            
            # Execute news synchronization tasks for all data sources in parallel
            if tasks:
                self.logger.info(f"🚀 Start parallel synchronization {len(tasks)} News from data sources: {task_sources}")
                
                # Parallel execution using asyncio.gather
                news_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Processing results
                for i, (source, news_result) in enumerate(zip(task_sources, news_results)):
                    if isinstance(news_result, Exception):
                        self.logger.error(f"❌ {source} Failed to get news: {news_result}")
                    elif news_result:
                        all_news.extend(news_result)
                        stats.sources_used.append(source)
                        self.logger.info(f"✅ {source} News obtained successfully: {len(news_result)}Article")
            else:
                self.logger.warning("⚠️ No data source available for news synchronization")
            
            # Save news data
            if all_news:
                stats.total_processed = len(all_news)
                
                # Deduplication
                unique_news = self._deduplicate_news(all_news)
                stats.duplicate_skipped = len(all_news) - len(unique_news)
                
                # Save in batches
                saved_count = await news_service.save_news_data(
                    unique_news, "multi_source", "CN"
                )
                stats.successful_saves = saved_count
                stats.failed_saves = len(unique_news) - saved_count
                
                self.logger.info(f"💾 {symbol} News synchronization completed: {saved_count}Article saved successfully")
            
            stats.end_time = datetime.utcnow()
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Failed to sync stock news {symbol}: {e}")
            stats.end_time = datetime.utcnow()
            return stats
    
    async def _sync_tushare_news(
        self,
        symbol: str,
        hours_back: int,
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync Tushare news"""
        try:
            provider = await self._get_tushare_provider()

            if not provider.is_available():
                self.logger.warning("⚠️ Tushare Provider is unavailable")
                return []

            # Get news data and pass hours_back parameter
            news_data = await provider.get_stock_news(
                symbol=symbol,
                limit=max_news,
                hours_back=hours_back
            )

            if news_data:
                # Standardized news data
                standardized_news = []
                for news in news_data:
                    standardized = self._standardize_tushare_news(news, symbol)
                    if standardized:
                        standardized_news.append(standardized)

                self.logger.info(f"✅ Tushare News obtained successfully: {len(standardized_news)}Article")
                return standardized_news
            else:
                self.logger.debug("⚠️ Tushare No news data returned")
                return []

        except Exception as e:
            # Detailed error handling
            if any(keyword in str(e).lower() for keyword in ['Permissions', 'permission', 'unauthorized']):
                self.logger.warning(f"⚠️ Tushare The news interface requires separate permissions.: {e}")
            elif "Points" in str(e) or "point" in str(e).lower():
                self.logger.warning(f"⚠️ Tushare Not enough points: {e}")
            else:
                self.logger.error(f"❌ Tushare News sync failed: {e}")
            return []
    
    async def _sync_akshare_news(
        self, 
        symbol: str, 
        hours_back: int, 
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync AKShare News"""
        try:
            provider = await self._get_akshare_provider()
            
            if not provider.is_available():
                return []
            
            # Get news data
            news_data = await provider.get_stock_news(symbol, limit=max_news)
            
            if news_data:
                # Standardized news data
                standardized_news = []
                for news in news_data:
                    standardized = self._standardize_akshare_news(news, symbol)
                    if standardized:
                        standardized_news.append(standardized)
                
                return standardized_news
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ AKShare News sync failed: {e}")
            return []
    
    async def _sync_realtime_news(
        self, 
        symbol: str, 
        hours_back: int, 
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync real-time news"""
        try:
            aggregator = await self._get_realtime_aggregator()
            
            # Get real-time news
            news_items = aggregator.get_realtime_stock_news(
                symbol, hours_back, max_news
            )
            
            if news_items:
                # Standardized news data
                standardized_news = []
                for news_item in news_items:
                    standardized = self._standardize_realtime_news(news_item, symbol)
                    if standardized:
                        standardized_news.append(standardized)
                
                return standardized_news
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ Real-time news synchronization failed: {e}")
            return []
    
    def _standardize_tushare_news(self, news: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """Standardize Tushare news data"""
        try:
            return {
                "symbol": symbol,
                "title": news.get("title", ""),
                "content": news.get("content", ""),
                "summary": news.get("summary", ""),
                "url": news.get("url", ""),
                "source": news.get("source", "Tushare"),
                "author": news.get("author", ""),
                "publish_time": news.get("publish_time"),
                "category": self._classify_news_category(news.get("title", "")),
                "sentiment": self._analyze_sentiment(news.get("title", "") + " " + news.get("content", "")),
                "importance": self._assess_importance(news.get("title", "")),
                "keywords": self._extract_keywords(news.get("title", "") + " " + news.get("content", "")),
                "data_source": "tushare"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardizing Tushare news failed: {e}")
            return None
    
    def _standardize_akshare_news(self, news: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """Standardize AKShare news data"""
        try:
            return {
                "symbol": symbol,
                "title": news.get("title", ""),
                "content": news.get("content", ""),
                "summary": news.get("summary", ""),
                "url": news.get("url", ""),
                "source": news.get("source", "AKShare"),
                "author": news.get("author", ""),
                "publish_time": news.get("publish_time"),
                "category": self._classify_news_category(news.get("title", "")),
                "sentiment": self._analyze_sentiment(news.get("title", "") + " " + news.get("content", "")),
                "importance": self._assess_importance(news.get("title", "")),
                "keywords": self._extract_keywords(news.get("title", "") + " " + news.get("content", "")),
                "data_source": "akshare"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardizing AKShare news fails: {e}")
            return None
    
    def _standardize_realtime_news(self, news_item, symbol: str) -> Optional[Dict[str, Any]]:
        """Standardized real-time news data"""
        try:
            return {
                "symbol": symbol,
                "title": news_item.title,
                "content": news_item.content,
                "summary": news_item.content[:200] + "..." if len(news_item.content) > 200 else news_item.content,
                "url": news_item.url,
                "source": news_item.source,
                "author": "",
                "publish_time": news_item.publish_time,
                "category": self._classify_news_category(news_item.title),
                "sentiment": self._analyze_sentiment(news_item.title + " " + news_item.content),
                "importance": self._assess_importance(news_item.title),
                "keywords": self._extract_keywords(news_item.title + " " + news_item.content),
                "data_source": "realtime"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardized real-time news fails: {e}")
            return None
    
    def _classify_news_category(self, title: str) -> str:
        """Classified News Categories"""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ["annual report", "quarterly report", "performance", "financial report", "Announcement"]):
            return "company_announcement"
        elif any(word in title_lower for word in ["policy", "central bank", "supervision", "regulations"]):
            return "policy_news"
        elif any(word in title_lower for word in ["market", "Quotes", "Index", "plate"]):
            return "market_news"
        elif any(word in title_lower for word in ["research report", "analysis", "Rating", "Recommended"]):
            return "research_report"
        else:
            return "general"
    
    def _analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment"""
        text_lower = text.lower()
        
        positive_words = ["growth", "rise", "good", "Profit", "success", "breakthrough", "innovation", "Excellent"]
        negative_words = ["fall", "Loss", "risk", "question", "difficult", "decline", "reduce", "warning"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"
    
    def _assess_importance(self, title: str) -> str:
        """Assess importance"""
        title_lower = title.lower()
        
        high_importance_words = ["significant", "urgent", "sudden", "annual report", "performance", "Reorganization", "acquisition"]
        medium_importance_words = ["Announcement", "Notification", "change", "adjust", "plan"]
        
        if any(word in title_lower for word in high_importance_words):
            return "high"
        elif any(word in title_lower for word in medium_importance_words):
            return "medium"
        else:
            return "low"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords"""
        # Simple keyword extraction, more complex NLP technology can be used in practical applications
        keywords = []
        
        common_keywords = [
            "performance", "annual report", "quarterly report", "growth", "profit", "Revenue", "stock price", "investment",
            "market", "Industry", "policy", "supervision", "risk", "opportunity", "innovation", "develop"
        ]
        
        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)
        
        return keywords[:10]  # Returns up to 10 keywords
    
    def _deduplicate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate news"""
        seen = set()
        unique_news = []
        
        for news in news_list:
            # Use title and URL as deduplication identifiers
            key = (news.get("title", ""), news.get("url", ""))
            if key not in seen:
                seen.add(key)
                unique_news.append(news)
        
        return unique_news
    
    async def sync_market_news(
        self,
        data_sources: List[str] = None,
        hours_back: int = 24,
        max_news_per_source: int = 100
    ) -> NewsSyncStats:
        """
        Synchronous market news
        
        Args:
            data_sources: Data source list
            hours_back: Lookback hours
            max_news_per_source: Maximum number of news per data source
            
        Returns:
            Sync statistics
        """
        stats = NewsSyncStats()
        
        try:
            self.logger.info("📰 Start synchronizing market news...")
            
            if data_sources is None:
                data_sources = ["realtime"]
            
            news_service = await self._get_news_service()
            all_news = []
            
            # Live market news
            if "realtime" in data_sources:
                try:
                    aggregator = await self._get_realtime_aggregator()
                    
                    # Get market news (without specifying a stock code)
                    news_items = aggregator.get_realtime_stock_news(
                        None, hours_back, max_news_per_source
                    )
                    
                    if news_items:
                        for news_item in news_items:
                            standardized = self._standardize_realtime_news(news_item, None)
                            if standardized:
                                all_news.append(standardized)
                        
                        stats.sources_used.append("realtime")
                        self.logger.info(f"✅ Market news for success: {len(all_news)}Article")
                        
                except Exception as e:
                    self.logger.error(f"❌ Failed to obtain market news: {e}")
            
            # Save news data
            if all_news:
                stats.total_processed = len(all_news)
                
                # Deduplication
                unique_news = self._deduplicate_news(all_news)
                stats.duplicate_skipped = len(all_news) - len(unique_news)
                
                # Save in batches
                saved_count = await news_service.save_news_data(
                    unique_news, "market_news", "CN"
                )
                stats.successful_saves = saved_count
                stats.failed_saves = len(unique_news) - saved_count
                
                self.logger.info(f"💾 Market news is synchronized: {saved_count}Article saved successfully")
            
            stats.end_time = datetime.utcnow()
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Failed to synchronize market news: {e}")
            stats.end_time = datetime.utcnow()
            return stats


# Global service instance
_sync_service_instance = None

async def get_news_data_sync_service() -> NewsDataSyncService:
    """Get news data synchronization service instance"""
    global _sync_service_instance
    if _sync_service_instance is None:
        _sync_service_instance = NewsDataSyncService()
        logger.info("✅ News data synchronization service initialized successfully")
    return _sync_service_instance

# === favorites_sync_task.py ===
"""
Stock watch list A-share historical data and financial data synchronization task

During synchronization, it is executed in order according to the unified data source priority (get_enabled_data_sources_async) of the project.
"""

import logging
from typing import List, Set, Dict, Any, Tuple
from datetime import datetime

from app.core.database import get_mongo_db
from app.core.data_source_priority import get_enabled_data_sources_async
from app.worker.tushare_sync_service import get_tushare_sync_service
from app.worker.akshare_sync_service import get_akshare_sync_service

logger = logging.getLogger("webapi")

# ETF Symbol prefix (consistent with ETF sync service)
ETF_SH_PREFIXES = ("50", "51", "52", "56", "58")
ETF_SZ_PREFIXES = ("15", "16", "18")


def _get_sync_data_sources(enabled_sources: List[str]) -> List[str]:
    """Exclude local from enabled data sources to get a list of data sources used for synchronization (in order of priority)."""
    sync_sources = [s for s in enabled_sources if s and s.lower() != "local"]
    return sync_sources if sync_sources else ["tushare", "akshare", "baostock"]


async def get_all_favorite_a_stocks() -> List[str]:
    """
    Get the list of A-share stock codes in all users stock watch lists
    
    Returns:
        A Stock code list (duplication removed)
    """
    db = get_mongo_db()
    
    try:
        # Get all user's stock watchlists from user_favorites collection
        cursor = db.user_favorites.find({}, {"favorites": 1})
        
        a_stock_codes: Set[str] = set()
        
        async for doc in cursor:
            favorites = doc.get("favorites", [])
            for favorite in favorites:
                # Only get A shares
                market = favorite.get("market", "A shares")
                if market == "A shares":
                    stock_code = favorite.get("stock_code")
                    if stock_code:
                        # Make sure the ticker symbol is in 6 digit format
                        stock_code = str(stock_code).zfill(6)
                        a_stock_codes.add(stock_code)
        
        codes_list = sorted(list(a_stock_codes))
        logger.info(f"📊 Get {len(codes_list)} Only the A-share stock watch list needs to be synchronized")
        
        return codes_list
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain stock watch list A-share list: {e}")
        return []


def _favorites_sync_task_is_etf_code(code: str) -> bool:
    """Determine if the 6-digit code is an ETF."""
    normalized = str(code or "").zfill(6)
    return len(normalized) == 6 and normalized.startswith(ETF_SH_PREFIXES + ETF_SZ_PREFIXES)


def _split_stock_and_etf_codes(codes: List[str]) -> Tuple[List[str], List[str]]:
    """Split the ticker list into common stocks and ETFs."""
    stock_codes: List[str] = []
    etf_codes: List[str] = []

    for code in codes:
        if _favorites_sync_task_is_etf_code(code):
            etf_codes.append(code)
        else:
            stock_codes.append(code)

    return stock_codes, etf_codes


def _filter_stock_codes_for_financial_sync(codes: List[str]) -> List[str]:
    """Financial sync only retains ticker symbols and excludes ETFs."""
    stock_codes, _ = _split_stock_and_etf_codes(codes)
    return stock_codes


async def sync_favorites_historical_data():
    """
    Synchronize the historical data of A shares in the stock watch list.
    In order of data source priority (get_enabled_data_sources_async), the first data source that supports the specified stock list is used.
    
    Returns:
        Synchronization result statistics
    """
    logger.info("🔄 Start synchronizing stock watchlist A-share historical data...")
    
    try:
        # 1. Get A-share codes in all stock watchlists
        a_stock_codes = await get_all_favorite_a_stocks()
        
        if not a_stock_codes:
            logger.info("ℹ️ There is no A-share stock watch list that requires synchronization of historical data.")
            return {
                "success": True,
                "message": "There is no A-share stock watch list that needs to be synchronized.",
                "total_count": 0,
                "synced_count": 0,
                "data_source": None
            }

        stock_codes, etf_codes = _split_stock_and_etf_codes(a_stock_codes)
        if etf_codes:
            logger.info(f"🔀 The history of the stock watch list synchronizes the identification of ETFs and switches to the ETF dedicated link.: {len(etf_codes)} only")
        if not stock_codes:
            logger.info("ℹ️ Stock watchlist history sync does not include common stocks, only ETF history sync will be performed")
        
        # 2. Get the list of synchronized data sources by data source priority (excluding local)
        enabled_sources = await get_enabled_data_sources_async("a_shares")
        data_sources = _get_sync_data_sources(enabled_sources)
        logger.info(f"📊 Stock watch list historical data synchronization data source priority: {data_sources}")
        
        # 🔥 Use unified thread pool service to perform synchronization tasks (avoid event loop conflicts)
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        # 🔥 Optimization: Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
        # The same data source is still serial internally (to avoid API current limiting)
        import asyncio
        
        tasks = []
        task_sources = []
        
        # Create concurrent tasks (only include data sources that support the specified stock list)
        for source in data_sources:
            source_lower = source.lower()
            
            # BaoStock Specified stock list is not supported, skip
            if source_lower == "baostock":
                logger.debug("BaoStock Historical synchronization does not support the specified stock list, skip")
                continue

            if not stock_codes:
                continue
            
            # 🔥 Create tasks (executed using a unified thread pool service to avoid event loop conflicts)
            if source_lower == "tushare":
                async def sync_tushare(codes=stock_codes):
                    service = await get_tushare_sync_service()
                    # 🔥 Execute synchronized methods in thread pool
                    sync_result = await unified_service.execute_sync_method(
                        sync_method=service.sync_historical_data,
                        method_kwargs={
                            "symbols": codes,
                            "incremental": True,
                            "period": "daily"
                        },
                        job_id="favorites_tushare_historical_sync",
                        rate_limit_per_minute=200  # Tushare rate limit
                    )
                    if sync_result.success:
                        return sync_result.result
                    else:
                        raise RuntimeError(sync_result.error)
                tasks.append(sync_tushare())
                task_sources.append("tushare")
            elif source_lower == "akshare":
                async def sync_akshare(codes=stock_codes):
                    service = await get_akshare_sync_service()
                    # 🔥 Execute synchronized methods in thread pool
                    sync_result = await unified_service.execute_sync_method(
                        sync_method=service.sync_historical_data,
                        method_kwargs={
                            "symbols": codes,
                            "incremental": True,
                            "period": "daily"
                        },
                        job_id="favorites_akshare_historical_sync",
                        rate_limit_per_minute=60  # AKShare rate limit
                    )
                    if sync_result.success:
                        return sync_result.result
                    else:
                        raise RuntimeError(sync_result.error)
                tasks.append(sync_akshare())
                task_sources.append("akshare")

        if etf_codes:
            async def sync_etf(codes=etf_codes):
                service = await get_etf_sync_service()
                return await service.sync_symbols(
                    symbols=codes,
                    force_update=False,
                    days=30,
                    job_id="favorites_etf_historical_sync",
                )

            tasks.append(sync_etf())
            task_sources.append("etf")
        
        # Execute synchronization tasks for all data sources in parallel
        if tasks:
            logger.info(f"🚀 Start parallel synchronization {len(tasks)} historical data from data sources: {task_sources}")
            
            # Parallel execution using asyncio.gather
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Processing results: merge all successful data source results
            stock_success_count = 0
            stock_records = 0
            etf_success_count = 0
            etf_records = 0
            used_sources = []
            all_details = {}
            
            for i, (source, result) in enumerate(zip(task_sources, results)):
                if isinstance(result, Exception):
                    logger.warning(f"⚠️ {source} Historical data synchronization failed: {result}")
                    all_details[source] = {"error": str(result)}
                else:
                    # 🔥 Debugging: print the complete return result and view the actual fields
                    logger.debug(f"📊 {source} Historical data synchronization return results: {result}")
                    
                    # 🔥 Check whether it is a skip situation (incremental synchronization time check)
                    if result.get("skipped", False):
                        skip_reason = result.get("skip_reason", result.get("message", "unknown reason"))
                        logger.info(f"⏸️ {source} Historical data synchronization skipped: {skip_reason}")
                        all_details[source] = {
                            "skipped": True,
                            "skip_reason": skip_reason,
                            "stats": result.get("stats", {})
                        }
                        # 🔥 Skipped situations are also counted in used_sources, but not counted in the number of successes.
                        used_sources.append(source)
                        continue

                    if source == "etf":
                        success_count = result.get("success_count", 0)
                        records = result.get("records_inserted", 0)
                        etf_success_count = success_count
                        etf_records += records
                        etf_source = result.get("data_source_used")
                        used_sources.append(f"etf:{etf_source}" if etf_source else "etf")
                        all_details[source] = result
                        logger.info(f"✅ ETF Historical data synchronization completed: success={success_count}, record={records}, data source={etf_source}")
                        continue

                    # 🔥 Check whether there are nested stats in the returned result (in some cases the return format may be {"stats": {...}}) 
                    if "stats" in result and isinstance(result["stats"], dict):
                        stats = result["stats"]
                        success_count = stats.get("success_count", 0)
                        records = stats.get("total_records", 0)
                    else:
                        # Use fields in result directly
                        success_count = result.get("success_count", 0)
                        records = result.get("total_records", 0)
                    
                    # 🔥 Debug log: Check which fields have values
                    logger.info(f"📊 {source} Historical data return: success_count={success_count}, total_records={records}, "
                               f"total_processed={result.get('total_processed', result.get('stats', {}).get('total_processed', 'N/A'))}, "
                               f"error_count={result.get('error_count', result.get('stats', {}).get('error_count', 'N/A'))}, "
                               f"result keys={list(result.keys())}")

                    stock_success_count = max(stock_success_count, success_count)  # Take the maximum value (because different data sources may cover the same stocks)
                    stock_records += records  # Cumulative number of records (data from different data sources will be merged)
                    used_sources.append(source)
                    all_details[source] = result
                    logger.info(f"✅ {source} Historical data synchronization completed: success={success_count}, record={records}")

            total_success_count = stock_success_count + etf_success_count
            total_records = stock_records + etf_records

            if not used_sources:
                logger.warning("⚠️ Stock watchlist historical data sync: all data sources failed")
                return {
                    "success": False,
                    "message": "Synchronization of all data sources failed",
                    "total_count": len(a_stock_codes),
                    "synced_count": 0,
                    "data_source": None,
                    "error": "Synchronization of all data sources failed",
                    "details": all_details
                }
            
            logger.info(
                f"✅ Stock watch list A-share historical data is synchronized (data source: {', '.join(used_sources)}) : "
                f"Number of shares={len(a_stock_codes)}, success={total_success_count}, Number of records={total_records}"
            )
            
            return {
                "success": True,
                "message": "Stock watch list A-share historical data is synchronized",
                "total_count": len(a_stock_codes),
                "synced_count": total_success_count,
                "total_records": total_records,
                "stock_count": len(stock_codes),
                "etf_count": len(etf_codes),
                "data_source": ", ".join(used_sources) if used_sources else None,
                "data_sources": used_sources,  # 🔥 New: Return list of all successful data sources
                "details": all_details  # 🔥 New: Return detailed results for all data sources
            }
        else:
            logger.warning("⚠️ Stock watch list historical data synchronization: no data source available (tried tushare/akshare)")
            return {
                "success": False,
                "message": "No data sources available or all failed",
                "total_count": len(a_stock_codes),
                "synced_count": 0,
                "data_source": None,
                "error": "No data source available"
            }
        
    except Exception as e:
        logger.error(f"❌ Stock watch list A-share historical data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "total_count": 0,
            "synced_count": 0,
            "error": str(e)
        }


async def sync_favorites_financial_data():
    """
    Synchronize the financial data of A shares in the stock watch list.
    Synchronize in order of data source priority (get_enabled_data_sources_async).
    
    Returns:
        Synchronization result statistics
    """
    logger.info("💰 Start synchronizing stock watchlist A-share financial data...")
    
    try:
        # 1. Get A-share codes in all stock watchlists
        a_stock_codes = await get_all_favorite_a_stocks()
        
        if not a_stock_codes:
            logger.info("ℹ️ No A-share stock watchlist needs to synchronize financial data")
            return {
                "success": True,
                "message": "There is no A-share stock watch list that needs to be synchronized.",
                "total_count": 0,
                "synced_count": 0
            }
        
        # Financial data is only synchronized for stocks, and ETFs use ETF-specific data links.
        stock_codes = _filter_stock_codes_for_financial_sync(a_stock_codes)
        skipped_etf_count = len(a_stock_codes) - len(stock_codes)

        if skipped_etf_count > 0:
            logger.info(f"⏭️ Stock Watchlist Financial Sync Excluded ETF: {skipped_etf_count} only")

        if not stock_codes:
            logger.info("ℹ️ Only ETFs are included in the stock watchlist, no stock financial sync is required")
            return {
                "success": True,
                "message": "Only includes ETFs, stock financial sync has been skipped",
                "total_count": len(a_stock_codes),
                "synced_count": 0,
                "error_count": 0,
                "skipped_etf_count": skipped_etf_count,
                "details": {}
            }

        # 2. Get the list of synchronized data sources by data source priority (excluding local)
        enabled_sources = await get_enabled_data_sources_async("a_shares")
        data_sources = _get_sync_data_sources(enabled_sources)
        logger.info(f"📊 Stock Watch List Financial Data Synchronization Data Source Priority: {data_sources}")
        
        # 3. Use the financial data synchronization service to synchronize in order of priority
        financial_service = FinancialDataSyncService()
        await financial_service.initialize()
        
        # Synchronize financial data (get the last 20 periods, about 5 years), data sources in order of priority
        result = await financial_service.sync_financial_data(
            symbols=stock_codes,
            data_sources=data_sources,
            report_types=["quarterly", "annual"],  # Quarterly and annual reports
            batch_size=50,
            delay_seconds=1.0,
            job_id="favorites_financial_sync"  # 🔥 Add job_id for progress tracking
        )
        
        # Statistical synchronization results
        total_synced = 0
        total_errors = 0
        for source, stats in result.items():
            total_synced += stats.success_count
            total_errors += stats.error_count
        
        logger.info(
            f"✅ Stock watch list A-share financial data is synchronized: "
            f"Number of shares={len(stock_codes)}, "
            f"exclude ETF={skipped_etf_count}, "
            f"Synced successfully={total_synced}, "
            f"failed={total_errors}"
        )
        
        return {
            "success": True,
            "message": "Stock watch list A-share financial data is synchronized",
            "total_count": len(stock_codes),
            "synced_count": total_synced,
            "error_count": total_errors,
            "skipped_etf_count": skipped_etf_count,
            "details": {source: {
                "success_count": stats.success_count,
                "error_count": stats.error_count,
                "skipped_count": stats.skipped_count,
                "total_symbols": stats.total_symbols
            } for source, stats in result.items()}
        }
        
    except Exception as e:
        logger.error(f"❌ Stock watch list A-share financial data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "total_count": 0,
            "synced_count": 0,
            "error": str(e)
        }


async def run_favorites_data_sync():
    """
    APScheduler Task: Synchronize the historical data and financial data of A shares in the stock watch list
    
    This task will:
    1. Get the A-share stock codes in all users stock watch lists
    2. Synchronize the historical data of these stocks (incremental synchronization)
    3. Synchronize the financial data of these stocks (last 20 periods)
    """
    job_id = "favorites_data_sync"
    logger.info("🚀 [APScheduler] Start executing the stock watch list A-share data synchronization task")
    
    start_time = datetime.now()
    
    try:
        # Import progress update function
        from app.services.scheduler_service import update_job_progress
        
        # Get the number of stock watchlists (used for progress calculation)
        a_stock_codes = await get_all_favorite_a_stocks()
        total_stocks = len(a_stock_codes)
        
        # Update progress: Started (0%)
        try:
            await update_job_progress(
                job_id=job_id,
                progress=0,
                message="Start synchronizing stock watchlist A-share data...",
                total_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to update task progress: {e}")
        
        # 🔥 Optimization: Historical data and financial data can be executed in parallel (because they use different APIs and do not affect each other)
        # 1. Perform historical and financial data synchronization in parallel
        try:
            await update_job_progress(
                job_id=job_id,
                progress=10,
                message="Synchronizing historical and financial data in parallel...",
                total_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception:
            pass
        
        # Use asyncio.gather to perform historical and financial data synchronization in parallel
        import asyncio
        hist_task = sync_favorites_historical_data()
        fin_task = sync_favorites_financial_data()
        
        hist_result, fin_result = await asyncio.gather(
            hist_task,
            fin_task,
            return_exceptions=True
        )
        
        # Handle abnormal results
        if isinstance(hist_result, Exception):
            logger.error(f"❌ Historical data synchronization failed: {hist_result}", exc_info=True)
            hist_result = {
                "success": False,
                "message": f"Historical data synchronization failed: {str(hist_result)}",
                "total_count": total_stocks,
                "synced_count": 0,
                "error": str(hist_result)
            }
        
        if isinstance(fin_result, Exception):
            logger.error(f"❌ Financial data synchronization failed: {fin_result}", exc_info=True)
            fin_result = {
                "success": False,
                "message": f"Financial data synchronization failed: {str(fin_result)}",
                "total_count": total_stocks,
                "synced_count": 0,
                "error": str(fin_result)
            }
        
        # Update progress: Parallel synchronization completed (90%)
        try:
            hist_synced = hist_result.get('synced_count', 0) if isinstance(hist_result, dict) else 0
            fin_synced = fin_result.get('synced_count', 0) if isinstance(fin_result, dict) else 0
            
            await update_job_progress(
                job_id=job_id,
                progress=90,
                message=f"Parallel synchronization completed: historical data {hist_synced}/{total_stocks}, financial data {fin_synced}/{total_stocks}",
                total_items=total_stocks if total_stocks > 0 else 1,
                processed_items=max(hist_synced, fin_synced)
            )
        except Exception:
            pass
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Update progress: Completed (100%)
        try:
            await update_job_progress(
                job_id=job_id,
                progress=100,
                message=f"Task completed (time consuming): {duration:.2f}seconds)",
                total_items=total_stocks if total_stocks > 0 else 1,
                processed_items=total_stocks if total_stocks > 0 else 1
            )
        except Exception:
            pass
        
        logger.info(
            f"✅ [APScheduler] Stock watch list A-share data synchronization task completed "
            f"(Time consuming: {duration:.2f}seconds)\n"
            f"   historical data: {hist_result.get('synced_count', 0)}/{hist_result.get('total_count', 0)} only stocks\n"
            f"   financial data: {fin_result.get('synced_count', 0)}/{fin_result.get('total_count', 0)} only stocks"
        )
        
        return {
            "success": True,
            "duration_seconds": duration,
            "historical_data": hist_result,
            "financial_data": fin_result
        }
        
    except Exception as e:
        logger.error(f"❌ [APScheduler] Stock watch list A-share data synchronization task failed: {e}", exc_info=True)
        
        # Update progress: failed
        try:
            from app.services.scheduler_service import update_job_progress
            await update_job_progress(
                job_id=job_id,
                progress=0,
                message=f"Task failed: {str(e)}"
            )
        except Exception:
            pass
        
        return {
            "success": False,
            "error": str(e)
        }

# === watchlist_analysis_task.py ===
"""
Stock watch list scheduled analysis tasks

Regularly analyze the stocks in the user s stock watch list and reuse existing analysis services.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.core.database import get_mongo_db
from app.services.notifications_service import NotificationsService
from app.models.notification import NotificationCreate
from app.models.analysis import SingleAnalysisRequest
from app.utils.compliance import GENERIC_RESEARCH_RECOMMENDATION, build_research_summary

logger = logging.getLogger("app.worker.watchlist_analysis")

# global state
_is_running = False


def _build_scheduled_email_attachments(results: List[Dict[str, Any]], analysis_time: str) -> List[tuple]:
    """Build attachments for scheduled analysis completion emails."""
    if not results:
        return []

    markdown_lines = [
        "# Scheduled Analysis Report",
        "",
        f"Analysis Time: {analysis_time}",
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    export_payload = []
    for item in results:
        stock_code = item.get("stock_code") or item.get("stock_symbol") or "unknown"
        stock_name = item.get("stock_name") or stock_code
        success = item.get("success", False)
        research_overview = build_research_summary({}, item.get("summary") or "")
        confidence_score = item.get("confidence_score") or 0
        risk_level = item.get("risk_level") or "medium"
        summary = (item.get("summary") or "").strip()
        key_points = item.get("key_points") or []

        markdown_lines.append(f"## {stock_code} {stock_name}")
        markdown_lines.append("")
        markdown_lines.append(f"- Status: {'success' if success else 'failed'}")
        markdown_lines.append(f"- Research Overview: {research_overview}")
        markdown_lines.append(f"- Confidence: {confidence_score}")
        markdown_lines.append(f"- Risk Level: {risk_level}")
        if summary:
            markdown_lines.append(f"- Summary: {summary}")
        if key_points:
            markdown_lines.append("- Key Points:")
            for point in key_points[:5]:
                markdown_lines.append(f"  - {point}")
        markdown_lines.append("")

        export_payload.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "success": success,
            "recommendation": GENERIC_RESEARCH_RECOMMENDATION,
            "analysis_overview": research_overview,
            "confidence_score": confidence_score,
            "risk_level": risk_level,
            "summary": summary,
            "key_points": key_points,
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_content = "\n".join(markdown_lines).encode("utf-8")
    json_content = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")

    return [
        (f"scheduled_analysis_{timestamp}.md", markdown_content, "text/markdown"),
        (f"scheduled_analysis_{timestamp}.json", json_content, "application/json"),
    ]


def _format_completed_task_result(task_id: str, task_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert task results into the required format for emails."""
    result = task_doc.get("result") or {}
    task_params = task_doc.get("task_params") or {}
    stock_code = task_params.get("stock_code") or task_params.get("symbol") or result.get("stock_code") or result.get("stock_symbol") or ""

    return {
        "task_id": task_id,
        "stock_code": stock_code,
        "stock_name": result.get("stock_name") or stock_code,
        "summary": result.get("summary", ""),
        "recommendation": GENERIC_RESEARCH_RECOMMENDATION,
        "confidence_score": result.get("confidence_score", 0),
        "risk_level": result.get("risk_level", "medium"),
        "key_points": result.get("key_points", []),
        "success": task_doc.get("status") == "completed",
    }


async def _wait_for_task_results(task_ids: List[str], timeout_seconds: int = 3600, poll_interval: int = 15) -> List[Dict[str, Any]]:
    """Wait for the batch task to complete and collect results that can be used for mail aggregation."""
    if not task_ids:
        return []

    db = get_mongo_db()
    pending_ids = set(task_ids)
    completed_results: Dict[str, Dict[str, Any]] = {}
    started_at = datetime.now()

    while pending_ids and (datetime.now() - started_at).total_seconds() < timeout_seconds:
        cursor = db.unified_analysis_tasks.find(
            {"task_id": {"$in": list(pending_ids)}},
            {"task_id": 1, "status": 1, "result": 1, "task_params": 1}
        )
        docs = await cursor.to_list(length=len(pending_ids))

        for doc in docs:
            task_id = doc.get("task_id")
            if not task_id:
                continue

            status = doc.get("status")
            if status in {"completed", "failed", "cancelled"}:
                completed_results[task_id] = _format_completed_task_result(task_id, doc)
                pending_ids.discard(task_id)

        if pending_ids:
            await asyncio.sleep(poll_interval)

    if pending_ids:
        logger.warning(f"⚠️ The scheduled mail analysis waits for timeout, and there are still {len(pending_ids)} tasks not completed")

    return [completed_results[task_id] for task_id in task_ids if task_id in completed_results]


async def _send_scheduled_completion_email_when_ready(
    user_id: str,
    task_ids: List[str],
    total: int,
    analysis_time: str,
) -> None:
    """After waiting for the task to complete, send a scheduled analysis completion email with attachments."""
    try:
        results = await _wait_for_task_results(task_ids)
        success = sum(1 for item in results if item.get("success"))
        failed = max(total - success, 0)
        await send_completion_notification(
            user_id=user_id,
            total=total,
            success=success,
            failed=failed,
            results=results,
            analysis_time=analysis_time,
            send_in_app_notification=True,
            send_email_notification=True,
        )
    except Exception as exc:
        logger.warning(f"⚠️ Failed to send scheduled analysis completion email: {exc}", exc_info=True)


async def get_watchlist_stocks() -> List[Dict[str, Any]]:
    """Get the list of stock watchlists for all valid users

    Only the stock watch lists of users that exist in the users collection are returned, and junk data left over from history is filtered out.

    Returns:
        List of dictionaries containing user_id and stocks
    """
    from bson import ObjectId

    db = get_mongo_db()

    # Step one: Get all valid users' ID
    users_cursor = db.users.find({}, {"_id": 1})
    valid_user_ids = set()
    async for user in users_cursor:
        user_id_str = str(user["_id"])
        valid_user_ids.add(user_id_str)

    logger.info(f"📊 There are total in the database {len(valid_user_ids)} valid users")

    # Step 2: Query records with stock watch lists from the user_favorites collection
    cursor = db.user_favorites.find(
        {"favorites": {"$exists": True, "$ne": []}}
    )

    result = []
    skipped_count = 0

    async for doc in cursor:
        user_id = doc.get("user_id", "unknown")
        favorites = doc.get("favorites", [])

        # Check if the user_id is in the list of valid users
        if user_id not in valid_user_ids:
            logger.warning(f"⚠️ Skip the stock watchlist of invalid users: {user_id} (User does not exist in users collection)")
            skipped_count += 1
            continue

        if favorites:
            logger.info(f"📋 Find valid user {user_id} of {len(favorites)} Only stock watch list")
            result.append({
                "user_id": user_id,
                "stocks": favorites
            })

    if skipped_count > 0:
        logger.info(f"🗑️ skipped {skipped_count} pieces of junk data left over from history")

    if not result:
        logger.info("📭 No stock watchlist data found for any valid user")
    else:
        logger.info(f"✅ Found in total {len(result)} valid users have stock watchlists")

    return result


async def analyze_user_watchlist_batch(
    user_id: str,
    stocks: List[Dict[str, Any]],
    analysis_date: str,
    analysis_depth: int = 3,
    quick_analysis_model: str = "qwen-plus",
    deep_analysis_model: str = "qwen-max"
) -> Dict[str, Any]:
    """
    Batch analysis of user s stock watchlist (concurrent execution) - using v2.0 engine

    Refer to the implementation of the batch analysis API:
    1. Create tasks for all stocks first (using v2.0 unified task engine)
    2. Then use asyncio.create_task to execute all tasks concurrently

    Args:
        user_id: User ID
        stocks: Stock Watchlist List
        analysis_date: Analysis date
        analysis_depth: Analysis depth (1-5)
        quick_analysis_model: Quickly analyze models
        deep_analysis_model: Deep analysis model

    Returns:
        A dictionary containing a list of task IDs and statistics
    """
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId

    task_service = get_task_analysis_service()

    # Convert numeric depth to Chinese description
    depth_mapping = {
        1: "fast",
        2: "Basics",
        3: "Standard",
        4: "Depth",
        5: "Comprehensive"
    }
    research_depth = depth_mapping.get(analysis_depth, "Standard")

    task_ids = []
    task_mapping = []
    submitted_task_ids = []
    submitted_count = 0
    failed_count = 0

    # Step 1: Create tasks for all stocks (using v2.0 engine)
    logger.info(f"  📝 [v2.0 engine] Start creating {len(stocks)} analysis tasks...")
    for idx, stock in enumerate(stocks, 1):
        stock_code = stock.get("stock_code")
        stock_name = stock.get("stock_name", stock_code)

        try:
            # 🔥 Identify security types based on ticker: ETFs follow the ETF workflow, stocks follow the stock workflow
            from tradingagents.utils.stock_utils import StockUtils, StockMarket, SecurityType

            sec_type = StockUtils.identify_security_type(stock_code)
            market = StockUtils.identify_stock_market(stock_code)
            market_type_mapping = {
                StockMarket.CHINA_A: "cn",
                StockMarket.HONG_KONG: "hk",
                StockMarket.US: "us",
                StockMarket.UNKNOWN: "cn"
            }
            market_type = market_type_mapping.get(market, "cn")

            # ETF Using the ETF Analysis Process
            if sec_type == SecurityType.FUND:
                task_type = AnalysisTaskType.ETF_ANALYSIS
                logger.info(f"    📊 {stock_code} Identify as an ETF, use the ETF analysis process")
            else:
                task_type = AnalysisTaskType.STOCK_ANALYSIS
                logger.info(f"    📊 stocks {stock_code} identified as market: {market_type}")

            # Prepare task parameters
            task_params = {
                "symbol": stock_code,
                "stock_code": stock_code,
                "market_type": market_type,
                "analysis_date": analysis_date,
                "research_depth": research_depth,
                "quick_analysis_model": quick_analysis_model,
                "deep_analysis_model": deep_analysis_model
            }

            # Create tasks using v2.0 Unified Task Engine
            task = await task_service.create_task(
                user_id=PyObjectId(user_id),
                task_type=task_type,
                task_params=task_params,
                engine_type="auto",  # Automatic engine selection
                preference_type="neutral"
            )

            task_id = task.task_id

            task_ids.append(task_id)
            task_mapping.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "task_id": task_id,
                "task": task
            })

            logger.info(f"    ✅ [{idx}/{len(stocks)}] Task created: {task_id} - {stock_code} {stock_name}")

        except Exception as e:
            logger.error(f"    ❌ [{idx}/{len(stocks)}] Failed to create task: {stock_code} {stock_name}, Error: {e}")
            task_mapping.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "task_id": None,
                "error": str(e)
            })

    logger.info(f"  ✅ Task creation completed: success {len(task_ids)}/{len(stocks)}")

    # Step 2: Submit the task to the queue, and the Worker will uniformly manage concurrency
    if task_ids:
        logger.info(f"  🚀 [v2.0 engine] Start submitting {len(task_ids)} analysis tasks to queue...")
        
        from app.services.queue_service import get_queue_service
        queue_service = get_queue_service()
        
        # Generate batch ID (for scheduled batch analysis)
        batch_id = str(uuid.uuid4())
        
        for item in task_mapping:
            if item.get("task_id"):
                task_id = item["task_id"]
                stock_code = item["stock_code"]
                
                # Prepare queue parameters
                queue_params = {
                    "task_id": task_id,
                    "symbol": stock_code,
                    "stock_code": stock_code,
                    "user_id": user_id,
                    "batch_id": batch_id,
                    "engine": "v2",  # v2 engine
                    "analysis_date": analysis_date,
                    "research_depth": depth_mapping.get(analysis_depth, "Standard"),
                    "quick_analysis_model": quick_analysis_model,
                    "deep_analysis_model": deep_analysis_model
                }
                
                try:
                    # Submit tasks to the queue (will automatically check concurrency limits)
                    await queue_service.enqueue_task(
                        user_id=user_id,
                        symbol=stock_code,
                        params=queue_params,
                        batch_id=batch_id,
                        task_id=task_id  # Use an already created task ID
                    )
                    submitted_count += 1
                    submitted_task_ids.append(task_id)
                    logger.info(f"    ✅ [v2.0 engine] The task has been queued: {task_id} - {stock_code}")
                except ValueError as e:
                    # Concurrency limit error
                    failed_count += 1
                    logger.warning(f"    ⚠️ [v2.0 engine] Task enqueue failed (concurrency limit): {task_id} - {stock_code}, Error: {e}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"    ❌ [v2.0 engine] Task enqueue failed: {task_id} - {stock_code}, Error: {e}", exc_info=True)
        
        logger.info(f"  ✅ Submitted {submitted_count} Tasks were queued and failed. {failed_count} a")

    return {
        "total": len(stocks),
        "created": submitted_count,
        "failed": len(stocks) - submitted_count,
        "task_ids": submitted_task_ids,
        "task_mapping": task_mapping
    }


async def send_completion_notification(
    user_id: str,
    total: int,
    success: int,
    failed: int,
    results: List[Dict[str, Any]],
    analysis_time: Optional[str] = None,
    send_in_app_notification: bool = True,
    send_email_notification: bool = True,
):
    """Send analysis completion notification"""
    notifications_service = NotificationsService()
    has_detailed_results = bool(results)
    analysis_time = analysis_time or datetime.now().strftime("%Y-%m-%d %H:%M")

    if has_detailed_results:
        if success > 0:
            severity = "success" if failed == 0 else "warning"
            title = "Stock watch list scheduled analysis completed"
            content = f"Completed {success}/{total} Stock analysis"
            if failed > 0:
                content += f", {failed} Only analysis failed"
        else:
            severity = "error"
            title = "Stock watch list scheduled analysis failed"
            content = f"All {total} Only stock analysis failed"
    else:
        severity = "info" if success > 0 else "error"
        title = "Stock watch list scheduled analysis has started"
        content = f"Submitted {success}/{total} Stock analysis tasks"
        if failed > 0:
            content += f", {failed} Only submission failed"

    notification = NotificationCreate(
        user_id=user_id,
        type="analysis",
        title=title,
        content=content,
        link="/analysis/history",
        source="watchlist_scheduler",
        severity=severity,
        metadata={
            "total": total,
            "success": success,
            "failed": failed,
            "analysis_date": analysis_time,
            "has_detailed_results": has_detailed_results,
            "stocks": [
                {
                    "stock_code": r.get("stock_code"),
                    "stock_name": r.get("stock_name"),
                    "success": r.get("success", False)
                }
                for r in results
            ]
        }
    )

    if send_in_app_notification:
        try:
            await notifications_service.create_and_publish(notification)
            logger.info(f"📬 Analysis notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")

    # Send email notifications (if the user has enabled email notifications)
    if not send_email_notification or not has_detailed_results:
        return

    try:
        from app.services.email_service import get_email_service
        from app.models.email import EmailType
        email_service = get_email_service()

        # Statistical recommendation results
        buy_count = 0
        hold_count = 0
        sell_count = 0

        attachments = _build_scheduled_email_attachments(results, analysis_time)

        await email_service.send_analysis_email(
            user_id=user_id,
            email_type=EmailType.SCHEDULED_ANALYSIS,  # 🔥 Fix: use enum instead of string
            template_name="scheduled_report",
            template_data={
                "task_name": "Stock watch list timing analysis",
                "analysis_date": analysis_time,
                "total_count": total,
                "success_count": success,
                "failed_count": failed,
                "buy_count": buy_count,
                "hold_count": hold_count,
                "sell_count": sell_count,
                "stocks": results[:10],  # Only send details of the first 10 stocks
                "detail_url": "/analysis/history"
            },
            reference_id=f"scheduled_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            attachments=attachments,
        )
        logger.info(f"📧 An attempt has been made to send a scheduled analysis completion email to the user. {user_id}")
    except Exception as email_err:
        logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")


async def run_watchlist_analysis():
    """
    Regular analysis of stock watch list tasks - Main entrance

    Called periodically by APScheduler.
    Iterate through all users who have stock watch lists and analyze their stock watch lists for each user.
    """
    global _is_running

    if _is_running:
        logger.warning("⚠️ The stock watch list scheduled analysis task is running, skip this execution")
        return

    _is_running = True
    start_time = datetime.now()
    analysis_date = start_time.strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("🚀 Start executing stock watch list scheduled analysis tasks")
    logger.info(f"   Analysis date: {analysis_date}")
    logger.info("=" * 60)

    total_stocks = 0
    total_success = 0
    total_failed = 0

    try:
        # 🔥 Get system default model configuration (from database)
        system_default_models = await get_system_default_models()
        default_quick_model = system_default_models.get("quick_analysis_model", "qwen-plus")
        default_deep_model = system_default_models.get("deep_analysis_model", "qwen-max")
        
        logger.info(f"📋 System default model configuration: fast={default_quick_model}, Depth={default_deep_model}")
        
        # Get a list of all users' stock watchlists
        watchlist_data = await get_watchlist_stocks()

        if not watchlist_data:
            logger.info("📭 No user s stock watchlist found, task ended")
            return

        logger.info(f"📊 total {len(watchlist_data)} Users have stock watchlists")

        # Iterate through each user
        for user_idx, user_data in enumerate(watchlist_data, 1):
            user_id = user_data["user_id"]
            stocks = user_data["stocks"]
            user_total = len(stocks)

            logger.info("-" * 40)
            logger.info(f"👤 [{user_idx}/{len(watchlist_data)}] User: {user_id}")
            logger.info(f"📊 Number of stocks to be analyzed: {user_total}")

            # Use the batch analysis method (concurrent execution) and use the system default model
            batch_result = await analyze_user_watchlist_batch(
                user_id=user_id,
                stocks=stocks,
                analysis_date=analysis_date,
                quick_analysis_model=default_quick_model,
                deep_analysis_model=default_deep_model
            )

            user_success = batch_result["created"]
            user_failed = batch_result["failed"]

            # Cumulative statistics
            total_stocks += user_total
            total_success += user_success
            total_failed += user_failed

            # Send notification to this user
            # Note: Due to concurrent execution, the task may still be executing when the notification is sent here.
            # Consider waiting until all tasks are completed before sending the notification, or stating this in the notification"Analysis started"
            await send_completion_notification(
                user_id=user_id,
                total=user_total,
                success=user_success,
                failed=user_failed,
                results=[],
                analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                send_in_app_notification=True,
                send_email_notification=False,
            )

            if batch_result.get("task_ids"):
                asyncio.create_task(
                    _send_scheduled_completion_email_when_ready(
                        user_id=user_id,
                        task_ids=batch_result["task_ids"],
                        total=user_total,
                        analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    )
                )

            logger.info(f"  ✅ User {user_id} Batch analysis started: Created successfully {user_success} tasks, failed {user_failed} a")

        # Calculate total time
        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info("✅ Stock watch list scheduled analysis tasks are all completed")
        logger.info(f"   Number of users: {len(watchlist_data)}")
        logger.info(f"   Total number of stocks analyzed: {total_stocks}")
        logger.info(f"   total success: {total_success}, total failure: {total_failed}")
        logger.info(f"   Total time spent: {elapsed:.2f} seconds")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Stock watch list scheduled analysis task execution failed: {e}", exc_info=True)
    finally:
        _is_running = False


async def get_system_default_models() -> Dict[str, str]:
    """
    Obtain the system default analysis model configuration from the database
    
    Returns:
        Dictionary containing quick_analysis_model and deep_analysis_model
    """
    try:
        db = get_mongo_db()
        # Get active system configuration
        system_config = await db.system_configs.find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )
        
        if system_config and "system_settings" in system_config:
            system_settings = system_config["system_settings"]
            return {
                "quick_analysis_model": system_settings.get("quick_analysis_model", "qwen-plus"),
                "deep_analysis_model": system_settings.get("deep_analysis_model", "qwen-max")
            }
    except Exception as e:
        logger.warning(f"⚠️ Failed to obtain system default model configuration: {e}, Use code defaults")
    
    # If the acquisition fails, return code default value
    return {
        "quick_analysis_model": "qwen-plus",
        "deep_analysis_model": "qwen-max"
    }


async def _execute_general_workflow_slot(
    config_id: str,
    user_id: str,
    slot: Dict[str, Any],
    workflow_id: str,
    config: Dict[str, Any],
    db,
):
    """
    Execute common research workflow time period tasks

    This function is called when the time period is configured with workflow_id, using the workflow_params in
    analysis_target and custom_params as workflow inputs.

    Args:
        config_id: Configuration ID
        user_id: User ID
        slot: Time period configuration
        workflow_id: Workflow ID
        config: Complete configuration documentation
        db: MongoDB Database handle
    """
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId
    from app.utils.timezone import now_tz
    from bson import ObjectId
    import asyncio

    logger.info("📋 Common research process execution parameters:")
    workflow_params = slot.get("workflow_params") or {}
    analysis_target = workflow_params.get("analysis_target", "") or ""
    custom_params = workflow_params.get("custom_params") or {}

    logger.info(f"   Analyze goals: {analysis_target}")
    logger.info(f"   Custom parameters: {custom_params}")

    if not analysis_target:
        logger.warning("⚠️ Analysis target not configured, execution skipped")
        # Record failure history
        try:
            history_doc = {
                "config_id": config_id,
                "config_name": config.get("name", "Unnamed"),
                "time_slot_name": slot.get("name", "Unnamed"),
                "created_at": now_tz(),
                "status": "failed",
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "task_ids": [],
                "result_summary": "No analysis target configured"
            }
            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as e:
            logger.error(f"❌ Record failure history failure: {e}")
        return

    total_success = 0
    total_failed = 0
    all_task_ids = []

    try:
        task_service = get_task_analysis_service()
        analysis_date = datetime.now().strftime("%Y-%m-%d")

        # 🆕 Query the input_config of the workflow to supplement the default parameters
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        wf_doc = await db.workflows.find_one(
            {"workflow_id": workflow_id} if isinstance(workflow_id, str) else {"_id": workflow_id},
            {"input_config": 1, "workflow_type": 1}
        )
        input_config = wf_doc.get("input_config") if wf_doc else None

        # Build task parameters: analysis target as ticker, merge custom_params
        task_params = {
            "symbol": analysis_target,
            "stock_code": analysis_target,
            "analysis_date": analysis_date,
            "task_category": "general",  # 🆕 Marked as a general research task
            **custom_params,  # Merge custom parameters
        }

        # 🆕 Supplement missing parameters based on the default value of input_config.fields
        if input_config and isinstance(input_config, dict):
            fields = input_config.get("fields", [])
            for field in fields:
                fname = field.get("name")
                if fname and fname not in task_params and fname not in ("ticker", "symbol", "stock_code"):
                    default_val = field.get("default")
                    if default_val is not None:
                        task_params[fname] = default_val

        # General parameters
        task_params.setdefault("research_depth", "Standard")
        task_params.setdefault("market_type", "cn")

        # Obtain user risk preference
        try:
            from app.routers.analysis import get_user_risk_preference
            preference_type = await get_user_risk_preference(user_id)
        except Exception:
            preference_type = "default"

        logger.info(f"🚀 Create a general research task: workflow_id={workflow_id}, target={analysis_target}")

        task = await task_service.create_task(
            user_id=PyObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="workflow",
            preference_type=preference_type,
            workflow_id=workflow_id,
        )

        # Execute tasks asynchronously
        asyncio.create_task(task_service.execute_task(task))

        all_task_ids.append(task.task_id)
        total_success += 1
        logger.info(f"✅ Generic research task created: task_id={task.task_id}")

    except Exception as e:
        total_failed += 1
        logger.error(f"❌ Failed to create universal research task: {e}", exc_info=True)

    # Update configuration last run time
    await db.scheduled_analysis_configs.update_one(
        {"_id": ObjectId(config_id)},
        {"$set": {"last_run_at": now_tz()}}
    )

    # Record execution history
    try:
        history_doc = {
            "config_id": config_id,
            "config_name": config.get("name", "Unnamed"),
            "time_slot_name": slot.get("name", "Unnamed"),
            "created_at": now_tz(),
            "status": "success" if total_failed == 0 else ("failed" if total_success == 0 else "partial"),
            "total_count": total_success + total_failed,
            "success_count": total_success,
            "failed_count": total_failed,
            "task_ids": all_task_ids,
            "result_summary": None
        }
        await db.scheduled_analysis_history.insert_one(history_doc)
    except Exception as e:
        logger.error(f"❌ Recording execution history failed: {e}")

    logger.info("=" * 70)
    logger.info("✅ The general research process time period task is completed")
    logger.info(f"   Successfully started: {total_success} tasks")
    logger.info(f"   failed: {total_failed} a")
    logger.info("=" * 70)


async def run_scheduled_analysis_slot(config_id: str, user_id: str, slot_index: int):
    """
    Execute scheduled analysis time period tasks - new version (supports grouping and custom parameters)

    Args:
        config_id: Configuration ID
        user_id: User ID
        slot_index: time period index
    """
    logger.info("=" * 70)
    logger.info("🚀 Start executing scheduled analysis time period tasks")
    logger.info(f"   Configuration ID: {config_id}")
    logger.info(f"   User ID: {user_id}")
    logger.info(f"   time period index: {slot_index}")
    logger.info("=" * 70)

    try:
        # 🔥 Get system default model configuration (from database)
        system_default_models = await get_system_default_models()
        logger.info(f"📋 System default model configuration: fast={system_default_models.get('quick_analysis_model', 'qwen-plus')}, Depth={system_default_models.get('deep_analysis_model', 'qwen-max')}")
        
        # Get configuration
        from bson import ObjectId
        config = await get_mongo_db().scheduled_analysis_configs.find_one({
            "_id": ObjectId(config_id),
            "user_id": user_id
        })

        if not config:
            logger.error(f"❌ Configuration does not exist: {config_id}")
            return

        if not config.get("enabled"):
            logger.warning(f"⚠️ Configuration is disabled: {config_id}")
            return

        time_slots = config.get("time_slots", [])
        if slot_index >= len(time_slots):
            logger.error(f"❌ Time period index out of range: {slot_index}")
            return

        slot = time_slots[slot_index]
        if not slot.get("enabled", True):
            logger.warning(f"⚠️ Time period disabled: {slot.get('name')}")
            return

        logger.info(f"📅 time period: {slot.get('name')}")
        logger.info(f"📋 Number of groups: {len(slot.get('group_ids', []))}")

        # 🆕 Branch: If a general research process is configured, workflow execution is called (skipping grouped stock analysis)
        workflow_id = slot.get("workflow_id")
        if workflow_id:
            logger.info(f"🎯 Generic research process configuration detected: workflow_id={workflow_id}")
            await _execute_general_workflow_slot(
                config_id=config_id,
                user_id=user_id,
                slot=slot,
                workflow_id=workflow_id,
                config=config,
                db=db,
            )
            return

        # Get a list of group IDs to analyze
        group_ids = slot.get("group_ids", [])
        
        # If no grouping is specified, try to use the configured default grouping
        if not group_ids:
            group_ids = config.get("default_group_ids", [])
            
        # If still no grouping specified, skip
        if not group_ids:
            logger.warning(f"⚠️ No grouping is configured for the time period: {slot.get('name')}")
            return

        # Get group information
        db = get_mongo_db()
        groups = []
        for group_id in group_ids:
            try:
                group = await db.watchlist_groups.find_one({
                    "_id": ObjectId(group_id),
                    "user_id": user_id,
                    "is_active": True
                })
                if group:
                    groups.append(group)
            except Exception as e:
                logger.error(f"❌ Failed to get group: {group_id} - {e}")

        if not groups:
            logger.warning("⚠️ No valid group found")
            return

        logger.info(f"✅ found {len(groups)} valid groups")

        # statistics
        total_stocks = 0
        total_success = 0
        total_failed = 0
        all_task_ids = []

        # Perform analysis for each grouping
        for group in groups:
            group_name = group.get("name", "Unnamed")
            stock_codes = group.get("stock_codes", [])

            if not stock_codes:
                logger.info(f"  📁 Group [{group_name}] No stocks, skip")
                continue

            logger.info(f"  📁 Group [{group_name}]: {len(stock_codes)} only stocks")

            # Determine analysis parameters (priority: time period > Group > configuration default value)
            analysis_depth = (
                slot.get("analysis_depth") or
                group.get("analysis_depth") or
                config.get("default_analysis_depth", 3)
            )
            # 🔥 Determine the analysis model: use the system default values directly (there is no place to configure these fields in the front-end interface)
            quick_model = system_default_models.get("quick_analysis_model", "qwen-plus")
            deep_model = system_default_models.get("deep_analysis_model", "qwen-max")

            logger.info(f"     Analysis depth: {analysis_depth}")
            logger.info(f"     quick model: {quick_model} (system default)")
            logger.info(f"     deep model: {deep_model} (system default)")

            # Build a stock list
            stocks = [{"stock_code": code} for code in stock_codes]

            # Perform batch analysis
            batch_result = await analyze_user_watchlist_batch(
                user_id=user_id,
                stocks=stocks,
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                analysis_depth=analysis_depth,
                quick_analysis_model=quick_model,
                deep_analysis_model=deep_model
            )

            group_success = batch_result["created"]
            group_failed = batch_result["failed"]

            total_stocks += len(stock_codes)
            total_success += group_success
            total_failed += group_failed
            
            if batch_result.get("task_ids"):
                all_task_ids.extend(batch_result["task_ids"])

            logger.info(f"     ✅ success: {group_success}, failed: {group_failed}")

        # Send notification
        await send_completion_notification(
            user_id=user_id,
            total=total_stocks,
            success=total_success,
            failed=total_failed,
            results=[],
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            send_in_app_notification=True,
            send_email_notification=False,
        )

        if all_task_ids:
            asyncio.create_task(
                _send_scheduled_completion_email_when_ready(
                    user_id=user_id,
                    task_ids=all_task_ids,
                    total=total_stocks,
                    analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
            )

        # Update configuration last run time
        from app.utils.timezone import now_tz
        await db.scheduled_analysis_configs.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": {"last_run_at": now_tz()}}
        )
        
        # Record execution history
        try:
            history_doc = {
                "config_id": config_id,
                "config_name": config.get("name", "Unnamed"),
                "time_slot_name": slot.get("name", "Unnamed"),
                "created_at": now_tz(),
                "status": "success" if total_failed == 0 else ("failed" if total_success == 0 else "partial"),
                "total_count": total_stocks,
                "success_count": total_success,
                "failed_count": total_failed,
                "task_ids": all_task_ids,
                "result_summary": None
            }
            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as e:
            logger.error(f"❌ Recording execution history failed: {e}")

        logger.info("=" * 70)
        logger.info("✅ Scheduled analysis time period task completed")
        logger.info(f"   Total number of shares: {total_stocks}")
        logger.info(f"   Successfully started: {total_success} analysis tasks")
        logger.info(f"   failed: {total_failed} a")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Scheduled analysis time period task execution failed: {e}", exc_info=True)

        # Record failure history to ensure that the front end can see execution failure records
        try:
            from app.utils.timezone import now_tz
            from bson import ObjectId
            db = get_mongo_db()
            history_doc = {
                "config_id": config_id,
                "config_name": "unknown",
                "time_slot_name": "unknown",
                "created_at": now_tz(),
                "status": "failed",
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "task_ids": [],
                "result_summary": f"Execution exception: {str(e)[:200]}"
            }
            # Try to get the configuration name
            try:
                config = await db.scheduled_analysis_configs.find_one({"_id": ObjectId(config_id)})
                if config:
                    history_doc["config_name"] = config.get("name", "unknown")
                    time_slots = config.get("time_slots", [])
                    if slot_index < len(time_slots):
                        history_doc["time_slot_name"] = time_slots[slot_index].get("name", "unknown")
            except Exception:
                pass

            await db.scheduled_analysis_history.insert_one(history_doc)
        except Exception as hist_err:
            logger.error(f"❌ Recording failure history also failed: {hist_err}")

