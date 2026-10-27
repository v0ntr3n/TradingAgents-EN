"""
Unified Stock News Tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call corresponding news data sources

Data source priority:
1. MongoDB Database (including local, akshare, tushare and other data sources)
2. External APIs (AKShare, Google News, Finnhub)
"""

import concurrent.futures
import hashlib
import logging
import unicodedata
from datetime import datetime, time, timedelta
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


A_SHARE_NEWS_LOOKBACK_DAYS = 7
TUSHARE_LIVE_SOURCES = [
    "sina",
    "eastmoney",
    "10jqka",
    "cls",
    "wallstreetcn",
]

SOURCE_DISPLAY_NAMES = {
    "local": "本地数据",
    "tushare": "Tushare",
    "akshare": "AKShare",
    "baostock": "Baostock",
    "google": "Google新闻",
    "finnhub": "Finnhub",
}

LIVE_SOURCE_DISPLAY_NAMES = {
    "tushare": "Tushare Multi-source news (paid enhancement)",
    "akshare": "AKShare Oriental Fortune (free fallback)",
}

CATEGORY_DISPLAY_NAMES = {
    "company_announcement": "公司公告",
    "policy_news": "政策监管",
    "industry_news": "行业新闻",
    "market_news": "市场动态",
    "other": "其他",
}

SENTIMENT_DISPLAY_NAMES = {
    "positive": "偏积极",
    "negative": "偏审慎",
    "neutral": "中性",
}

IMPORTANCE_DISPLAY_NAMES = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

A_SHARE_DIRECT_EVENT_KEYWORDS = [
    "业绩",
    "财报",
    "公告",
    "年报",
    "季报",
    "半年报",
    "业绩预告",
    "业绩快报",
    "回购",
    "分红",
    "派息",
    "增持",
    "减持",
    "合作",
    "协议",
    "中标",
    "签约",
    "发布",
    "发货",
    "落地",
    "停牌",
    "复牌",
    "重组",
    "并购",
    "回应",
    "传闻",
    "辟谣",
    "澄清",
]

A_SHARE_BROAD_CONTEXT_KEYWORDS = [
    "资本市场",
    "市场大事提醒",
    "大事提醒",
    "国家统计局",
    "重磅数据",
    "板块",
    "指数",
    "etf",
    "基金",
    "资金流入",
    "资金流出",
    "市场",
    "a股",
    "沪深",
    "早报",
    "午报",
    "晚报",
    "策略",
    "一周",
    "下周",
]

A_SHARE_ENUMERATION_MARKERS = [
    "等",
    "多家",
    "多只",
    "多股",
    "名单",
    "提醒",
]

A_SHARE_GENERIC_ALIAS_TERMS = {
    "银行",
    "证券",
    "保险",
    "科技",
    "医药",
    "药业",
    "电子",
    "集团",
    "股份",
    "控股",
    "发展",
    "实业",
    "能源",
    "电力",
    "信息",
    "投资",
    "材料",
    "航空",
    "汽车",
    "家居",
    "制造",
    "通信",
    "地产",
}

HIGH_CONFIDENCE_A_SHARE_RELEVANCE_SCORE = 85

HIGH_SIGNAL_NEWS_SOURCE_KEYWORDS = [
    "公告",
    "交易所",
    "证监会",
    "财联社",
    "证券时报",
    "新浪财经",
    "华尔街见闻",
    "同花顺",
    "东方财富",
    "红星资本局",
    "路透",
    "彭博",
]

LOW_SIGNAL_NEWS_SOURCE_KEYWORDS = [
    "股吧",
    "论坛",
    "微博",
    "自媒体",
    "社区",
]


def _normalize_analysis_date(curr_date: str) -> str:
    """Normalize parsing date strings."""
    return curr_date.split()[0] if " " in curr_date else curr_date


def _build_a_share_news_window(curr_date: str) -> Tuple[datetime, datetime, str, str]:
    """Construct A-share news query time window, covering 7 natural days before the analysis date by default."""
    analysis_date_str = _normalize_analysis_date(curr_date)
    analysis_date = datetime.strptime(analysis_date_str, "%Y-%m-%d")
    start_date = datetime.combine(
        (analysis_date - timedelta(days=A_SHARE_NEWS_LOOKBACK_DAYS - 1)).date(),
        time.min,
    )
    end_date = datetime.combine(analysis_date.date(), time.max)
    return start_date, end_date, start_date.strftime("%Y-%m-%d"), analysis_date_str


def _normalize_a_share_symbol(ticker: str) -> str:
    """Standardized A-share ticker."""
    return (
        ticker.upper()
        .replace(".SH", "")
        .replace(".SZ", "")
        .replace(".SS", "")
        .replace(".XSHE", "")
        .replace(".XSHG", "")
    )


def _collapse_whitespace(value: Any) -> str:
    """Fold excess whitespace to facilitate Markdown output."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _parse_publish_time(value: Any) -> Optional[datetime]:
    """Parse news release time."""
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None

    text = _collapse_whitespace(value)
    if not text:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%m-%d %H:%M",
        "%m/%d %H:%M",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in {"%m-%d %H:%M", "%m/%d %H:%M"}:
                parsed = parsed.replace(year=datetime.now().year)
            return parsed
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        logger.debug(f"⚠️ [unified news tool] Unable to parse news time: {text}")
        return None


def _format_publish_time(value: Any) -> str:
    """Format news release time."""
    parsed = _parse_publish_time(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return _collapse_whitespace(value) or "未知时间"


def _coerce_keywords(value: Any) -> List[str]:
    """The unified keyword is a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in (_collapse_whitespace(keyword) for keyword in value) if item]
    if isinstance(value, str):
        text = _collapse_whitespace(value)
        if not text:
            return []
        separators = [",", "，", ";", "；", "|"]
        tokens = [text]
        for separator in separators:
            if separator in text:
                tokens = text.split(separator)
                break
        return [item for item in (_collapse_whitespace(token) for token in tokens) if item]
    return []


def _get_source_display_name(source: str) -> str:
    """Get the data source display name."""
    return SOURCE_DISPLAY_NAMES.get(source, source or "未知来源")


def _get_live_source_display_name(source: str) -> str:
    """Get the display name of A-share real-time data source."""
    return LIVE_SOURCE_DISPLAY_NAMES.get(source, _get_source_display_name(source))


def _get_a_share_enabled_sources() -> List[str]:
    """Get the priority of the data source enabled for A shares."""
    try:
        from app.core.data_source_priority import get_enabled_data_sources_sync

        return get_enabled_data_sources_sync(market_category="a_shares")
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Failed to obtain A-share data source priority, use default order: {exc}")
        return ["local", "tushare", "akshare", "baostock"]


def _build_a_share_live_source_plan(enabled_sources: List[str]) -> List[str]:
    """Generate A-share real-time news analysis links, only using AKShare."""
    return ["akshare"] if "akshare" in enabled_sources else ["akshare"]


def _build_a_share_analysis_priority(enabled_sources: List[str]) -> List[str]:
    """Generate A-share news analysis link priority description."""
    priority = ["local"] if "local" in enabled_sources else []
    for source in _build_a_share_live_source_plan(enabled_sources):
        if source not in priority:
            priority.append(source)

    return priority or ["local", "akshare"]


def _is_placeholder_company_name(company_name: str, symbol: str) -> bool:
    """Determines whether the company name is just a placeholder."""
    cleaned_name = _collapse_whitespace(company_name)
    return not cleaned_name or cleaned_name in {symbol, f"股票{symbol}"}


def _get_company_name(symbol: str) -> Optional[str]:
    """Get the company name corresponding to the stock code."""
    try:
        from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified

        stock_info = get_china_stock_info_unified(symbol)
        company_name = _collapse_whitespace(stock_info.get("name")) if isinstance(stock_info, dict) else ""
        if company_name and not _is_placeholder_company_name(company_name, symbol):
            return company_name
    except Exception as exc:
        logger.debug(f"⚠️ [unified news tool] Failed to obtain company name through data_source_manager: {exc}")

    try:
        from tradingagents.utils.news_filter import get_company_name

        company_name = _collapse_whitespace(get_company_name(symbol))
        if company_name and not _is_placeholder_company_name(company_name, symbol):
            return company_name
    except Exception as exc:
        logger.debug(f"⚠️ [unified news tool] Failed to get company name through news filter: {exc}")

    return None


def _get_company_aliases(company_name: Optional[str]) -> List[str]:
    """Generate company name aliases for use in Tushare news relevance filtering."""
    if not company_name:
        return []

    normalized_name = _collapse_whitespace(company_name)
    aliases = set()
    suffixes = [
        "股份有限公司",
        "集团股份有限公司",
        "集团有限公司",
        "有限公司",
        "股份",
        "集团",
    ]

    def _add_alias(alias_value: Optional[str]) -> None:
        alias_text = _collapse_whitespace(alias_value)
        if not alias_text or len(alias_text) < 2:
            return

        aliases.add(alias_text)

        alias_nfkc = _normalize_nfkc_text(alias_text)
        if alias_nfkc and alias_nfkc != alias_text and len(alias_nfkc) >= 2:
            aliases.add(alias_nfkc)

    _add_alias(normalized_name)

    for suffix in suffixes:
        if normalized_name.endswith(suffix):
            alias = normalized_name[: -len(suffix)]
            _add_alias(alias)

    if len(normalized_name) >= 4:
        shortened_alias = normalized_name[2:]
        if shortened_alias and shortened_alias not in A_SHARE_GENERIC_ALIAS_TERMS:
            _add_alias(shortened_alias)

    for alias in list(aliases):
        alias_nfkc = _normalize_nfkc_text(alias)
        if len(alias_nfkc) >= 3 and alias_nfkc[-1].upper() in {"A", "B", "H"}:
            stripped_alias = alias_nfkc[:-1].strip()
            if stripped_alias and stripped_alias not in A_SHARE_GENERIC_ALIAS_TERMS:
                _add_alias(stripped_alias)

    return [alias for alias in sorted(aliases, key=len, reverse=True) if len(alias) >= 2]


def _normalize_nfkc_text(value: Any) -> str:
    """Whitespace folding and NFKC normalization of text, compatible with full-width/half-width stock abbreviations."""
    text = _collapse_whitespace(value)
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def _text_contains_company_name(text: Optional[str], company_name: Optional[str]) -> bool:
    """Determine whether the text contains the company name, compatible with full-width/half-width differences."""
    normalized_text = _collapse_whitespace(text)
    normalized_company_name = _collapse_whitespace(company_name)
    if not normalized_text or not normalized_company_name:
        return False

    if normalized_company_name in normalized_text:
        return True

    text_nfkc = _normalize_nfkc_text(normalized_text)
    company_name_nfkc = _normalize_nfkc_text(normalized_company_name)
    return bool(company_name_nfkc and company_name_nfkc in text_nfkc)


def _find_matching_aliases(text: Optional[str], aliases: List[str]) -> List[str]:
    """Returns the company alias hit in the text, compatible with full-width/half-width differences."""
    normalized_text = _collapse_whitespace(text)
    if not normalized_text or not aliases:
        return []

    text_nfkc = _normalize_nfkc_text(normalized_text)
    matches = []
    for alias in aliases:
        normalized_alias = _collapse_whitespace(alias)
        if not normalized_alias:
            continue

        alias_nfkc = _normalize_nfkc_text(normalized_alias)
        if normalized_alias in normalized_text or (alias_nfkc and alias_nfkc in text_nfkc):
            matches.append(normalized_alias)

    return matches


def _text_starts_with_any_alias(text: Optional[str], aliases: List[str]) -> bool:
    """Determine whether the title starts with any company alias, compatible with full-width/half-width differences."""
    normalized_text = _collapse_whitespace(text)
    if not normalized_text or not aliases:
        return False

    text_nfkc = _normalize_nfkc_text(normalized_text)
    for alias in aliases:
        normalized_alias = _collapse_whitespace(alias)
        if not normalized_alias:
            continue

        alias_nfkc = _normalize_nfkc_text(normalized_alias)
        if normalized_text.startswith(normalized_alias) or (
            alias_nfkc and text_nfkc.startswith(alias_nfkc)
        ):
            return True

    return False


def _is_relevant_a_share_news(news_item: Dict[str, Any], symbol: str, company_name: Optional[str]) -> bool:
    """Determine whether the news is relevant to the target A-share company."""
    symbol_clean = symbol.zfill(6)
    text_parts = [
        _collapse_whitespace(news_item.get("title")),
        _collapse_whitespace(news_item.get("content")),
        _collapse_whitespace(news_item.get("summary")),
        " ".join(_coerce_keywords(news_item.get("keywords"))),
    ]
    text_blob = " ".join(part for part in text_parts if part)

    if not text_blob:
        return False

    if symbol_clean in text_blob or symbol in text_blob:
        return True

    return bool(_find_matching_aliases(text_blob, _get_company_aliases(company_name)))


def _filter_news_by_date_range(
    news_list: List[Dict[str, Any]],
    start_date: datetime,
    end_date: datetime,
) -> List[Dict[str, Any]]:
    """Filter news strictly by analysis date window."""
    filtered_news = []

    for news in news_list:
        publish_time = _parse_publish_time(news.get("publish_time"))
        if publish_time is None:
            continue
        if start_date <= publish_time <= end_date:
            filtered_news.append(news)

    return filtered_news


def _contains_any_keyword(text: str, keywords: List[str]) -> bool:
    """Determine whether the text contains any keyword."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def _strip_redundant_title_from_body_text(title: str, body_text: str) -> str:
    """Remove repetitively spliced titles from the abstract/text to avoid repeated scoring."""
    normalized_title = _collapse_whitespace(title)
    normalized_body = _collapse_whitespace(body_text)
    if not normalized_title or not normalized_body:
        return normalized_body

    body_without_title = normalized_body.replace(normalized_title, "", 1)
    return body_without_title.strip("【】[]():：- \n\t")


def _calculate_a_share_news_relevance(
    news_item: Dict[str, Any],
    symbol: str,
    company_name: Optional[str],
) -> int:
    """Calculate the company directness and event relevance scores of A-share news."""
    title = _collapse_whitespace(news_item.get("title"))
    summary = _collapse_whitespace(news_item.get("summary"))
    content = _collapse_whitespace(news_item.get("content"))
    body_text = " ".join(part for part in [summary, content] if part)
    body_text_for_scoring = _strip_redundant_title_from_body_text(title, body_text)
    aliases = _get_company_aliases(company_name)
    symbol_clean = symbol.zfill(6)

    title_alias_matches = _find_matching_aliases(title, aliases)
    body_alias_matches = _find_matching_aliases(body_text_for_scoring, aliases)
    title_has_symbol = symbol_clean in title or symbol in title
    body_has_symbol = symbol_clean in body_text_for_scoring or symbol in body_text_for_scoring
    title_has_company_name = _text_contains_company_name(title, company_name)
    body_has_company_name = _text_contains_company_name(body_text_for_scoring, company_name)

    score = 0

    if title_has_symbol:
        score += 90
    elif body_has_symbol:
        score += 35

    if title_has_company_name:
        score += 70
    elif title_alias_matches:
        score += 55

    if title_alias_matches and _text_starts_with_any_alias(title, title_alias_matches):
        score += 15

    if body_has_company_name:
        score += 30
    elif body_alias_matches:
        score += 20

    if _contains_any_keyword(title, A_SHARE_DIRECT_EVENT_KEYWORDS):
        score += 18
    elif _contains_any_keyword(body_text_for_scoring, A_SHARE_DIRECT_EVENT_KEYWORDS):
        score += 8

    category = _collapse_whitespace(news_item.get("category"))
    importance = _collapse_whitespace(news_item.get("importance"))
    if category == "company_announcement":
        score += 15
    if importance == "high":
        score += 12
    elif importance == "medium":
        score += 6

    if _contains_any_keyword(title, A_SHARE_BROAD_CONTEXT_KEYWORDS):
        score -= 35

    if title_alias_matches and _contains_any_keyword(title, A_SHARE_ENUMERATION_MARKERS):
        score -= 20

    if (
        not title_alias_matches
        and not title_has_symbol
        and not title_has_company_name
        and (body_alias_matches or body_has_symbol or body_has_company_name)
    ):
        score -= 25

    if not title_alias_matches and not body_alias_matches and not title_has_symbol and not body_has_symbol:
        score -= 25

    return max(0, min(100, score))


def _is_high_confidence_a_share_news_item(
    news_item: Dict[str, Any],
    symbol: str,
    company_name: Optional[str],
) -> bool:
    """Determine whether it is a high-confidence company that can stop the rollback early and point directly to the news."""
    relevance_score = int(
        news_item.get("relevance_score", 0)
        or _calculate_a_share_news_relevance(news_item, symbol, company_name)
    )
    if relevance_score < HIGH_CONFIDENCE_A_SHARE_RELEVANCE_SCORE:
        return False

    title = _collapse_whitespace(news_item.get("title"))
    if not title:
        return False

    aliases = _get_company_aliases(company_name)
    symbol_clean = symbol.zfill(6)
    title_alias_matches = _find_matching_aliases(title, aliases)
    title_has_company_name = _text_contains_company_name(title, company_name)
    title_has_symbol = symbol_clean in title or symbol in title
    title_starts_with_alias = bool(title_alias_matches and _text_starts_with_any_alias(title, title_alias_matches))
    title_has_direct_event = _contains_any_keyword(title, A_SHARE_DIRECT_EVENT_KEYWORDS)
    title_has_broad_context = _contains_any_keyword(title, A_SHARE_BROAD_CONTEXT_KEYWORDS)
    title_has_enumeration = _contains_any_keyword(title, A_SHARE_ENUMERATION_MARKERS)
    category = _collapse_whitespace(news_item.get("category"))

    if title_has_broad_context or title_has_enumeration:
        return False

    if not (title_has_symbol or title_has_company_name or title_starts_with_alias):
        return False

    return title_has_direct_event or category == "company_announcement"


def _rank_a_share_news_items(
    news_list: List[Dict[str, Any]],
    symbol: str,
    company_name: Optional[str],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """A-share news is sorted by company directness and event relevance."""
    ranked_news = []

    for news in news_list:
        relevance_score = _calculate_a_share_news_relevance(news, symbol, company_name)
        if relevance_score <= 0:
            continue

        ranked_item = dict(news)
        ranked_item["relevance_score"] = relevance_score
        ranked_news.append(ranked_item)

    ranked_news.sort(
        key=lambda item: (
            item.get("relevance_score", 0),
            _parse_publish_time(item.get("publish_time")) or datetime(1970, 1, 1),
        ),
        reverse=True,
    )
    return ranked_news[:limit]


def _get_top_relevance_score(news_list: List[Dict[str, Any]]) -> int:
    """Get the highest relevance score for your news listing."""
    if not news_list:
        return 0
    return int(news_list[0].get("relevance_score", 0) or 0)


def _select_best_live_news_source(
    source_news_map: Dict[str, List[Dict[str, Any]]],
    live_source_plan: List[str],
) -> Optional[str]:
    """Choose the best results among real-time news candidate sources."""
    best_source = None
    best_key = None

    for source in live_source_plan:
        ranked_news = source_news_map.get(source) or []
        if not ranked_news:
            continue

        source_key = (
            _get_top_relevance_score(ranked_news),
            len(ranked_news),
            -live_source_plan.index(source),
        )

        if best_key is None or source_key > best_key:
            best_source = source
            best_key = source_key

    return best_source


def _deduplicate_news_items(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate news list by title."""
    seen_titles = set()
    deduplicated_news = []

    for news in news_list:
        title = _collapse_whitespace(news.get("title"))
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        deduplicated_news.append(news)

    return deduplicated_news


def _sort_news_by_time(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort news in descending order of release date."""
    return sorted(
        news_list,
        key=lambda item: _parse_publish_time(item.get("publish_time")) or datetime.min,
        reverse=True,
    )


def _summarize_news_item(news_item: Dict[str, Any]) -> str:
    """To obtain news summaries, use structured summaries first, then fall back to text truncation."""
    summary = _collapse_whitespace(news_item.get("summary"))
    if summary:
        return summary

    content = _collapse_whitespace(news_item.get("content"))
    if not content:
        return ""

    if len(content) <= 160:
        return content
    return content[:160] + "..."


def _format_news_item(news_item: Dict[str, Any]) -> str:
    """Format a single news item into structured Markdown."""
    title = _collapse_whitespace(news_item.get("title")) or "无标题"
    url = _collapse_whitespace(news_item.get("url"))
    source = _collapse_whitespace(news_item.get("source")) or _get_source_display_name(
        _collapse_whitespace(news_item.get("data_source"))
    )
    summary = _summarize_news_item(news_item)
    category = CATEGORY_DISPLAY_NAMES.get(_collapse_whitespace(news_item.get("category")), "其他")
    sentiment = SENTIMENT_DISPLAY_NAMES.get(_collapse_whitespace(news_item.get("sentiment")), "中性")
    importance = IMPORTANCE_DISPLAY_NAMES.get(_collapse_whitespace(news_item.get("importance")), "中")
    keywords = _coerce_keywords(news_item.get("keywords"))

    if url:
        lines = [f"- [**{title}**]({url})"]
    else:
        lines = [f"- **{title}**"]

    lines.append(f"  - 时间: {_format_publish_time(news_item.get('publish_time'))} | 来源: {source}")

    if summary:
        lines.append(f"  - 摘要: {summary}")

    lines.append(f"  - 类别: {category} | 情绪: {sentiment} | 重要性: {importance}")

    if keywords:
        lines.append(f"  - 关键词: {', '.join(keywords[:8])}")

    return "\n".join(lines)


def _format_news_section(news_list: List[Dict[str, Any]], section_title: str, source_note: str = "") -> str:
    """Format news list into Markdown chapters."""
    if not news_list:
        return ""

    header = f"## {section_title}"
    if source_note:
        header += f"\n**说明**: {source_note}"

    news_items = "\n".join(_format_news_item(news) for news in news_list)
    return f"{header}\n{news_items}"


def _query_news_from_database(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Query news from a MongoDB database and aggregate results by enabled data sources.

    Args:
        symbol: Stock code (6-digit code, such as 000001)
        start_date: start date
        end_date: end date
        limit: Return quantity limit

    Returns:
        A dictionary containing news lists, enabled data sources, and hit data sources
    """
    enabled_sources = _get_a_share_enabled_sources()

    try:
        from app.core.database import get_mongo_db_sync

        db = get_mongo_db_sync()
        collection = db.stock_news

        logger.info(f"📊 [News database query] Data source priority: {enabled_sources}")

        query = {
            "symbol": symbol,
            "data_source": {"$in": enabled_sources},
            "publish_time": {
                "$gte": start_date,
                "$lte": end_date,
            },
        }

        raw_news = list(
            collection.find(query).sort("publish_time", -1).limit(max(limit * max(len(enabled_sources), 1), limit))
        )

        if not raw_news:
            logger.info(f"⚠️ [新闻数据库查询] 所有数据源都没有 {symbol} 的新闻数据")
            return {
                "news": [],
                "enabled_sources": enabled_sources,
                "used_sources": [],
            }

        priority_map = {source: index for index, source in enumerate(enabled_sources)}
        raw_news.sort(
            key=lambda item: (
                _parse_publish_time(item.get("publish_time")) or datetime(1970, 1, 1),
                -priority_map.get(item.get("data_source"), 999),
            ),
            reverse=True,
        )

        unique_news = _deduplicate_news_items(raw_news)[:limit]
        used_sources = []
        for news in unique_news:
            data_source = _collapse_whitespace(news.get("data_source"))
            if data_source and data_source not in used_sources:
                used_sources.append(data_source)

        logger.info(
            f"✅ [News database query] Aggregate to {len(unique_news)} news, hit data source: {used_sources or 'None'}"
        )
        return {
            "news": unique_news,
            "enabled_sources": enabled_sources,
            "used_sources": used_sources,
        }

    except Exception as exc:
        logger.error(f"❌ [News database query] Query failed: {exc}")
        return {
            "news": [],
            "enabled_sources": enabled_sources,
            "used_sources": [],
        }


def _run_async_in_thread(coroutine_factory: Callable[[], Any], timeout: float = 30.0) -> Any:
    """Execute asynchronous coroutines in independent threads to avoid event loop conflicts."""

    def _runner() -> Any:
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine_factory())
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        return future.result(timeout=timeout)


def _fetch_tushare_news_live(
    symbol: str,
    company_name: Optional[str],
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Directly pull multi-source real-time news in a specified time window from Tushare."""
    logger.info(
        f"📰 [unified news tool] Try Tushare Live News: symbol={symbol}, "
        f"company_name={company_name or '-'}, window={start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}"
    )

    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Failed to initialize Tushare provider: {exc}")
        return []

    if not provider or not provider.is_available() or provider.api is None:
        logger.info("⚠️ [unified news tool] Tushare provider Not available, skip the paid enhancement link")
        return []

    start_date_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
    end_date_str = end_date.strftime("%Y-%m-%d %H:%M:%S")
    fetch_limit = max(limit * 4, 40)
    collected_news: List[Dict[str, Any]] = []

    for source_code in TUSHARE_LIVE_SOURCES:
        try:
            logger.debug(f"📰 [unified news tool] Tushare Try a news source: {source_code}")
            news_df = provider.api.news(
                src=source_code,
                start_date=start_date_str,
                end_date=end_date_str,
            )
        except Exception as exc:
            error_text = str(exc).lower()
            if any(keyword in error_text for keyword in ["权限", "permission", "unauthorized", "access denied", "积分", "point"]):
                logger.warning(f"⚠️ [unified news tool] Tushare News permission is not available, skip the paid enhancement link: {exc}")
                return []
            logger.debug(f"⚠️ [统一新闻工具] Tushare 新闻源 {source_code} 拉取失败: {exc}")
            continue

        if news_df is None or news_df.empty:
            logger.info(f"📰 [统一新闻工具] Tushare 新闻源 {source_code} 未返回数据")
            continue

        raw_row_count = 0
        try:
            raw_row_count = int(len(news_df))
        except Exception:
            raw_row_count = 0

        process_limit = max(fetch_limit, raw_row_count) if raw_row_count else fetch_limit
        if raw_row_count > fetch_limit * 2:
            logger.info(
                f"📰 [统一新闻工具] Tushare 新闻源 {source_code} 原始返回 {raw_row_count} 条，"
                f"Scan in full to prevent company-related news from falling outside the truncation range"
            )

        processed_news = provider._process_tushare_news(  # type: ignore[attr-defined]
            news_df,
            source_code,
            symbol=None,
            limit=process_limit,
        )
        relevant_news = [
            news
            for news in processed_news
            if _is_relevant_a_share_news(news, symbol, company_name)
        ]

        if relevant_news:
            collected_news.extend(relevant_news)
            logger.info(
                f"📰 [统一新闻工具] Tushare 新闻源 {source_code} 命中 {len(relevant_news)} 条相关候选"
            )
        else:
            logger.info(
                f"📰 [unified news tool] Tushare news source {source_code} There is original data, but no relevant candidates for the target company were hit."
            )

        if len(_deduplicate_news_items(collected_news)) >= limit * 2:
            break

    if not collected_news:
        logger.info("📰 [unified news tool] Tushare No available candidates were obtained for the real-time link")
        return []

    filtered_news = _filter_news_by_date_range(_deduplicate_news_items(collected_news), start_date, end_date)
    final_news = _sort_news_by_time(filtered_news)[:limit]
    logger.info(f"📰 [统一新闻工具] Tushare 实时链路最终返回 {len(final_news)} 条新闻")
    return final_news


def _fetch_akshare_news_live(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Pull structured news from AKShare and filter strictly by analysis date window."""
    logger.info(
        f"📰 [unified news tool] Try AKShare Live News: symbol={symbol}, "
        f"window={start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}"
    )

    try:
        from tradingagents.dataflows.providers.china.akshare import AKShareProvider

        provider = AKShareProvider()
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Failed to initialize AKShare provider: {exc}")
        return []

    if not provider.is_available():
        logger.info("⚠️ [unified news tool] AKShare provider Not available, skip free fallback link")
        return []

    fetch_limit = max(limit * 5, 50)

    async def _get_news() -> Any:
        return await provider.get_stock_news(symbol=symbol, limit=fetch_limit)

    try:
        news_list = _run_async_in_thread(_get_news, timeout=30.0) or []
    except concurrent.futures.TimeoutError:
        logger.warning("⚠️ [unified news tool] AKShare News retrieval timed out, skipping free fallback link")
        return []
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] AKShare Failed to get news: {exc}")
        return []

    if not isinstance(news_list, list):
        logger.info("📰 [unified news tool] AKShare The live link returned a non-list result and is considered invalid.")
        return []

    filtered_news = _filter_news_by_date_range(news_list, start_date, end_date)
    final_news = _sort_news_by_time(_deduplicate_news_items(filtered_news))[:limit]
    logger.info(f"📰 [统一新闻工具] AKShare 实时链路最终返回 {len(final_news)} 条新闻")
    return final_news


def _fetch_google_news_candidates(
    query: str,
    start_date_str: str,
    end_date_str: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch structured candidate news from Google News."""
    try:
        from tradingagents.dataflows.news.google_news import getNewsData
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Failed to initialize Google News crawl: {exc}")
        return []

    try:
        raw_results = getNewsData(query.replace(" ", "+"), start_date_str, end_date_str)
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Google News crawl failed: {exc}")
        return []

    news_items = []
    for index, news in enumerate(raw_results[:limit]):
        news_items.append(
            {
                "title": _collapse_whitespace(news.get("title")),
                "summary": _collapse_whitespace(news.get("snippet")),
                "content": _collapse_whitespace(news.get("snippet")),
                "publish_time": _collapse_whitespace(news.get("date")),
                "source": _collapse_whitespace(news.get("source")) or "Google新闻",
                "url": _collapse_whitespace(news.get("link")),
                "category": "other",
                "sentiment": "neutral",
                "importance": "medium",
                "data_source": "google",
                "relevance_score": max(35, 95 - index),
            }
        )

    return _deduplicate_news_items(news_items)


def _fetch_finnhub_news_candidates(
    ticker: str,
    start_date_str: str,
    end_date_str: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Building structured news candidates from Finnhub local cache."""
    try:
        from tradingagents.config.config_manager import config_manager
        from tradingagents.dataflows.providers.us import get_data_in_range
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Failed to initialize Finnhub news reading: {exc}")
        return []

    try:
        raw_results = get_data_in_range(
            ticker,
            start_date_str,
            end_date_str,
            "news_data",
            config_manager.get_data_dir(),
        )
    except Exception as exc:
        logger.warning(f"⚠️ [unified news tool] Finnhub News reading failed: {exc}")
        return []

    if not raw_results:
        return []

    news_items: List[Dict[str, Any]] = []
    for day in sorted(raw_results.keys(), reverse=True):
        day_entries = raw_results.get(day) or []
        for entry in day_entries:
            news_items.append(
                {
                    "title": _collapse_whitespace(entry.get("headline")),
                    "summary": _collapse_whitespace(entry.get("summary")),
                    "content": _collapse_whitespace(entry.get("summary")),
                    "publish_time": day,
                    "source": _collapse_whitespace(entry.get("source")) or "Finnhub",
                    "url": _collapse_whitespace(entry.get("url")),
                    "category": "other",
                    "sentiment": "neutral",
                    "importance": "medium",
                    "data_source": "finnhub",
                }
            )
            if len(news_items) >= limit:
                return _deduplicate_news_items(news_items)

    return _deduplicate_news_items(news_items)


def _normalize_news_title_key(title: Any) -> str:
    """Standardized news title keys for title-level duplication removal."""
    return _collapse_whitespace(title).lower()


def _collect_unique_text_values(*values: Any) -> List[str]:
    """Merge multiple texts or text lists, maintaining the original order after deduplication."""
    collected: List[str] = []
    seen = set()

    for value in values:
        if value is None:
            continue

        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            text = _collapse_whitespace(candidate)
            if not text or text in seen:
                continue
            seen.add(text)
            collected.append(text)

    return collected


def _build_news_id(news_item: Dict[str, Any]) -> str:
    """Generate stable news_id for headline-aggregated news."""
    title_key = _normalize_news_title_key(news_item.get("title"))
    if not title_key:
        title_key = _collapse_whitespace(news_item.get("url")) or "untitled-news"
    digest = hashlib.md5(title_key.encode("utf-8")).hexdigest()[:10]
    return f"news_{digest}"


def _get_news_priority_key(news_item: Dict[str, Any]) -> Tuple[int, int, int, datetime]:
    """Get the priority key when aggregating news."""
    return (
        int(news_item.get("relevance_score", 0) or 0),
        1 if _collapse_whitespace(news_item.get("content")) else 0,
        1 if _collapse_whitespace(news_item.get("summary")) else 0,
        _parse_publish_time(news_item.get("publish_time")) or datetime.min,
    )


def _normalize_news_cluster_item(news_item: Dict[str, Any]) -> Dict[str, Any]:
    """Standardized aggregation of candidate news items."""
    normalized_item = dict(news_item)
    normalized_item["title"] = _collapse_whitespace(normalized_item.get("title"))
    normalized_item["summary"] = _collapse_whitespace(normalized_item.get("summary"))
    normalized_item["content"] = _collapse_whitespace(normalized_item.get("content"))
    normalized_item["source"] = _collapse_whitespace(normalized_item.get("source"))
    normalized_item["data_source"] = _collapse_whitespace(normalized_item.get("data_source"))
    normalized_item["url"] = _collapse_whitespace(normalized_item.get("url"))
    normalized_item["source_variants"] = _collect_unique_text_values(
        normalized_item.get("source_variants"),
        normalized_item.get("source"),
    )
    normalized_item["data_source_variants"] = _collect_unique_text_values(
        normalized_item.get("data_source_variants"),
        normalized_item.get("data_source"),
    )
    normalized_item["origin_paths"] = _collect_unique_text_values(
        normalized_item.get("origin_paths"),
        normalized_item.get("origin_path"),
    )
    normalized_item["url_variants"] = _collect_unique_text_values(
        normalized_item.get("url_variants"),
        normalized_item.get("url"),
    )
    normalized_item["duplicate_count"] = int(normalized_item.get("duplicate_count", 1) or 1)
    normalized_item["news_id"] = _build_news_id(normalized_item)
    return normalized_item


def _merge_news_cluster_items(
    existing_item: Dict[str, Any],
    incoming_item: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge news with the same title, keep better master records and aggregate source information."""
    normalized_existing = _normalize_news_cluster_item(existing_item)
    normalized_incoming = _normalize_news_cluster_item(incoming_item)

    preferred_item = normalized_incoming
    fallback_item = normalized_existing
    if _get_news_priority_key(normalized_existing) >= _get_news_priority_key(normalized_incoming):
        preferred_item = normalized_existing
        fallback_item = normalized_incoming

    merged_item = dict(preferred_item)
    merged_item["source_variants"] = _collect_unique_text_values(
        preferred_item.get("source_variants"),
        fallback_item.get("source_variants"),
    )
    merged_item["data_source_variants"] = _collect_unique_text_values(
        preferred_item.get("data_source_variants"),
        fallback_item.get("data_source_variants"),
    )
    merged_item["origin_paths"] = _collect_unique_text_values(
        preferred_item.get("origin_paths"),
        fallback_item.get("origin_paths"),
    )
    merged_item["url_variants"] = _collect_unique_text_values(
        preferred_item.get("url_variants"),
        fallback_item.get("url_variants"),
    )
    merged_item["duplicate_count"] = int(preferred_item.get("duplicate_count", 1) or 1) + int(
        fallback_item.get("duplicate_count", 1) or 1
    )

    if not merged_item.get("summary") and fallback_item.get("summary"):
        merged_item["summary"] = fallback_item["summary"]
    if len(_collapse_whitespace(fallback_item.get("content"))) > len(_collapse_whitespace(merged_item.get("content"))):
        merged_item["content"] = fallback_item.get("content")
    if not merged_item.get("url") and fallback_item.get("url"):
        merged_item["url"] = fallback_item.get("url")

    merged_item["news_id"] = _build_news_id(merged_item)
    return merged_item


def _merge_news_items_by_title(
    news_list: List[Dict[str, Any]],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Aggregate news by headline and keep source aggregation information."""
    clusters: Dict[str, Dict[str, Any]] = {}

    for news_item in news_list:
        title_key = _normalize_news_title_key(news_item.get("title"))
        if not title_key:
            continue

        normalized_item = _normalize_news_cluster_item(news_item)
        existing_item = clusters.get(title_key)
        if existing_item is None:
            clusters[title_key] = normalized_item
        else:
            clusters[title_key] = _merge_news_cluster_items(existing_item, normalized_item)

    merged_items = list(clusters.values())
    merged_items.sort(key=_get_news_priority_key, reverse=True)
    return merged_items[:limit]


def _get_news_source_signal(news_item: Dict[str, Any]) -> Tuple[str, str]:
    """Determine news signal strength based on source."""
    source_text = " ".join(
        _collect_unique_text_values(news_item.get("source_variants"), news_item.get("source"))
    )

    if any(keyword in source_text for keyword in HIGH_SIGNAL_NEWS_SOURCE_KEYWORDS):
        return "高", "Sources include announcements or mainstream financial media"

    if any(keyword in source_text for keyword in LOW_SIGNAL_NEWS_SOURCE_KEYWORDS):
        return "低", "来源偏社区或弱信号渠道"

    return "中", "The source can be used as a clue, but it still needs to be judged based on the title and details."


def _get_detail_recommendation(news_item: Dict[str, Any]) -> Tuple[str, str]:
    """Give a judgment as to whether it is recommended to continue viewing the news details."""
    title = _collapse_whitespace(news_item.get("title"))
    category = _collapse_whitespace(news_item.get("category"))
    relevance_score = int(news_item.get("relevance_score", 0) or 0)
    source_signal, source_reason = _get_news_source_signal(news_item)

    if _contains_any_keyword(title, A_SHARE_BROAD_CONTEXT_KEYWORDS):
        if _contains_any_keyword(title, A_SHARE_ENUMERATION_MARKERS):
            return "可暂不展开", "More like macro alerts or multi-company enumeration news"
        return "按需查看", "更像宏观背景或日历提醒"

    if category == "company_announcement" or _contains_any_keyword(title, A_SHARE_DIRECT_EVENT_KEYWORDS):
        return "建议查看", "涉及公告或直接公司事件"

    if relevance_score >= HIGH_CONFIDENCE_A_SHARE_RELEVANCE_SCORE:
        return "建议查看", "标题与目标公司高度相关"

    if source_signal == "高" and relevance_score >= 55:
        return "建议查看", source_reason

    if relevance_score >= 45:
        return "按需查看", "The title has some research relevance and can be expanded into details if needed."

    return "可暂不展开", "更像背景提及或弱相关线索"


def _annotate_headline_items(news_list: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    """Supplement news_id, source signals and detail suggestions for headline candidates."""
    annotated_items = []
    for news_item in news_list[:limit]:
        annotated_item = _normalize_news_cluster_item(news_item)
        source_signal, source_signal_reason = _get_news_source_signal(annotated_item)
        detail_action, detail_reason = _get_detail_recommendation(annotated_item)
        annotated_item["source_signal"] = source_signal
        annotated_item["source_signal_reason"] = source_signal_reason
        annotated_item["detail_action"] = detail_action
        annotated_item["detail_reason"] = detail_reason
        annotated_items.append(annotated_item)

    return annotated_items


def _format_variant_values(values: List[str], fallback: str) -> str:
    """Format candidate aggregate values."""
    cleaned_values = _collect_unique_text_values(values)
    return " / ".join(cleaned_values[:4]) if cleaned_values else fallback


def _format_headline_item(news_item: Dict[str, Any]) -> str:
    """Format news headline candidates."""
    title = _collapse_whitespace(news_item.get("title")) or "无标题"
    source_text = _format_variant_values(
        news_item.get("source_variants") or [],
        _collapse_whitespace(news_item.get("source")) or "未知来源",
    )
    data_source_text = _format_variant_values(
        [_get_source_display_name(source) for source in news_item.get("data_source_variants") or []],
        _get_source_display_name(_collapse_whitespace(news_item.get("data_source"))),
    )

    lines = [f"- [news_id: {news_item.get('news_id')}] **{title}**"]
    lines.append(
        f"  - 时间: {_format_publish_time(news_item.get('publish_time'))} | 来源: {source_text} | 数据源: {data_source_text}"
    )
    lines.append(
        f"  - 相关性: {int(news_item.get('relevance_score', 0) or 0)} | 来源信号: {news_item.get('source_signal')} | 明细建议: {news_item.get('detail_action')}（{news_item.get('detail_reason')}）"
    )

    if int(news_item.get("duplicate_count", 1) or 1) > 1:
        lines.append(f"  - 去重合并: 已合并 {int(news_item.get('duplicate_count', 1) or 1)} 条同标题新闻")

    return "\n".join(lines)


def _format_headline_section(news_list: List[Dict[str, Any]], section_title: str, source_note: str = "") -> str:
    """Format title candidates as Markdown chapters."""
    if not news_list:
        return ""

    header = f"## {section_title}"
    if source_note:
        header += f"\n**说明**: {source_note}"

    headline_items = "\n".join(_format_headline_item(news) for news in news_list)
    return f"{header}\n{headline_items}"


def _format_news_detail_item(news_item: Dict[str, Any]) -> str:
    """Format single news details."""
    source_text = _format_variant_values(
        news_item.get("source_variants") or [],
        _collapse_whitespace(news_item.get("source")) or "未知来源",
    )
    data_source_text = _format_variant_values(
        [_get_source_display_name(source) for source in news_item.get("data_source_variants") or []],
        _get_source_display_name(_collapse_whitespace(news_item.get("data_source"))),
    )
    summary = _summarize_news_item(news_item)
    content = _collapse_whitespace(news_item.get("content"))
    keywords = _coerce_keywords(news_item.get("keywords"))
    url = _collapse_whitespace(news_item.get("url"))

    lines = [f"## [news_id: {news_item.get('news_id')}] {_collapse_whitespace(news_item.get('title')) or 'Untitled'}"]
    lines.append(
        f"- 时间: {_format_publish_time(news_item.get('publish_time'))} | 来源: {source_text} | 数据源: {data_source_text}"
    )
    lines.append(
        f"- 相关性: {int(news_item.get('relevance_score', 0) or 0)} | 来源信号: {news_item.get('source_signal')} | 明细建议: {news_item.get('detail_action')}"
    )

    if summary:
        lines.append(f"- 摘要: {summary}")

    if content and content != summary:
        lines.append(f"- 正文要点: {content}")
    else:
        lines.append("- Main points of the text: The tool results do not provide longer text, and currently the analysis can only be carried out based on the title and abstract.")

    if keywords:
        lines.append(f"- 关键词: {', '.join(keywords[:8])}")

    if int(news_item.get("duplicate_count", 1) or 1) > 1:
        lines.append(
            f"- 去重来源: 已合并 {int(news_item.get('duplicate_count', 1) or 1)} 条同标题新闻，来源包括 {source_text}"
        )

    if url:
        lines.append(f"- 链接: {url}")

    return "\n".join(lines)


def _parse_requested_news_ids(news_ids: str) -> List[str]:
    """Parse the news_id list passed in by the detail tool."""
    normalized_ids = news_ids or ""
    for separator in ["，", "；", ";", "|", "\n", "\t"]:
        normalized_ids = normalized_ids.replace(separator, ",")

    requested_ids = []
    for raw_news_id in normalized_ids.split(","):
        news_id = _collapse_whitespace(raw_news_id)
        if news_id and news_id not in requested_ids:
            requested_ids.append(news_id)

    return requested_ids


def _build_a_share_news_bundle(ticker: str, curr_date: str, limit: int = 20) -> Dict[str, Any]:
    """Construct a candidate set of A-share news headlines/details."""
    start_date, end_date, start_date_str, end_date_str = _build_a_share_news_window(curr_date)
    clean_ticker = _normalize_a_share_symbol(ticker)
    company_name = _get_company_name(clean_ticker)
    candidate_limit = max(limit * 4, 40)

    db_result = _query_news_from_database(
        symbol=clean_ticker,
        start_date=start_date,
        end_date=end_date,
        limit=candidate_limit,
    )
    enabled_sources = db_result.get("enabled_sources") or _get_a_share_enabled_sources()

    combined_candidates: List[Dict[str, Any]] = []
    db_news = _rank_a_share_news_items(
        db_result.get("news") or [],
        clean_ticker,
        company_name,
        limit=candidate_limit,
    )
    for news_item in db_news:
        candidate = dict(news_item)
        candidate["origin_path"] = "database"
        combined_candidates.append(candidate)

    live_source_plan = _build_a_share_live_source_plan(enabled_sources)
    logger.info(f"📰 [unified news tool] A Stock news candidates build real-time fallback chains: {live_source_plan}")
    for live_source in live_source_plan:
        if live_source != "akshare":
            logger.info(f"📰 [unified news tool] Skip non-real-time analytics sources: {live_source}")
            continue

        live_news = _fetch_akshare_news_live(
            symbol=clean_ticker,
            start_date=start_date,
            end_date=end_date,
            limit=candidate_limit,
        )

        ranked_live_news = _rank_a_share_news_items(
            live_news,
            clean_ticker,
            company_name,
            limit=candidate_limit,
        )
        logger.info(
            f"📰 [统一新闻工具] A股新闻候选源 {live_source} 排序后保留 {len(ranked_live_news)} 条新闻"
        )
        for news_item in ranked_live_news:
            candidate = dict(news_item)
            candidate["origin_path"] = f"{live_source}_live"
            combined_candidates.append(candidate)

    merged_candidates = _merge_news_items_by_title(combined_candidates, limit=candidate_limit)
    annotated_items = _annotate_headline_items(merged_candidates, limit=limit)

    return {
        "ticker": clean_ticker,
        "market_name": "中国A股",
        "analysis_date": curr_date,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "company_name": company_name,
        "items": annotated_items,
        "footer_note": _build_a_share_footer(enabled_sources),
    }


def _build_hk_news_bundle(ticker: str, curr_date: str, limit: int = 20) -> Dict[str, Any]:
    """Construct a candidate set of Hong Kong stock news headlines/details."""
    _, _, start_date_str, end_date_str = _build_a_share_news_window(curr_date)
    google_candidates = _fetch_google_news_candidates(
        query=f"{ticker} 港股",
        start_date_str=start_date_str,
        end_date_str=end_date_str,
        limit=max(limit * 3, 30),
    )
    merged_candidates = _merge_news_items_by_title(google_candidates, limit=max(limit * 3, 30))
    annotated_items = _annotate_headline_items(merged_candidates, limit=limit)

    return {
        "ticker": ticker,
        "market_name": "港股",
        "analysis_date": curr_date,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "company_name": ticker,
        "items": annotated_items,
        "footer_note": "---\n*Hong Kong stock headline candidates are currently retrieved from Google News; if the tool does not provide longer text, the details only include abstracts and links.*",
    }


def _build_us_news_bundle(ticker: str, curr_date: str, limit: int = 20) -> Dict[str, Any]:
    """Construct a candidate set of US stock news headlines/details."""
    _, _, start_date_str, end_date_str = _build_a_share_news_window(curr_date)
    finnhub_candidates = _fetch_finnhub_news_candidates(
        ticker=ticker,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
        limit=max(limit * 2, 20),
    )
    for index, news_item in enumerate(finnhub_candidates):
        news_item.setdefault("relevance_score", max(40, 100 - index))

    google_candidates = _fetch_google_news_candidates(
        query=f"{ticker} stock news",
        start_date_str=start_date_str,
        end_date_str=end_date_str,
        limit=max(limit * 2, 20),
    )
    for index, news_item in enumerate(google_candidates):
        news_item.setdefault("relevance_score", max(35, 90 - index))

    merged_candidates = _merge_news_items_by_title(
        finnhub_candidates + google_candidates,
        limit=max(limit * 3, 30),
    )
    annotated_items = _annotate_headline_items(merged_candidates, limit=limit)

    return {
        "ticker": ticker,
        "market_name": "美股",
        "analysis_date": curr_date,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "company_name": ticker,
        "items": annotated_items,
        "footer_note": "---\n*U.S. stock headline candidates are prioritized using Finnhub cache and Google News retrieval; if the tool does not provide longer text, the details will only include abstracts and links.*",
    }


def _build_stock_news_bundle(ticker: str, curr_date: str, limit: int = 20) -> Dict[str, Any]:
    """Constructing a unified news candidate set by market."""
    from tradingagents.utils.stock_utils import StockUtils

    market_info = StockUtils.get_market_info(ticker)
    curr_date_clean = _normalize_analysis_date(curr_date)

    if market_info["is_china"]:
        return _build_a_share_news_bundle(ticker, curr_date_clean, limit=limit)
    if market_info["is_hk"]:
        return _build_hk_news_bundle(ticker, curr_date_clean, limit=limit)
    if market_info["is_us"]:
        return _build_us_news_bundle(ticker, curr_date_clean, limit=limit)

    _, _, start_date_str, end_date_str = _build_a_share_news_window(curr_date_clean)
    return {
        "ticker": ticker,
        "market_name": market_info.get("market_name", "未知市场"),
        "analysis_date": curr_date_clean,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "company_name": ticker,
        "items": [],
        "footer_note": "",
    }


def _build_a_share_footer(enabled_sources: List[str]) -> str:
    """Generate tail notes for A-share news tools."""
    live_path = _build_a_share_live_source_plan(enabled_sources)
    live_path_text = " → ".join(_get_live_source_display_name(source) for source in live_path)
    priority_text = " > ".join(_build_a_share_analysis_priority(enabled_sources))

    footer_lines = [
        "---",
        f"*A share preference path: Database cache{' → ' + live_path_text if live_path_text else ''}*",
        f"*当前分析优先级: {priority_text}*",
        "*Tushare The news source is currently only used for synchronous storage and does not participate in real-time news analysis calls.*",
    ]
    return "\n".join(footer_lines)


@tool
@register_tool(
    tool_id="get_stock_news_headlines_unified",
    name="统一股票新闻标题",
    description="Obtain stock news headline candidates, source judgment and deduplication results for subsequent pull details on demand",
    category="news",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_news", "news_headlines", "news_articles", "company_news", "market_news", "news", "event_driven"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["news_headline_screening", "news_deduplication", "company_event_discovery"],
)
def get_stock_news_headlines_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"],
    limit: Annotated[int, "Number of title candidates returned, default 12"] = 12,
) -> str:
    """Obtain deduplicated stock news headline candidates, support A shares, Hong Kong stocks, and US stocks, and return titles, source judgments, and deduplication results.

    Args:
        ticker: Stock code (supports A shares, Hong Kong stocks, and US stocks)
        curr_date: current date, format YYYY-MM-DD
        limit: Number of title candidates returned, default 12 (actual limit is between 1-30)

    Returns:
        str: Markdown Format news headline candidate report, including —
            # {ticker} News title candidate: report main title
            **Stock type**: Market type name
            **Analysis date**: Actual analysis date used
            **News time range**: start date to end date
            ## News titles after deduplication: title candidate list (each article contains news_id, title, source, time, summary, etc.)
            Bottom description: Source path and next step operation tips
        Returns include when there is no news "No available news titles are currently available" Markdown string
        In case of exception, return to "Unified news headline tool execution failed" Error description string at the beginning
    """
    try:
        bundle = _build_stock_news_bundle(ticker, curr_date, limit=max(1, min(limit, 30)))
        news_items = bundle.get("items") or []

        if not news_items:
            return (
                f"# {ticker} 新闻标题候选\n\n"
                f"**Stock type**: {bundle.get('market_name')}\n"
                f"**Analysis date**: {bundle.get('analysis_date')}\n"
                f"**News time range**: {bundle.get('start_date')} to {bundle.get('end_date')}\n\n"
                "## News headline candidates\n No available news titles are currently available."
            )

        result_parts = [
            f"# {ticker} 新闻标题候选",
            "",
            f"**股票类型**: {bundle.get('market_name')}",
            f"**分析日期**: {bundle.get('analysis_date')}",
            f"**新闻时间范围**: {bundle.get('start_date')} 至 {bundle.get('end_date')}",
            "",
            _format_headline_section(
                news_items,
                "去重后的新闻标题",
                "First filter events based on news_id, source, relevance and detail suggestions, and then call get_stock_news_details_unified to pull the news details that need to be dug in depth.",
            ),
            "",
            "*Next step: Pass the selected news_id (multiple ones can be separated by commas) to get_stock_news_details_unified to get the summary and main text points.*",
        ]

        footer_note = _collapse_whitespace(bundle.get("footer_note"))
        if footer_note:
            result_parts.extend(["", bundle.get("footer_note")])

        return "\n".join(part for part in result_parts if part is not None)

    except Exception as exc:
        error_msg = f"Unified news headline tool execution failed: {exc}"
        logger.error(f"❌ [统一新闻标题工具] {error_msg}")
        return error_msg


@tool
@register_tool(
    tool_id="get_stock_news_details_unified",
    name="统一股票新闻明细",
    description="Get stock news summaries, text highlights and source details based on the news_id returned by the headline tool",
    category="news",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_news", "news_details", "news_articles", "company_news", "news_summary", "news", "event_driven"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["news_detail_review", "news_content_analysis", "event_investigation"],
)
def get_stock_news_details_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"],
    news_ids: Annotated[str, "To view detailed news_id, use commas to separate multiple ID"],
) -> str:
    """Obtain stock news details based on news_id and return news summary, text highlights and source details.

    Args:
        ticker: Stock code (supports A shares, Hong Kong stocks, and US stocks)
        curr_date: current date, format YYYY-MM-DD
        news_ids: To view detailed news_id, use commas to separate multiple ID

    Returns:
        str: Markdown A detailed news report in the format of —
            # {ticker} News details: main title of the report
            **Stock type**: Market type name
            **Analysis date**: Actual analysis date used
            **News time range**: start date to end date
            News details text: summary, main points, source links, etc. of each news (in the order of incoming news_ids)
            Bottom description: optional, news_id not found prompt and source description
        When no valid news_id is provided, returns "Unified news detail tool execution failed" Error description string at the beginning
        Returns a Markdown string containing a list of not found IDs when the requested news_id is not found
        In case of exception, return to "Unified news detail tool execution failed" Error description string at the beginning
    """
    requested_ids = _parse_requested_news_ids(news_ids)
    if not requested_ids:
        return "Unified news detail tool execution failed: No valid news_id provided."

    try:
        bundle = _build_stock_news_bundle(
            ticker,
            curr_date,
            limit=max(len(requested_ids) * 12, 60),
        )
        item_map = {item.get("news_id"): item for item in bundle.get("items") or []}
        selected_items = [item_map[news_id] for news_id in requested_ids if news_id in item_map]
        missing_ids = [news_id for news_id in requested_ids if news_id not in item_map]

        if not selected_items:
            return (
                f"# {ticker} 新闻明细\n\n"
                f"**Stock type**: {bundle.get('market_name')}\n"
                f"**Analysis date**: {bundle.get('analysis_date')}\n\n"
                f"Requested not found news_id: {', '.join(missing_ids)}. The possible reason is that the real-time news has been refreshed, please call get_stock_news_headlines_unified again first."
            )

        result_parts = [
            f"# {ticker} 新闻明细",
            "",
            f"**股票类型**: {bundle.get('market_name')}",
            f"**分析日期**: {bundle.get('analysis_date')}",
            f"**新闻时间范围**: {bundle.get('start_date')} 至 {bundle.get('end_date')}",
            "",
            "\n\n".join(_format_news_detail_item(item) for item in selected_items),
        ]

        if missing_ids:
            result_parts.extend(
                [
                    "",
                    f"*The following news_id was not found:{', '.join(missing_ids)}. Live news may have been refreshed, please call get_stock_news_headlines_unified again first.*",
                ]
            )

        footer_note = bundle.get("footer_note")
        if footer_note:
            result_parts.extend(["", footer_note])

        return "\n".join(part for part in result_parts if part is not None)

    except Exception as exc:
        error_msg = f"Unified news detail tool execution failed: {exc}"
        logger.error(f"❌ [统一新闻明细工具] {error_msg}")
        return error_msg


@tool
@register_tool(
    tool_id="get_stock_news_unified",
    name="统一股票新闻",
    description="Obtain stock-related news (supports A-shares, Hong Kong stocks, and US stocks), and returns structured fields such as news titles, abstracts, source links, emotional tendencies, and importance.",
    category="news",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_news", "news", "news_articles", "company_news", "market_news", "event_driven", "market_sentiment"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["news_analysis", "company_event_review", "market_sentiment_collection"],
)
def get_stock_news_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"]
) -> str:
    """
    Unified stock news tool
    Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call corresponding news data sources

    Args:
        ticker: Stock code (such as: 000001, 0700.HK, AAPL)
        curr_date: Current date (format: YYYY-MM-DD)

    Returns:
        str: News analysis report
    """
    logger.info(f"📰 [unified news tool] Analyze stocks: {ticker}")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        # Automatically identify stock types
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info["is_china"]
        is_hk = market_info["is_hk"]
        is_us = market_info["is_us"]

        logger.info(f"📰 [unified news tool] Stock type: {market_info['market_name']}")

        curr_date_clean = _normalize_analysis_date(curr_date)
        start_date, end_date, start_date_str, end_date_str = _build_a_share_news_window(curr_date_clean)

        result_data = []
        footer_note = ""

        if is_china:
            logger.info(f"🇨🇳 [unified news tool] Handle A-share news...")

            clean_ticker = _normalize_a_share_symbol(ticker)
            company_name = _get_company_name(clean_ticker)
            db_result = _query_news_from_database(
                symbol=clean_ticker,
                start_date=start_date,
                end_date=end_date,
                limit=20,
            )
            enabled_sources = db_result.get("enabled_sources") or _get_a_share_enabled_sources()
            footer_note = _build_a_share_footer(enabled_sources)

            db_news = _rank_a_share_news_items(
                db_result.get("news") or [],
                clean_ticker,
                company_name,
                limit=20,
            )
            if db_news:
                used_sources = db_result.get("used_sources") or []
                source_note = "命中来源: " + " / ".join(
                    f"{_get_source_display_name(source)}（数据库缓存）" for source in used_sources
                ) if used_sources else "命中来源: 数据库缓存"
                result_data.append(_format_news_section(db_news, "数据库缓存", source_note))
                logger.info(f"✅ [统一新闻工具] 从数据库缓存获取到 {len(db_news)} 条结构化新闻")
            else:
                live_source_plan = _build_a_share_live_source_plan(enabled_sources)
                logger.info(f"📰 [unified news tool] A Stock real-time news fallback chain: {live_source_plan}")
                live_source_candidates: Dict[str, List[Dict[str, Any]]] = {}
                selected_live_source = None

                for live_source in live_source_plan:
                    logger.info(f"📰 [unified news tool] Start trying real-time news feeds: {live_source}")
                    if live_source != "akshare":
                        logger.info(f"📰 [unified news tool] Skip non-real-time analytics sources: {live_source}")
                        continue

                    live_news = _fetch_akshare_news_live(
                        symbol=clean_ticker,
                        start_date=start_date,
                        end_date=end_date,
                        limit=20,
                    )

                    ranked_live_news = _rank_a_share_news_items(
                        live_news,
                        clean_ticker,
                        company_name,
                        limit=20,
                    )
                    if not ranked_live_news:
                        logger.info(
                            f"📰 [统一新闻工具] {live_source} 实时链路无可用候选，继续回退"
                        )
                        continue

                    live_source_candidates[live_source] = ranked_live_news
                    logger.info(
                        f"✅ [统一新闻工具] {live_source} 实时链路命中 {len(ranked_live_news)} 条新闻，"
                        f"Highest relevance score: {_get_top_relevance_score(ranked_live_news)}"
                    )

                    if _is_high_confidence_a_share_news_item(
                        ranked_live_news[0],
                        clean_ticker,
                        company_name,
                    ):
                        selected_live_source = live_source
                        logger.info(
                            f"✅ [统一新闻工具] {live_source} 命中高置信度公司直指新闻，停止继续回退"
                        )
                        break

                if selected_live_source is None:
                    selected_live_source = _select_best_live_news_source(live_source_candidates, live_source_plan)
                    logger.info(
                        f"📰 [unified news tool] A Best candidate source for real-time stock news: {selected_live_source or 'None'}"
                    )

                if selected_live_source:
                    live_news = live_source_candidates[selected_live_source]
                    live_section_title = "AKShare Oriental Fortune News (real time)"
                    live_note = "It has been strictly filtered by the analysis date window and sorted and displayed based on company directness and event relevance."

                    result_data.append(_format_news_section(live_news, live_section_title, live_note))
                else:
                    result_data.append("## A stock news\n No news data matching the analysis date window was obtained.")

        elif is_hk:
            # Hong Kong stocks: Use Google News
            logger.info(f"🇭🇰 [unified news tool] Handle Hong Kong stock news...")

            try:
                search_query = f"{ticker} 港股"

                from tradingagents.dataflows.interface import get_google_news
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(get_google_news, search_query, curr_date_clean)
                    try:
                        news_data = future.result(timeout=30.0)  # Wait up to 30 seconds
                        if news_data:
                            result_data.append(f"## Google新闻\n{news_data}")
                            logger.info(f"✅ Successfully obtained Google News")
                        else:
                            logger.warning(f"⚠️ Google News returns empty results")
                    except FutureTimeoutError:
                        logger.warning(f"⚠️ Google News fetch timeout (30 seconds), skipping Google News to avoid blocking the process")
                    except Exception as e:
                        logger.error(f"❌ Google Failed to get news: {e}")
            except Exception as google_e:
                logger.error(f"❌ Google News acquisition exception: {google_e}")

        elif is_us:
            # US stocks: Use Finnhub News and Google News
            logger.info(f"🇺🇸 [unified news tool] Handle US stock news...")

            # 1. Get Finnhub News
            try:
                from tradingagents.dataflows.interface import get_finnhub_news
                news_data = get_finnhub_news(ticker, start_date_str, end_date_str)
                if news_data:
                    result_data.append(f"## 美股新闻\n{news_data}")
            except Exception as e:
                logger.error(f"❌ Finnhub Failed to get news: {e}")
                result_data.append(f"## US stock news\n Failed to obtain: {e}")

            # 2. Get Google News as a supplement (with timeout protection to avoid blocking the entire process)
            try:
                search_query = f"{ticker} stock news"

                from tradingagents.dataflows.interface import get_google_news
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(get_google_news, search_query, curr_date_clean)
                    try:
                        news_data = future.result(timeout=30.0)  # Wait up to 30 seconds
                        if news_data:
                            result_data.append(f"## Google新闻\n{news_data}")
                            logger.info(f"✅ Successfully obtained Google News")
                        else:
                            logger.warning(f"⚠️ Google News returns empty results")
                    except FutureTimeoutError:
                        logger.warning(f"⚠️ Google News fetch timeout (30 seconds), skipping Google News to avoid blocking the process")
                    except Exception as e:
                        logger.error(f"❌ Google Failed to get news: {e}")
            except Exception as google_e:
                logger.error(f"❌ Google News acquisition exception: {google_e}")

        if not result_data:
            result_data.append("## news results\n No news data is currently available.")

        # Combine all data
        combined_result = f"""# {ticker} 新闻分析

**股票类型**: {market_info['market_name']}
**分析日期**: {curr_date_clean}
**新闻时间范围**: {start_date_str} 至 {end_date_str}

{chr(10).join(result_data)}

{footer_note}
"""

        logger.info(f"📰 [unified news tool] Data acquisition completed, total length: {len(combined_result)}")
        return combined_result

    except Exception as e:
        error_msg = f"统一新闻工具执行失败: {str(e)}"
        logger.error(f"❌ [统一新闻工具] {error_msg}")
        return error_msg

