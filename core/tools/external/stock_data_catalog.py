"""
Stock data collection directory

This directory is specially used by Skill generators and maintainers to uniformly describe the current system
Directly reusable stock MongoDB collection, key fields, recommended access methods, and considerations.

Maintenance principles:
1. Prioritize recording Stable and commonly used fields, we do not pursue writing all the historical fields at once.
2. If a collection allows source-specific extension fields, this must be clearly stated in the notes.
3. When local_data.py adds new access functions or collection fields change, this file will be synchronized first.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence


StockField = Dict[str, Any]
CollectionCatalog = Dict[str, Any]


COLLECTION_CATEGORY_HINTS: Dict[str, Sequence[str]] = {
    "stock_basic_info": ("fundamentals", "utility", "profile", "company"),
    "market_quotes": ("market", "technical", "realtime", "quote"),
    "stock_daily_quotes": ("market", "technical", "trend", "history"),
    "stock_financial_data": ("fundamentals", "valuation", "finance"),
    "stock_news": ("news", "event", "sentiment"),
}

COLLECTION_KEYWORDS: Dict[str, Sequence[str]] = {
    "stock_basic_info": (
        "基础信息", "公司信息", "行业", "板块", "静态估值", "市值", "股息率", "roe",
        "profile", "company", "industry", "sector", "valuation", "market cap", "dividend",
    ),
    "market_quotes": (
        "实时", "最新价", "盘口", "分时", "quote", "snapshot", "tick", "现价", "涨跌幅",
        "成交额", "成交量", "买一", "卖一",
    ),
    "stock_daily_quotes": (
        "日线", "k线", "历史行情", "区间走势", "技术指标", "均线", "波动率", "回测",
        "daily", "history", "ohlc", "candlestick", "trend", "technical", "moving average",
    ),
    "stock_financial_data": (
        "财务", "报表", "利润", "营收", "现金流", "资产负债", "估值", "基本面", "业绩",
        "financial", "revenue", "net income", "balance sheet", "cash flow", "earnings",
    ),
    "stock_news": (
        "新闻", "公告", "事件", "舆情", "情绪", "研报", "快讯", "headline", "news",
        "sentiment", "research report", "event",
    ),
}

PARAMETER_COLLECTION_HINTS: Dict[str, Sequence[str]] = {
    "start_date": ("stock_daily_quotes",),
    "end_date": ("stock_daily_quotes",),
    "trade_date": ("stock_daily_quotes", "market_quotes"),
    "report_period": ("stock_financial_data",),
    "report_type": ("stock_financial_data",),
    "limit": ("stock_news",),
    "sentiment": ("stock_news",),
    "publish_time": ("stock_news",),
}


STOCK_DATA_COLLECTION_CATALOG: List[CollectionCatalog] = [
    {
        "collection": "stock_basic_info",
        "purpose": "Basic stock information, industry affiliation, static valuation and some trading indicators.",
        "preferred_access": ["get_stock_basic_info", "get_industry_peer_basic_info", "summarize_industry_valuation"],
        "query_keys": ["symbol", "code", "source"],
        "notes": [
            "A The stock core basic table is first accessed with get_stock_basic_info.",
            "If the requirement is peer screening, industry samples or relative valuation of PB/PE/PS, use get_industry_peer_basic_info / summarize_industry_valuation first.",
            "The same stock may retain multiple records by source, and the query usually needs to be combined with the source or priority strategy.",
            "In addition to the standard fields, data source extension fields are allowed to be retained.",
        ],
        "fields": [
            {"name": "symbol", "type": "str", "description": "6 Bit stock code, primary query key."},
            {"name": "code", "type": "str", "description": "6-digit ticker compatible with legacy logic."},
            {"name": "full_symbol", "type": "str", "description": "Standardize the complete code, such as 600519.SH / 000001.SZ."},
            {"name": "name", "type": "str", "description": "Stock name."},
            {"name": "area", "type": "str", "description": "region."},
            {"name": "industry", "type": "str", "description": "industry."},
            {"name": "market", "type": "str", "description": "Trading market name."},
            {"name": "list_date", "type": "str", "description": "Date of release."},
            {"name": "sse", "type": "str", "description": "Section information."},
            {"name": "sec", "type": "str", "description": "Section/category to which it belongs."},
            {"name": "source", "type": "str", "description": "Basic information data sources, such as tushare/akshare/baostock/multi_source."},
            {"name": "updated_at", "type": "datetime|str", "description": "Last updated time."},
            {"name": "total_mv", "type": "float", "description": "Total market capitalization, a common caliber is 100 million yuan."},
            {"name": "circ_mv", "type": "float", "description": "Circulation market value, a common caliber is 100 million yuan."},
            {"name": "pe", "type": "float", "description": "P/E ratio."},
            {"name": "pb", "type": "float", "description": "Price to Book Ratio."},
            {"name": "ps", "type": "float", "description": "Price to sales ratio."},
            {"name": "pe_ttm", "type": "float", "description": "Rolling P/E ratio."},
            {"name": "pb_mrq", "type": "float", "description": "Latest price-to-book ratio."},
            {"name": "ps_ttm", "type": "float", "description": "Rolling price-to-sales ratio."},
            {"name": "roe", "type": "float", "description": "ROE."},
            {"name": "turnover_rate", "type": "float", "description": "Turnover rate."},
            {"name": "volume_ratio", "type": "float", "description": "Quantity ratio."},
            {"name": "dividend_yield", "type": "float", "description": "Dividend rate."},
            {"name": "dividend_yield_ttm", "type": "float", "description": "TTM Dividend rate."},
            {"name": "total_share", "type": "float", "description": "Total equity, part of the synchronization link uses this field name."},
            {"name": "float_share", "type": "float", "description": "Circulating share capital, some synchronization links use this field name."},
            {"name": "total_shares", "type": "float", "description": "Total share capital, standardized extension field."},
            {"name": "float_shares", "type": "float", "description": "Outstanding share capital, standardized extension field."},
            {"name": "board", "type": "str", "description": "Section standardization fields."},
            {"name": "sector", "type": "str", "description": "Industry/track standardized fields."},
            {"name": "industry_code", "type": "str", "description": "Industry code."},
            {"name": "status", "type": "str", "description": "Listing status such as L/D/P."},
            {"name": "is_hs", "type": "bool", "description": "Whether it is subject to Shanghai-Shenzhen-Hong Kong Stock Connect."},
            {"name": "currency", "type": "str", "description": "Trading currencies."},
            {"name": "market_info", "type": "dict", "description": "Market information extended structure, including exchange / currency / timezone, etc."},
            {"name": "data_version", "type": "int", "description": "Data version."},
        ],
    },
    {
        "collection": "market_quotes",
        "purpose": "Fields related to near-real-time market conditions, rise and fall, turnover and market opening.",
        "preferred_access": ["get_market_quotes"],
        "query_keys": ["symbol", "code"],
        "notes": [
            "The main real-time market table usually only retains one latest record for each stock.",
            "Prioritize access with get_market_quotes to avoid direct dependence on field compatibility differences.",
        ],
        "fields": [
            {"name": "symbol", "type": "str", "description": "6 Bit stock code, primary query key."},
            {"name": "code", "type": "str", "description": "6-digit ticker compatible with legacy logic."},
            {"name": "full_symbol", "type": "str", "description": "Standardize the complete code."},
            {"name": "market", "type": "str", "description": "Market identification, such as CN/HK/US."},
            {"name": "close", "type": "float", "description": "Latest price/closing price."},
            {"name": "current_price", "type": "float", "description": "The current price, usually aligned with close."},
            {"name": "pre_close", "type": "float", "description": "previous closing price."},
            {"name": "change", "type": "float", "description": "Increase or decrease."},
            {"name": "pct_chg", "type": "float", "description": "Increase or decrease."},
            {"name": "open", "type": "float", "description": "opening price."},
            {"name": "high", "type": "float", "description": "Highest price."},
            {"name": "low", "type": "float", "description": "lowest price."},
            {"name": "volume", "type": "float", "description": "Volume."},
            {"name": "amount", "type": "float", "description": "Turnover."},
            {"name": "turnover_rate", "type": "float", "description": "Turnover rate."},
            {"name": "volume_ratio", "type": "float", "description": "Quantity ratio."},
            {"name": "trade_date", "type": "str", "description": "Transaction date."},
            {"name": "timestamp", "type": "datetime", "description": "Quotation timestamp."},
            {"name": "updated_at", "type": "datetime", "description": "Update time."},
            {"name": "bid_prices", "type": "list[float]", "description": "Buy price ranges 1-5."},
            {"name": "bid_volumes", "type": "list[float]", "description": "Buy in quantities 1-5."},
            {"name": "ask_prices", "type": "list[float]", "description": "Selling price range 1-5."},
            {"name": "ask_volumes", "type": "list[float]", "description": "Sold in quantities of 1-5."},
            {"name": "data_source", "type": "str", "description": "Quotation source field."},
            {"name": "data_version", "type": "int", "description": "Data version."},
        ],
    },
    {
        "collection": "stock_daily_quotes",
        "purpose": "Historical daily/K lines are used for price trends, interval statistics, and technical indicator calculations.",
        "preferred_access": ["get_stock_daily_quotes"],
        "query_keys": ["symbol", "trade_date", "period", "data_source"],
        "notes": [
            "Historical market main table, often used for pressing symbol + Date range query.",
            "It is preferable to use get_stock_daily_quotes. It is not recommended to generate low-level Mongo queries by yourself in the generated Skill.",
        ],
        "fields": [
            {"name": "symbol", "type": "str", "description": "6 stock code."},
            {"name": "code", "type": "str", "description": "Stock ticker compatible with old logic."},
            {"name": "full_symbol", "type": "str", "description": "Standardize the complete code."},
            {"name": "market", "type": "str", "description": "Market identity."},
            {"name": "trade_date", "type": "str", "description": "Transaction date, common format YYYY-MM-DD."},
            {"name": "period", "type": "str", "description": "Period, such as daily / weekly / monthly."},
            {"name": "open", "type": "float", "description": "opening price."},
            {"name": "high", "type": "float", "description": "Highest price."},
            {"name": "low", "type": "float", "description": "lowest price."},
            {"name": "close", "type": "float", "description": "closing price."},
            {"name": "pre_close", "type": "float", "description": "previous closing price."},
            {"name": "change", "type": "float", "description": "Increase or decrease."},
            {"name": "pct_chg", "type": "float", "description": "Increase or decrease."},
            {"name": "volume", "type": "float", "description": "Volume."},
            {"name": "amount", "type": "float", "description": "Turnover."},
            {"name": "turnover_rate", "type": "float", "description": "Turnover rate."},
            {"name": "volume_ratio", "type": "float", "description": "Quantity ratio."},
            {"name": "pe", "type": "float", "description": "P/E ratio in current day or snapshot valuation metrics."},
            {"name": "pb", "type": "float", "description": "Price to Book Ratio."},
            {"name": "ps", "type": "float", "description": "Price to sales ratio."},
            {"name": "adjustflag", "type": "float|str", "description": "Re-weighting mark or re-weighting factor."},
            {"name": "tradestatus", "type": "float|str", "description": "Transaction status."},
            {"name": "isST", "type": "float|str", "description": "Whether ST."},
            {"name": "data_source", "type": "str", "description": "Historical data sources."},
            {"name": "created_at", "type": "datetime", "description": "Creation time."},
            {"name": "updated_at", "type": "datetime", "description": "Update time."},
            {"name": "version", "type": "int", "description": "Data version."},
        ],
    },
    {
        "collection": "stock_financial_data",
        "purpose": "Financial statements and key financial indicators for use in fundamental analysis and valuation calculations.",
        "preferred_access": ["get_stock_financial_data"],
        "query_keys": ["symbol", "report_period", "data_source", "report_type"],
        "notes": [
            "This is a unified financial master table. The basic metadata fields are relatively stable, and the detailed indicators can be expanded due to different sources.",
            "When generating Skills, you should first rely on report_period / report_type / data_source for filtering.",
            "The report_date field may also appear in historical data. When generating Skills, it must be compatible with report_period / report_date.",
            "If you only need the most recent financial data, use get_stock_financial_data instead of doing complex aggregation yourself.",
        ],
        "fields": [
            {"name": "symbol", "type": "str", "description": "6 stock code."},
            {"name": "code", "type": "str", "description": "Stock ticker compatible with old logic."},
            {"name": "full_symbol", "type": "str", "description": "Standardize the complete code."},
            {"name": "market", "type": "str", "description": "Market identity."},
            {"name": "report_period", "type": "str", "description": "Reporting period, such as 20241231."},
            {"name": "report_type", "type": "str", "description": "Report type, such as quarterly / annual."},
            {"name": "data_source", "type": "str", "description": "Financial data sources such as tushare/akshare/baostock."},
            {"name": "ann_date", "type": "str", "description": "Announcement date, some sources exist."},
            {"name": "revenue", "type": "float", "description": "operating income."},
            {"name": "net_income", "type": "float", "description": "net profit."},
            {"name": "total_assets", "type": "float", "description": "total assets."},
            {"name": "total_equity", "type": "float", "description": "Total stockholders equity."},
            {"name": "total_liab", "type": "float", "description": "Total liabilities."},
            {"name": "cash_and_equivalents", "type": "float", "description": "Monetary funds/cash and equivalents."},
            {"name": "roe", "type": "float", "description": "ROE."},
            {"name": "debt_to_assets", "type": "float", "description": "Asset-liability ratio."},
            {"name": "created_at", "type": "datetime", "description": "Creation time."},
            {"name": "updated_at", "type": "datetime", "description": "Update time."},
            {"name": "version", "type": "int", "description": "Data version."},
        ],
    },
    {
        "collection": "stock_news",
        "purpose": "Stock news, events, sentiment and tags.",
        "preferred_access": ["get_stock_news", "get_stock_news_by_date_range"],
        "query_keys": ["symbol", "symbols", "publish_time", "data_source"],
        "notes": [
            "The news main table is suitable for pressing symbol + Time interval query.",
            "Uniqueness is usually given by url + title + publish_time Combination Guarantee.",
            "When generating Skills, try to reuse get_stock_news / get_stock_news_by_date_range.",
        ],
        "fields": [
            {"name": "symbol", "type": "str", "description": "Mainly associated with stock codes."},
            {"name": "full_symbol", "type": "str", "description": "Standardize the complete code."},
            {"name": "market", "type": "str", "description": "Market identity."},
            {"name": "symbols", "type": "list[str]", "description": "Multiple stock symbols associated with this news."},
            {"name": "title", "type": "str", "description": "News headlines."},
            {"name": "content", "type": "str", "description": "News text or summary text."},
            {"name": "summary", "type": "str", "description": "Summary."},
            {"name": "url", "type": "str", "description": "Original link."},
            {"name": "source", "type": "str", "description": "Original media source."},
            {"name": "author", "type": "str", "description": "Author."},
            {"name": "publish_time", "type": "datetime", "description": "Release time."},
            {"name": "category", "type": "str", "description": "News categories."},
            {"name": "sentiment", "type": "str", "description": "Sentiment labels such as positive/neutral/negative."},
            {"name": "sentiment_score", "type": "float", "description": "Sentiment score."},
            {"name": "keywords", "type": "list[str]", "description": "Keyword list."},
            {"name": "importance", "type": "str", "description": "Importance level."},
            {"name": "data_source", "type": "str", "description": "News aggregation source."},
            {"name": "created_at", "type": "datetime", "description": "Creation time."},
            {"name": "updated_at", "type": "datetime", "description": "Update time."},
            {"name": "version", "type": "int", "description": "Data version."},
        ],
    },
]


def _render_collection_block(item: CollectionCatalog) -> str:
    lines = [
        f"- 集合: {item['collection']}",
        f"  用途: {item['purpose']}",
        f"  推荐访问函数: {', '.join(item.get('preferred_access', [])) or '无'}",
        f"  常用查询键: {', '.join(item.get('query_keys', [])) or '无'}",
        "  关键字段:",
    ]
    for field in item.get("fields", []):
        lines.append(
            f"    - {field['name']} ({field['type']}): {field['description']}"
        )
    if item.get("notes"):
        lines.append("  维护说明:")
        for note in item["notes"]:
            lines.append(f"    - {note}")
    return "\n".join(lines)


def _normalize_text_parts(values: Iterable[Any]) -> List[str]:
    parts: List[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text.lower())
            continue
        if isinstance(value, dict):
            parts.extend(_normalize_text_parts(value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            parts.extend(_normalize_text_parts(value))
            continue
        text = str(value).strip()
        if text:
            parts.append(text.lower())
    return parts


def _build_skill_context_text(
    *,
    category: str = "",
    description: str = "",
    data_source: str = "",
    constraints: Sequence[str] | None = None,
    expected_fields: Sequence[str] | None = None,
    parameter_names: Sequence[str] | None = None,
) -> str:
    return "\n".join(
        _normalize_text_parts(
            [
                category,
                description,
                data_source,
                constraints or [],
                expected_fields or [],
                parameter_names or [],
            ]
        )
    )


def select_relevant_stock_collections(
    *,
    category: str = "",
    description: str = "",
    data_source: str = "",
    constraints: Sequence[str] | None = None,
    expected_fields: Sequence[str] | None = None,
    parameter_names: Sequence[str] | None = None,
    max_items: int = 3,
) -> List[CollectionCatalog]:
    context_text = _build_skill_context_text(
        category=category,
        description=description,
        data_source=data_source,
        constraints=constraints,
        expected_fields=expected_fields,
        parameter_names=parameter_names,
    )
    category_lower = (category or "").strip().lower()
    param_names = {(name or "").strip().lower() for name in (parameter_names or []) if name}

    ranked: List[tuple[int, CollectionCatalog]] = []
    for item in STOCK_DATA_COLLECTION_CATALOG:
        collection = item["collection"]
        score = 0

        if category_lower in COLLECTION_CATEGORY_HINTS.get(collection, ()):
            score += 6

        for keyword in COLLECTION_KEYWORDS.get(collection, ()):
            if keyword.lower() in context_text:
                score += 2

        for param_name, related_collections in PARAMETER_COLLECTION_HINTS.items():
            if param_name in param_names and collection in related_collections:
                score += 2

        field_names = {field.get("name", "").lower() for field in item.get("fields", [])}
        for expected_field in (expected_fields or []):
            normalized_field = (expected_field or "").strip().lower()
            if normalized_field and normalized_field in field_names:
                score += 1

        if any(
            query_key.lower() in param_names and query_key.lower() not in {"symbol", "code"}
            for query_key in item.get("query_keys", [])
        ):
            score += 1

        ranked.append((score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for score, item in ranked if score > 0][:max_items]

    if not selected:
        fallback_map = {
            "news": ["stock_news", "stock_basic_info"],
            "market": ["market_quotes", "stock_daily_quotes"],
            "technical": ["stock_daily_quotes", "market_quotes"],
            "fundamentals": ["stock_financial_data", "stock_basic_info"],
            "utility": ["stock_basic_info"],
        }
        fallback_collections = fallback_map.get(category_lower, ["stock_basic_info"])
        selected = [
            item for item in STOCK_DATA_COLLECTION_CATALOG
            if item["collection"] in fallback_collections
        ]

    selected_names = {item["collection"] for item in selected}
    if "stock_basic_info" not in selected_names and category_lower in {"fundamentals", "market", "news", "technical"}:
        basic_info = next(
            (item for item in STOCK_DATA_COLLECTION_CATALOG if item["collection"] == "stock_basic_info"),
            None,
        )
        if basic_info is not None and len(selected) < max_items:
            selected.append(basic_info)

    return selected[:max_items]


def build_stock_data_collection_doc_for_skill(skill_spec: Any, max_items: int = 3) -> str:
    category = getattr(skill_spec, "category", "")
    description = getattr(skill_spec, "description", "")
    data_source = getattr(skill_spec, "data_source", "")
    constraints = getattr(skill_spec, "constraints", []) or []
    expected_output = getattr(skill_spec, "expected_output", None)
    expected_fields = getattr(expected_output, "fields", []) if expected_output else []
    parameter_names = [getattr(param, "name", "") for param in getattr(skill_spec, "parameters", []) or []]

    selected = select_relevant_stock_collections(
        category=category,
        description=description,
        data_source=data_source,
        constraints=constraints,
        expected_fields=expected_fields,
        parameter_names=parameter_names,
        max_items=max_items,
    )
    focus_summary = "、".join(item["collection"] for item in selected)
    return render_stock_data_collection_doc(
        collections=selected,
        focus_summary=focus_summary,
    )


def render_stock_data_collection_doc(
    collections: Sequence[CollectionCatalog] | None = None,
    focus_summary: str = "",
) -> str:
    collection_items = list(collections or STOCK_DATA_COLLECTION_CATALOG)
    header = [
        "【股票本地数据集合目录】",
        "The following directory is the most important stock data MongoDB collection description in the current system for reference when generating Skills.",
        "When generating a Skill, priority is given to calling the encapsulated function in local_data.py; only when the encapsulated function cannot satisfy the requirement, direct querying of the collection will be considered.",
        "If you query MongoDB directly, you must strictly use the following field names and do not make up non-existent columns.",
        "It is strictly prohibited to create your own MongoClient in generated code, hard-code database names, or invent database helpers that do not exist in your project.",
        "",
    ]
    if focus_summary:
        header.insert(1, f"This time only relevant collections are loaded according to current needs.: {focus_summary}")
    body = ["\n\n".join(_render_collection_block(item) for item in collection_items)]
    footer = [
        "",
        "【使用原则】",
        "1. Prioritize local data, then external API.",
        "2. Prioritize stock_basic_info when basic information is needed; market_quotes when the latest price is needed; stock_daily_quotes when range market conditions are needed.",
        "3. When industry peer samples, collection field reuse, or PB/PE/PS industry statistics are needed, get_industry_peer_basic_info / summarize_industry_valuation is preferred.",
        "3. Financial data is taken from the most recent periods in reverse order of report_period; if report_date is used for historical records, this field must also be compatible.",
        "4. news data press symbol + publish_time Filter and control the limit to avoid returning too much text at one time.",
        "5. If the collection fields do not completely match the current Skill requirements, give priority to secondary sorting in the returned results. Do not guess that there are undeclared fields in the database.",
    ]
    return "\n".join(header + body + footer)


STOCK_DATA_COLLECTION_DOC = render_stock_data_collection_doc()
