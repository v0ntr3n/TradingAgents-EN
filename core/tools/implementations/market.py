from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['china_market_overview', 'chip_distribution_tools', 'dongchedi_sales_rank', 'index_market_tools', 'qmt_market_tools', 'sector_market_tools', 'stock_market_data', 'stock_screening_tool', 'technical_factor_bundle_tool', 'technical_indicators']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === china_market_overview ===
"""
China Market Overview Tool (Tushare version)
Replace the old version get_china_market_overview_legacy
"""
import logging
import pandas as pd
from typing import Annotated, Dict, Any, Optional
from langchain_core.tools import tool
from datetime import datetime

from core.tools.base import register_tool
from tradingagents.dataflows.providers.china.tushare import TushareProvider

logger = logging.getLogger(__name__)

@tool
@register_tool(
    tool_id="get_china_market_overview",
    name="China market overview (Tushare)",
    description="Get an overview of China s major stock market indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, Science and Technology Innovation 50)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["china_market_overview", "market_overview", "index_data", "market_quote", "main_index"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["china_market_overview", "index_performance_review", "main_index_tracking"],
)
def get_china_market_overview(
    curr_date: Annotated[str, "current date, format yyyy-mm-dd"]
) -> str:
    """
    Get a comprehensive overview of China s stock market, including quotes from major indexes.
    Covers major indices such as Shanghai Composite Index, Shenzhen Composite Component Index, GEM Index, and Science and Technology Innovation 50 Index.
    
    Args:
        curr_date (str): current date, format yyyy-mm-dd
        
    Returns:
        str: Market overview report containing major index quotes
    """
    logger.info(f"📊 [China market overview] Start getting data, Date: {curr_date}")
    
    try:
        # initialization Tushare Provider
        provider = TushareProvider()
        if not provider.connect_sync():
            return "❌ Unable to connect to Tushare data source, please check API Token configuration."
            
        api = provider.api
        
        # Define major index codes
        indices = {
            "000001.SH": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000688.SH": "科创50"
        }
        
        results = []
        
        # Get index daily data
        # Note: Tushare index_daily interface
        # 🔑 Record actual date of use for reporting purposes
        actual_dates = []
        
        for code, name in indices.items():
            try:
                # 🔑 Get the data on the specified date. If there is no data on that day (such as weekend), search forward to the nearest day.
                # Use the end_date parameter,limit=1 Will return the most recent data before the specified date
                curr_date_clean = curr_date.replace('-', '')
                df = api.index_daily(ts_code=code, end_date=curr_date_clean, limit=1)
                
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    trade_date = row['trade_date']
                    close = row['close']
                    change = row['change']
                    pct_chg = row['pct_chg']
                    vol = row['vol']
                    amount = row['amount']
                    
                    # Format date
                    trade_date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                    actual_dates.append(trade_date_str)
                    
                    # 🔑 If the actual date does not match the requested date, state this in the report
                    date_note = ""
                    if trade_date_str != curr_date:
                        date_note = f" (Note:{curr_date} No data, use the latest trading day {trade_date_str})"
                    
                    # Format up/down symbols
                    sign = "+" if change > 0 else ""
                    
                    item = f"""### {name} ({code})
- **日期**: {trade_date_str}{date_note}
- **收盘**: {close:.2f}
- **涨跌**: {sign}{change:.2f} ({sign}{pct_chg:.2f}%)
- **成交量**: {vol/10000:.2f} 万手
- **成交额**: {amount/100000:.2f} 亿元
"""
                    results.append(item)
                else:
                    results.append(f"### {name} ({code})\n- No data yet (request date:{curr_date}) ")
                    
            except Exception as e:
                logger.error(f"❌ 获取指数 {name} 失败: {e}")
                results.append(f"### {name} ({code})\n- Failed to obtain: {e}")
        
        # 🔑 If the actual date is consistent for all indices, use the actual date; otherwise use the requested date
        if actual_dates and len(set(actual_dates)) == 1:
            actual_date = actual_dates[0]
            date_note = f" (Request date:{curr_date}, Actual use:{actual_date}) " if actual_date != curr_date else ""
        else:
            actual_date = curr_date
            date_note = ""
        
        # Portfolio Report
        report = f"""# 中国市场概览
**分析基准日期**: {curr_date}{date_note}

## 📉 主要指数表现
{chr(10).join(results)}

---
*数据来源: Tushare Pro*
"""
        logger.info("✅ [China market overview] get success")
        return report
        
    except Exception as e:
        error_msg = f"中国市场概览获取失败: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return error_msg

# === chip_distribution_tools ===
"""
Chip distribution analysis tool

Provides chip distribution data acquisition function and supports AkShare (preferred) and Tushare (backup) data sources.
These tools are used with ChipDistributionAnalystV2 analysts.
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_chip_distribution",
    name="筹码分布",
    description="Obtain stock chip distribution data and analyze profit ratio, average cost and chip concentration (AkShare is preferred, Tushare is backup)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "cost_distribution", "profit_ratio", "chip_concentration", "holder_cost"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["chip_distribution_analysis", "cost_structure_analysis", "support_resistance_identification"],
)
def get_chip_distribution(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Obtain stock chip distribution data (unified interface)

    Analyze the chip distribution of stocks, including:
    - Profit ratio: the proportion of chips that make a profit at the current price
    - Average cost: the average holding cost of all position holders
    - 90%/70%Chip cost range: the cost range of concentrated positions
    - Chip concentration: the degree of concentration of chip distribution

    Data source priority: AkShare (东财) → Tushare (Official API)

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution analysis report
    """
    try:
        from core.tools.chip_distribution_tools import get_chip_distribution_sync
        return get_chip_distribution_sync(ticker, trade_date)
    except Exception as e:
        logger.error(f"获取筹码分布失败: {e}")
        return f"❌ 获取筹码分布失败: {e}"


@tool
@register_tool(
    tool_id="get_chip_distribution_akshare",
    name="Chip distribution(AkShare)",
    description="Obtain stock chip distribution data through AkShare (Oriental Fortune Data Source, free)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "akshare", "cost_distribution", "profit_ratio", "eastmoney"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["chip_distribution_via_akshare", "cost_structure_analysis", "free_data_source_chip"],
)
def get_chip_distribution_akshare_tool(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Get stock chip distribution data through AkShare

    Use the Oriental Fortune data interface to obtain A-share chip distribution information for free.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution data (JSON format) or error message
    """
    try:
        import json
        from core.tools.chip_distribution_tools import get_chip_distribution_akshare
        data = get_chip_distribution_akshare(ticker, trade_date)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return f"❌ AkShare未能获取 {ticker} 的筹码分布数据"
    except Exception as e:
        logger.error(f"AkShare Failed to obtain chip distribution: {e}")
        return f"❌ AkShare Failed to obtain chip distribution: {e}"


@tool
@register_tool(
    tool_id="get_chip_distribution_tushare",
    name="Chip distribution(Tushare)",
    description="Obtain stock chip distribution data through Tushare (official API, requires 5,000 points)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "tushare", "cost_distribution", "cyq_perf", "profit_ratio"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["chip_distribution_via_tushare", "cost_structure_analysis", "official_api_chip"],
)
def get_chip_distribution_tushare_tool(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Obtain stock chip distribution data through Tushare (cyq_perf interface)

    Using Tushare s official API to obtain chip analysis data requires 5,000 points permission.
    Including: profit ratio (winner_rate), weighted average cost (weight_avg), each percentile cost price, etc.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution data (JSON format) or error message
    """
    try:
        import json
        from core.tools.chip_distribution_tools import get_chip_distribution_tushare
        data = get_chip_distribution_tushare(ticker, trade_date)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return f"❌ Tushare Failed to obtain {ticker} Chip distribution data (may require 5000 points permission)"
    except Exception as e:
        logger.error(f"Tushare Failed to obtain chip distribution: {e}")
        return f"❌ Tushare Failed to obtain chip distribution: {e}"


# === dongchedi_sales_rank ===
"""
The monthly sales query tool for car brands that understands Chedi

Data source: Understanding Chedi s public sales list interface
    https://www.dongchedi.com/motor/pc/car/rank_data
    ?month=202608          # Specify month;500=In the past half year,1000=Aggregation in the past year
    &rank_data_type=11     # National monthly sales list
    &count=100             # Single limit 100
    &offset=0              # Page turning is valid

The interface only requires User-Agent + Referer, No certification required.
The list is at the granularity of car series (model), including brand_name (such as "AITO Ask the world") , 
Therefore, querying by brand requires fetching the full list and then matching by brand name.
"""

import logging
import re
import time
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

import requests
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

_RANK_API = "https://www.dongchedi.com/motor/pc/car/rank_data"

# Those who understand cars only require carrying UA + Referer, No certification required
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.dongchedi.com/auto/rank",
}

_RANK_TYPE_SALES = 11   # 11=National monthly sales list (default is attention list)
_PAGE_SIZE = 100        # The upper limit of the interface's single return
_MAX_PAGES = 12         # The upper limit of page turning (1200 items) prevents unlimited page turning under abnormal circumstances.
_REQUEST_TIMEOUT = 15
_REQUEST_RETRIES = 2
_RETRY_INTERVAL = 0.5

# Cache key prefix (take the unified cache entrance of the project to avoid the list of the same month being pulled repeatedly)
_CACHE_SYMBOL_PREFIX = "dongchedi_rank"
_CACHE_DATA_SOURCE = "dongchedi"


def _request_rank(params: Dict[str, Any]) -> Dict[str, Any]:
    """请求销量榜接口（带重试）"""
    last_error = ""
    for attempt in range(_REQUEST_RETRIES + 1):
        try:
            resp = requests.get(
                _RANK_API,
                params=params,
                headers=_HTTP_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") == 0:
                return payload
            last_error = f"The interface returns an exception status: status={payload.get('status')}, message={payload.get('message')}"
        except Exception as e:
            last_error = str(e)
        if attempt < _REQUEST_RETRIES:
            time.sleep(_RETRY_INTERVAL * (attempt + 1))
    raise RuntimeError(last_error or "未知错误")


def _fetch_page(month: str, offset: int, count: int = _PAGE_SIZE) -> Dict[str, Any]:
    """拉取单页榜单数据"""
    payload = _request_rank({
        "month": month,
        "rank_data_type": _RANK_TYPE_SALES,
        "count": count,
        "offset": offset,
    })
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _fetch_rank_list(month: str) -> List[Dict[str, Any]]:
    """Turn the page to pull the full data of the national sales list for the specified month"""
    items: List[Dict[str, Any]] = []
    offset = 0
    for page in range(_MAX_PAGES):
        data = _fetch_page(month, offset)
        page_items = data.get("list") or []
        if not page_items:
            break
        items.extend(page_items)
        has_more = (data.get("paging") or {}).get("has_more")
        logger.debug(f"懂车帝销量榜 {month} 第 {page + 1} 页: {len(page_items)} 条, has_more={has_more}")
        if not has_more:
            break
        offset += _PAGE_SIZE
    return items


def _probe_month(month: str) -> bool:
    """Detect whether there is sales data in a certain month (only take 1 to save traffic)"""
    try:
        data = _fetch_page(month, 0, count=1)
        return bool(data.get("list"))
    except Exception:
        return False


def _previous_month(year_month: int) -> int:
    """Returns the previous calendar month (YYYYMM integer form)"""
    year, month = divmod(year_month, 100)
    if month == 1:
        return (year - 1) * 100 + 12
    return year * 100 + (month - 1)


def _detect_latest_month() -> str:
    """
    Returns the most recent complete month with data

    The starting point is the previous natural month: the current month s list is a rolling cumulative caliber (the month has not yet ended),
    As monthly sales is incomplete, it is not used by default.
    """
    today = datetime.now()
    cursor = _previous_month(today.year * 100 + today.month)
    for _ in range(4):
        candidate = f"{cursor:06d}"
        if _probe_month(candidate):
            return candidate
        cursor = _previous_month(cursor)
    return ""


def _normalize_month(month: str) -> Optional[str]:
    """
    Normalized month input

    Returns:
        Month value available for the interface; None means not provided (automatic detection required); empty string means the format is illegal
    """
    if month is None or str(month).strip() == "":
        return None
    text = str(month).strip()
    # First deal with the writing method with delimiters (August 2026 / 2026-8 / 2026/8 / 2026.8),
    # Otherwise"8"After removing non-numeric characters it will become"20268", Month leading 0 missing
    separated = re.search(r"(\d{4})\s*[year\-/.]\s*(\d{1,2})", text)
    if separated:
        return f"{separated.group(1)}{int(separated.group(2)):02d}"
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if digits in ("500", "1000"):   # Aggregated caliber in the past half year/last year
        return digits
    if len(digits) == 6:            # YYYYMM
        return digits
    return ""


def _format_month_label(month: str) -> str:
    """Convert the month parameter value into a readable statistical caliber description"""
    if month == "500":
        return "近半年（销量聚合）"
    if month == "1000":
        return "近一年（销量聚合）"
    if len(month) == 6:
        return f"{month[:4]}年{int(month[4:6])}月"
    return month


def _normalize_text(value: Any) -> str:
    """Normalize brand/model names to facilitate case-independent and whitespace-independent matching"""
    return re.sub(r"\s+", "", str(value or "")).lower()


def _match_brand_items(items: List[Dict[str, Any]], brand: str) -> List[Dict[str, Any]]:
    """
    Match list entries by brand name

    Matching priority: brand name exact match > Brand name/sub-brand name/car series name contains keywords
     (Understand that Chedi brand names often have prefixes, such as "AITO Ask the world", Therefore, inclusion matching must be supported)
    """
    key = _normalize_text(brand)
    if not key:
        return []

    exact: List[Dict[str, Any]] = []
    fuzzy: List[Dict[str, Any]] = []
    for item in items:
        brand_name = _normalize_text(item.get("brand_name"))
        sub_brand = _normalize_text(item.get("sub_brand_name"))
        series_name = _normalize_text(item.get("series_name"))
        if brand_name and brand_name == key:
            exact.append(item)
        elif key in brand_name or key in sub_brand or key in series_name or (brand_name and brand_name in key):
            fuzzy.append(item)

    return exact or fuzzy


def _format_rank_trend(rank: Any, last_rank: Any) -> str:
    """Calculate ranking changes based on current/previous issue rankings"""
    if not rank:
        return "-"
    if not last_rank:
        return "新上榜"
    delta = int(last_rank) - int(rank)
    if delta > 0:
        return f"↑{delta}"
    if delta < 0:
        return f"↓{abs(delta)}"
    return "—"


def _render_brand_section(brand_name: str, sub_brand_name: str, rows: List[Dict[str, Any]]) -> str:
    """渲染单个品牌的车型销量表"""
    total = sum(int(item.get("count") or 0) for item in rows)
    header = f"### {brand_name}"
    if sub_brand_name and sub_brand_name != brand_name:
        header += f"（{sub_brand_name}）"
    header += f" — 合计 {total:,} 辆"

    lines = [
        header,
        "",
        "| Ranking | car model | monthly sales(vehicle) | Selling price range | Last issue ranking | Ranking changes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        rank = item.get("rank") or "-"
        last_rank = item.get("last_rank") or "-"
        lines.append(
            f"| {rank} | {item.get('series_name') or '-'} "
            f"| {int(item.get('count') or 0):,} "
            f"| {item.get('price') or '-'} "
            f"| {last_rank} "
            f"| {_format_rank_trend(item.get('rank'), item.get('last_rank'))} |"
        )
    return "\n".join(lines)


def _load_rank_list(month: str) -> List[Dict[str, Any]]:
    """Obtain the full data of the list of the specified month (unified cache of prioritized hit items)"""
    symbol = f"{_CACHE_SYMBOL_PREFIX}_{month}_{_RANK_TYPE_SALES}"

    try:
        from tradingagents.dataflows.cache import get_cache

        cache = get_cache()
        cache_key = cache.find_cached_stock_data(
            symbol=symbol,
            start_date="",
            end_date="",
            data_source=_CACHE_DATA_SOURCE,
        )
        if cache_key:
            cached = cache.load_stock_data(cache_key)
            if isinstance(cached, list) and cached:
                logger.info(f"✅ 懂车帝销量榜命中缓存: {symbol}（{len(cached)} 条）")
                return cached
    except Exception as e:
        logger.warning(f"⚠️ The cache reading of the car sales list failed and was changed to real-time fetching.: {e}")

    items = _fetch_rank_list(month)

    try:
        from tradingagents.dataflows.cache import get_cache

        get_cache().save_stock_data(
            symbol=symbol,
            data=items,
            start_date="",
            end_date="",
            data_source=_CACHE_DATA_SOURCE,
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to write cache of car sales list: {e}")

    return items


@tool
@register_tool(
    tool_id="get_auto_brand_monthly_sales",
    name="汽车品牌月度销量",
    description="Query the sales volume of all models of a specified car brand in a certain month (Dongchedi national monthly sales list), and return the model ranking, monthly sales volume, price range and ranking changes",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["auto_sales", "brand_sales", "monthly_sales", "auto_industry", "dongchedi"],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=["汽车品牌月度销量查询", "品牌旗下车型销量对比", "整车厂商销量跟踪"],
)
def get_auto_brand_monthly_sales(
    brand: Annotated[str, "Car brand name, such as Ask the world  BYD  ideal car . Support fuzzy matching: input Ask the world Can match the brand name of the Chedi brand AITO Ask the world "],
    month: Annotated[str, "Statistics month, format YYYYMM (for example, 202608 means August 2026); you can also pass 500 (aggregation in the past half year) or 1000 (aggregation in the past year); if left blank, the most recent complete month with data will be automatically used."] = "",
) -> str:
    """
    Check the monthly sales volume of car brands.

    Obtain the monthly sales of all models under the designated brand through the national monthly sales list of Dianchedi.
    Suitable for sales tracking and horizontal comparison of the automotive industry chain/vehicle manufacturers.

    Args:
        brand: Car brand name (supports fuzzy matching)
        month: Statistical month YYYYMM, or 500/1000 aggregation caliber, leave it blank to automatically select the latest complete month

    Returns:
        str: markdown Brand model sales report in format
    """
    if not brand or not str(brand).strip():
        return "❌ Please provide the car brand name, for example: Wenjie, BYD, Li Auto."

    normalized_month = _normalize_month(month)
    if normalized_month == "":
        return f"❌ The month format is not recognized:{month}. Please use YYYYMM format (such as 202608), or 500 (last half year)/1000 (last year)."

    try:
        if normalized_month is None:
            normalized_month = _detect_latest_month()
            if not normalized_month:
                return "❌ Failed to obtain the latest sales list data, please try again later or specify the month explicitly (such as 202608)."
            logger.info(f"📅 The car sales list automatically selects the latest month: {normalized_month}")

        month_label = _format_month_label(normalized_month)
        logger.info(f"🚗 [汽车品牌销量] 品牌={brand}, 月份={month_label}")

        items = _load_rank_list(normalized_month)
        if not items:
            return f"❌ 未获取到 {month_label} 的销量榜数据（数据可能尚未发布）。"

        matched = _match_brand_items(items, brand)
        if not matched:
            top_brands: List[str] = []
            for item in items[:80]:
                name = item.get("brand_name")
                if name and name not in top_brands:
                    top_brands.append(name)
                if len(top_brands) >= 15:
                    break
            return (
                f"❌ 未在 {month_label} 销量榜中找到品牌“{brand}”。\n\n"
                f"This month s list includes a total of {len(items)} models,{len(set(i.get('brand_name') for i in items))} brand.\n"
                f"Examples of brand names to consider:{', '.join(top_brands)}. "
            )

        # Group by brand (fuzzy matching may hit multiple brands of the same car company, such as"Geely Galaxy""Geely Automobile") 
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in matched:
            grouped.setdefault(item.get("brand_name") or str(brand), []).append(item)

        sections = []
        for brand_name, rows in grouped.items():
            rows.sort(key=lambda x: (x.get("rank") or 9999))
            sub_brand = rows[0].get("sub_brand_name") or ""
            sections.append(_render_brand_section(brand_name, sub_brand, rows))

        total_count = sum(int(item.get("count") or 0) for item in matched)
        # The list of the current month is a rolling cumulative caliber, and readers need to be informed that the data is not yet complete.
        current_month = f"{datetime.now():%Y%m}"
        month_note = " (The month has not yet ended, it is rolling cumulative data)" if normalized_month == current_month else ""
        report = f"""# 汽车品牌月度销量：{brand}

- **统计口径**：懂车帝全国月度销量榜（{month_label}）{month_note}
- **匹配车型数**：{len(matched)} 款
- **合计销量**：{total_count:,} 辆

{chr(10).join(sections)}

---
数据来源：懂车帝公开销量榜。以上为车型零售销量统计，仅供研究参考，不构成投资建议。
"""
        logger.info(f"✅ [汽车品牌销量] 完成，匹配 {len(matched)} 款车型，合计 {total_count} 辆")
        return report

    except Exception as e:
        logger.error(f"❌ [car brand sales] Query failed: {e}", exc_info=True)
        return f"Car brand monthly sales query failed:{e}"

# === index_market_tools ===
"""
Market/index analysis tools

Provides index trend analysis, market breadth analysis and other functions
These tools are for IndexAnalystV2 analysts
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_analysis_data_source

logger = logging.getLogger(__name__)


def _resolve_market_analysis_source() -> str:
    """Get the data source that should be used by the current market analysis tool."""
    current_source = get_current_analysis_data_source()
    if current_source == "qmt":
        return "qmt"
    return "tushare"


def _index_market_tools_is_tushare_available() -> bool:
    """Check if Tushare data source is available."""
    try:
        from app.services.data_sources.tushare_adapter import TushareAdapter
        return TushareAdapter().is_available()
    except Exception:
        return False


def _index_market_tools_is_qmt_available() -> bool:
    """Check if the QMT data source is available."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        return QMTAdapter().is_available()
    except Exception:
        return False


def _qmt_fallback_index_trend(trade_date: str, lookback_days: int = 60) -> str:
    """QMT Downgrade: Get trend data for major indices."""
    try:
        from core.tools.qmt_market_tools import get_market_overview_qmt_sync
        report = get_market_overview_qmt_sync(trade_date, lookback_days)
        # Extract the exponential trend section from the full report
        lines = report.split("\n")
        result_lines = ["📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)", ""]
        capture = False
        for line in lines:
            if "主要指数趋势" in line:
                capture = True
            if capture:
                result_lines.append(line)
                if line.strip().startswith("##") and "主要指数趋势" not in line:
                    break
        captured = "\n".join(result_lines)
        return captured if len(captured) > 50 else report
    except Exception as e:
        return f"⚠️ Tushare Unavailable, QMT downgrade failed to obtain index data.: {e}"


def _qmt_fallback_market_breadth(trade_date: str) -> str:
    """QMT Downgrade: Use a snapshot of the entire market to represent the number of rising and falling stocks."""
    try:
        from core.tools.qmt_market_tools import get_market_overview_qmt_sync
        report = get_market_overview_qmt_sync(trade_date, 5)
        lines = report.split("\n")
        result_lines = ["📊 The following data is based on QMT snapshot agent metrics (degraded data when Tushare is unavailable)", ""]
        capture = False
        for line in lines:
            if "市场快照代理" in line:
                capture = True
            if capture:
                result_lines.append(line)
                if line.strip().startswith("##") and "市场快照代理" not in line:
                    break
        captured = "\n".join(result_lines)
        return captured if len(captured) > 50 else report
    except Exception as e:
        return f"⚠️ Tushare Not available, QMT downgrade to obtain market width also failed: {e}"


def _qmt_fallback_technical(trade_date: str, lookback_days: int = 60) -> str:
    """QMT Downgrade: Calculate technical indicators through index K-line."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        from statistics import median as _median

        adapter = QMTAdapter()
        if not adapter.is_available():
            return "⚠️ Tushare Not available, QMT is not available, and technical indicator data cannot be obtained."

        index_codes = {
            "000001.SH": "上证指数",
            "399006.SZ": "创业板指",
            "000300.SH": "沪深300",
        }

        result_lines = [
            "📊 Index technical indicators (based on QMT K-line calculation, downgraded data when Tushare is unavailable)",
            "",
        ]

        for code, name in index_codes.items():
            items = adapter.get_kline(code, period="day", limit=max(lookback_days, 60) + 5)
            if not items:
                result_lines.append(f"- {name}: 暂无数据")
                continue

            closes = []
            for item in items:
                c = item.get("close")
                if c is not None:
                    try:
                        closes.append(float(c))
                    except (TypeError, ValueError):
                        pass

            if len(closes) < 20:
                result_lines.append(f"- {name}: 数据不足")
                continue

            # Calculate MA
            ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else None
            ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
            ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None

            # Calculate RSI(14)
            rsi = None
            if len(closes) >= 15:
                gains, losses = [], []
                for i in range(-14, 0):
                    diff = closes[i] - closes[i - 1]
                    gains.append(max(diff, 0))
                    losses.append(max(-diff, 0))
                avg_gain = sum(gains) / 14
                avg_loss = sum(losses) / 14
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100

            # Trend judgment
            latest = closes[-1]
            trend = "数据不足"
            if ma5 and ma10 and ma20 and ma60:
                if latest > ma5 > ma20 > ma60:
                    trend = "多头排列"
                elif latest < ma5 < ma20 < ma60:
                    trend = "空头排列"
                else:
                    trend = "震荡整理"

            ma60_str = f"{ma60:.2f}" if ma60 else "-"
            rsi_str = f"{rsi:.1f}" if rsi else "-"
            result_lines.append(
                f"- {name}: 最新 {latest:.2f} | MA5={ma5:.2f} MA20={ma20:.2f} MA60={ma60_str} | "
                f"RSI(14)={rsi_str} | {trend}"
            )

        return "\n".join(result_lines)
    except Exception as e:
        return f"⚠️ Tushare Not available, QMT downgrade failed to obtain technical indicators.: {e}"


def _index_market_tools_tushare_unavailable_msg(dimensions: str) -> str:
    """Tushare Unified prompt when QMT is unavailable and cannot be replaced."""
    return (
        f"⚠️ The Tushare data source is currently unavailable,{dimensions}The data is only provided by Tushare, QMT does not support this dimension."
        f"Please give priority to the QMT market analysis data returned by the get_market_analysis tool."
    )


@tool
@register_tool(
    tool_id="get_index_data",
    name="指数数据",
    description="Obtain major index data (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.) and analyze market trends and trends",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["index_data", "index_trend", "market_trend", "moving_average", "main_index"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["index_trend_analysis", "market_direction_assessment", "moving_average_analysis"],
)
def get_index_data(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """
    Get major index data and trend analysis

    Analyze the trends of major indexes such as Shanghai Composite Index, Shenzhen Composite Component Index, ChiNext Index, CSI 300, and CSI 500,
    Including today s rise and fall, the 5th/20th day s rise and fall, moving average position and trend judgment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back, used to calculate moving averages and trends (default 60 days)

    Returns:
        str: Index trend analysis report
    """
    try:
        from core.tools.index_tools import get_index_trend_sync
        return get_index_trend_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取指数数据失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain index data, try QMT downgrade")
            return _qmt_fallback_index_trend(trade_date, lookback_days)
        return f"❌ 获取指数数据失败: {e}"


@tool
@register_tool(
    tool_id="get_market_breadth",
    name="市场宽度",
    description="Analyze the market width to evaluate the overall participation sentiment, and return structured participation indicators such as the number of rising companies, the number of falling companies, the number of daily limit, the number of lower limit, the ratio of rise and fall, and market temperature.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_breadth", "market_sentiment", "advance_decline", "limit_up_down", "participation"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_breadth_analysis", "market_sentiment_assessment", "participation_level_evaluation"],
)
def get_market_breadth(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Analyze market breadth

    Count the number of rising and falling companies, the number of daily limit and lower limit, trading volume distribution, etc., and evaluate the overall market participation and sentiment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market Breadth Analysis Report
    """
    try:
        from core.tools.index_tools import get_market_breadth_sync
        return get_market_breadth_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场宽度失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to get market width, try QMT downgrade")
            return _qmt_fallback_market_breadth(trade_date)
        return f"❌ 获取市场宽度失败: {e}"


@tool
@register_tool(
    tool_id="get_market_environment",
    name="市场环境",
    description="Comprehensively evaluate the multi-dimensional status of the market environment and return comprehensive market environment indicator data such as volatility, turnover rate, turnover, market size, market temperature labels, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_environment", "market_overview", "volatility", "turnover", "market_scale"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_environment_assessment", "comprehensive_market_evaluation", "volatility_analysis"],
)
def get_market_environment(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Comprehensive assessment of market environment

    Integrate multi-dimensional data such as fluctuations, turnover and market size to provide a comprehensive assessment of the market environment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Comprehensive assessment report on market environment
    """
    try:
        from core.tools.index_tools import get_market_environment_sync
        return get_market_environment_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场环境失败: {e}")
        # Tushare Attempts QMT downgrade on failure (returns to QMT Overview as an alternative)
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain market environment, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取市场环境失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取市场环境失败: {e}"


@tool
@register_tool(
    tool_id="identify_market_cycle",
    name="市场周期识别",
    description="Identify the cycle stage the current market is in, and return cycle judgment results such as bull market/bear market/concussion cycle stage labels, trend intensity, judgment basis and confidence level.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_cycle", "cycle_identification", "bull_bear", "regime_detection", "market_phase"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_cycle_identification", "regime_classification", "bull_bear_assessment"],
)
def identify_market_cycle(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Identify market cycles

    Identify the current cycle stage of the market based on technical indicators and market data.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market cycle analysis report
    """
    try:
        from core.tools.index_tools import identify_market_cycle_sync
        return identify_market_cycle_sync(trade_date)
    except Exception as e:
        logger.error(f"识别市场周期失败: {e}")
        # Tushare Attempt QMT downgrade on failure (based on exponential trend judgment period)
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failure to identify market cycles, attempt QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return (
                    "📊 Market cycle identification (based on QMT enhanced analysis, downgrade analysis when Tushare is unavailable)\n\n"
                    "⚠️ Note: This downgrade analysis is based on exponential trends, moving average alignments and MACD signals and is not as comprehensive as the Tushare version.\n\n"
                    f"{report}"
                )
            except Exception as qmt_e:
                return f"❌ 识别市场周期失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 识别市场周期失败: {e}"


@tool
@register_tool(
    tool_id="get_market_overview",
    name="市场概览",
    description="Get an overview of the overall market environment, including comprehensive data such as index trends, rise and fall statistics, capital flows, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_overview", "market_environment", "market_breadth", "capital_flow", "market_sentiment"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["overall_market_overview", "comprehensive_market_analysis", "market_environment_snapshot"],
)
def get_market_overview(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Get an overall market overview

    Comprehensive multi-dimensional data provides an overview of the overall market environment, including:
    - Major index trends
    - Statistics on the number of stocks rising and falling
    - Fund flow situation
    - Market Sentiment Assessment

    This is an alias for get_market_environment and provides the same comprehensive market analysis.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market Overview Analysis Report
    """
    try:
        from core.tools.index_tools import get_market_environment_sync
        return get_market_environment_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场概览失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to get market overview, trying QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取市场概览失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取市场概览失败: {e}"


@tool
@register_tool(
    tool_id="get_market_analysis",
    name="统一大盘分析",
    description="Automatically select the QMT or Tushare path based on the current analysis data source and return unified market analysis results.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_analysis", "market_overview", "unified_analysis", "data_source_routing", "comprehensive_market"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["unified_market_analysis", "multi_source_market_overview", "comprehensive_market_report"],
)
def get_market_analysis(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """The unified market analysis tool automatically routes according to the current data source (QMT or Tushare) and returns the integrated market analysis report.

    Args:
        trade_date: transaction date, format YYYY-MM-DD
        lookback_days: Number of days to look back, default 60

    Returns:
        str: Markdown format of the market analysis report, which is composed of multiple sections. The sections include —
            ## Index trend: index market and trend analysis
            ## Market breadth: number of rising and falling firms, distribution of rising and falling limits
            ## Market environment: Comprehensive market environment assessment
            ## Market Cycle: Market Cycle Phase Identification
            ## Northbound Funds: Northbound Fund Flows from Shanghai-Shenzhen-Hong Kong Stock Connect
            ## Balance of margin financing and securities lending: changes in balance of margin financing and securities lending
            ## Statistics on price limit and price limit: Statistics on number of companies with price limit and price limit
            ## Index technical aspects: MACD/RSI/KDJ and other technical indicators
        QMT Or when Tushare fails, it returns "❌" Error description string at the beginning
    """
    source = _resolve_market_analysis_source()

    if source == "qmt":
        try:
            from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
            return get_market_overview_qmt_enhanced(trade_date, lookback_days)
        except Exception as e:
            logger.error(f"QMT 大盘分析失败: {e}")
            # QMT try when failed Tushare
            if _index_market_tools_is_tushare_available():
                logger.info("QMT Market analysis failed, try to downgrade Tushare")
                try:
                    from core.tools.index_tools import get_market_environment_sync
                    return get_market_environment_sync(trade_date)
                except Exception as ts_e:
                    return f"❌ Market analysis failed: QMT={e}, Tushare={ts_e}"
            return f"❌ QMT Market analysis failed: {e}"

    sections = []
    tool_calls = [
        ("指数趋势", lambda: get_index_data.invoke({"trade_date": trade_date, "lookback_days": lookback_days})),
        ("市场宽度", lambda: get_market_breadth.invoke({"trade_date": trade_date})),
        ("市场环境", lambda: get_market_environment.invoke({"trade_date": trade_date})),
        ("市场周期", lambda: identify_market_cycle.invoke({"trade_date": trade_date})),
        ("北向资金", lambda: get_north_flow.invoke({"trade_date": trade_date, "lookback_days": min(lookback_days, 10)})),
        ("两融余额", lambda: get_margin_trading.invoke({"trade_date": trade_date, "lookback_days": min(lookback_days, 10)})),
        ("涨跌停统计", lambda: get_limit_stats.invoke({"trade_date": trade_date})),
        ("指数技术面", lambda: get_index_technical.invoke({"trade_date": trade_date, "lookback_days": lookback_days})),
    ]

    for title, producer in tool_calls:
        try:
            content = producer()
        except Exception as exc:
            logger.error(f"统一大盘分析组装失败 [{title}]: {exc}")
            content = f"❌ {title} 获取失败: {exc}"
        sections.append(f"## {title}\n{content}")

    return "\n\n".join(sections)


# ==================== Added market analysis tools ====================

@tool
@register_tool(
    tool_id="get_north_flow",
    name="北向资金流向",
    description="Obtain the northbound capital flow data of Shanghai-Shenzhen-Hong Kong Stock Connect and analyze foreign investment trends, and return foreign investment structured data such as net purchases, cumulative positions, industry distribution, active stocks, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["north_flow", "capital_flow", "foreign_capital", "stock_connect", "liquidity"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["northbound_capital_analysis", "foreign_investor_sentiment", "liquidity_assessment"],
)
def get_north_flow(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 10 days"] = 10
) -> str:
    """
    Get northbound capital flow analysis

    Analyze the inflows and outflows of Shanghai-Hong Kong Stock Connect and Shenzhen-Hong Kong Stock Connect, and assess the attitude of foreign investors.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 10 days)

    Returns:
        str: Northbound capital flow analysis report
    """
    try:
        from core.tools.index_tools import get_north_flow_sync
        return get_north_flow_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取北向资金失败: {e}")
        if not _index_market_tools_is_tushare_available():
            return _index_market_tools_tushare_unavailable_msg("北向资金")
        return f"❌ 获取北向资金失败: {e}"


@tool
@register_tool(
    tool_id="get_margin_trading",
    name="两融余额",
    description="Obtain margin financing and securities lending balance data and identify abnormal fields, and return margin financing balance indicator data such as margin financing balance, securities lending balance, margin purchase amount, and balance change trend.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["margin_trading", "financing_balance", "securities_lending", "leverage", "margin_balance"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["margin_balance_analysis", "leverage_level_assessment", "financing_lending_monitoring"],
)
def get_margin_trading(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 10 days"] = 10
) -> str:
    """
    Obtain analysis of the balance of financing and financing

    Describe margin balance levels and identify anomalies or caliber conflicts in changing fields.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 10 days)

    Returns:
        str: Financial balance analysis report
    """
    try:
        from core.tools.index_tools import get_margin_trading_sync
        return get_margin_trading_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取两融余额失败: {e}")
        if not _index_market_tools_is_tushare_available():
            return _index_market_tools_tushare_unavailable_msg("两融余额")
        return f"❌ 获取两融余额失败: {e}"


@tool
@register_tool(
    tool_id="get_limit_stats",
    name="涨跌停统计",
    description="Obtain the statistics of the number of companies with daily limit and the number of companies with rise and fall, describe the rise and fall distribution, and return the statistical data of rise and fall distribution such as the number of companies with daily limit/lower limit, price ratio, height of connecting board, and board explosion rate.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["limit_stats", "limit_up_down", "advance_decline", "price_distribution", "market_breadth"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["limit_up_down_statistics", "market_breadth_assessment", "price_distribution_analysis"],
)
def get_limit_stats(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Obtain statistics on price limits and number of companies rising and falling

    Count the number of companies with price limits, the number of companies with price increases, and distribution of price changes, and output factual data for induction by the upper-layer model.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Analysis report on price limit and number of companies rising and falling
    """
    try:
        from core.tools.index_tools import get_limit_stats_sync
        return get_limit_stats_sync(trade_date)
    except Exception as e:
        logger.error(f"获取涨跌停统计失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain price limit statistics, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_limit_stats_qmt_sync
                return get_limit_stats_qmt_sync(trade_date)
            except Exception as qmt_e:
                return f"❌ 获取涨跌停统计失败: Tushare={e}, QMT降级={qmt_e}"
        if not _index_market_tools_is_tushare_available():
            return _index_market_tools_tushare_unavailable_msg("涨跌停统计")
        return f"❌ 获取涨跌停统计失败: {e}"


@tool
@register_tool(
    tool_id="get_index_technical",
    name="指数技术指标",
    description="Obtain index technical indicators and rule labels, and return technical indicator data such as MACD/RSI/KDJ numerical sequences, golden cross and dead cross signals, trend labels, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["index_technical", "technical_indicators", "technical_analysis", "macd", "rsi", "kdj"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["index_technical_analysis", "index_momentum_assessment", "index_signal_detection"],
)
def get_index_technical(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """
    Get analysis of index technical indicators

    Calculate the MACD, RSI, KDJ and other technical indicators of the Shanghai Composite Index, and return the indicator values ​​and lightweight rule labels.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 60 days)

    Returns:
        str: Index Technical Indicator Report
    """
    try:
        from core.tools.index_tools import get_index_technical_sync
        return get_index_technical_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取指数技术指标失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _index_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain technical indicators, try QMT downgrade")
            return _qmt_fallback_technical(trade_date, lookback_days)
        return f"❌ Failed to obtain index technical indicators: {e}"

# === qmt_market_tools ===
"""QMT Market and sector analysis tools in mode."""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced, get_sector_analysis_qmt_enhanced

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_market_overview_qmt",
    name="QMT 大盘概览",
    description="Based on QMT index prices, market-wide snapshots and activity proxy indicators, a broad market analysis report is generated.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_overview", "qmt", "index_data", "market_breadth", "market_activity"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["qmt_market_overview", "market_breadth_analysis", "market_activity_assessment"],
)
def get_market_overview_qmt(
    trade_date: Annotated[str, "Analysis date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60,
) -> str:
    """Based on QMT index prices, market-wide snapshots and activity proxy indicators, a broad market analysis report is generated.

    Args:
        trade_date: Analysis date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 60 days)

    Returns:
        str: Market analysis report
    """
    try:
        return get_market_overview_qmt_enhanced(trade_date, lookback_days)
    except Exception as exc:
        logger.error(f"QMT 大盘概览失败: {exc}")
        return f"❌ QMT Market overview failed: {exc}"


@tool
@register_tool(
    tool_id="get_sector_analysis_qmt",
    name="QMT 板块分析",
    description="Based on QMT individual stock prices and local industry mapping, analyze the strength, weakness, leadership and diffusion within the industry.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "qmt", "industry_rotation", "peer_comparison", "sector_strength"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["qmt_sector_analysis", "industry_strength_comparison", "sector_leader_identification"],
)
def get_sector_analysis_qmt(
    ticker: Annotated[str, "Stock code (e.g. 600519, 000001)"],
    trade_date: Annotated[str, "Analysis date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
    top_n: Annotated[int, "Display the top N strong constituent stocks, default 10"] = 10,
) -> str:
    """Based on QMT individual stock prices and local industry mapping, analyze the strength, weakness, leadership and diffusion within the industry.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        trade_date: Analysis date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 20 days)
        top_n: Display the top N strong constituent stocks (default 10)

    Returns:
        str: Sector analysis report
    """
    try:
        return get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days, top_n)
    except Exception as exc:
        logger.error(f"QMT 板块分析失败: {exc}")
        return f"❌ QMT Sector analysis failed: {exc}"

# === sector_market_tools ===
"""
Sector analysis tools

Provides sector performance analysis, rotation identification, peer comparison and other functions
These tools are for SectorAnalystV2 analysts
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_analysis_data_source

logger = logging.getLogger(__name__)


def _resolve_sector_analysis_source() -> str:
    """Get the data sources that current industry analysis tools should use."""
    current_source = get_current_analysis_data_source()
    if current_source == "qmt":
        return "qmt"
    return "tushare"


def _sector_market_tools_is_tushare_available() -> bool:
    """Check if Tushare data source is available."""
    try:
        from app.services.data_sources.tushare_adapter import TushareAdapter
        return TushareAdapter().is_available()
    except Exception:
        return False


def _sector_market_tools_is_qmt_available() -> bool:
    """Check if the QMT data source is available."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        return QMTAdapter().is_available()
    except Exception:
        return False


def _sector_market_tools_tushare_unavailable_msg(dimensions: str) -> str:
    """Tushare Unified prompt when QMT is unavailable and cannot be replaced."""
    return (
        f"⚠️ The Tushare data source is currently unavailable,{dimensions}The data is only provided by Tushare, QMT does not support this dimension."
        f"Please give priority to the QMT industry analysis data returned by the get_sector_analysis tool."
    )


@tool
@register_tool(
    tool_id="get_sector_data",
    name="板块数据",
    description="Obtain the performance data of the sector to which the stock belongs and analyze industry trends, and return sector trend data information such as sector gains and losses, turnover, leading stocks, capital flows, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_data", "sector_performance", "industry_trend", "sector_ranking", "industry_analysis"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_performance_analysis", "industry_trend_evaluation", "sector_ranking_review"],
)
def get_sector_data(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20
) -> str:
    """
    Get performance data for the sector to which a stock belongs

    Analyze the recent performance of the industry sector to which the stock belongs, including gains and losses, capital flows, sector rankings, etc.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 20 days)

    Returns:
        str: Sector performance analysis report
    """
    try:
        from core.tools.sector_tools import get_sector_performance_sync
        return get_sector_performance_sync(ticker, trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取板块数据失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _sector_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain sector data, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取板块数据失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取板块数据失败: {e}"


@tool
@register_tool(
    tool_id="get_fund_flow_data",
    name="资金流向",
    description=(
        "Obtain sector fund flow data and analyze main fund trends, sector net fund inflows/outflows, and sector rotations."
        "Here s Fund flow It refers to the capital side of the trading market, not operating cash flow, investment cash flow, financing cash flow or free cash flow in financial statements."
    ),
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["fund_flow", "capital_flow", "sector_rotation", "main_capital", "liquidity_flow"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_capital_flow_analysis", "sector_rotation_identification", "main_capital_tracking"],
    when_to_use="Use it when you need evidence of sector capital flows, main capital inflows and outflows, and industry rotation capital.",
    when_not_to_use="It is not used for cash flow statement analysis, cash flow deterioration, profit content, financial risk or individual stock financial cash flow quality judgment; these needs should use cash flow/financial risk tools.",
)
def get_fund_flow_data(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the first N sections, default 10"] = 10,
    lookback_days: Annotated[int, "Looking back the number of days,1=On that day only,30=Accumulated in the last month, default 1"] = 1
) -> str:
    """
    Obtain sector fund flow data

    Analyze the inflow and outflow of funds in each sector, and identify the main capital trends and sector rotation trends.
    Supports single-day snapshots (lookback_days=1) and multi-day cumulative aggregation (lookback_days>1) Two modes.

    Args:
        trade_date: Closing transaction date (format: YYYY-MM-DD)
        top_n: Return the first N sections (default 10)
        lookback_days: Looking back the number of days,1=On that day only,30=Accumulated in the last month (default 1)

    Returns:
        str: Sector capital flow analysis report
    """
    try:
        from core.tools.sector_tools import get_sector_rotation_sync
        return get_sector_rotation_sync(trade_date, top_n, lookback_days)
    except Exception as e:
        logger.error(f"获取资金流向失败: {e}")
        if not _sector_market_tools_is_tushare_available():
            return _sector_market_tools_tushare_unavailable_msg("板块资金流向")
        return f"❌ 获取资金流向失败: {e}"


@tool
@register_tool(
    tool_id="get_peer_comparison",
    name="同业对比",
    description="Obtain comparative data of stocks in the same industry to analyze the position of individual stocks in the industry, and return to peer comparison tables such as market capitalization, PE, PB, ROE, increase and decrease rankings, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["peer_comparison", "industry_ranking", "competitor_analysis", "competitive_positioning"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["peer_comparison_analysis", "industry_ranking_evaluation", "competitive_positioning"],
)
def get_peer_comparison(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the top N peer stocks, default 10"] = 10
) -> str:
    """
    Get comparative data on stocks in the same industry

    Analyze the performance ranking of target stocks in the same industry, including comparisons in terms of increase and decrease, market value, valuation and other dimensions.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)
        top_n: Returns the top N peer stocks (default 10)

    Returns:
        str: Comparative analysis report of peers
    """
    try:
        from core.tools.sector_tools import get_peer_comparison_sync
        return get_peer_comparison_sync(ticker, trade_date, top_n)
    except Exception as e:
        logger.error(f"获取同业对比失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _sector_market_tools_is_qmt_available():
            logger.info("Tushare Failed to obtain peer comparison, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, 20, top_n)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取同业对比失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取同业对比失败: {e}"


@tool
@register_tool(
    tool_id="get_industry_top_companies",
    name="同行业TOP公司",
    description="Obtain a list of the top N companies in the same industry by market capitalization, suitable for quickly understanding the industry competition landscape and peer comparison.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["industry_top_companies", "industry_leaders", "competitive_landscape", "market_cap_ranking", "moat_analysis"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["industry_leader_identification", "competitive_landscape_overview", "market_cap_ranking_review"],
)
def get_industry_top_companies(
    ticker: Annotated[str, "Stock code (such as 600519 or 600519.SH)"],
    top_n: Annotated[int, "Returns the top N companies in the same industry, default 5"] = 5
) -> str:
    """
    Get the list of TOP N companies in the same industry (light version)

    Automatically identify the industry to which the stock belongs, and return the top N companies in the same industry sorted by market value.
    Contains key indicators such as code, name, market capitalization, PE, PB, etc.
    There is no need to enter the transaction date, and the latest transaction day data will be automatically obtained.

    Args:
        ticker: Stock code (such as 600519 or 600519.SH)
        top_n: Return the top N companies in the same industry (default 5)

    Returns:
        str: Brief list of TOP N companies in the same industry
    """
    try:
        from core.tools.sector_tools import get_industry_top_companies_sync
        return get_industry_top_companies_sync(ticker, top_n)
    except Exception as e:
        logger.error(f"Failed to obtain TOP company in the same industry: {e}")
        return f"❌ Failed to obtain TOP company in the same industry: {e}"


@tool
@register_tool(
    tool_id="analyze_sector",
    name="综合板块分析",
    description="Comprehensive analysis of the sector to which the stock belongs includes performance rotation, peer comparison, etc. Returns comprehensive analysis reports on sector performance, rotation signals, peer comparison, capital flow, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "sector_performance", "sector_rotation", "peer_comparison", "comprehensive_sector"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["comprehensive_sector_analysis", "multi_dimension_sector_evaluation", "integrated_industry_review"],
)
def analyze_sector(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Comprehensive sector analysis

    Integrate multi-dimensional data such as sector performance, capital flow, and peer comparison to provide a comprehensive sector analysis report.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Comprehensive sector analysis report
    """
    try:
        from core.tools.sector_tools import analyze_sector_sync
        return analyze_sector_sync(ticker, trade_date)
    except Exception as e:
        logger.error(f"综合板块分析失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _sector_market_tools_is_qmt_available():
            logger.info("Tushare Comprehensive sector analysis failed, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, 20, 10)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 综合板块分析失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 综合板块分析失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_analysis",
    name="统一行业分析",
    description="Automatically select the QMT or Tushare path based on the current analysis data source and return unified industry analysis results.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "unified_analysis", "sector_performance", "data_source_routing", "comprehensive_industry"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["unified_sector_analysis", "multi_source_sector_evaluation", "comprehensive_industry_report"],
)
def get_sector_analysis(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
    top_n: Annotated[int, "Returns the first N results, default 10"] = 10
) -> str:
    """A unified industry analysis tool that automatically routes according to the current data source (QMT or Tushare) and returns integrated industry analysis reports.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: transaction date, format YYYY-MM-DD
        lookback_days: Number of days to look back, default 20
        top_n: Returns the first N results, default 10

    Returns:
        str: Markdown Format industry analysis report, composed of multiple sections, including —
            ## Sector performance: sector trends and rise and fall performance
            ## Sector Fund Flow Direction: Ranking of Sector Fund Inflows and Outflows
            ## Comparison with peers: Comparison of stocks in the same industry
        QMT Or when Tushare fails, it returns "❌" Error description string at the beginning
    """
    source = _resolve_sector_analysis_source()

    if source == "qmt":
        try:
            from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
            return get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days, top_n)
        except Exception as e:
            logger.error(f"QMT 行业分析失败: {e}")
            # QMT try when failed Tushare
            if _sector_market_tools_is_tushare_available():
                logger.info("QMT Industry analysis failed, try Tushare downgrade")
                try:
                    from core.tools.sector_tools import analyze_sector_sync
                    return analyze_sector_sync(ticker, trade_date)
                except Exception as ts_e:
                    return f"❌ Industry analysis failed: QMT={e}, Tushare={ts_e}"
            return f"❌ QMT Industry analysis failed: {e}"

    sections = []
    tool_calls = [
        ("板块表现", lambda: get_sector_data.invoke({"ticker": ticker, "trade_date": trade_date, "lookback_days": lookback_days})),
        ("板块资金流向", lambda: get_fund_flow_data.invoke({"trade_date": trade_date, "top_n": top_n, "lookback_days": 1})),
        ("同业对比", lambda: get_peer_comparison.invoke({"ticker": ticker, "trade_date": trade_date, "top_n": top_n})),
    ]

    for title, producer in tool_calls:
        try:
            content = producer()
        except Exception as exc:
            logger.error(f"统一行业分析组装失败 [{title}]: {exc}")
            content = f"❌ {title} 获取失败: {exc}"
        sections.append(f"## {title}\n{content}")

    return "\n\n".join(sections)


# ============================================================
# Section level tools (use the section name as the entry, no ticker required)
# ============================================================

@tool
@register_tool(
    tool_id="search_sector",
    name="板块搜索",
    description="Search A-share sectors (industry/concept/region) by name keywords and return a list of matching sectors",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_search", "sector_lookup", "industry_classification", "concept_classification"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_lookup", "industry_classification_search", "sector_code_discovery"],
    when_to_use="Used when the user mentions keywords such as sector, industry, concept, etc. and needs to find the sector code first.",
)
def search_sector_tool(
    keyword: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor, new energy)"],
    sector_type: Annotated[str, "Section type: N=Industry sector I=Industry Index S=concept R=Region, default N"] = "N",
) -> str:
    """
    Search the Flush section by name and keywords

    Returns a list of matching sectors, including sector code, name, and number of constituent stocks.

    Args:
        keyword: Section name keywords
        sector_type: Section type (N=Industry, S=concept, R=region)

    Returns:
        str: Section search results
    """
    try:
        from core.tools.sector_tools import search_sector_sync
        return search_sector_sync(keyword, sector_type)
    except Exception as e:
        logger.error(f"板块搜索失败: {e}")
        if not _sector_market_tools_is_tushare_available():
            return _sector_market_tools_tushare_unavailable_msg("Section search (flush section list)")
        return f"❌ 板块搜索失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_daily",
    name="板块行情",
    description="Obtain the daily market data of the sector index, including rise and fall, trading volume, turnover rate, market value, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_daily", "sector_quote", "sector_index", "sector_trend", "sector_volume"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_index_quote", "sector_daily_performance", "sector_trend_review"],
    when_to_use="Used when users want to know the recent trend, rise and fall of a certain sector",
)
def get_sector_daily_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
) -> str:
    """
    Get daily quotes of sector indexes

    Args:
        sector_name: Section name keywords
        trade_date: transaction date
        lookback_days: Number of days to look back

    Returns:
        str: Sector market report
    """
    try:
        from core.tools.sector_tools import get_sector_daily_sync
        return get_sector_daily_sync(sector_name, trade_date, lookback_days)
    except Exception as e:
        logger.error(f"板块行情获取失败: {e}")
        if not _sector_market_tools_is_tushare_available():
            return _sector_market_tools_tushare_unavailable_msg("Sector Quotes (Daily Flush Sector Index)")
        return f"❌ 板块行情获取失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_constituents",
    name="板块成分股",
    description="Obtain the list of constituent stocks of the sector and its market value and valuation ranking, and return the sorting table data information such as constituent stock code, name, market value, PE, PB, increase and decrease, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_constituents", "sector_members", "sector_leaders", "constituent_ranking"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_member_listing", "sector_leader_identification", "constituent_ranking_review"],
    when_to_use="Used when users want to know which stocks are in a certain sector and which are the leading stocks.",
)
def get_sector_constituents_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the top N constituent stocks, default 15"] = 15,
) -> str:
    """
    Get the list of sector constituent stocks and their performance

    Args:
        sector_name: Section name keywords
        trade_date: transaction date
        top_n: Return the top N constituent stocks

    Returns:
        str: Sector constituent stock report
    """
    try:
        from core.tools.sector_tools import get_sector_constituents_sync
        return get_sector_constituents_sync(sector_name, trade_date, top_n)
    except Exception as e:
        logger.error(f"板块成分股获取失败: {e}")
        if not _sector_market_tools_is_tushare_available():
            return _sector_market_tools_tushare_unavailable_msg("Sector constituent stocks (flush sector constituent list)")
        return f"❌ 板块成分股获取失败: {e}"


@tool
@register_tool(
    tool_id="analyze_sector_by_name",
    name="板块综合分析",
    description="Comprehensive analysis by sector name, integrating sector market conditions, leading constituent stocks, and market-wide capital flows",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "sector_comprehensive", "sector_performance", "fund_flow", "sector_leaders"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["sector_comprehensive_analysis", "sector_investment_opportunity", "multi_dimension_sector_review"],
    when_to_use="Used when users ask about investment opportunities, sector analysis, and industry prospects of a certain sector.",
)
def analyze_sector_by_name_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaics, semiconductors, liquor, new energy vehicles)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Comprehensive analysis of sectors (use sector name as entry)

    Args:
        sector_name: Section name keywords
        trade_date: transaction date

    Returns:
        str: Comprehensive sector analysis report
    """
    try:
        from core.tools.sector_tools import analyze_sector_by_name_sync
        return analyze_sector_by_name_sync(sector_name, trade_date)
    except Exception as e:
        logger.error(f"板块综合分析失败: {e}")
        if not _sector_market_tools_is_tushare_available():
            return _sector_market_tools_tushare_unavailable_msg("Comprehensive analysis of sectors (flush sector system)")
        return f"❌ 板块综合分析失败: {e}"

# === stock_market_data ===
"""
Unified stock market data tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources
"""

import asyncio
import concurrent.futures
import json
import logging
import re
from datetime import datetime
from typing import Annotated, Optional, Tuple
from zoneinfo import ZoneInfo
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)
_CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _get_china_now() -> datetime:
    return datetime.now(_CHINA_TZ)


def _normalize_trade_date(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    return text


def _resolve_china_actual_data_date(
    ticker: str,
    requested_end_date: str,
    now: Optional[datetime] = None,
    db_latest_trade_date: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    requested_date = _normalize_trade_date(requested_end_date) or requested_end_date
    latest_trade_date = _normalize_trade_date(db_latest_trade_date or _get_db_latest_trade_date_sync(ticker))

    if not latest_trade_date:
        return requested_date, None, None

    if latest_trade_date >= requested_date:
        return requested_date, requested_date, None

    current_time = now or _get_china_now()
    current_date = current_time.strftime("%Y-%m-%d")
    trading_status = None

    try:
        from app.utils.trading_time import get_trading_status

        trading_status = get_trading_status(current_time)
    except Exception as exc:
        logger.debug(f"[market tools] Failed to read session status (non-fatal): {exc}")

    if requested_date == current_date:
        status_messages = {
            "pre_market": "It is currently in the pre-market period and the daily data for the day has not yet been formed.",
            "morning_session": "It is currently in the trading session, and the daily closing price of the day has not yet been finalized.",
            "noon_break": "The market is currently closed at noon, and the daily closing price has not yet been finalized.",
            "afternoon_session": "It is currently in the trading session, and the daily closing price of the day has not yet been finalized.",
            "after_market": "Currently in the after-hours buffer period, the daily data may not have been completed yet.",
        }
        reason = status_messages.get(trading_status, "There is no complete daily data for the current requested date.")
        note = (
            f"请求分析日期为 {requested_date}，但{reason}；"
            f"The following prices and technical indicators are based on the most recent completed trading days {latest_trade_date} shall prevail."
        )
    else:
        note = (
            f"请求分析日期为 {requested_date}，但工具可用的最近完整日线数据截至 {latest_trade_date}；"
            f"The following prices and technical indicators are based on {latest_trade_date} shall prevail."
        )

    return latest_trade_date, latest_trade_date, note


def _get_last_trade_date_sync() -> Optional[str]:
    """Synchronously read the latest trading day (from TradingCalendarService) from Redis.

    Returns:
        String of the latest trading day in the format YYYY-MM-DD; if read fails, None is returned.
    """
    try:
        from app.core.database import get_redis_sync_client
        redis_client = get_redis_sync_client()
        raw = redis_client.get("trading_calendar:last_trade_date")
        if raw:
            data = json.loads(raw)
            return data.get("last_trade_date")
    except Exception as e:
        logger.debug(f"[JIT-Tool] Failed to read Redis transaction calendar (non-fatal): {e}")
    return None


def _get_db_latest_trade_date_sync(symbol: str, data_source: Optional[str] = None) -> Optional[str]:
    """Query the latest trade_date of a security from MongoDB.

    Args:
        symbol: Securities code (6 digits or suffix is acceptable)
        data_source: Specify the data source (such as "tushare") ; When None, query the latest date in all data sources.

    Returns:
        Latest date string in the format YYYY-MM-DD; if it does not exist, None is returned.
    """
    try:
        from app.core.database import get_mongo_db_sync
        from tradingagents.utils.stock_utils import StockUtils

        db = get_mongo_db_sync()
        code6 = str(symbol).zfill(6)
        is_fund = StockUtils.is_fund(code6)
        collection = db.etf_daily_quotes if is_fund else db.stock_daily_quotes
        symbol_field = "code" if is_fund else "symbol"
        query: dict = {symbol_field: code6}
        if data_source:
            query["data_source"] = data_source

        doc = collection.find_one(
            query,
            {"trade_date": 1, "_id": 0},
            sort=[("trade_date", -1)]
        )
        if doc:
            raw_date = doc.get("trade_date", "")
            # uniformly converted to YYYY-MM-DD
            s = str(raw_date).replace("-", "")
            if len(s) == 8:
                return f"{s[:4]}-{s[4:6]}-{s[6:]}"
            return str(raw_date)
    except Exception as e:
        logger.debug(f"[JIT-Tool] Failed to read MongoDB latest trading day (non-fatal): {e}")
    return None


def _trigger_jit_sync_in_thread(stock_code: str) -> None:
    """Run JIT asynchronous synchronization in a separate thread to avoid nested event loop issues.

    Because the agent tool runs in a thread that already has an event loop (ThreadWorker s async context),
    not directly asyncio.run(), An independent event loop needs to be created with the help of a new thread.

    An independent asynchronous MongoDB connection is initialized in the new thread to avoid sharing event loop-bound clients across threads.
    """
    async def _do_sync():
        # 🔥 Initialize a standalone asynchronous MongoDB connection in a new event loop
        from motor.motor_asyncio import AsyncIOMotorClient
        from app.core.config import settings

        mongo_client = None
        try:
            # Create a new asynchronous MongoDB client (bound to the current thread's event loop)
            mongo_client = AsyncIOMotorClient(
                settings.MONGO_URI,
                maxPoolSize=10,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000
            )
            mongo_db = mongo_client[settings.MONGO_DB]  # Use MONGO_DB instead MONGO_DB_NAME

            # Temporarily injected into global variables for use by jit_sync_stock_data
            import app.core.database as db_module
            original_db = db_module.mongo_db
            db_module.mongo_db = mongo_db

            try:
                from app.worker.analysis_worker import jit_sync_stock_data
                result = await jit_sync_stock_data(
                    stock_code=stock_code,
                    parameters_dict={"market_type": "cn"}
                )
                return result
            finally:
                # Restore original global variables
                db_module.mongo_db = original_db
        finally:
            # Close the newly created MongoDB connection
            if mongo_client:
                mongo_client.close()

    def _run_in_new_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_do_sync())
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_in_new_loop)
            result = future.result(timeout=120)  # Wait up to 2 minutes
            if result and hasattr(result, "is_valid"):
                if result.is_valid:
                    logger.info(f"✅ [JIT-Tool] {stock_code} 数据同步完成: {getattr(result, 'message', '')}")
                else:
                    logger.warning(f"⚠️ [JIT-Tool] {stock_code} Data synchronization failed (continue using existing data): {getattr(result, 'message', '')}")
    except concurrent.futures.TimeoutError:
        logger.warning(f"⚠️ [JIT-Tool] {stock_code} JIT Synchronization timeout (120s), continue to use existing data")
    except Exception as e:
        logger.warning(f"⚠️ [JIT-Tool] {stock_code} JIT Synchronization exception (continue using existing data): {e}")


def _ensure_fresh_china_data(ticker: str, data_source: Optional[str] = None) -> None:
    """Check the freshness of A-share data and trigger JIT synchronization if it is stale.

    freshness**Highest priority real API data source**Subject to:
    - If data_source is not specified, the first non-local data source in the database configuration is automatically taken.
    - If data_source is specified, the data source is directly used for checking.

    This function is completely synchronous, and internally handles asynchronous JIT synchronous calls through independent threads.
    Will not block the current event loop, and will not cause nested event loop conflicts.
    """
    # 1. Get the latest trading day from Redis (Trading Calendar Service Maintenance)
    last_trade_date = _get_last_trade_date_sync()
    if not last_trade_date:
        logger.debug("[JIT-Tool] The Redis transaction calendar was not obtained, so the freshness check was skipped and the existing data was used directly.")
        return

    # 2. Determine the data source to check: the caller-specified value is used first; otherwise, the real API source with the highest priority is used
    check_source = data_source
    if not check_source:
        try:
            from app.core.data_source_priority import get_enabled_data_sources_sync
            all_sources = get_enabled_data_sources_sync("a_shares")
            # Exclude cache layers such as local/mongodb and only take the real API data source
            api_sources = [s for s in all_sources if s not in ("local", "mongodb", "local_file")]
            check_source = api_sources[0] if api_sources else None
        except Exception as _e:
            logger.debug(f"[JIT-Tool] Failed to get data source priority (non-fatal): {_e}")

    # 3. Check the latest data date of MongoDB (filter by specified data source)
    db_latest = _get_db_latest_trade_date_sync(ticker, data_source=check_source)

    logger.info(
        f"🔍 [JIT-Tool] {ticker} 新鲜度检查 [数据源={check_source or '全部'}]: "
        f"DB latest day={db_latest or 'No data'}, Last trading day={last_trade_date}"
    )

    # 4. Determine whether synchronization is required
    if db_latest is None or db_latest < last_trade_date:
        logger.info(
            f"📡 [JIT-Tool] {ticker} 数据陈旧，触发 JIT 同步 "
            f"[{check_source or 'All'}] (DB={db_latest or 'N/A'} < Last trading day={last_trade_date})"
        )
        _trigger_jit_sync_in_thread(ticker)
    else:
        logger.info(
            f"✅ [JIT-Tool] {ticker} 数据已是最新 [{check_source or '全部'}]"
            f" ({db_latest} >= {last_trade_date}) , Skip sync"
        )


@tool
@register_tool(
    tool_id="get_stock_market_data_unified",
    name="统一股票市场数据",
    description="Obtain stock market data and technical indicators, support A-shares, Hong Kong stocks, and US stocks, and return data such as K-line data, trading volume, technical indicators, and basic market snapshots.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_market_data", "market_data", "stock_price", "price_history", "market_quote", "technical_indicators"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["stock_market_data_retrieval", "price_history_analysis", "multi_market_data_query"],
)
def get_stock_market_data_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    start_date: Annotated[str, "Start date, format: YYYY-MM-DD. Note: The system automatically expands to the configured number of lookback days (usually 365 days), you only need to pass the analysis date"],
    end_date: Annotated[str, "End date, format: YYYY-MM-DD. Usually the same as start_date, just pass the current analysis date"]
) -> str:
    """
    Unified stock market data tool
    Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources to obtain price and technical indicator data

    ⚠️ Important: The system automatically extends the date range to the configured number of lookback days (usually 365 days) to ensure there is sufficient historical data for technical indicator calculations.
    You only need to pass the current analysis date as start_date and end_date, no need to manually calculate the historical date range.

    Args:
        ticker: Stock code (such as: 000001, 0700.HK, AAPL)
        start_date: Start date (format: YYYY-MM-DD). Just pass the current analysis date and the system will automatically expand it.
        end_date: End date (format: YYYY-MM-DD). Just pass the current analysis date

    Returns:
        str: Market data and technical analysis reports

    Example:
        If the analysis date is 2025-11-09, pass:
        - ticker: "00700.HK"
        - start_date: "2025-11-09"
        - end_date: "2025-11-09"
        The system will automatically obtain 365 days of historical data from 2024-11-09 to 2025-11-09
    """
    # Standardized A-share code: remove the .SZ/.SH/.BJ suffix (the front and back ends use pure 6-digit numbers uniformly)
    original_ticker = ticker
    ticker = re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', ticker.strip())
    if original_ticker != ticker:
        logger.info(f"📈 [unified market tools] Standardized stock code: {original_ticker} -> {ticker}")

    logger.info(f"📈 [unified market tools] Analyze stocks: {ticker}")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        # Automatically identify stock types
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        logger.info(f"📈 [unified market tools] Stock type: {market_info['market_name']}")
        logger.info(f"📈 [unified market tools] Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")

        result_data = []

        if is_china:
            # China A Shares: Using China Stock Data Sources
            logger.info("🇨🇳 [unified market tools] Process A-share market data...")

            requested_start_date = _normalize_trade_date(start_date) or start_date
            requested_end_date = _normalize_trade_date(end_date) or end_date
            effective_start_date = start_date
            effective_end_date = end_date
            actual_data_date = None
            date_note = None

            # ===== JIT Freshness check: Ensure MongoDB data covers the most recent trading day =====
            # First check whether the DB data has overwritten the latest trading day cached by Redis;
            # If it is stale, asynchronously pull the latest market data in a separate thread and write it to MongoDB.
            # Then get_china_stock_data_unified can read the latest data.
            try:
                _ensure_fresh_china_data(ticker)
            except Exception as _jit_err:
                logger.warning(f"⚠️ [JIT-Tool] An exception occurred in the freshness check (does not affect analysis): {_jit_err}")
            # ============================================================

            try:
                effective_end_date, actual_data_date, date_note = _resolve_china_actual_data_date(
                    ticker,
                    requested_end_date,
                )
                if requested_start_date == requested_end_date:
                    effective_start_date = effective_end_date
                logger.info(
                    f"📅 [统一市场工具] A股日期语义: 请求日期={requested_end_date}, "
                    f"actual data date={actual_data_date or 'unknown'}, Inquiry deadline={effective_end_date}"
                )
            except Exception as date_err:
                logger.warning(f"⚠️ [unified market tools] Failed to parse the actual data date of A shares (continue to request according to the original date): {date_err}")

            try:
                from tradingagents.dataflows.interface import get_china_stock_data_unified
                stock_data = get_china_stock_data_unified(ticker, effective_start_date, effective_end_date)

                # 🔍 Debugging: Print the first 500 characters of the returned data
                logger.info(f"🔍 [Market tool debugging] A Stock data return length: {len(stock_data)}")
                logger.info(f"🔍 [Market tool debugging] A The first 500 characters of stock data:\n{stock_data[:500]}")

                date_context_lines = [f"**请求分析日期**: {requested_end_date}"]
                if actual_data_date:
                    date_context_lines.append(f"**实际数据日期**: {actual_data_date}")
                if date_note:
                    date_context_lines.append(f"**日期说明**: {date_note}")

                result_data.append(
                    "## A股市场数据\n"
                    + "\n".join(date_context_lines)
                    + f"\n\n{stock_data}"
                )
            except Exception as e:
                logger.error(f"❌ [Market tool debugging] A Failed to obtain stock data: {e}")
                result_data.append(f"## A stock market data\n Failed to obtain: {e}")

        elif is_hk:
            # Hong Kong stocks: using AKShare data source
            logger.info("🇭🇰 [unified market tools] Process Hong Kong stock market data...")

            try:
                from tradingagents.dataflows.interface import get_hk_stock_data_unified
                hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                # 🔍 Debugging: Print the first 500 characters of the returned data
                logger.info(f"🔍 [Market tool debugging] Hong Kong stock data return length: {len(hk_data)}")
                logger.info(f"🔍 [Market tool debugging] The first 500 characters of Hong Kong stock data:\n{hk_data[:500]}")

                result_data.append(f"## 港股市场数据\n{hk_data}")
            except Exception as e:
                logger.error(f"❌ [Market tool debugging] Failed to obtain Hong Kong stock data: {e}")
                result_data.append(f"## Hong Kong stock market data\n Failed to obtain: {e}")

        else:
            # US stocks: Prioritize the use of FINNHUB API data sources
            logger.info("🇺🇸 [unified market tools] Process U.S. stock market data...")

            try:
                from tradingagents.dataflows.providers.us.optimized import get_us_stock_data_cached
                us_data = get_us_stock_data_cached(ticker, start_date, end_date)
                result_data.append(f"## 美股市场数据\n{us_data}")
            except Exception as e:
                result_data.append(f"## US stock market data\n Failed to obtain: {e}")

        # Combine all data
        combined_result = f"""# {ticker} 市场数据分析

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
    **请求分析期间**: {start_date} 至 {end_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

        logger.info(f"📈 [unified market tools] Data acquisition completed, total length: {len(combined_result)}")
        return combined_result

    except Exception as e:
        error_msg = f"Unified market data tool execution failed: {str(e)}"
        logger.error(f"❌ [统一市场工具] {error_msg}")
        return error_msg


# === stock_screening_tool ===
"""
Market-wide stock batch screening tool

Encapsulate EnhancedScreeningService / DatabaseScreeningService,
Let LLM filter A shares in batches by condition through function calling.
"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

def resolve_metric_value(*a, **kw):
    from app.services.screening_services import resolve_metric_value as _rmv
    return _rmv(*a, **kw)
def select_metric_display_spec(*a, **kw):
    from app.services.screening_services import select_metric_display_spec as _smds
    return _smds(*a, **kw)
from app.services.factor_registry_service import build_screening_fields_markdown, build_screening_tool_description
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

MAX_DETAILED_RESULTS = 8

SUPPORTED_FIELDS_DOC = """
Supported filter fields:
{fields_markdown}

Supported operators:> < >= <= == != between in not_in contains
- between The value is [minimum value, maximum value]
- in / not_in The value is a list
""".format(fields_markdown=build_screening_fields_markdown(public_only=True))


def _format_metric(value, *, suffix: str = "", decimals: int = 2, scale: float = 1.0) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    scaled = value / scale
    return f"{scaled:.{decimals}f}{suffix}"


def _build_compact_candidate_line(
    index: int,
    item: dict,
    pe_display_field: str,
    pe_display_label: str,
    pb_display_field: str,
    pb_display_label: str,
) -> str:
    code = item.get("code") or item.get("symbol", "")
    name = item.get("name", "")
    industry = item.get("industry", "-")
    pe_value = resolve_metric_value(item, pe_display_field, "pe")
    pb_value = resolve_metric_value(item, pb_display_field, "pb")

    parts = [
        f"股息率={_format_metric(item.get('dividend_yield'), suffix='%')}",
        f"{pe_display_label}={_format_metric(pe_value)}",
        f"{pb_display_label}={_format_metric(pb_value)}",
        f"ROE={_format_metric(item.get('roe'), suffix='%')}",
        f"负债率={_format_metric(item.get('debt_to_assets'), suffix='%', decimals=1)}",
        f"经营现金流={_format_metric(item.get('n_cashflow_act'), suffix='亿', decimals=2, scale=1e8)}",
        f"市值={_format_metric(item.get('total_mv'), suffix='亿')}",
    ]

    price = item.get("close")
    if isinstance(price, (int, float)):
        parts.append(f"股价={price:.2f}元")

    pct_chg = item.get("pct_chg")
    if isinstance(pct_chg, (int, float)):
        parts.append(f"涨跌={pct_chg:+.2f}%")

    report_period = item.get("report_period")
    if report_period:
        parts.append(f"财报期={report_period}")

    if item.get("is_st") is True:
        parts.append("ST")

    compact_parts = [part for part in parts if not part.endswith("=-")]
    return f"{index}. {code} {name}（{industry}） | " + " | ".join(compact_parts)


@tool
@register_tool(
    tool_id="screen_stocks_by_criteria",
    name="全市场股票批量筛选",
    description=build_screening_tool_description(),
    category="screening",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["screening", "fundamentals", "technical"],
    tool_role_hint="specialized",
    when_to_use="Use it when you need to batch screen A-share stocks based on multiple combinations of financial, trading and technical indicators. support 50+ fields and > < >= <= == != between in not_in contains etc. operators. Suitable for complex custom filter conditions.",
    when_not_to_use="Not suitable for in-depth analysis of a single stock; not suitable for simple single-condition screening (special screening tools such as get_graham_screen and other preset strategies can be considered).",
    related_tools=["get_multi_factor_screening", "get_graham_screen", "get_growth_stock_screen", "get_dividend_stock_screen", "get_turnaround_screen"],
)
async def screen_stocks_by_criteria(
    conditions_json: Annotated[
        str,
        (
            'Filter criteria JSON array, format: [{"field": "pe", "operator": "<", "value": 15}, '
            '{"field": "total_mv", "operator": ">", "value": 50}]。'
            "field is the field name, operator is the operator, and value is the comparison value."
            "between The value format of the operator is [minimum value, maximum value], in/not_in for a list."
        )
    ],
    limit: Annotated[int, "Return quantity, default 20, maximum 100"] = 20,
    order_by_field: Annotated[str, "Sorting fields, such as pe/pb/roe/total_mv, default to descending order by total market value"] = "total_mv",
    order_direction: Annotated[str, "Sorting direction: asc (ascending) or desc (descending), default desc"] = "desc",
) -> str:
    """Market-wide A-share batch screening tool.

    {supported_fields_doc}
    """
    try:
        # parsing conditions
        try:
            raw_conditions = json.loads(conditions_json)
        except json.JSONDecodeError as e:
            return f"Error: conditions_json format is incorrect, please pass in a legal JSON array. Details:{e}"

        if not isinstance(raw_conditions, list) or len(raw_conditions) == 0:
            return "Error: conditions_json must be a non-empty JSON array."

        limit = max(1, min(limit, 100))

        return await _run_screening(raw_conditions, limit, order_by_field, order_direction)

    except Exception as e:
        logger.error(f"screen_stocks_by_criteria Execution failed: {e}", exc_info=True)
        return f"Filter execution failed:{e}"


async def _execute_screening_query(
    raw_conditions: list,
    limit: int,
    order_by_field: str,
    order_direction: str,
) -> tuple[list, int]:
    """Call DatabaseScreeningService asynchronously to perform filtering and return structured results."""
    from app.core.database import init_database
    from app.services.database_screening_service import get_database_screening_service

    # Make sure the database is initialized
    try:
        await init_database()
    except Exception:
        pass  # may have been initialized

    service = get_database_screening_service()

    order_by = [{"field": order_by_field, "direction": order_direction}]

    items, total = await service.screen_stocks(
        conditions=raw_conditions,
        limit=limit,
        offset=0,
        order_by=order_by,
    )

    return items, total


def _format_screening_output(
    raw_conditions: list,
    items: list,
    total: int,
    order_by_field: str,
) -> str:
    """Format structured filter results into tool text output."""

    if total == 0 or not items:
        return "No matching stocks found. There is currently no target that meets the screening requirements. Do not recommend other stocks that do not meet the conditions."

    display_count = min(len(items), MAX_DETAILED_RESULTS)
    pe_display_field, pe_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pe")
    pb_display_field, pb_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pb")
    lines = [
        f"共找到 {total} 只符合条件的股票，以下展示前 {display_count} 只核心候选：",
        "The results have been compressed into a summary to avoid occupying too much context; if you need to continue verification, please first use the code list below to call subsequent tools.\n",
    ]

    for i, item in enumerate(items[:display_count], 1):
        lines.append(
            _build_compact_candidate_line(
                i,
                item,
                pe_display_field,
                pe_display_label,
                pb_display_field,
                pb_display_label,
            )
        )

    all_codes = [
        str(item.get("code") or item.get("symbol", "")).strip()
        for item in items
        if str(item.get("code") or item.get("symbol", "")).strip()
    ]
    if all_codes:
        lines.append("")
        lines.append(f"候选代码列表（按当前排序，共 {len(all_codes)} 只）: {', '.join(all_codes)}")

    if len(items) > display_count:
        lines.append(f"其余 {len(items) - display_count} 只候选已省略详细展开。")

    return "\n".join(lines)


async def _run_screening(
    raw_conditions: list,
    limit: int,
    order_by_field: str,
    order_direction: str,
) -> str:
    items, total = await _execute_screening_query(raw_conditions, limit, order_by_field, order_direction)
    return _format_screening_output(raw_conditions, items, total, order_by_field)


# === technical_factor_bundle_tool ===
"""Standardized technology factor package tool."""

import json
import logging
from typing import Annotated, Any, Dict

from langchain_core.tools import tool

try:
    from app.core.database import get_mongo_db_sync
except ImportError:
    get_mongo_db = get_mongo_db_sync = None
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

TECHNICAL_FIELDS = [
    "ma20",
    "rsi14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "dif",
    "dea",
    "macd_hist",
]


def _normalize_symbol(symbol: str) -> str:
    digits = "".join(ch for ch in str(symbol or "") if ch.isdigit())
    return digits.zfill(6)


def _pick_numeric(doc: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = doc.get(key)
        if value is not None:
            return value
    return None


@tool
@register_tool(
    tool_id="get_technical_factor_bundle_tool",
    name="技术因子包",
    description=(
        "Returns the stock s technical_core package of standardized technical factors."
        "Suitable for obtaining MA20, RSI14,KDJ(K/D/J), MACD(DIF/DEA/HIST) This batch of technical indicators that the current warehouse has materialized and stably supports."
        "The output is structured JSON, which is suitable for direct binding to Agent for timing, trend judgment and technical screening."
        "Here s factor/signal It is a technical price indicator, not a fundamental factor, financial risk signal, sentiment signal or Agent capability gap."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["technical_indicators", "factor_bundle", "structured_data", "ma", "rsi", "kdj", "macd"],
    tool_role_hint="supporting",
    preferred_for=["技术指标批量获取", "结构化技术因子", "Agent 技术面输入"],
    data_source="stock_technical_indicators/market_quotes",
    when_to_use=(
        "It is used when the Agent needs technical indicators such as trend, momentum, overbought and oversold, and MACD/KDJ signals."
        "If you need a collection of technical indicator fields rather than a long technical analysis report, bind this tool first."
    ),
    when_not_to_use=(
        "Not suitable for obtaining fundamental indicators such as PE/PB/ROE/cash flow;"
        "Not suitable for financial risk, cash flow deterioration, announcement events, emotional aspects or Agent workshop capability gap analysis;"
        "It is also not suitable for scenarios that require complete historical sequence backtesting. If you only need readable text for technical analysis, consider get_technical_indicators."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, current_price, trade_date, data_source,bundle=technical_core, "
        "factors、missing_factors、calculation_notes。"
        "factors Fixed to include ma20, rsi14, kdj_k, kdj_d, kdj_j, dif, dea, macd_hist."
    ),
    example="get_technical_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_technical_indicators",
        "get_stock_market_data_unified",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_technical_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Obtain the standardized technical factor package and read core technical indicators such as MA20, RSI14, KDJ, and MACD from MongoDB materialized snapshots.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON String, returns field description normally——
            symbol: Standardized 6-digit stock code
            name: Stock name
            current_price: latest price
            trade_date: Data transaction day
            data_source: Data source
            bundle: Factor package identifier, fixed to "technical_core"
            factors: Technical factors dictionary, subfield —
                ma20: 20 daily moving average
                rsi14: 14 day RSI
                kdj_k: KDJ The K value of
                kdj_d: KDJ The D value of
                kdj_j: KDJ The J value of
                dif: MACD of DIF
                dea: MACD of DEA
                macd_hist: MACD bar chart
            missing_factors: List of missing factor field names (fields with value None)
            calculation_notes: Calculation description text list
        Field returned on exception —
            status: "error"
            message: error message
            symbol: Standardized stock code
    """
    normalized_symbol = _normalize_symbol(symbol)

    try:
        db = get_mongo_db_sync()
        technical_doc = db["stock_technical_indicators"].find_one(
            {"code": normalized_symbol},
            sort=[("trade_date", -1), ("updated_at", -1)],
        ) or {}
        quote_doc = db["market_quotes"].find_one(
            {"code": normalized_symbol},
            sort=[("trade_date", -1), ("updated_at", -1)],
        ) or {}
        basic_doc = db["stock_basic_info"].find_one({"code": normalized_symbol}) or {}

        factors = {field: technical_doc.get(field) for field in TECHNICAL_FIELDS}
        missing_factors = [field for field, value in factors.items() if value is None]

        payload = {
            "symbol": normalized_symbol,
            "name": basic_doc.get("name") or quote_doc.get("name"),
            "current_price": _pick_numeric(quote_doc, "close", "price", "last_price"),
            "trade_date": technical_doc.get("trade_date") or quote_doc.get("trade_date"),
            "data_source": technical_doc.get("source") or quote_doc.get("source"),
            "bundle": "technical_core",
            "factors": factors,
            "missing_factors": missing_factors,
            "calculation_notes": [
                "Technical indicators give priority to reading the latest materialized snapshot in stock_technical_indicators.",
                "The current standard technical factor package includes MA20, RSI14,KDJ(K/D/J), MACD(DIF/DEA/HIST). ",
                "If missing_factors is non-empty, it means that the corresponding indicator is temporarily unavailable in the latest technology snapshot.",
            ],
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.error("Failed to obtain technical factor package: %s", exc, exc_info=True)
        return json.dumps(
            {"status": "error", "message": f"获取技术因子包失败: {exc}", "symbol": normalized_symbol},
            ensure_ascii=False,
            indent=2,
            default=str,
        )


__all__ = ["get_technical_factor_bundle_tool"]

# === technical_indicators ===
"""
Unified Technical Indicators Tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources to obtain data.
Then use stockstats to calculate technical indicators.
"""

import logging
import re
import pandas as pd
from typing import Annotated, List, Union
from langchain_core.tools import tool
from datetime import datetime, timedelta

from core.tools.base import register_tool
from tradingagents.utils.stock_utils import StockUtils

logger = logging.getLogger(__name__)

@tool
@register_tool(
    tool_id="get_technical_indicators",
    name="统一技术指标分析",
    description="Get various technical indicators of stocks (MACD, RSI, KDJ, BOLL etc.), supports A shares/Hong Kong stocks/US stocks",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["technical_indicators", "technical_analysis", "macd", "rsi", "kdj", "boll", "momentum"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["technical_indicator_analysis", "trend_analysis", "momentum_analysis", "overbought_oversold_detection"],
    related_tools=["get_stock_market_data_unified", "get_stock_fundamentals_unified", "get_technical_factor_bundle_tool", "get_crossover_signals", "get_candlestick_patterns"],
)
def get_technical_indicators(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    indicators: Annotated[str, "List of technical indicators, separated by commas, such as 'macd,rsi_14,boll,kdj'"],
    start_date: Annotated[str, "Start date, format: YYYY-MM-DD. Usually the year before the analysis date to ensure there is enough data to calculate the indicator"] = None,
    end_date: Annotated[str, "End date, format: YYYY-MM-DD. Usually the date of analysis"] = None
) -> str:
    """
    Get a unified technical indicator analysis report
    
    Args:
        ticker: Stock code
        indicators: Indicator list string, such as "macd,rsi,kdj"
        start_date: start date (By default, it will be automatically calculated as 365 days before end_date)
        end_date: end date (Default is today)
        
    Returns:
        str: Formatted technical indicator reports
    """
    # 1. initialization date
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if not start_date:
        # The default lookback is 365 days to ensure that long-term indicators such as MA250 are available
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365)
        start_date = start_dt.strftime("%Y-%m-%d")

    # 2. Standardized stock code
    original_ticker = ticker
    ticker = re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', ticker.strip())
    
    logger.info(f"📈 [Technical indicators] Analyze stocks: {ticker} ({start_date} -> {end_date})")
    
    try:
        # 3. Identify the market
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']
        
        df = None
        
        # 4. Get raw data (DataFrame)
        if is_china:
            from tradingagents.dataflows.providers.china.tushare import TushareProvider
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider
            import asyncio
            
            # Helper to run async code in sync tool
            def run_async(coro):
                try:
                    return asyncio.run(coro)
                except RuntimeError:
                    # Loop already running, try to use it
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import nest_asyncio
                        nest_asyncio.apply()
                        return asyncio.run(coro)
                    return loop.run_until_complete(coro)

            # Try first Tushare
            try:
                provider = TushareProvider()
                # TushareProvider needs async call
                df = run_async(provider.get_historical_data(ticker, start_date, end_date))
                
                if df is not None and not df.empty:
                    # Rename columns for stockstats
                    # Tushare: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
                    df = df.rename(columns={
                        'trade_date': 'date',
                        'vol': 'volume'
                    })
            except Exception as e:
                logger.warning(f"Tushare Failed to get data: {e}")
            
            # downgrade to AKShare
            if df is None or df.empty:
                try:
                    provider = AKShareProvider()
                    # AKShareProvider needs async call
                    df = run_async(provider.get_historical_data(ticker, start_date, end_date))
                    # AKShareProvider.get_historical_data already standardizes columns
                except Exception as e:
                    logger.warning(f"AKShare Failed to get data: {e}")

        elif is_hk:
            from tradingagents.dataflows.providers.hk.improved_hk import ImprovedHKStockProvider
            try:
                provider = ImprovedHKStockProvider()
                df = provider.get_daily_data(ticker, start_date, end_date)
            except Exception as e:
                logger.warning(f"港股数据获取失败: {e}")
                
        elif is_us:
            from tradingagents.dataflows.providers.us.optimized import OptimizedUSProvider
            try:
                provider = OptimizedUSProvider()
                df = provider.get_daily_data(ticker, start_date, end_date)
            except Exception as e:
                logger.warning(f"美股数据获取失败: {e}")

        # 5. Validate data
        if df is None or df.empty:
            return f"❌ 无法获取股票 {ticker} 的历史数据，无法计算技术指标。"
            
        # 6. Calculate indicators (Use stockstats)
        from stockstats import wrap
        
        # Make sure column names comply with stockstats requirements (open, high, low, close, volume)
        # Our get_daily_data should already have normalized column names, but double check just to be safe
        df.columns = [c.lower() for c in df.columns]
        
        # stockstats Requires Date column as index or column? 
        # wrap() usually accepted DataFrame
        stock = wrap(df)
        
        indicator_list = [i.strip() for i in indicators.split(',')]
        
        # Extended abbreviation indicator
        expanded_list = []
        for ind in indicator_list:
            if ind.lower() == 'kdj':
                expanded_list.extend(['kdjk', 'kdjd', 'kdjj'])
            else:
                expanded_list.append(ind)
        indicator_list = expanded_list
        
        report_lines = [f"## {original_ticker} 技术指标分析", f"日期范围: {start_date} 至 {end_date}", ""]
        
        # Get the most recent data (last row)
        latest_date = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else df['date'].iloc[-1]
        report_lines.append(f"### 最新数据 ({latest_date})")
        report_lines.append(f"收盘价: {stock['close'].iloc[-1]:.2f}")
        
        for ind in indicator_list:
            try:
                # Calculate indicators
                series = stock[ind]
                val = series.iloc[-1]
                
                # Formatted output
                val_str = f"{val:.4f}" if isinstance(val, (int, float)) else str(val)
                
                # Add simple trend judgment (Based on changes in the last two days)
                trend = ""
                if len(series) >= 2:
                    prev_val = series.iloc[-2]
                    if isinstance(val, (int, float)) and isinstance(prev_val, (int, float)):
                        if val > prev_val: trend = "↑"
                        elif val < prev_val: trend = "↓"
                        else: trend = "-"
                
                report_lines.append(f"- **{ind}**: {val_str} {trend}")
                
                # For some indicators, additional information is provided
                if 'rsi' in ind:
                    status = "中性"
                    if val > 70: status = "超买 ⚠️"
                    elif val < 30: status = "超卖 💎"
                    report_lines.append(f"  - 状态: {status}")
                elif 'macd' in ind and ind == 'macd':
                    # MACD contains macd, macds (signal), macdh (hist)
                    macds = stock['macds'].iloc[-1]
                    macdh = stock['macdh'].iloc[-1]
                    report_lines.append(f"  - Signal: {macds:.4f}")
                    report_lines.append(f"  - Hist: {macdh:.4f}")
                    if macdh > 0 and stock['macdh'].iloc[-2] <= 0:
                        report_lines.append("  - signal: Golden Cross (positive kinetic energy signal)📈")
                    elif macdh < 0 and stock['macdh'].iloc[-2] >= 0:
                        report_lines.append("  - signal: Death Cross (negative kinetic energy signal)📉")

            except Exception as e:
                report_lines.append(f"- {ind}: 计算失败 ({e})")
        
        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"技术指标计算失败: {e}", exc_info=True)
        return f"❌ Technical indicator calculation error occurred: {str(e)}"

