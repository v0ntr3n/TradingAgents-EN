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