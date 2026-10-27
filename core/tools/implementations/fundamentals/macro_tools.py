"""Macro dashboard and yield curve analysis tools."""

import datetime
import json
import logging
from statistics import median
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _get_market_pe_pb_distribution() -> Dict[str, Any]:
    """Statistics on market-wide PE/PB distribution from stock_basic_info."""
    db = _get_db()
    col = db["stock_basic_info"]

    all_stocks = list(col.find({}, {
        "_id": 0,
        "symbol": 1,
        "name": 1,
        "industry": 1,
        "pe_ttm": 1,
        "pb": 1,
        "pb_mrq": 1,
        "total_mv": 1,
    }))

    pe_values: List[float] = []
    pb_values: List[float] = []
    industry_stats: Dict[str, List[float]] = {}
    total_tracked = 0

    for stock in all_stocks:
        if not stock.get("symbol"):
            continue
        total_tracked += 1

        pe = _safe_float(stock.get("pe_ttm"))
        if pe is not None and 0 < pe < 1000:
            pe_values.append(pe)

        pb_raw = _safe_float(stock.get("pb") or stock.get("pb_mrq"))
        if pb_raw is not None and 0 < pb_raw < 100:
            pb_values.append(pb_raw)

        industry = (stock.get("industry") or "未知").strip()
        if industry not in industry_stats:
            industry_stats[industry] = []
        if pe is not None and 0 < pe < 1000:
            industry_stats[industry].append(pe)

    return {
        "total_tracked": total_tracked,
        "pe": {
            "count": len(pe_values),
            "avg": round(sum(pe_values) / len(pe_values), 2) if pe_values else None,
            "median": round(median(pe_values), 2) if pe_values else None,
            "min": round(min(pe_values), 2) if pe_values else None,
            "max": round(max(pe_values), 2) if pe_values else None,
        },
        "pb": {
            "count": len(pb_values),
            "avg": round(sum(pb_values) / len(pb_values), 2) if pb_values else None,
            "median": round(median(pb_values), 2) if pb_values else None,
            "min": round(min(pb_values), 2) if pb_values else None,
            "max": round(max(pb_values), 2) if pb_values else None,
        },
        "industry_count": len(industry_stats),
    }


@tool
@register_tool(
    tool_id="get_macro_dashboard",
    name="宏观仪表盘",
    description=(
        "Return to the market macro overview dashboard, including market valuation distribution (PE/PB) and macro indicator slots (CPI/GDP/PMI/Interest Rate)"
        "and market breadth statistics. Macro indicators need to be supplemented from external sources."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "market_overview"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["市场整体估值概览", "宏观数据框架查询"],
    when_to_use=(
        "Use it when you need to quickly understand the full market valuation level, PE/PB distribution, and overall market width."
        "This tool provides market statistics available from a local database, as well as a list of macro indicators that need to be populated externally."
    ),
    when_not_to_use=(
        "Not suitable for querying the fundamentals or financial data of specific stocks;"
        "Not suitable for obtaining real-time CPI/GDP/PMI actual values (these need to be supplemented by external data sources)."
    ),
    returns=(
        "Returns a JSON string, including market_overview (full market valuation statistics),"
        "indicator_slots (Macro indicator occupancy, status is pending_external_data),"
        "market_breadth (Market breadth, including data source description)."
    ),
    example="get_macro_dashboard()",
    related_tools=["get_yield_curve_analysis", "get_sector_performance"],
)
def get_macro_dashboard() -> str:
    """Get a macro overview of the market dashboard.

    Returns market-wide PE/PB statistics, as well as a macro indicator framework that needs to be supplemented by external data sources.

    Returns:
        str: JSON String, field description——
            dashboard_date: Dashboard date (YYYY-MM-DD)
            data_source_note: Data source description
            market_overview: dict Market overview——
                — total_stocks_tracked: Total number of stocks tracked
                — pe_ttm_distribution: dict PE_TTM Distribution (avg/median/min/max/valid_samples)
                — pb_distribution: dict PB Distribution (avg/median/min/max/valid_samples)
                — industry_coverage: dict Industry coverage (total_industries)
            indicator_slots: dict Macro indicator occupancy, each indicator structure——
                — label: Indicator name
                — status: status (fixed to "pending_external_data") 
                — suggested_source: Suggested data sources
                — note: Description
                contains key: cpi / gdp / pmi / interest_rates
            market_breadth: dict market breadth——
                — status: status (fixed to "partial_data") 
                — note: Description
                — available_from_system: list[str] System available data sources
            suggested_external_sources: dict Suggested external data sources (akshare/tushare/eastmoney)
            status: Status (only when abnormal) "error") 
            message: Error message (only status="error" exist)
    """
    try:
        today = datetime.date.today()
        market_stats = _get_market_pe_pb_distribution()

        dashboard = {
            "dashboard_date": today.isoformat(),
            "data_source_note": (
                "The following market_overview is a statistics snapshot from the local database stock_basic_info collection,"
                "Reflects the system-synchronized A-share market-wide PE/PB distribution."
                "indicator_slots The macro indicators in need to be obtained from external data sources (such as Oriental Fortune, National Bureau of Statistics API)."
            ),
            "market_overview": {
                "total_stocks_tracked": market_stats["total_tracked"],
                "pe_ttm_distribution": {
                    "avg": market_stats["pe"]["avg"],
                    "median": market_stats["pe"]["median"],
                    "min": market_stats["pe"]["min"],
                    "max": market_stats["pe"]["max"],
                    "valid_samples": market_stats["pe"]["count"],
                },
                "pb_distribution": {
                    "avg": market_stats["pb"]["avg"],
                    "median": market_stats["pb"]["median"],
                    "min": market_stats["pb"]["min"],
                    "max": market_stats["pb"]["max"],
                    "valid_samples": market_stats["pb"]["count"],
                },
                "industry_coverage": {
                    "total_industries": market_stats["industry_count"],
                },
            },
            "indicator_slots": {
                "cpi": {
                    "label": "consumer price index (CPI)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "External API is required to supplement monthly CPI year-on-year/month-on-month data",
                },
                "gdp": {
                    "label": "国内生产总值 (GDP)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "External API is needed to supplement quarterly GDP year-on-year/cumulative growth rate",
                },
                "pmi": {
                    "label": "purchasing managers index (PMI)",
                    "status": "pending_external_data",
                    "suggested_source": "National Bureau of Statistics/Oriental Fortune Macroeconomic Data",
                    "note": "Requires external API to supplement manufacturing/non-manufacturing industries PMI",
                },
                "interest_rates": {
                    "label": "interest rate (LPR/MLF/Treasury yield)",
                    "status": "pending_external_data",
                    "suggested_source": "People s Bank of China / China Money Network / Oriental Fortune",
                    "note": "External API is needed to supplement LPR, MLF interest rates and government bond yield curves",
                },
            },
            "market_breadth": {
                "status": "partial_data",
                "note": (
                    "Market breadth statistics (number of rising and falling stocks, proportion above MA50, etc.) require full calculation of daily data."
                    "The current system has not pre-aggregated this statistics. Can be supplemented by external data sources or downstream queries."
                ),
                "available_from_system": [
                    "Daily quotes of a single stock (get_stock_daily_quotes)",
                    "Industry valuation summary (summarize_industry_valuation)",
                    "Market-wide PE/PB distribution (provided by this tool)",
                ],
            },
            "suggested_external_sources": {
                "akshare": "Macroeconomic indicators and bond yield data are available through akshare",
                "tushare": "Macroeconomic indicators can be obtained through tushare (points required)",
                "eastmoney": "东方财富宏观经济数据接口",
            },
        }

        return json.dumps(dashboard, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Failed to obtain macro dashboard: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


def _fetch_china_yield_curve() -> dict:
    """Get the latest data on China s government bond yield curve via AKShare."""
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        # Filter"ChinaBond Treasury Bond Yield Curve"
        treasury = df[df["曲线名称"] == "中债国债收益率曲线"]
        if treasury.empty:
            return {"status": "no_data", "message": "未找到国债收益率曲线数据"}
        # Get the latest date
        treasury["日期"] = pd.to_datetime(treasury["日期"])
        latest = treasury.loc[treasury["日期"].idxmax()]
        yields = {}
        for col in ["3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]:
            val = latest.get(col)
            if val is not None and val == val:
                yields[col] = round(float(val), 4)
            else:
                yields[col] = None
        return {
            "status": "ok",
            "date": str(latest["日期"].date()),
            "yields": yields,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain treasury bond yield: %s", e)
        return {"status": "error", "message": str(e)}


def _fetch_zh_us_rate() -> dict:
    """Get the latest data comparing U.S. and Chinese yields with AKShare."""
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        df["日期"] = pd.to_datetime(df["日期"])
        latest = df.sort_values("日期").iloc[-1]
        result = {
            "date": str(latest["日期"].date()),
            "china": {},
            "us": {},
            "spread_cn": {},
        }
        cn_cols = {"中国国债收益率2年": "2年", "中国国债收益率5年": "5年",
                    "中国国债收益率10年": "10年", "中国国债收益率30年": "30年"}
        us_cols = {"美国国债收益率2年": "2年", "美国国债收益率5年": "5年",
                    "美国国债收益率10年": "10年", "美国国债收益率30年": "30年"}
        for raw, name in cn_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["china"][name] = round(float(v), 4)
        for raw, name in us_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["us"][name] = round(float(v), 4)
        spread = latest.get("中国国债收益率10年-2年")
        if spread is not None and spread == spread:
            result["spread_cn"]["10Y-2Y"] = round(float(spread), 4)
        return result
    except Exception as e:
        logger.warning("AKShare Failed to obtain Sino-US yield: %s", e)
        return {"status": "error", "message": str(e)}


@tool
@register_tool(
    tool_id="get_yield_curve_analysis",
    name="收益率曲线分析",
    description=(
        "Get real-time data on China s government bond yield curve through akshare,"
        "Including the yield to maturity of government bonds of various maturities (3 months/6 months/1 year/3 years/5 years/7 years/10 years/30 years),"
        "10Y-2Y Term spreads and yield comparison between China and the United States. It also provides curve shape judgment."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "yield_curve", "interest_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["国债收益率查询", "收益率曲线形态判断", "中美利差对比"],
    when_to_use=(
        "When users ask about the current level of government bond yields, the shape of the yield curve (normal/inverted/flat),"
        "Used when comparing Sino-US interest rate spreads and term interest rate spreads (10Y-2Y)."
    ),
    when_not_to_use=(
        "Not suitable for querying the yield or valuation data of individual bonds (single bonds);"
        "It is not suitable for querying historical return series (if you need a long-term series, please use akshare directly)."
    ),
    returns=(
        "Returns a JSON string, including yield_curve (the yield of each maturity of Chinese government bonds),"
        "date (Data date), curve_shape (curve shape judgment),"
        "key_spreads (Key spreads), zh_us_comparison (Comparison between China and the United States)."
    ),
    example="get_yield_curve_analysis()",
    related_tools=["get_macro_dashboard", "get_bond_yield_calculation", "get_monetary_environment", "get_credit_spread_analysis"],
)
def get_yield_curve_analysis() -> str:
    """Get real-time analysis of China s government bond yield curve.

    Obtain ChinaBond treasury bond yield curve data through AKShare, including yields of each maturity,
    Judgment of curve shape, term spread and comparison between China and the United States.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            date: Data date (YYYY-MM-DD)
            data_source: Data source description
            yield_curve: dict The yield rate of each term (key is "3 month"/"6 month"/"1 year"/"3 year"/"5 year"/"7 year"/"10 year"/"30 year") 
            curve_shape: curve shape: "normal upward tilt" | "hanging upside down" | "flat" | "Insufficient data to determine"
            key_spreads: dict Key spread (key such as "10Y-1Y"/"10Y-3Y"/"10Y-5Y") 
            zh_us_comparison: dict Comparison of U.S. and Chinese yields (when data are not available) {"status": "unavailable", "message": ...}) ——
                — date: Date
                — china: dict Yields of various terms in China
                — us: dict U.S. yields by maturity
                — spread_cn: dict China term spread (such as 10Y-2Y)
            data_note: Data annotation
            message: Error message (only status="error" exist)
            suggestion: Suggestions (only some error scenarios exist)
    """
    try:
        curve = _fetch_china_yield_curve()
        zh_us = _fetch_zh_us_rate()

        if curve.get("status") == "error":
            return json.dumps({
                "status": "error",
                "message": f"国债收益率数据获取失败: {curve.get('message')}",
                "suggestion": "Passable akshare.bond_china_yield() Get it directly",
            }, ensure_ascii=False, indent=2, default=str)

        yields = curve.get("yields", {})
        date = curve.get("date", "未知")

        # Determine curve shape
        y1 = yields.get("1年")
        y10 = yields.get("10年")
        y2 = yields.get("3月")
        if y10 is not None and y1 is not None:
            if y10 > y1 + 0.5:
                curve_shape = "正常向上倾斜"
            elif y10 < y1 - 0.1:
                curve_shape = "倒挂"
            else:
                curve_shape = "平坦"
        else:
            curve_shape = "数据不足无法判断"

        # key spread
        spreads = {}
        if y10 is not None and yields.get("1年") is not None:
            spreads["10Y-1Y"] = round(y10 - yields["1年"], 4)
        if y10 is not None and yields.get("3年") is not None:
            spreads["10Y-3Y"] = round(y10 - yields["3年"], 4)
        if y10 is not None and yields.get("5年") is not None:
            spreads["10Y-5Y"] = round(y10 - yields["5年"], 4)

        payload = {
            "status": "ok",
            "date": date,
            "data_source": "akshare.bond_china_yield() / bond_zh_us_rate()",
            "yield_curve": yields,
            "curve_shape": curve_shape,
            "key_spreads": spreads,
            "zh_us_comparison": zh_us if "status" not in zh_us else {
                "status": "unavailable",
                "message": zh_us.get("message", ""),
            },
            "data_note": "The curve is based on the latest data of ChinaBond Treasury Bond Yield Curve, the unit is percentage (%)",
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Yield curve analysis fails: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_macro_dashboard", "get_yield_curve_analysis"]
