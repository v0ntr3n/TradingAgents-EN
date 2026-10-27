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


def _is_etf_code(code: str) -> bool:
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
            if not _is_etf_code(code):
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
            if not _is_etf_code(code):
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
            if not _is_etf_code(code):
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
                if not _is_etf_code(code):
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
            if not _is_etf_code(code):
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
            if not _is_etf_code(code):
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
        if not _is_etf_code(code):
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
                if _is_etf_code(normalized)
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
