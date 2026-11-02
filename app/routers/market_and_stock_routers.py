from __future__ import annotations
import sys as _sys
import types as _types
import app.routers as _routers_pkg
_self_mod = _sys.modules[__name__]
_snapshots = {}

# === stocks.py ===
"""
Stock details related API
- Unified response package: {success, data, message, timestamp}
- All endpoints require authentication (Bearer Token)
- The path prefix is mounted as /api in main.py, and the prefix of the current route itself is /stocks
"""
from datetime import date, datetime
from typing import Optional, Dict, Any, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Query
import asyncio
import logging
import re

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from core.skill_runtime.fundamental_factors import get_fundamental_factor_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["stocks"])


FINANCIAL_RAW_GROUPS = [
    "income_statement",
    "balance_sheet",
    "cashflow_statement",
    "financial_indicators",
    "main_business",
]


def _pick_first_value(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _build_financial_summary(financial_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not financial_data:
        return {}

    indicators = financial_data.get("financial_indicators") or {}

    summary = {
        "report_period": financial_data.get("report_period"),
        "report_type": financial_data.get("report_type"),
        "ann_date": financial_data.get("ann_date"),
        "data_source": financial_data.get("data_source"),
        "revenue": financial_data.get("revenue"),
        "revenue_ttm": financial_data.get("revenue_ttm"),
        "oper_rev": financial_data.get("oper_rev"),
        "net_income": financial_data.get("net_income"),
        "net_profit": financial_data.get("net_profit"),
        "net_profit_ttm": financial_data.get("net_profit_ttm"),
        "oper_profit": financial_data.get("oper_profit"),
        "total_profit": financial_data.get("total_profit"),
        "gross_margin": _pick_first_value(financial_data.get("gross_margin"), indicators.get("gross_margin")),
        "netprofit_margin": _pick_first_value(financial_data.get("netprofit_margin"), indicators.get("netprofit_margin")),
        "roe": _pick_first_value(financial_data.get("roe"), indicators.get("roe"), indicators.get("roe_avg")),
        "roa": _pick_first_value(financial_data.get("roa"), indicators.get("roa")),
        "roe_waa": financial_data.get("roe_waa"),
        "roe_dt": financial_data.get("roe_dt"),
        "debt_to_assets": _pick_first_value(financial_data.get("debt_to_assets"), indicators.get("debt_to_assets")),
        "assets_to_eqt": _pick_first_value(financial_data.get("assets_to_eqt"), indicators.get("assets_to_eqt")),
        "current_ratio": _pick_first_value(financial_data.get("current_ratio"), indicators.get("current_ratio")),
        "quick_ratio": _pick_first_value(financial_data.get("quick_ratio"), indicators.get("quick_ratio")),
        "cash_ratio": _pick_first_value(financial_data.get("cash_ratio"), indicators.get("cash_ratio")),
        "total_assets": financial_data.get("total_assets"),
        "total_liab": financial_data.get("total_liab"),
        "total_equity": financial_data.get("total_equity"),
        "total_cur_assets": financial_data.get("total_cur_assets"),
        "total_cur_liab": financial_data.get("total_cur_liab"),
        "money_cap": financial_data.get("money_cap"),
        "accounts_receiv": financial_data.get("accounts_receiv"),
        "inventories": financial_data.get("inventories"),
        "fix_assets": financial_data.get("fix_assets"),
        "n_cashflow_act": financial_data.get("n_cashflow_act"),
        "n_cashflow_inv_act": financial_data.get("n_cashflow_inv_act"),
        "n_cashflow_fin_act": financial_data.get("n_cashflow_fin_act"),
        "c_cash_equ_end_period": financial_data.get("c_cash_equ_end_period"),
        "c_cash_equ_beg_period": financial_data.get("c_cash_equ_beg_period"),
        "updated_at": financial_data.get("updated_at"),
    }

    return {k: v for k, v in summary.items() if v is not None}


def _build_financial_raw_data(financial_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not financial_data:
        return {}

    raw_data = financial_data.get("raw_data") or {}
    result: Dict[str, Any] = {}
    for group in FINANCIAL_RAW_GROUPS:
        if raw_data.get(group):
            result[group] = raw_data.get(group)
    return result


def _get_p0_fundamental_snapshot(symbol: str) -> Dict[str, Any]:
    try:
        # allow_remote_fetch=False: This function only serves the interactive interface (factor preview/financial details page),
        # When the local dividend details are missing, it is prohibited to pull Tushare on-site (about 20 seconds), and the synchronized dividend rate snapshot is used for downgrade;
        # Data should be actively obtained through the data synchronization function, in line with"Verify read-only, pull only after synchronization"semantics
        return get_fundamental_factor_snapshot(symbol, allow_remote_fetch=False) or {}
    except Exception as e:
        logger.warning("Failed to obtain P0 fundamental snapshot %s: %s", symbol, e)
        return {}


def _merge_snapshot_fields_into_fundamentals(data: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot:
        return data

    factors = snapshot.get("factors") or {}
    if factors.get("pe") is not None:
        data["pe"] = factors.get("pe")
    if factors.get("pe_ttm") is not None:
        data["pe_ttm"] = factors.get("pe_ttm")
    if factors.get("pb") is not None:
        data["pb"] = factors.get("pb")
    if factors.get("pb_mrq") is not None:
        data["pb_mrq"] = factors.get("pb_mrq")
    if factors.get("ps_ttm") is not None:
        data["ps_ttm"] = factors.get("ps_ttm")
        if data.get("ps") is None:
            data["ps"] = factors.get("ps_ttm")

    fundamentals_field_map = {
        "dividend_yield": "dividend_yield",
        "roe": "roe",
        "roa": "roa",
        "gross_margin": "gross_margin",
        "netprofit_margin": "netprofit_margin",
        "debt_to_assets": "debt_ratio",
        "assets_to_eqt": "assets_to_eqt",
        "current_ratio": "current_ratio",
        "quick_ratio": "quick_ratio",
        "cash_ratio": "cash_ratio",
        "revenue_ttm": "revenue_ttm",
        "net_profit_ttm": "net_profit_ttm",
        "n_cashflow_act": "n_cashflow_act",
    }
    for snapshot_field, response_field in fundamentals_field_map.items():
        if factors.get(snapshot_field) is not None:
            data[response_field] = factors.get(snapshot_field)

    if factors.get("debt_to_assets") is not None:
        data["debt_to_assets"] = factors.get("debt_to_assets")

    if snapshot.get("report_period"):
        data["report_period"] = snapshot.get("report_period")
    if snapshot.get("data_source"):
        data["financial_data_source"] = snapshot.get("data_source")

    if snapshot.get("factor_diagnostics"):
        data["factor_diagnostics"] = snapshot.get("factor_diagnostics")
    if snapshot.get("factor_warnings"):
        data["factor_warnings"] = snapshot.get("factor_warnings")

    return data


def _merge_snapshot_fields_into_financial_summary(summary: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot:
        return summary

    factors = snapshot.get("factors") or {}
    summary_field_map = {
        "roe": "roe",
        "roa": "roa",
        "gross_margin": "gross_margin",
        "netprofit_margin": "netprofit_margin",
        "debt_to_assets": "debt_to_assets",
        "assets_to_eqt": "assets_to_eqt",
        "current_ratio": "current_ratio",
        "quick_ratio": "quick_ratio",
        "cash_ratio": "cash_ratio",
        "revenue_ttm": "revenue_ttm",
        "net_profit_ttm": "net_profit_ttm",
        "n_cashflow_act": "n_cashflow_act",
    }
    for snapshot_field, summary_field in summary_field_map.items():
        if factors.get(snapshot_field) is not None:
            summary[summary_field] = factors.get(snapshot_field)

    if snapshot.get("report_period"):
        summary["report_period"] = snapshot.get("report_period")

    return summary


async def _get_cn_source_priority() -> List[str]:
    """Returns the enabled A-share data source priority according to system configuration. The larger the number, the higher the priority."""
    try:
        from app.core.unified_config import UnifiedConfigManager

        config = UnifiedConfigManager()
        data_source_configs = await config.get_data_source_configs_async()
        enabled_sources = [
            ds.type.lower()
            for ds in data_source_configs
            if ds.enabled and ds.type.lower() in ["tushare", "multi_source", "akshare", "baostock"]
        ]
        if enabled_sources:
            return enabled_sources
    except Exception as e:
        logger.warning("Failed to get data source priority, using default order: %s", e)

    return ["tushare", "multi_source", "akshare", "baostock"]


def _zfill_code(code: str) -> str:
    try:
        s = str(code).strip()
        if len(s) == 6 and s.isdigit():
            return s
        return s.zfill(6)
    except Exception:
        return str(code)


ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _is_cn_etf_code(code: str) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _get_etf_market_label(code: str) -> str:
    return "ETF"


def _parse_trade_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _build_etf_fundamentals_data(etf_doc: Dict[str, Any], latest_quote: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    latest_quote = latest_quote or {}
    return {
        "code": etf_doc.get("code"),
        "name": etf_doc.get("name"),
        "industry": etf_doc.get("fund_type") or "ETF",
        "market": _get_etf_market_label(etf_doc.get("code")),
        "sector": etf_doc.get("track_index") or "ETF",
        "security_type": "ETF",
        "fund_type": etf_doc.get("fund_type") or "ETF",
        "track_index": etf_doc.get("track_index"),
        "fund_scale": etf_doc.get("fund_scale"),
        "fund_share": etf_doc.get("fund_share"),
        "fund_share_date": etf_doc.get("fund_share_date"),
        "management": etf_doc.get("management"),
        "custodian": etf_doc.get("custodian"),
        "management_fee": etf_doc.get("management_fee"),
        "custodian_fee": etf_doc.get("custodian_fee"),
        "unit_nav": _pick_first_value(etf_doc.get("unit_nav"), latest_quote.get("unit_nav")),
        "accum_nav": _pick_first_value(etf_doc.get("accum_nav"), latest_quote.get("accum_nav")),
        "nav_change_value": etf_doc.get("nav_change_value"),
        "nav_growth_rate": etf_doc.get("nav_growth_rate"),
        "market_price": _pick_first_value(latest_quote.get("close"), etf_doc.get("market_price")),
        "premium_discount_rate": etf_doc.get("premium_discount_rate"),
        "latest_nav_date": etf_doc.get("latest_nav_date"),
        "purchase_status": etf_doc.get("purchase_status"),
        "redemption_status": etf_doc.get("redemption_status"),
        "updated_at": _pick_first_value(latest_quote.get("updated_at"), etf_doc.get("updated_at")),
    }


async def _get_etf_basic_info_by_sources(db, code6: str, preferred_sources: List[str]) -> Optional[Dict[str, Any]]:
    for source in preferred_sources:
        doc = await db["etf_basic_info"].find_one(
            {"code": code6, "source": source},
            {"_id": 0},
            sort=[("updated_at", -1)]
        )
        if doc:
            return doc

    return await db["etf_basic_info"].find_one(
        {"code": code6},
        {"_id": 0},
        sort=[("updated_at", -1)]
    )


def _aggregate_etf_kline_rows(rows: List[Dict[str, Any]], period: str, limit: int) -> List[Dict[str, Any]]:
    parsed_rows = []
    for row in rows:
        trade_date = _parse_trade_date(row.get("trade_date"))
        if not trade_date:
            continue
        parsed_rows.append((trade_date, row))

    parsed_rows.sort(key=lambda item: item[0])
    if not parsed_rows:
        return []

    def build_bar(bar_rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
        opens = [float(r["open"]) for r in bar_rows if r.get("open") is not None]
        highs = [float(r["high"]) for r in bar_rows if r.get("high") is not None]
        lows = [float(r["low"]) for r in bar_rows if r.get("low") is not None]
        closes = [float(r["close"]) for r in bar_rows if r.get("close") is not None]
        volumes = [float(r["volume"]) for r in bar_rows if r.get("volume") is not None]
        amounts = [float(r["amount"]) for r in bar_rows if r.get("amount") is not None]

        return {
            "time": label,
            "open": opens[0] if opens else None,
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "close": closes[-1] if closes else None,
            "volume": sum(volumes) if volumes else None,
            "amount": sum(amounts) if amounts else None,
        }

    if period == "day":
        items = []
        for trade_date, row in parsed_rows[-limit:]:
            items.append({
                "time": trade_date.strftime("%Y-%m-%d"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
            })
        return items

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for trade_date, row in parsed_rows:
        if period == "week":
            iso_year, iso_week, _ = trade_date.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        else:
            key = trade_date.strftime("%Y-%m")
        grouped.setdefault(key, []).append(row)

    items = [build_bar(bar_rows, key) for key, bar_rows in grouped.items()]
    return items[-limit:]


def _detect_market_and_code(code: str) -> Tuple[str, str]:
    """
    Detect the market type of a ticker and standardize the ticker

    Args:
        code: Stock code

    Returns:
        (market, normalized_code): Market types and standardized codes
            - CN: A Share (6 digits)
            - HK: Hong Kong stocks (4-5 digits or with .HK suffix)
            - US: US stocks (letter code)
    """
    code = code.strip().upper()

    # Hong Kong stocks: with .HK suffix
    if code.endswith('.HK'):
        return ('HK', code[:-3].zfill(5))  # Remove .HK and fill it to 5 digits

    # US stocks: pure letters
    if re.match(r'^[A-Z]+$', code):
        return ('US', code)

    # Hong Kong stocks: 4-5 digits
    if re.match(r'^\d{4,5}$', code):
        return ('HK', code.zfill(5))  # Complete to 5 digits

    # A Share: 6 digits
    if re.match(r'^\d{6}$', code):
        return ('CN', code)

    # Treated as A shares by default
    return ('CN', _zfill_code(code))


@router.get("/{code}/quote", response_model=dict)
async def get_quote(
    code: str,
    force_refresh: bool = Query(False, description="Whether to force refresh (skip cache)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time stock quotes (supports A shares/Hong Kong stocks/US stocks)

    Automatically identify market types:
    - 6 digits → A shares
    - 4 digit or.HK → Hong Kong stocks
    - pure letters → US stocks

    Parameters:
    - code: Stock code
    - force_refresh: Whether to force refresh (skip cache)

    Return field (in data, named in snake shape):
      - code, name, market
      - price(close), change_percent(pct_chg), amount, prev_close(Estimate)
      - turnover_rate, amplitude (Amplitude, substitution ratio)
      - trade_date, updated_at
    """
    # Detect market type
    market, normalized_code = _detect_market_and_code(code)

    # Hong Kong and US stocks: using new services
    if market in ['HK', 'US']:
        from app.services.foreign_stock_service import ForeignStockService

        db = get_mongo_db()  # No need to await, return database object directly
        service = ForeignStockService(db=db)

        try:
            quote = await service.get_quote(market, normalized_code, force_refresh)
            return ok(data=quote)
        except Exception as e:
            logger.error(f"get{market}stocks{code}Quote failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get quotes: {str(e)}"
            )

    # A Share: Use existing logic
    db = get_mongo_db()
    code6 = normalized_code
    is_etf = _is_cn_etf_code(code6)

    q = None
    b = None

    if is_etf:
        # ETF: Check directly etf_daily_quotes + etf_basic_info (ETF does not exist in market_quotes)
        etf_q = await db["etf_daily_quotes"].find_one(
            {"code": code6}, sort=[("trade_date", -1)], projection={"_id": 0}
        )
        if etf_q:
            q = etf_q
        b = await db["etf_basic_info"].find_one({"code": code6}, {"_id": 0})
        logger.debug(f"🔍 ETF Query: code={code6}, quote={'✅' if q else '❌'}, basic={'✅' if b else '❌'}")
    else:
        # Stocks: check market_quotes
        q = await db["market_quotes"].find_one({"code": code6}, {"_id": 0})
        if q:
            logger.debug(f"🔍 market_quotes: code={code6} ✅ volume={q.get('volume')}, amount={q.get('amount')}")
        else:
            logger.debug(f"🔍 market_quotes: code={code6} ❌ Not found, will try to fall back")

        # Basic information - query by data source priority
        from app.core.unified_config import UnifiedConfigManager
        config = UnifiedConfigManager()
        data_source_configs = await config.get_data_source_configs_async()

        enabled_sources = [
            ds.type.lower() for ds in data_source_configs
            if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
        ]
        if not enabled_sources:
            enabled_sources = ['tushare', 'akshare', 'baostock']

        for src in enabled_sources:
            b = await db["stock_basic_info"].find_one({"code": code6, "source": src}, {"_id": 0})
            if b:
                break

        # Compatible with old data (without source condition)
        if not b:
            b = await db["stock_basic_info"].find_one({"code": code6}, {"_id": 0})

        # Fallback: check when stock_basic_info misses etf_basic_info + etf_daily_quotes
        if not b:
            b = await db["etf_basic_info"].find_one({"code": code6}, {"_id": 0})
        if not q:
            etf_q = await db["etf_daily_quotes"].find_one(
                {"code": code6}, sort=[("trade_date", -1)], projection={"_id": 0}
            )
            if etf_q:
                q = etf_q

    if not q and not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No information found for this stock")

    close = (q or {}).get("close")
    pct = (q or {}).get("pct_chg")
    pre_close_saved = (q or {}).get("pre_close")
    prev_close = pre_close_saved
    if prev_close is None:
        try:
            if close is not None and pct is not None:
                prev_close = round(float(close) / (1.0 + float(pct) / 100.0), 4)
        except Exception:
            prev_close = None

    # 🔥 Prioritize getting turnover_rate (real-time data) from market_quotes
    # If not in market_quotes, get it from stock_basic_info (daily data)
    turnover_rate = (q or {}).get("turnover_rate")
    turnover_rate_date = None
    if turnover_rate is None:
        turnover_rate = (b or {}).get("turnover_rate")
        turnover_rate_date = (b or {}).get("trade_date")  # From daily data
    else:
        turnover_rate_date = (q or {}).get("trade_date")  # from real-time data

    # 🔥 Calculate amplitude (amplitude) instead of volume ratio (volume_ratio)
    # Amplitude = (Highest price - Lowest price) / Yesterday's closing price × 100%
    amplitude = None
    amplitude_date = None
    try:
        high = (q or {}).get("high")
        low = (q or {}).get("low")
        logger.debug(f"🔍 Calculate amplitude: high={high}, low={low}, prev_close={prev_close}")
        if high is not None and low is not None and prev_close is not None and prev_close > 0:
            amplitude = round((float(high) - float(low)) / float(prev_close) * 100, 2)
            amplitude_date = (q or {}).get("trade_date")  # from real-time data
            logger.debug(f"  ✅ Amplitude calculation successful: {amplitude}%")
        else:
            logger.debug("  ⚠️ Incomplete data, unable to calculate amplitude")
    except Exception as e:
        logger.warning(f"  ❌ Failed to calculate amplitude: {e}")
        amplitude = None

    data = {
        "code": code6,
        "name": (b or {}).get("name"),
        "market": _get_etf_market_label(code6) if _is_cn_etf_code(code6) else (b or {}).get("market"),
        "price": close,
        "change_percent": pct,
        "amount": (q or {}).get("amount"),
        "volume": (q or {}).get("volume"),
        "open": (q or {}).get("open"),
        "high": (q or {}).get("high"),
        "low": (q or {}).get("low"),
        "prev_close": prev_close,
        # 🔥 Prioritize the use of real-time data and downgrade to daily data
        "turnover_rate": turnover_rate,
        "amplitude": amplitude,  # 🔥 New: Amplitude (Alternative Amount Ratio)
        "turnover_rate_date": turnover_rate_date,  # 🔥 New: turnover rate data date
        "amplitude_date": amplitude_date,  # 🔥 New: Amplitude Data Date
        "trade_date": (q or {}).get("trade_date"),
        "updated_at": (q or {}).get("updated_at"),
    }

    return ok(data)


@router.get("/{code}/fundamentals", response_model=dict)
async def get_fundamentals(
    code: str,
    source: Optional[str] = Query(None, description="data source (tushare/akshare/baostock/multi_source)"),
    force_refresh: bool = Query(False, description="Whether to force refresh (skip cache)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get fundamental snapshot (supports A shares/Hong Kong stocks/US stocks)

    Data source priority:
    1. stock_basic_info Collection (basic information, valuation indicators)
    2. stock_financial_data Collection (financial indicators: ROE, debt ratio, etc.)

    Parameters:
    - code: Stock code
    - source: Data source (optional), default by priority:tushare > multi_source > akshare > baostock
    - force_refresh: Whether to force refresh (skip cache)
    """
    # Detect market type
    market, normalized_code = _detect_market_and_code(code)

    # Hong Kong and US stocks: using new services
    if market in ['HK', 'US']:
        from app.services.foreign_stock_service import ForeignStockService

        db = get_mongo_db()  # No need to await, return database object directly
        service = ForeignStockService(db=db)

        try:
            info = await service.get_basic_info(market, normalized_code, force_refresh)
            return ok(data=info)
        except Exception as e:
            logger.error(f"get{market}stocks{code}Basic information failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to obtain basic information: {str(e)}"
            )

    # A Share: Use existing logic
    db = get_mongo_db()
    code6 = normalized_code
    # P0 The factor snapshot includes synchronized Mongo query and Tushare dividend data extraction, and the actual measurement can reach 20s+, 
    # The thread pool must be used for execution, otherwise the event loop will be blocked and the entire backend interface will become unresponsive.
    p0_snapshot = await asyncio.to_thread(_get_p0_fundamental_snapshot, code6)

    if _is_cn_etf_code(code6):
        if source:
            etf_doc = await db["etf_basic_info"].find_one(
                {"code": code6, "source": source},
                {"_id": 0},
                sort=[("updated_at", -1)]
            )
        else:
            etf_source_priority = [src for src in await _get_cn_source_priority() if src in ["tushare", "akshare", "baostock", "qmt"]]
            if not etf_source_priority:
                etf_source_priority = ["tushare", "akshare", "qmt"]
            etf_doc = await _get_etf_basic_info_by_sources(db, code6, etf_source_priority)

        latest_quote = await db["etf_daily_quotes"].find_one(
            {"code": code6},
            {"_id": 0},
            sort=[("trade_date", -1)]
        )

        if not etf_doc:
            if source:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"The ETF was not found in the data source {source} Basic information in")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No underlying information found for this ETF")

        return ok(data=_build_etf_fundamentals_data(etf_doc, latest_quote))

    # 1. Obtain basic information (supports data source filtering)
    query = {"code": code6}

    if source:
        # Specify data source
        query["source"] = source
        b = await db["stock_basic_info"].find_one(query, {"_id": 0})
        if not b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"The stock was not found in the data source {source} Basic information in"
            )
    else:
        # 🔥 No data source specified, query by priority
        source_priority = await _get_cn_source_priority()
        b = None

        for src in source_priority:
            query_with_source = {"code": code6, "source": src}
            b = await db["stock_basic_info"].find_one(query_with_source, {"_id": 0})
            if b:
                logger.info(f"✅ Use data sources: {src} Check stocks {code6}")
                break

        # If all data sources are not available, try querying without source conditions (compatible with old data)
        if not b:
            b = await db["stock_basic_info"].find_one({"code": code6}, {"_id": 0})
            if b:
                logger.warning(f"⚠️ Use old data (no source field): {code6}")

        if not b:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No basic information found for this stock")

    # 2. Try to get the latest financial metrics from stock_financial_data
    # 🔥 Query by data source priority rather than by timestamp to avoid mixing data from different data sources
    financial_data = None
    try:
        enabled_sources = [src for src in await _get_cn_source_priority() if src in ['tushare', 'akshare', 'baostock']]
        if not enabled_sources:
            enabled_sources = ['tushare', 'akshare', 'baostock']

        # Query financial data by data source priority
        for data_source in enabled_sources:
            financial_data = await db["stock_financial_data"].find_one(
                {"$or": [{"symbol": code6}, {"code": code6}], "data_source": data_source},
                {"_id": 0},
                sort=[("report_period", -1)]  # Get the latest data from this data source in descending order of reporting period
            )
            if financial_data:
                logger.info(f"✅ Use data sources {data_source} financial data (reporting period: {financial_data.get('report_period')})")
                break

        if not financial_data:
            logger.warning(f"⚠️ not found {code6} financial data")
    except Exception as e:
        logger.error(f"Failed to get financial data: {e}")

    # 3. Get real-time PE/PB (real-time calculation is preferred)
    from tradingagents.dataflows.realtime_metrics import get_pe_pb_with_fallback

    # Perform synchronized real-time calculations in a thread pool
    realtime_metrics = await asyncio.to_thread(
        get_pe_pb_with_fallback,
        code6,
        db.client
    )

    # 4. Build return data
    # 🔥 Prioritize using real-time market capitalization and downgrading to the static market capitalization of stock_basic_info
    realtime_market_cap = realtime_metrics.get("market_cap")  # Real-time market capitalization (100 million yuan)
    total_mv = realtime_market_cap if realtime_market_cap else b.get("total_mv")

    data = {
        "code": code6,
        "name": b.get("name"),
        "industry": b.get("industry"),  # Industry (e.g. banking, software services)
        "market": b.get("market"),      # Exchanges (such as: main board, GEM)

        # Sector information: use the market field (Main Board/GEM/Science and Technology Innovation Board/North Exchange, etc.)
        "sector": b.get("market"),

        # Valuation indicators (priority to real-time calculation, downgrade to stock_basic_info)
        "pe": realtime_metrics.get("pe") or b.get("pe"),
        "pb": realtime_metrics.get("pb") or b.get("pb"),
        "pe_ttm": realtime_metrics.get("pe_ttm") or b.get("pe_ttm"),
        "pb_mrq": realtime_metrics.get("pb_mrq") or b.get("pb_mrq"),

        # 🔥 Price to Sales (PS) - dynamic calculation (using real-time market capitalization)
        "ps": None,
        "ps_ttm": None,

        # PE/PB Data source identification
        "pe_source": realtime_metrics.get("source", "unknown"),
        "pe_is_realtime": realtime_metrics.get("is_realtime", False),
        "pe_updated_at": realtime_metrics.get("updated_at"),

        # ROE (Get it from stock_financial_data first, then stock_basic_info)
        "roe": None,

        # Debt ratio (obtained from stock_financial_data)
        "debt_ratio": None,

        # Extend financial fields
        "dividend_yield": b.get("dividend_yield"),
        "dividend_yield_ttm": b.get("dividend_yield_ttm"),
        "current_ratio": None,
        "quick_ratio": None,
        "cash_ratio": None,
        "gross_margin": None,
        "netprofit_margin": None,
        "revenue": None,
        "revenue_ttm": None,
        "net_income": None,
        "net_profit": None,
        "net_profit_ttm": None,
        "oper_profit": None,
        "total_profit": None,
        "total_assets": None,
        "total_liab": None,
        "total_equity": None,
        "n_cashflow_act": None,
        "report_period": None,
        "report_type": None,
        "ann_date": None,
        "financial_data_source": None,

        # Market capitalization: Give priority to real-time market capitalization and downgrade to static market capitalization.
        "total_mv": total_mv,
        "circ_mv": b.get("circ_mv"),

        # 🔥 Market value source identifier
        "mv_is_realtime": bool(realtime_market_cap),

        # Trading indicator (may be empty)
        "turnover_rate": b.get("turnover_rate"),
        "volume_ratio": b.get("volume_ratio"),

        "updated_at": b.get("updated_at"),
    }

    # 5. Extract ROE, gearing and calculations from financial data PS
    if financial_data:
        data["report_period"] = financial_data.get("report_period")
        data["report_type"] = financial_data.get("report_type")
        data["ann_date"] = financial_data.get("ann_date")
        data["financial_data_source"] = financial_data.get("data_source")

        # ROE (ROE)
        if financial_data.get("financial_indicators"):
            indicators = financial_data["financial_indicators"]
            data["roe"] = indicators.get("roe")
            data["debt_ratio"] = indicators.get("debt_to_assets")
            data["current_ratio"] = indicators.get("current_ratio")
            data["quick_ratio"] = indicators.get("quick_ratio")
            data["cash_ratio"] = indicators.get("cash_ratio")
            data["gross_margin"] = indicators.get("gross_margin")
            data["netprofit_margin"] = indicators.get("netprofit_margin")
            data["dividend_yield"] = data["dividend_yield"] or indicators.get("dividend_yield")

        # If there is no financial_indicators, try to get it from the top field
        if data["roe"] is None:
            data["roe"] = financial_data.get("roe")
        if data["debt_ratio"] is None:
            data["debt_ratio"] = financial_data.get("debt_to_assets")
        if data["current_ratio"] is None:
            data["current_ratio"] = financial_data.get("current_ratio")
        if data["quick_ratio"] is None:
            data["quick_ratio"] = financial_data.get("quick_ratio")
        if data["cash_ratio"] is None:
            data["cash_ratio"] = financial_data.get("cash_ratio")
        if data["gross_margin"] is None:
            data["gross_margin"] = financial_data.get("gross_margin")
        if data["netprofit_margin"] is None:
            data["netprofit_margin"] = financial_data.get("netprofit_margin")
        if data["dividend_yield"] is None:
            data["dividend_yield"] = financial_data.get("dividend_yield")

        for field in [
            "revenue",
            "revenue_ttm",
            "net_income",
            "net_profit",
            "net_profit_ttm",
            "oper_profit",
            "total_profit",
            "total_assets",
            "total_liab",
            "total_equity",
            "n_cashflow_act",
        ]:
            data[field] = financial_data.get(field)

        # 🔥 Dynamically calculate PS (price to sales ratio) - using real-time market cap
        # Priority is given to using TTM operating income, if not then single period operating income is used
        revenue_ttm = financial_data.get("revenue_ttm")
        revenue = financial_data.get("revenue")
        revenue_for_ps = revenue_ttm if revenue_ttm and revenue_ttm > 0 else revenue

        if revenue_for_ps and revenue_for_ps > 0:
            # 🔥 Use real-time market cap if available, otherwise use static market cap
            if total_mv and total_mv > 0:
                # Operating income unit: Yuan, needs to be converted into 100 million Yuan
                revenue_yi = revenue_for_ps / 100000000
                ps_calculated = total_mv / revenue_yi
                data["ps"] = round(ps_calculated, 2)
                data["ps_ttm"] = round(ps_calculated, 2) if revenue_ttm else None

    # 6. If there is no ROE in the financial data, use the
    if data["roe"] is None:
        data["roe"] = b.get("roe")

    if data["dividend_yield"] is None:
        data["dividend_yield"] = b.get("dividend_yield")

    data = _merge_snapshot_fields_into_fundamentals(data, p0_snapshot)

    return ok(data)


@router.get("/{code}/financials", response_model=dict)
async def get_financials(
    code: str,
    source: Optional[str] = Query(None, description="data source (tushare/akshare/baostock)"),
    include_raw: bool = Query(True, description="Whether to return raw_data grouping details"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the latest financial details of a stock.

    Main link interface, returns:
    1. summary: Snapshot of common financial fields
    2. raw_data: Original details grouped by income statement/balance sheet/cash flow/financial indicators/main business
    3. available_fields: List of top-level fields that are actually stored in the current document
    """
    market, normalized_code = _detect_market_and_code(code)
    if market != 'CN':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The current interface only supports A-share financial details")

    db = get_mongo_db()
    base_query: Dict[str, Any] = {"$or": [{"symbol": normalized_code}, {"code": normalized_code}]}

    financial_data = None
    if source:
        query = {**base_query, "data_source": source}
        financial_data = await db["stock_financial_data"].find_one(
            query,
            {"_id": 0},
            sort=[("report_period", -1), ("updated_at", -1)]
        )
    else:
        source_priority = [src for src in await _get_cn_source_priority() if src in ["tushare", "akshare", "baostock"]]
        for preferred_source in source_priority:
            query = {**base_query, "data_source": preferred_source}
            financial_data = await db["stock_financial_data"].find_one(
                query,
                {"_id": 0},
                sort=[("report_period", -1), ("updated_at", -1)]
            )
            if financial_data:
                logger.info("✅ financials The interface uses data source %s to query stocks %s", preferred_source, normalized_code)
                break

        if not financial_data:
            financial_data = await db["stock_financial_data"].find_one(
                base_query,
                {"_id": 0},
                sort=[("report_period", -1), ("updated_at", -1)]
            )
    if not financial_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "No financial data yet",
                "suggestion": "Please synchronize the financial data of the stock on the Data Synchronization page first",
                "sync_url": "/sync",
            }
        )

    summary = _build_financial_summary(financial_data)
    # P0 Factor snapshots are synchronously recalculated (including pulling from external data sources), and are placed in the thread pool to avoid blocking the event loop.
    p0_snapshot = await asyncio.to_thread(_get_p0_fundamental_snapshot, normalized_code)
    summary = _merge_snapshot_fields_into_financial_summary(summary, p0_snapshot)
    raw_data = _build_financial_raw_data(financial_data) if include_raw else {}
    available_fields = sorted(
        key for key in financial_data.keys()
        if key not in {"_id", "raw_data"} and financial_data.get(key) is not None
    )

    return ok(data={
        "code": normalized_code,
        "name": financial_data.get("name"),
        "data_source": financial_data.get("data_source"),
        "report_period": p0_snapshot.get("report_period") or financial_data.get("report_period"),
        "report_type": financial_data.get("report_type"),
        "ann_date": financial_data.get("ann_date"),
        "summary": summary,
        "factor_snapshot": p0_snapshot.get("factors") or {},
        "factor_diagnostics": p0_snapshot.get("factor_diagnostics") or {},
        "factor_warnings": p0_snapshot.get("factor_warnings") or {},
        "raw_data": raw_data,
        "available_fields": available_fields,
    })


@router.get("/{code}/kline", response_model=dict)
async def get_kline(
    code: str,
    period: str = "day",
    limit: int = 120,
    adj: str = "none",
    force_refresh: bool = Query(False, description="Whether to force refresh (skip cache)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get K-line data (supports A shares/Hong Kong stocks/US stocks)

    period: day/week/month/5m/15m/30m/60m
    adj: none/qfq/hfq
    force_refresh: Whether to force refresh (skip cache)

    🔥 New feature: Real-time K-line data for the day
    - During trading hours (09:30-15:00) : Get real-time data from market_quotes
    - After closing: Check whether the historical data has data for the current day, if not, get it from market_quotes
    """
    import logging
    from datetime import datetime, timedelta, time as dtime
    from zoneinfo import ZoneInfo
    logger = logging.getLogger(__name__)

    valid_periods = {"day","week","month","5m","15m","30m","60m"}
    if period not in valid_periods:
        raise HTTPException(status_code=400, detail=f"Not supported period: {period}")

    # Detect market type
    market, normalized_code = _detect_market_and_code(code)

    # Hong Kong and US stocks: using new services
    if market in ['HK', 'US']:
        from app.services.foreign_stock_service import ForeignStockService

        db = get_mongo_db()  # No need to await, return database object directly
        service = ForeignStockService(db=db)

        try:
            kline_data = await service.get_kline(market, normalized_code, period, limit, force_refresh)
            return ok(data={
                'code': normalized_code,
                'period': period,
                'items': kline_data,
                'source': 'cache_or_api'
            })
        except Exception as e:
            logger.error(f"get{market}stocks{code}K Line data failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to obtain K-line data: {str(e)}"
            )

    # A Share: Use existing logic
    code_padded = normalized_code

    if _is_cn_etf_code(code_padded):
        db = get_mongo_db()
        rows = await db["etf_daily_quotes"].find(
            {"code": code_padded},
            {"_id": 0}
        ).sort("trade_date", 1).to_list(length=2000)

        if not rows:
            etf_exists = await db["etf_basic_info"].find_one({"code": code_padded}, {"_id": 1})
            if not etf_exists:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No K-line data for this ETF found")
            return ok(data={
                "code": code_padded,
                "period": period,
                "items": [],
                "source": "etf_daily_quotes"
            })

        if period not in {"day", "week", "month"}:
            period = "day"

        items = _aggregate_etf_kline_rows(rows, period, limit)
        return ok(data={
            "code": code_padded,
            "period": period,
            "items": items,
            "source": "etf_daily_quotes"
        })

    adj_norm = None if adj in (None, "none", "", "null") else adj
    items = None
    source = None

    # Cycle Mapping: Front End -> MongoDB
    period_map = {
        "day": "daily",
        "week": "weekly",
        "month": "monthly",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "60m": "60min"
    }
    mongodb_period = period_map.get(period, "daily")

    # Get the current time (Beijing time)
    from app.core.config import settings
    tz = ZoneInfo(settings.TIMEZONE)
    now = datetime.now(tz)
    today_str_yyyymmdd = now.strftime("%Y%m%d")  # Format: 20251028 (for query)
    today_str_formatted = now.strftime("%Y-%m-%d")  # Format: 2025-10-28 (for return)

    # 1. Prioritize checking local data sources (stock_historical_data collection)
    try:
        from app.core.data_source_priority import get_preferred_data_source_async
        preferred_source = await get_preferred_data_source_async(market_category="a_shares")

        if preferred_source == 'local':
            logger.info("🔍 The preferred data source is local, try to obtain K-line data from stock_daily_quotes")
            db = get_mongo_db()
            collection = db.stock_daily_quotes

            # Query local historical data (asynchronous iteration)
            cursor = collection.find(
                {"symbol": code_padded, "data_source": "local", "period": period}
            ).sort("trade_date", 1).limit(limit)

            # Get data using asynchronous iteration
            local_klines = []
            async for kline in cursor:
                local_klines.append(kline)

            if local_klines:
                items = []
                for kline in local_klines:
                    items.append({
                        "time": kline.get("trade_date"),
                        "open": float(kline.get("open", 0)),
                        "high": float(kline.get("high", 0)),
                        "low": float(kline.get("low", 0)),
                        "close": float(kline.get("close", 0)),
                        "volume": float(kline.get("volume", 0)),
                        "amount": float(kline.get("amount", 0)) if "amount" in kline else None,
                    })
                source = "local"
                logger.info(f"✅ Obtained from local data source {len(items)} K-line data")
    except Exception as e:
        logger.warning(f"⚠️ Failed to obtain K-line from local data source: {e}")

    # 2. If there is no data in the local data source, try to get it from the MongoDB cache
    if not items:
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
            adapter = get_mongodb_cache_adapter()

            # Calculate date range
            end_date = now.strftime("%Y-%m-%d")
            start_date = (now - timedelta(days=limit * 2)).strftime("%Y-%m-%d")

            logger.info(f"🔍 Try to get K-line data from MongoDB cache: {code_padded}, period={period} (MongoDB: {mongodb_period}), limit={limit}")
            df = adapter.get_historical_data(code_padded, start_date, end_date, period=mongodb_period)

            if df is not None and not df.empty:
                # Convert DataFrame to list format
                items = []
                for _, row in df.tail(limit).iterrows():
                    items.append({
                        "time": row.get("trade_date", row.get("date", "")),  # Frontend expects time field
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", row.get("vol", 0))),
                        "amount": float(row.get("amount", 0)) if "amount" in row else None,
                    })
                source = "mongodb"
                logger.info(f"✅ Obtained from MongoDB cache {len(items)} K-line data")
        except Exception as e:
            logger.warning(f"⚠️ MongoDB Cache failed to obtain K line: {e}")

    # 3. If there is no data locally or cached, fall back to external API (with timeout protection)
    if not items:
        logger.info("📡 There is no data locally or in the cache, so it is downgraded to the outside. API")
        try:
            import asyncio
            from app.services.data_sources.manager import DataSourceManager

            mgr = DataSourceManager()
            # Add 10 second timeout protection
            items, source = await asyncio.wait_for(
                asyncio.to_thread(mgr.get_kline_with_fallback, code_padded, period, limit, adj_norm),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.error("❌ External API acquisition K line timeout (10 seconds)")
            raise HTTPException(status_code=504, detail="Retrieval of K-line data timed out, please try again later.")
        except Exception as e:
            logger.error(f"❌ External API failed to obtain K-line: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to obtain K-line data: {str(e)}")

    # 🔥 4. Check whether you need to add real-time data for the day (only for daily lines)
    if period == "day" and items:
        try:
            # Check whether there is data for the current day in the historical data (two date formats are supported)
            has_today_data = any(
                item.get("time") in [today_str_yyyymmdd, today_str_formatted]
                for item in items
            )

            # Determine whether it is during trading hours or post-closing buffer period
            current_time = now.time()
            is_weekday = now.weekday() < 5  # Monday to Friday

            # Trading hours:9:30-11:30, 13:00-15:00
            # Post-closing buffer period:15:00-15:30 (Make sure to get the closing price)
            is_trading_time = (
                is_weekday and (
                    (dtime(9, 30) <= current_time <= dtime(11, 30)) or
                    (dtime(13, 0) <= current_time <= dtime(15, 30))
                )
            )

            # 🔥 Only add real-time data during trading hours or during the post-close buffer period
            # No real-time data is added on non-trading days (weekends and holidays)
            should_fetch_realtime = is_trading_time

            if should_fetch_realtime:
                logger.info(f"🔥 Try to get the current day s real-time data from market_quotes: {code_padded} (trading hours: {is_trading_time}, Already have data for the day: {has_today_data})")

                db = get_mongo_db()
                market_quotes_coll = db["market_quotes"]

                # Check the real-time market conditions of the day
                realtime_quote = await market_quotes_coll.find_one({"code": code_padded})

                if realtime_quote:
                    # 🔥 Construct the K-line data of the day (using the unified date format YYYY-MM-DD)
                    today_kline = {
                        "time": today_str_formatted,  # 🔥 Use YYYY-MM-DD format to be consistent with historical data
                        "open": float(realtime_quote.get("open", 0)),
                        "high": float(realtime_quote.get("high", 0)),
                        "low": float(realtime_quote.get("low", 0)),
                        "close": float(realtime_quote.get("close", 0)),
                        "volume": float(realtime_quote.get("volume", 0)),
                        "amount": float(realtime_quote.get("amount", 0)),
                    }

                    # If there is data for the current day in the historical data, replace it; otherwise, append it.
                    if has_today_data:
                        # Replace the last piece of data (assuming the last piece is from the current day)
                        items[-1] = today_kline
                        logger.info(f"✅ Replace the K-line data of the day: {code_padded}")
                    else:
                        # Append to the end
                        items.append(today_kline)
                        logger.info(f"✅ Add K-line data for the day: {code_padded}")

                    source = f"{source}+market_quotes"
                else:
                    logger.warning(f"⚠️ market_quotes No data for the day found in: {code_padded}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain real-time data of the day (ignored): {e}")

    data = {
        "code": code_padded,
        "period": period,
        "limit": limit,
        "adj": adj if adj else "none",
        "source": source,
        "items": items or []
    }
    return ok(data)


@router.get("/{code}/news", response_model=dict)
async def get_news(code: str, days: int = 30, limit: int = 50, include_announcements: bool = True, current_user: dict = Depends(get_current_user)):
    """Get news and announcements (supports A shares, Hong Kong stocks, and US stocks)"""
    from app.services.foreign_stock_service import ForeignStockService
    from app.services.news_data_service import get_news_data_service, NewsQueryParams

    # Detect stock type
    market, normalized_code = _detect_market_and_code(code)

    if market == 'US':
        # US stocks: use ForeignStockService
        service = ForeignStockService()
        result = await service.get_us_news(normalized_code, days=days, limit=limit)
        return ok(result)
    elif market == 'HK':
        # Hong Kong stocks: Use ForeignStockService (including yfinance / finnhub / akshare fallback)
        service = ForeignStockService()
        result = await service.get_hk_news(normalized_code, days=days, limit=limit)
        return ok(result)
    else:
        # A Share: Directly call the query method of the synchronization service (including intelligent fallback logic)
        try:
            logger.info("=" * 80)
            logger.info(f"📰 Start getting news: code={code}, normalized_code={normalized_code}, days={days}, limit={limit}")

            # Directly use the query logic of news_data routing
            from app.services.news_data_service import get_news_data_service, NewsQueryParams
            from datetime import datetime, timedelta
            from app.worker.akshare_sync_service import get_akshare_sync_service

            service = await get_news_data_service()
            sync_service = await get_akshare_sync_service()

            # Calculation time range
            hours_back = days * 24

            # 🔥 Without setting start_time limit, directly query the latest N news
            # Because the news in the database may not be from the last few days, but historical data
            params = NewsQueryParams(
                symbol=normalized_code,
                limit=limit,
                sort_by="publish_time",
                sort_order=-1
            )

            logger.info(f"🔍 query parameters: symbol={params.symbol}, limit={params.limit} (No time limit)")

            # 1. First query from the database
            logger.info("📊 steps 1: Query news from database...")
            news_list = await service.query_news(params)
            logger.info(f"📊 Database query results: Return {len(news_list)} news")

            data_source = "database"

            # 2. If there is no data in the database, call the synchronization service
            if not news_list:
                logger.info(f"⚠️ There is no news data in the database. Call the synchronization service to obtain it.: {normalized_code}")
                try:
                    # 🔥 Call the synchronization service, passing in a single stock symbol list
                    logger.info("📡 steps 2: Call synchronization service...")
                    await sync_service.sync_news_data(
                        symbols=[normalized_code],
                        max_news_per_stock=limit,
                        force_update=False,
                        favorites_only=False
                    )

                    # Query again
                    logger.info("🔄 steps 3: Query again from database...")
                    news_list = await service.query_news(params)
                    logger.info(f"📊 Query results again: Return {len(news_list)} news")
                    data_source = "realtime"

                except Exception as e:
                    logger.error(f"❌ Synchronization service exception: {e}", exc_info=True)

            # Convert to old format (frontend compatible)
            logger.info("🔄 steps 4: Convert data format...")
            items = []
            for news in news_list:
                # 🔥 Convert datetime object to ISO string
                publish_time = news.get("publish_time", "")
                if isinstance(publish_time, datetime):
                    publish_time = publish_time.isoformat()

                items.append({
                    "title": news.get("title", ""),
                    "source": news.get("source", ""),
                    "time": publish_time,
                    "url": news.get("url", ""),
                    "type": "news",
                    "content": news.get("content", ""),
                    "summary": news.get("summary", "")
                })

            logger.info(f"✅ Conversion completed: {len(items)} news")

            data = {
                "code": normalized_code,
                "days": days,
                "limit": limit,
                "include_announcements": include_announcements,
                "source": data_source,
                "items": items
            }

            logger.info(f"📤 eventually return: source={data_source}, items_count={len(items)}")
            logger.info("=" * 80)
            return ok(data)

        except Exception as e:
            logger.error(f"❌ Failed to get news: {e}", exc_info=True)
            data = {
                "code": normalized_code,
                "days": days,
                "limit": limit,
                "include_announcements": include_announcements,
                "source": None,
                "items": []
            }
            return ok(data)

_snapshots['stocks'] = dict(globals())

# === multi_market_stocks.py ===
"""
Multi-market stock API routing
Supports unified query interface for A-shares, Hong Kong stocks, and US stocks

Function:
1. Cross-market stock information query
2. Multiple data source priority query
3. Unified response format

path prefix: /api/markets
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from app.services.unified_stock_service import UnifiedStockService

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/markets", tags=["multi-market"])


@router.get("", response_model=dict)
async def get_supported_markets(current_user: dict = Depends(get_current_user)):
    """
    Get a list of supported markets
    
    Returns:
        {
            "success": true,
            "data": {
                "markets": [
                    {
                        "code": "CN",
                        "name": "A shares",
                        "name_en": "China A-Shares",
                        "currency": "CNY",
                        "timezone": "Asia/Shanghai"
                    },
                    ...
                ]
            }
        }
    """
    markets = [
        {
            "code": "CN",
            "name": "A shares",
            "name_en": "China A-Shares",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "trading_hours": "09:30-15:00"
        },
        {
            "code": "HK",
            "name": "Hong Kong stocks",
            "name_en": "Hong Kong Stocks",
            "currency": "HKD",
            "timezone": "Asia/Hong_Kong",
            "trading_hours": "09:30-16:00"
        },
        {
            "code": "US",
            "name": "US stocks",
            "name_en": "US Stocks",
            "currency": "USD",
            "timezone": "America/New_York",
            "trading_hours": "09:30-16:00 EST"
        }
    ]
    
    return ok(data={"markets": markets})


@router.get("/{market}/stocks/search", response_model=dict)
async def search_stocks(
    market: str,
    q: str = Query(..., description="Search keyword (code or name)"),
    limit: int = Query(20, ge=1, le=100, description="Number of results returned"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for stocks (multi-market supported)
    
    Args:
        market: market type (CN/HK/US)
        q: Search keywords
        limit: Number of results returned
    
    Returns:
        {
            "success": true,
            "data": {
                "stocks": [
                    {
                        "code": "00700",
                        "name": "Tencent Holdings",
                        "name_en": "Tencent Holdings",
                        "market": "HK",
                        "source": "yfinance",
                        ...
                    }
                ],
                "total": 1
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        results = await service.search_stocks(market, q, limit)
        return ok(data={
            "stocks": results,
            "total": len(results)
        })
    except Exception as e:
        logger.error(f"❌ Stock search failed: market={market}, q={q}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/info", response_model=dict)
async def get_stock_info(
    market: str,
    code: str,
    source: Optional[str] = Query(None, description="Specify data source (optional)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtain basic stock information (supports multiple markets and multiple data sources)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
        source: Specify the data source (optional, if not specified, it will be automatically selected according to priority)
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "name": "Tencent Holdings",
                "name_en": "Tencent Holdings",
                "market": "HK",
                "source": "yfinance",
                "total_mv": 32000.0,
                "pe": 25.5,
                "pb": 4.2,
                "lot_size": 100,
                "currency": "HKD",
                ...
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        stock_info = await service.get_stock_info(market, code, source)
        
        if not stock_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No stock found: {market}:{code}"
            )
        
        return ok(data=stock_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to obtain stock information: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain stock information: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/quote", response_model=dict)
async def get_stock_quote(
    market: str,
    code: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time stock quotes (supports multiple markets)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "close": 320.50,
                "pct_chg": 2.15,
                "open": 315.00,
                "high": 325.00,
                "low": 312.00,
                "volume": 48500000,
                "amount": 15800000000,
                "trade_date": "2024-01-15",
                "currency": "HKD",
                ...
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        quote = await service.get_stock_quote(market, code)
        
        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No stock quotes found: {market}:{code}"
            )
        
        return ok(data=quote)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get stock quotes: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock quotes: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/daily", response_model=dict)
async def get_stock_daily_quotes(
    market: str,
    code: str,
    start_date: Optional[str] = Query(None, description="start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="end date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Return the number of records"),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtain stock historical K-line data (supports multiple markets)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
        start_date: start date
        end_date: end date
        limit: Return the number of records
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "market": "HK",
                "quotes": [
                    {
                        "trade_date": "2024-01-15",
                        "open": 315.00,
                        "high": 325.00,
                        "low": 312.00,
                        "close": 320.50,
                        "volume": 48500000,
                        "amount": 15800000000
                    },
                    ...
                ],
                "total": 100
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        quotes = await service.get_daily_quotes(
            market, code, start_date, end_date, limit
        )
        
        return ok(data={
            "code": code,
            "market": market,
            "quotes": quotes,
            "total": len(quotes)
        })
    except Exception as e:
        logger.error(f"❌ Failed to obtain historical K-line: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain historical K-line: {str(e)}"
        )

_snapshots['multi_market_stocks'] = dict(globals())

# === stock_data.py ===
"""
Stock Data API Routing - Based on Extended Data Model
Provide standardized stock data access interface
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.services.stock_data_service import get_stock_data_service
from app.models import (
    StockBasicInfoResponse,
    MarketQuotesResponse,
    StockListResponse,
    StockBasicInfoExtended,
    MarketQuotesExtended,
    MarketType
)
from app.core.response import ok

router = APIRouter(prefix="/api/stock-data", tags=["stock data"])


# ==================== Batch import request model ====================

class StockBasicInfoBatchRequest(BaseModel):
    """Save basic stock information requests in batches"""
    stocks: List[Dict[str, Any]] = Field(..., description="List of basic stock information")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


class MarketQuotesBatchRequest(BaseModel):
    """Save real-time quotation requests in batches"""
    quotes: List[Dict[str, Any]] = Field(..., description="Market data list")
    overwrite: bool = Field(True, description="Whether to overwrite existing data (the market overwrites it by default)")


# ==================== Query interface ====================

@router.get("/basic-info/{symbol}", response_model=StockBasicInfoResponse)
async def get_stock_basic_info(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get basic stock information

    Args:
        symbol: Stock code (Supports 6-digit A-share code)

    Returns:
        StockBasicInfoResponse: Basic stock information including extended fields
    """
    try:
        service = get_stock_data_service()
        stock_info = await service.get_stock_basic_info(symbol)

        if not stock_info:
            return StockBasicInfoResponse(
                success=False,
                message=f"Stock symbol not found {symbol} basic information"
            )

        return StockBasicInfoResponse(
            success=True,
            data=stock_info,
            message="get success"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain basic stock information: {str(e)}"
        )


@router.get("/quotes/{symbol}", response_model=MarketQuotesResponse)
async def get_market_quotes(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time market data

    Args:
        symbol: Stock code (Supports 6-digit A-share code)

    Returns:
        MarketQuotesResponse: Real-time market data including extended fields
    """
    try:
        service = get_stock_data_service()
        quotes = await service.get_market_quotes(symbol)

        if not quotes:
            return MarketQuotesResponse(
                success=False,
                message=f"Stock symbol not found {symbol} market data"
            )

        return MarketQuotesResponse(
            success=True,
            data=quotes,
            message="get success"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain real-time quotes: {str(e)}"
        )


@router.get("/list", response_model=StockListResponse)
async def get_stock_list(
    market: Optional[str] = Query(None, description="Market screening"),
    industry: Optional[str] = Query(None, description="Industry screening"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="page size"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a list of stocks
    
    Args:
        market: Market screening (Optional)
        industry: Industry screening (Optional)
        page: Page number (Start from 1)
        page_size: page size (1-100)
        
    Returns:
        StockListResponse: Stock list data
    """
    try:
        service = get_stock_data_service()
        stock_list = await service.get_stock_list(
            market=market,
            industry=industry,
            page=page,
            page_size=page_size
        )
        
        # Calculate the total (Simplify the implementation, in fact it should be queried separately)
        total = len(stock_list)
        
        return StockListResponse(
            success=True,
            data=stock_list,
            total=total,
            page=page,
            page_size=page_size,
            message="get success"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock list: {str(e)}"
        )


@router.get("/combined/{symbol}")
async def get_combined_stock_data(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive stock data (Basic information + Real-time quotes)

    Args:
        symbol: Stock code

    Returns:
        dict: Comprehensive data including basic information and real-time market conditions
    """
    try:
        service = get_stock_data_service()

        # Obtain basic information and market data in parallel
        import asyncio
        basic_info_task = service.get_stock_basic_info(symbol)
        quotes_task = service.get_market_quotes(symbol)

        basic_info, quotes = await asyncio.gather(
            basic_info_task,
            quotes_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(basic_info, Exception):
            basic_info = None
        if isinstance(quotes, Exception):
            quotes = None

        if not basic_info and not quotes:
            return {
                "success": False,
                "message": f"Stock symbol not found {symbol} any data of"
            }

        return {
            "success": True,
            "data": {
                "basic_info": basic_info.dict() if basic_info else None,
                "quotes": quotes.dict() if quotes else None,
                "symbol": symbol,
                "timestamp": quotes.updated_at if quotes else None
            },
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain comprehensive stock data: {str(e)}"
        )


@router.get("/search")
async def search_stocks(
    keyword: str = Query(..., min_length=1, description="Search keywords"),
    limit: int = Query(10, ge=1, le=50, description="Return quantity limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search stocks
    
    Args:
        keyword: Search keywords (Stock code or name)
        limit: Return quantity limit
        
    Returns:
        dict: Search results
    """
    try:
        from app.core.database import get_mongo_db
        from app.core.data_source_priority import get_preferred_data_source_async

        db = get_mongo_db()
        collection = db.stock_basic_info

        # 🔥 Use unified data source priority management functions
        preferred_source = await get_preferred_data_source_async(market_category="a_shares")

        # Build search criteria
        search_conditions = []

        # If it is a 6-digit number, match it exactly according to the code
        if keyword.isdigit() and len(keyword) == 6:
            search_conditions.append({"symbol": keyword})
        else:
            # Fuzzy match by name
            search_conditions.append({"name": {"$regex": keyword, "$options": "i"}})
            # Also attempts code matching if numbers are included
            if any(c.isdigit() for c in keyword):
                search_conditions.append({"symbol": {"$regex": keyword}})

        # 🔥 Add data source filtering: only query the data source with the highest priority
        query = {
            "$and": [
                {"$or": search_conditions},
                {"source": preferred_source}
            ]
        }

        # Perform a search
        cursor = collection.find(query, {"_id": 0}).limit(limit)

        results = await cursor.to_list(length=limit)

        # Data normalization
        service = get_stock_data_service()
        standardized_results = []
        for doc in results:
            standardized_doc = service._standardize_basic_info(doc)
            standardized_results.append(standardized_doc)

        return {
            "success": True,
            "data": standardized_results,
            "total": len(standardized_results),
            "keyword": keyword,
            "source": preferred_source,  # 🔥 Return data source
            "message": "Search completed"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stock search failed: {str(e)}"
        )


@router.get("/markets")
async def get_market_summary(
    current_user: dict = Depends(get_current_user)
):
    """
    Get a market overview

    Returns:
        dict: Statistics on the number of stocks in each market
    """
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()
        collection = db.stock_basic_info

        # Count the number of stocks in each market
        pipeline = [
            {
                "$group": {
                    "_id": "$market",
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"count": -1}
            }
        ]

        cursor = collection.aggregate(pipeline)
        market_stats = await cursor.to_list(length=None)

        # Total statistics
        total_count = await collection.count_documents({})

        return {
            "success": True,
            "data": {
                "total_stocks": total_count,
                "market_breakdown": market_stats,
                "supported_markets": ["CN"],  # Currently supported markets
                "last_updated": None  # The latest update time can be obtained from the data
            },
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get market overview: {str(e)}"
        )


@router.get("/sync-status/quotes")
async def get_quotes_sync_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time market synchronization status

    Returns:
        dict: {
            "success": True,
            "data": {
                "last_sync_time": "2025-10-28 15:06:00",
                "last_sync_time_iso": "2025-10-28T15:06:00+08:00",
                "interval_seconds": 360,
                "interval_minutes": 6,
                "data_source": "tushare",
                "success": True,
                "records_count": 5440,
                "error_message": None
            },
            "message": "get success"
        }
    """
    try:
        from app.services.quotes_ingestion_service import QuotesIngestionService

        service = QuotesIngestionService()
        status_data = await service.get_sync_status()

        return {
            "success": True,
            "data": status_data,
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync status: {str(e)}"
        )


# ==================== Batch import interface ====================

@router.post("/save-basic-info", response_model=dict, dependencies=[Depends(require_pro)])
async def save_basic_info_batch(
    request: StockBasicInfoBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save basic stock information in batches (optimized version)[PRO]

    Allow users to import basic stock information data in batches through API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request with stock list and data source ID

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "skipped": skip quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime
        from pymongo import UpdateOne, InsertOne
        import logging

        logger = logging.getLogger(__name__)
        db = get_mongo_db()
        collection = db.stock_basic_info

        # Data validation and preprocessing
        valid_stocks = []
        errors = []
        failed_count = 0

        for idx, stock_data in enumerate(request.stocks):
            try:
                # ==================== 1. Validate required fields ====================
                if "symbol" not in stock_data or "name" not in stock_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: symbol or name"
                    })
                    failed_count += 1
                    continue

                # Verify symbol format (6 digits)
                symbol = stock_data["symbol"]
                if not (isinstance(symbol, str) and symbol.isdigit() and len(symbol) == 6):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "symbol Must be 6 digits"
                    })
                    failed_count += 1
                    continue

                # ==================== 2. Validate core business fields (must have values) ====================
                # These fields are the basis for analysis and must be provided
                required_fields = {
                    "area": "area",
                    "industry": "Industry",
                    "list_date": "Listing date"
                }

                missing_fields = []
                for field, field_name in required_fields.items():
                    if field not in stock_data or not stock_data[field]:
                        missing_fields.append(field_name)

                if missing_fields:
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": f"Missing core business fields: {', '.join(missing_fields)}"
                    })
                    failed_count += 1
                    continue

                # ==================== 3. Validate financial data fields (provide at least one set) ====================
                # Market capitalization data group
                has_market_cap = ("total_mv" in stock_data and stock_data["total_mv"]) or \
                                ("circ_mv" in stock_data and stock_data["circ_mv"])

                # financial ratio group
                has_financial_ratios = any(
                    field in stock_data and stock_data[field]
                    for field in ["pe", "pb", "ps", "pe_ttm", "pb_mrq", "ps_ttm", "roe"]
                )

                # Equity data group
                has_share_capital = ("total_share" in stock_data and stock_data["total_share"]) or \
                                   ("float_share" in stock_data and stock_data["float_share"])

                # There must be at least one set of financial data
                if not (has_market_cap or has_financial_ratios or has_share_capital):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "Missing financial data: Must provide at least market capitalization(total_mv/circ_mv), financial ratios(pe/pb/ps Wait)or share capital(total_share/float_share)a set of data in"
                    })
                    failed_count += 1
                    continue

                # ==================== 4. Standardized field handling ====================
                # Make sure both code and symbol fields exist
                if "code" not in stock_data:
                    stock_data["code"] = symbol
                stock_data["symbol"] = symbol  # Standardized fields

                # Generate full_symbol if not provided
                if "full_symbol" not in stock_data:
                    # Determine the exchange based on the code prefix
                    if symbol.startswith(('6', '5')):  # Shanghai
                        stock_data["full_symbol"] = f"{symbol}.SH"
                    elif symbol.startswith(('0', '3', '2')):  # Shenzhen
                        stock_data["full_symbol"] = f"{symbol}.SZ"
                    elif symbol.startswith('8'):  # Beijing
                        stock_data["full_symbol"] = f"{symbol}.BJ"
                    else:
                        stock_data["full_symbol"] = symbol

                # Make sure the sse (exchange) field exists
                if "sse" not in stock_data:
                    if symbol.startswith(('6', '5')):
                        stock_data["sse"] = "Shanghai Stock Exchange"
                    elif symbol.startswith(('0', '3', '2')):
                        stock_data["sse"] = "Shenzhen Stock Exchange"
                    elif symbol.startswith('8'):
                        stock_data["sse"] = "Beijing Stock Exchange"
                    else:
                        stock_data["sse"] = "unknown"

                # Make sure the sec (classification) field exists
                if "sec" not in stock_data:
                    stock_data["sec"] = "stock_cn"

                # Make sure the category field exists
                if "category" not in stock_data:
                    stock_data["category"] = "stock_cn"

                # Add metadata (fixed use local as local data identifier)
                stock_data["source"] = "local"
                stock_data["updated_at"] = datetime.utcnow()

                valid_stocks.append((idx, stock_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "symbol": stock_data.get("symbol", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_stocks:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.stocks),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        symbols = [stock["symbol"] for _, stock in valid_stocks]
        existing_docs = await collection.find({
            "symbol": {"$in": symbols},
            "source": "local"
        }).to_list(length=None)

        existing_symbols = {doc["symbol"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, stock_data in valid_stocks:
            symbol = stock_data["symbol"]

            if symbol in existing_symbols:
                if request.overwrite:
                    # Batch update
                    stock_data["created_at"] = existing_symbols[symbol].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {"symbol": symbol, "source": "local"},
                            {"$set": stock_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                stock_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(stock_data))
                saved_count += 1

        # Perform batch operations
        if bulk_operations:
            try:
                result = await collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ Batch operation completed: Insert{result.inserted_count}, update{result.modified_count}")
            except Exception as e:
                logger.error(f"❌ Batch operation failed: {e}")
                # If the batch operation fails, fall back to inserting items one by one.
                logger.warning("⚠️ Return to item-by-item operation mode")
                saved_count = 0
                updated_count = 0

                for idx, stock_data in valid_stocks:
                    try:
                        symbol = stock_data["symbol"]
                        if symbol in existing_symbols and request.overwrite:
                            await collection.update_one(
                                {"symbol": symbol, "source": "local"},
                                {"$set": stock_data}
                            )
                            updated_count += 1
                        elif symbol not in existing_symbols:
                            await collection.insert_one(stock_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "symbol": stock_data.get("symbol", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.stocks),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save basic stock information in batches: {str(e)}"
        )


@router.post("/save-quotes", response_model=dict, dependencies=[Depends(require_pro)])
async def save_quotes_batch(
    request: MarketQuotesBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save real-time market data in batches (optimized version)[PRO]

    Allow users to import real-time market data in batches through API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request, including market list and data source identifier

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime
        from pymongo import UpdateOne, InsertOne
        import logging

        logger = logging.getLogger(__name__)
        db = get_mongo_db()
        collection = db.market_quotes

        # Data validation and preprocessing
        valid_quotes = []
        errors = []
        failed_count = 0

        for idx, quote_data in enumerate(request.quotes):
            try:
                # Validate required fields
                if "symbol" not in quote_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: symbol"
                    })
                    failed_count += 1
                    continue

                # Verify symbol format (6 digits)
                symbol = quote_data["symbol"]
                if not (isinstance(symbol, str) and symbol.isdigit() and len(symbol) == 6):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "symbol Must be 6 digits"
                    })
                    failed_count += 1
                    continue

                # Add metadata (fixed use local as local data identifier)
                quote_data["data_source"] = "local"
                quote_data["updated_at"] = datetime.utcnow()

                valid_quotes.append((idx, quote_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "symbol": quote_data.get("symbol", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_quotes:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "failed": failed_count,
                    "total": len(request.quotes),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        symbols = [quote["symbol"] for _, quote in valid_quotes]
        existing_docs = await collection.find({
            "symbol": {"$in": symbols}
        }).to_list(length=None)

        existing_symbols = {doc["symbol"] for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0

        for idx, quote_data in valid_quotes:
            symbol = quote_data["symbol"]

            if symbol in existing_symbols:
                # Batch update
                bulk_operations.append(
                    UpdateOne(
                        {"symbol": symbol},
                        {"$set": quote_data}
                    )
                )
                updated_count += 1
            else:
                # Batch insert
                quote_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(quote_data))
                saved_count += 1

        # Perform batch operations
        if bulk_operations:
            try:
                result = await collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ Batch operation completed: Insert{result.inserted_count}, update{result.modified_count}")
            except Exception as e:
                logger.error(f"❌ Batch operation failed: {e}")
                # If the batch operation fails, fall back to inserting items one by one.
                logger.warning("⚠️ Return to item-by-item operation mode")
                saved_count = 0
                updated_count = 0

                for idx, quote_data in valid_quotes:
                    try:
                        symbol = quote_data["symbol"]
                        result = await collection.update_one(
                            {"symbol": symbol},
                            {"$set": quote_data},
                            upsert=True
                        )
                        if result.upserted_id:
                            saved_count += 1
                        else:
                            updated_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "symbol": quote_data.get("symbol", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "failed": failed_count,
                "total": len(request.quotes),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: New{saved_count}, update{updated_count}, failed{failed_count}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save real-time quotes in batches: {str(e)}"
        )


# ==================== API Guide interface ====================

@router.get("/api-guide-content")
async def get_api_guide_content():
    """Get the Markdown raw content of the Stock Data Bulk Import API Guide (for front-end rendering)"""
    from fastapi.responses import Response
    from pathlib import Path

    try:
        # Read Markdown files
        guide_path = Path("docs/03-development/api/stock-data-import.md")

        if not guide_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API Guide file does not exist"
            )

        with open(guide_path, "r", encoding="utf-8") as f:
            content = f.read()

        return Response(
            content=content,
            media_type="text/plain; charset=utf-8"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read API guide content: {str(e)}"
        )


@router.get("/download-test-program")
async def download_test_program():
    """Download stock data batch import test program"""
    from fastapi.responses import FileResponse
    from pathlib import Path

    try:
        project_root = Path(__file__).parent.parent.parent
        candidate_paths = [
            project_root / "docs" / "api" / "examples" / "stock_data_import_examples.py",
            project_root / "scripts" / "test_batch_import_apis.py",
        ]

        test_program_path = next((path for path in candidate_paths if path.exists()), None)

        if not test_program_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test program file does not exist"
            )

        return FileResponse(
            path=str(test_program_path),
            filename=test_program_path.name,
            media_type="text/x-python"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download test program failed: {str(e)}"
        )
_snapshots['stock_data'] = dict(globals())

# === financial_data.py ===
#!/usr/bin/env python3
"""
Financial Data API Routing
Provide financial data query and synchronization management interface
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.worker.financial_data_sync_service import get_financial_sync_service
from app.services.financial_data_service import get_financial_data_service
from app.core.response import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financial-data", tags=["financial data"])


# ==================== request model ====================

class FinancialSyncRequest(BaseModel):
    """Financial data synchronization request"""
    symbols: Optional[List[str]] = Field(None, description="Stock code list, if empty, all stocks will be synchronized.")
    data_sources: Optional[List[str]] = Field(
        ["tushare", "akshare", "baostock"], 
        description="Data source list"
    )
    report_types: Optional[List[str]] = Field(
        ["quarterly"], 
        description="List of report types (quarterly/annual)"
    )
    batch_size: int = Field(50, description="batch size", ge=1, le=200)
    delay_seconds: float = Field(1.0, description="API Call delay seconds", ge=0.1, le=10.0)


class SingleStockSyncRequest(BaseModel):
    """Single stock financial data synchronization request"""
    symbol: str = Field(..., description="Stock code")
    data_sources: Optional[List[str]] = Field(
        ["tushare", "akshare", "baostock"],
        description="Data source list"
    )


class FinancialDataBatchRequest(BaseModel):
    """Batch save financial data requests"""
    symbol: str = Field(..., description="Stock code")
    financial_data: List[Dict[str, Any]] = Field(..., description="Financial data list")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


# ==================== API endpoint ====================

@router.get("/query/{symbol}", summary="Query stock financial data")
async def query_financial_data(
    symbol: str,
    report_period: Optional[str] = Query(None, description="Reporting period screening (YYYYMMDD)"),
    data_source: Optional[str] = Query(None, description="Data source filtering"),
    report_type: Optional[str] = Query(None, description="Report type filter"),
    limit: Optional[int] = Query(10, description="Limit the number of returns", ge=1, le=100)
) -> dict:
    """
    Query stock financial data
    
    - **symbol**: Stock code (Required)
    - **report_period**: Report period screening, format YYYYMMDD
    - **data_source**: Data source filtering (tushare/akshare/baostock)
    - **report_type**: Report type filter (quarterly/annual)
    - **limit**: Limit the number of returns, default is 10
    """
    try:
        service = await get_financial_data_service()
        
        results = await service.get_financial_data(
            symbol=symbol,
            report_period=report_period,
            data_source=data_source,
            report_type=report_type,
            limit=limit
        )
        
        return ok(data={
                "symbol": symbol,
                "count": len(results),
                "financial_data": results
            },
            message=f"Found {len(results)} financial data"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to query financial data {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query financial data: {str(e)}")


@router.get("/latest/{symbol}", summary="Get the latest financial data")
async def get_latest_financial_data(
    symbol: str,
    data_source: Optional[str] = Query(None, description="Data source filtering")
) -> dict:
    """
    Get the latest financial data for a stock
    
    - **symbol**: Stock code (Required)
    - **data_source**: Data source filtering (tushare/akshare/baostock)
    """
    try:
        service = await get_financial_data_service()
        
        result = await service.get_latest_financial_data(
            symbol=symbol,
            data_source=data_source
        )
        
        if result:
            return ok(data=result,
                message="Obtain the latest financial data successfully"
            )
        else:
            return ok(success=False, data=None,
                message="No financial data found"
            )
        
    except Exception as e:
        logger.error(f"❌ Failed to get latest financial data {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest financial data: {str(e)}")


@router.get("/statistics", summary="Get financial statistics")
async def get_financial_statistics() -> dict:
    """
    Get financial data statistics
    
    Returns financial data statistics from each data source, including:
    - Total number of records
    - Total number of shares
    - Statistics grouped by data source and report type
    """
    try:
        service = await get_financial_data_service()
        
        stats = await service.get_financial_statistics()
        
        return ok(data=stats,
            message="Obtain financial data statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain financial data statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain financial data statistics: {str(e)}")


@router.post("/sync/start", summary="Start financial data synchronization")
async def start_financial_sync(
    request: FinancialSyncRequest,
    background_tasks: BackgroundTasks
) -> dict:
    """
    Start financial data synchronization task
    
    Supported configurations:
    - Stock code list (if empty, all stocks will be synchronized)
    - Data source selection
    - Report type selection
    - Batch size and delay settings
    """
    try:
        service = await get_financial_sync_service()
        
        # Perform synchronization tasks in the background
        background_tasks.add_task(
            _execute_financial_sync,
            service,
            request
        )
        
        return ok(data={
                "task_started": True,
                "config": request.dict()
            },
            message="Financial data synchronization task has been started"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start financial data synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start financial data synchronization: {str(e)}")


@router.post("/sync/single", summary="Synchronize financial data of a single stock")
async def sync_single_stock_financial(
    request: SingleStockSyncRequest
) -> dict:
    """
    Synchronize financial data for individual stocks
    
    - **symbol**: Stock code (Required)
    - **data_sources**: Data source list, all data sources are used by default
    """
    try:
        service = await get_financial_sync_service()
        
        results = await service.sync_single_stock(
            symbol=request.symbol,
            data_sources=request.data_sources
        )
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        return ok(
            success=success_count > 0,
            data={
                "symbol": request.symbol,
                "results": results,
                "success_count": success_count,
                "total_count": total_count
            },
            message=f"Single stock financial data synchronization completed: {success_count}/{total_count} success"
        )
        
    except Exception as e:
        logger.error(f"❌ Single stock financial data synchronization failed {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Single stock financial data synchronization failed: {str(e)}")


@router.get("/sync/statistics", summary="Get sync statistics")
async def get_sync_statistics() -> dict:
    """
    Get financial data synchronization statistics
    
    Returns the synchronization statistics of each data source, including the number of records, number of stocks, etc.
    """
    try:
        service = await get_financial_sync_service()
        
        stats = await service.get_sync_statistics()
        
        return ok(data=stats,
            message="Obtain synchronization statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain synchronization statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain synchronization statistics: {str(e)}")


@router.get("/health", summary="Financial Data Services Health Check")
async def health_check() -> dict:
    """
    Financial Data Services Health Check
    
    Check service status and database connection
    """
    try:
        # Check service initialization status
        service = await get_financial_data_service()
        sync_service = await get_financial_sync_service()
        
        # Simple database connection test
        stats = await service.get_financial_statistics()
        
        return ok(data={
                "service_status": "healthy",
                "database_connected": True,
                "total_records": stats.get("total_records", 0),
                "total_symbols": stats.get("total_symbols", 0)
            },
            message="The financial data service is running normally"
        )
        
    except Exception as e:
        logger.error(f"❌ Financial Data Service health check failed: {e}")
        return ok(success=False, data={
                "service_status": "unhealthy",
                "error": str(e)
            },
            message="Financial data service exception"
        )


# ==================== Background tasks ====================

async def _execute_financial_sync(
    service: Any,
    request: FinancialSyncRequest
):
    """Perform financial data synchronization background tasks"""
    try:
        logger.info(f"🚀 Start the financial data synchronization task: {request.dict()}")
        
        # Generate task ID (use if task_id is present in the request, otherwise generate a new one)
        import uuid
        task_id = getattr(request, 'task_id', None) or f"financial_sync_{uuid.uuid4().hex[:8]}"
        
        results = await service.sync_financial_data(
            symbols=request.symbols,
            data_sources=request.data_sources,
            report_types=request.report_types,
            batch_size=request.batch_size,
            delay_seconds=request.delay_seconds,
            job_id=task_id  # 🔥 Add job_id for progress tracking
        )
        
        # Statistics overall results
        total_success = sum(stats.success_count for stats in results.values())
        total_symbols = sum(stats.total_symbols for stats in results.values())
        
        logger.info(f"✅ Financial data synchronization task completed: {total_success}/{total_symbols} success")
        
        # Here you can add notification logic, such as sending emails or messages
        
    except Exception as e:
        logger.error(f"❌ Financial data synchronization task execution failed: {e}")


# ==================== Batch import interface ====================

@router.post("/save", response_model=dict, dependencies=[Depends(require_pro)])
async def save_financial_data_batch(
    request: FinancialDataBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save financial data in batches (optimized version)[PRO]

    Allow users to bulk import financial data via API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Bulk save request with ticker, financial data list, and data source identifier

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "skipped": skip quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from pymongo import UpdateOne, InsertOne

        db = get_mongo_db()
        collection = db.stock_financial_data

        # Data validation and preprocessing
        valid_data = []
        errors = []
        failed_count = 0

        for idx, fin_data in enumerate(request.financial_data):
            try:
                # Validate required fields
                if "report_period" not in fin_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: report_period"
                    })
                    failed_count += 1
                    continue

                # Verify report_period format (YYYYMMDD)
                report_period = fin_data["report_period"]
                if not (isinstance(report_period, str) and report_period.isdigit() and len(report_period) == 8):
                    errors.append({
                        "index": idx,
                        "report_period": report_period,
                        "error": "report_period Must be an 8-digit number (YYYYMMDD format)"
                    })
                    failed_count += 1
                    continue

                # Add stock code and metadata (fixed use of local as local data identifier)
                fin_data["symbol"] = request.symbol
                fin_data["code"] = request.symbol  # Compatible with old fields
                fin_data["data_source"] = "local"
                fin_data["updated_at"] = datetime.utcnow()

                valid_data.append((idx, fin_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "report_period": fin_data.get("report_period", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_data:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.financial_data),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        report_periods = [data["report_period"] for _, data in valid_data]
        existing_docs = await collection.find({
            "symbol": request.symbol,
            "report_period": {"$in": report_periods},
            "data_source": "local"
        }).to_list(length=None)

        existing_periods = {doc["report_period"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, fin_data in valid_data:
            report_period = fin_data["report_period"]

            if report_period in existing_periods:
                if request.overwrite:
                    # Batch update
                    fin_data["created_at"] = existing_periods[report_period].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {
                                "symbol": request.symbol,
                                "report_period": report_period,
                                "data_source": "local"
                            },
                            {"$set": fin_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                fin_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(fin_data))
                saved_count += 1

        # Perform batch operations
        if bulk_operations:
            try:
                result = await collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ Batch operation completed: Insert{result.inserted_count}, update{result.modified_count}")
            except Exception as e:
                logger.error(f"❌ Batch operation failed: {e}")
                # If the batch operation fails, fall back to inserting items one by one.
                logger.warning("⚠️ Return to item-by-item operation mode")
                saved_count = 0
                updated_count = 0

                for idx, fin_data in valid_data:
                    try:
                        report_period = fin_data["report_period"]
                        if report_period in existing_periods and request.overwrite:
                            await collection.update_one(
                                {
                                    "symbol": request.symbol,
                                    "report_period": report_period,
                                    "data_source": "local"
                                },
                                {"$set": fin_data}
                            )
                            updated_count += 1
                        elif report_period not in existing_periods:
                            await collection.insert_one(fin_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "report_period": fin_data.get("report_period", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.financial_data),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to save financial data in batches: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save financial data in batches: {str(e)}"
        )
_snapshots['financial_data'] = dict(globals())

# === news_data.py ===
"""
News data API routing
Provides news data query, synchronization and management interfaces
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, status
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.core.response import ok
from app.services.news_data_service import get_news_data_service, NewsQueryParams
from app.worker.news_data_sync_service import get_news_data_sync_service

router = APIRouter(prefix="/api/news-data", tags=["news data"])
logger = logging.getLogger("webapi")


class NewsQueryRequest(BaseModel):
    """News query request"""
    symbol: Optional[str] = Field(None, description="Stock code")
    symbols: Optional[List[str]] = Field(None, description="Multiple tickers")
    start_time: Optional[datetime] = Field(None, description="start time")
    end_time: Optional[datetime] = Field(None, description="end time")
    category: Optional[str] = Field(None, description="News category")
    sentiment: Optional[str] = Field(None, description="sentiment analysis")
    importance: Optional[str] = Field(None, description="importance")
    data_source: Optional[str] = Field(None, description="data source")
    keywords: Optional[List[str]] = Field(None, description="keywords")
    limit: int = Field(50, description="Return quantity limit")
    skip: int = Field(0, description="skip quantity")


class NewsSyncRequest(BaseModel):
    """News sync request"""
    symbol: Optional[str] = Field(None, description="Stock code, if empty, market news will be synchronized")
    data_sources: Optional[List[str]] = Field(None, description="Data source list")
    hours_back: int = Field(24, description="Lookback hours")
    max_news_per_source: int = Field(50, description="Maximum number of news per data source")


class NewsDataBatchRequest(BaseModel):
    """Batch save news data requests"""
    symbol: Optional[str] = Field(None, description="Main relevant stock symbols")
    news_list: List[Dict[str, Any]] = Field(..., description="News data list")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


@router.get("/query/{symbol}", response_model=dict)
async def query_stock_news(
    symbol: str,
    hours_back: int = Query(24, description="Lookback hours"),
    limit: int = Query(20, description="Return quantity limit"),
    category: Optional[str] = Query(None, description="News category"),
    sentiment: Optional[str] = Query(None, description="sentiment analysis"),
    current_user: dict = Depends(get_current_user)
):
    """
    Query stock news (intelligent acquisition: priority database, real-time acquisition when no data is available)

    Args:
        symbol: Stock code
        hours_back: Lookback hours
        limit: Return quantity limit
        category: News category filtering
        sentiment: Sentiment analysis filter

    Returns:
        dict: News data list
    """
    try:
        service = await get_news_data_service()

        # Build query parameters
        start_time = datetime.utcnow() - timedelta(hours=hours_back)

        params = NewsQueryParams(
            symbol=symbol,
            start_time=start_time,
            category=category,
            sentiment=sentiment,
            limit=limit,
            sort_by="publish_time",
            sort_order=-1
        )

        # 1. First query from the database
        news_list = await service.query_news(params)
        data_source = "database"

        # 2. If there is no data in the database, obtain it in real time
        if not news_list:
            logger.info(f"📰 There is no news data in the database, which can be obtained in real time.: {symbol}")
            try:
                from app.worker.akshare_sync_service import get_akshare_sync_service
                sync_service = await get_akshare_sync_service()

                # Get news in real time
                news_data = await sync_service.provider.get_stock_news(
                    symbol=symbol,
                    limit=limit
                )

                if news_data:
                    # Save to database
                    saved_count = await service.save_news_data(
                        news_data=news_data,
                        data_source="akshare",
                        market="CN"
                    )
                    logger.info(f"✅ Get and save in real time {saved_count} news")

                    # Query again
                    news_list = await service.query_news(params)
                    data_source = "realtime"
                else:
                    logger.warning(f"⚠️ Failed to get news in real time: {symbol}")

            except Exception as e:
                logger.error(f"❌ Get news exceptions in real time: {e}")

        return ok(data={
                "symbol": symbol,
                "hours_back": hours_back,
                "total_count": len(news_list),
                "news": news_list,
                "data_source": data_source
            },
            message=f"The query is successful and returns {len(news_list)} news (source:{data_source}) "
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query stock news: {str(e)}"
        )


@router.post("/query", response_model=dict)
async def query_news_advanced(
    request: NewsQueryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Advanced news query
    
    Args:
        request: Query request parameters
        
    Returns:
        dict: News data list
    """
    try:
        service = await get_news_data_service()
        
        # Build query parameters
        params = NewsQueryParams(
            symbol=request.symbol,
            symbols=request.symbols,
            start_time=request.start_time,
            end_time=request.end_time,
            category=request.category,
            sentiment=request.sentiment,
            importance=request.importance,
            data_source=request.data_source,
            keywords=request.keywords,
            limit=request.limit,
            skip=request.skip
        )
        
        # Query news
        news_list = await service.query_news(params)
        
        return ok(data={
                "query_params": request.dict(),
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Advanced query successful, return {len(news_list)} news"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Advanced news query failed: {str(e)}"
        )


@router.get("/latest", response_model=dict)
async def get_latest_news(
    symbol: Optional[str] = Query(None, description="Stock code, if empty, get all news"),
    limit: int = Query(10, description="Return quantity limit"),
    hours_back: int = Query(24, description="Lookback hours"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the latest news
    
    Args:
        symbol: Stock code, if empty, get all news
        limit: Return quantity limit
        hours_back: Lookback hours
        
    Returns:
        dict: Latest news list
    """
    try:
        service = await get_news_data_service()
        
        # Get the latest news
        news_list = await service.get_latest_news(
            symbol=symbol,
            limit=limit,
            hours_back=hours_back
        )
        
        return ok(data={
                "symbol": symbol,
                "limit": limit,
                "hours_back": hours_back,
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Get the latest news successfully, return {len(news_list)} Article"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest news: {str(e)}"
        )


@router.get("/search", response_model=dict)
async def search_news(
    query: str = Query(..., description="Search keywords"),
    symbol: Optional[str] = Query(None, description="Stock code filter"),
    limit: int = Query(20, description="Return quantity limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search news in full text
    
    Args:
        query: Search keywords
        symbol: Stock code filter
        limit: Return quantity limit
        
    Returns:
        dict: Search result list
    """
    try:
        service = await get_news_data_service()
        
        # Full text search
        news_list = await service.search_news(
            query_text=query,
            symbol=symbol,
            limit=limit
        )
        
        return ok(data={
                "query": query,
                "symbol": symbol,
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Search successful, return {len(news_list)} results"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News search failed: {str(e)}"
        )


@router.get("/statistics", response_model=dict)
async def get_news_statistics(
    symbol: Optional[str] = Query(None, description="Stock code"),
    days_back: int = Query(7, description="Lookback days"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get news statistics
    
    Args:
        symbol: Stock code
        days_back: Lookback days
        
    Returns:
        dict: News statistics
    """
    try:
        service = await get_news_data_service()
        
        # Calculation time range
        start_time = datetime.utcnow() - timedelta(days=days_back)
        
        # Get statistics
        stats = await service.get_news_statistics(
            symbol=symbol,
            start_time=start_time
        )
        
        return ok(data={
                "symbol": symbol,
                "days_back": days_back,
                "statistics": {
                    "total_count": stats.total_count,
                    "sentiment_distribution": {
                        "positive": stats.positive_count,
                        "negative": stats.negative_count,
                        "neutral": stats.neutral_count
                    },
                    "importance_distribution": {
                        "high": stats.high_importance_count,
                        "medium": stats.medium_importance_count,
                        "low": stats.low_importance_count
                    },
                    "categories": stats.categories,
                    "sources": stats.sources
                }
            },
            message="Obtain news statistics successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain news statistics: {str(e)}"
        )


@router.post("/sync/start", response_model=dict)
async def start_news_sync(
    request: NewsSyncRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start news synchronization task
    
    Args:
        request: Synchronous request parameters
        background_tasks: Background tasks
        
    Returns:
        dict: Task start result
    """
    try:
        sync_service = await get_news_data_sync_service()
        
        # Add background sync task
        if request.symbol:
            background_tasks.add_task(
                _execute_stock_news_sync,
                sync_service,
                request
            )
            message = f"stocks {request.symbol} News synchronization task has been started"
        else:
            background_tasks.add_task(
                _execute_market_news_sync,
                sync_service,
                request
            )
            message = "Market news synchronization task has been started"
        
        return ok(data={
                "sync_type": "stock" if request.symbol else "market",
                "symbol": request.symbol,
                "data_sources": request.data_sources,
                "hours_back": request.hours_back,
                "max_news_per_source": request.max_news_per_source
            },
            message=message
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start news sync: {str(e)}"
        )


@router.post("/sync/single", response_model=dict)
async def sync_single_stock_news(
    symbol: str,
    data_sources: Optional[List[str]] = None,
    hours_back: int = 24,
    max_news_per_source: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Synchronize single stock news (synchronous execution)
    
    Args:
        symbol: Stock code
        data_sources: Data source list
        hours_back: Lookback hours
        max_news_per_source: Maximum number of news per data source
        
    Returns:
        dict: Synchronization results
    """
    try:
        sync_service = await get_news_data_sync_service()
        
        # Perform synchronization
        stats = await sync_service.sync_stock_news(
            symbol=symbol,
            data_sources=data_sources,
            hours_back=hours_back,
            max_news_per_source=max_news_per_source
        )
        
        return ok(data={
                "symbol": symbol,
                "sync_stats": {
                    "total_processed": stats.total_processed,
                    "successful_saves": stats.successful_saves,
                    "failed_saves": stats.failed_saves,
                    "duplicate_skipped": stats.duplicate_skipped,
                    "sources_used": stats.sources_used,
                    "duration_seconds": stats.duration_seconds,
                    "success_rate": stats.success_rate
                }
            },
            message=f"stocks {symbol} News synchronization completed and saved successfully {stats.successful_saves} Article"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync stock news: {str(e)}"
        )


@router.delete("/cleanup", response_model=dict)
async def cleanup_old_news(
    days_to_keep: int = Query(90, description="retention days"),
    current_user: dict = Depends(get_current_user)
):
    """
    Clean up expired news
    
    Args:
        days_to_keep: retention days
        
    Returns:
        dict: Clean results
    """
    try:
        service = await get_news_data_service()
        
        # Delete expired news
        deleted_count = await service.delete_old_news(days_to_keep)
        
        return ok(data={
                "days_to_keep": days_to_keep,
                "deleted_count": deleted_count
            },
            message=f"Cleanup completed, delete {deleted_count} expired news"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clean up expired news: {str(e)}"
        )


@router.get("/health", response_model=dict)
async def health_check():
    """health check"""
    try:
        service = await get_news_data_service()
        sync_service = await get_news_data_sync_service()
        
        return ok(data={
                "service_status": "healthy",
                "timestamp": datetime.utcnow().isoformat()
            },
            message="News data service is running normally"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


# Background task execution function
async def _execute_stock_news_sync(sync_service, request: NewsSyncRequest):
    """Perform stock news synchronization"""
    try:
        await sync_service.sync_stock_news(
            symbol=request.symbol,
            data_sources=request.data_sources,
            hours_back=request.hours_back,
            max_news_per_source=request.max_news_per_source
        )
    except Exception as e:
        logger.error(f"❌ Backend stock news synchronization failed: {e}")


async def _execute_market_news_sync(sync_service, request: NewsSyncRequest):
    """Perform market news synchronization"""
    try:
        await sync_service.sync_market_news(
            data_sources=request.data_sources,
            hours_back=request.hours_back,
            max_news_per_source=request.max_news_per_source
        )
    except Exception as e:
        logger.error(f"❌ Backstage market news synchronization failed: {e}")


# ==================== Batch import interface ====================

@router.post("/save", response_model=dict, dependencies=[Depends(require_pro)])
async def save_news_data_batch(
    request: NewsDataBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save news data in batches (optimized version)[PRO]

    Allow users to import news data in batches via API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request, including news list and data source identification

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "skipped": skip quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from pymongo import UpdateOne, InsertOne

        db = get_mongo_db()
        collection = db.stock_news

        # Data validation and preprocessing
        valid_news = []
        errors = []
        failed_count = 0

        for idx, news_data in enumerate(request.news_list):
            try:
                # Validate required fields
                required_fields = ["title", "url", "publish_time"]
                missing_fields = [f for f in required_fields if f not in news_data]

                if missing_fields:
                    errors.append({
                        "index": idx,
                        "error": f"Missing required field: {', '.join(missing_fields)}"
                    })
                    failed_count += 1
                    continue

                # Verify URL format
                url = news_data["url"]
                if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
                    errors.append({
                        "index": idx,
                        "url": url,
                        "error": "url Must be a valid HTTP/HTTPS link"
                    })
                    failed_count += 1
                    continue

                # Add ticker and metadata
                if request.symbol:
                    news_data["symbol"] = request.symbol
                    if "symbols" not in news_data:
                        news_data["symbols"] = [request.symbol]

                # Fixed use of local as local data identifier
                news_data["data_source"] = "local"
                news_data["updated_at"] = datetime.utcnow()

                # Convert publish_time to datetime object (if string)
                if isinstance(news_data.get("publish_time"), str):
                    try:
                        news_data["publish_time"] = datetime.fromisoformat(
                            news_data["publish_time"].replace("Z", "+00:00")
                        )
                    except Exception as e:
                        errors.append({
                            "index": idx,
                            "error": f"Unable to parse publish_time: {str(e)}"
                        })
                        failed_count += 1
                        continue

                valid_news.append((idx, news_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "title": news_data.get("title", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_news:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.news_list),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Batch query for existing data (based on URL)
        urls = [news["url"] for _, news in valid_news]
        existing_docs = await collection.find({
            "url": {"$in": urls}
        }).to_list(length=None)

        existing_urls = {doc["url"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, news_data in valid_news:
            url = news_data["url"]

            if url in existing_urls:
                if request.overwrite:
                    # Batch update
                    news_data["created_at"] = existing_urls[url].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {"url": url},
                            {"$set": news_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                news_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(news_data))
                saved_count += 1

        # Perform batch operations
        if bulk_operations:
            try:
                result = await collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ Batch operation completed: Insert{result.inserted_count}, update{result.modified_count}")
            except Exception as e:
                logger.error(f"❌ Batch operation failed: {e}")
                # If the batch operation fails, fall back to inserting items one by one.
                logger.warning("⚠️ Return to item-by-item operation mode")
                saved_count = 0
                updated_count = 0

                for idx, news_data in valid_news:
                    try:
                        url = news_data["url"]
                        if url in existing_urls and request.overwrite:
                            await collection.update_one(
                                {"url": url},
                                {"$set": news_data}
                            )
                            updated_count += 1
                        elif url not in existing_urls:
                            await collection.insert_one(news_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "title": news_data.get("title", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.news_list),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to save news data in batches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save news data in batches: {str(e)}"
        )
_snapshots['news_data'] = dict(globals())

for _stem, _snap in _snapshots.items():
    _vmod = _types.ModuleType(f"app.routers.{_stem}")
    _vmod.__dict__.update(_snap)
    _sys.modules[f"app.routers.{_stem}"] = _vmod
    setattr(_routers_pkg, _stem, _vmod)
    setattr(_self_mod, _stem, _vmod)