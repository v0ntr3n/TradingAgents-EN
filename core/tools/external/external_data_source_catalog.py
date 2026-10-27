"""
External interface and data source directory

Provide the Skill Builder with a maintainable catalog of capabilities from external data sources,
Used to filter sources such as AKShare, Tushare, Google News, Finnhub, etc. according to your needs,
Avoid injecting all external interface descriptions into prompt words at once.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence


ExternalSourceCatalog = Dict[str, Any]


EXTERNAL_DATA_SOURCE_CATALOG: List[ExternalSourceCatalog] = [
    {
        "source_id": "akshare",
        "display_name": "AKShare",
        "source_type": "python_library",
        "markets": ["CN", "HK", "US", "ETF", "macro"],
        "categories": ["market", "technical", "fundamentals", "news", "etf"],
        "preferred_for": [
            "A Free real-time/historical stock price supplement",
            "Oriental Fortune News, Handicaps, Sectors, ETFs and other public data",
            "Online degradation without stable local cache",
        ],
        "interfaces": [
            "tradingagents.dataflows.providers.china.akshare.AKShareProvider",
            "provider.get_stock_news_sync(symbol)",
            "provider.get_historical_data(symbol, start_date, end_date)",
            "Directly import akshare as ak to adjust the public interface",
        ],
        "usage_examples": [
            "from tradingagents.dataflows.providers.china.akshare import get_akshare_provider",
            "provider = get_akshare_provider()",
            "news_df = provider.get_stock_news_sync(symbol, limit=10)",
            "# Or directly import akshare as ak to adjust the public free interface",
        ],
        "constraints": [
            "Field names often have Chinese column names and must be standardized immediately after returning.",
            "The return structures of different interfaces are not completely consistent, and it cannot be assumed that all fields are stable in the long term.",
            "It is suitable for free complement, but it is not suitable for treating every interface as a strict contract.",
        ],
        "notes": [
            "A The first choice for stocks to be downgraded online.",
            "If there is a local library cache, read the local library first and then fill in AKShare.",
        ],
    },
    {
        "source_id": "tushare",
        "display_name": "Tushare Pro",
        "source_type": "provider_api",
        "markets": ["CN", "fundamentals", "index", "ETF"],
        "categories": ["market", "fundamentals", "valuation", "dividend", "chip"],
        "preferred_for": [
            "A Structured fundamental data such as stock financial statements, dividends, main business composition, etc.",
            "Official style data that requires a more stable field caliber",
            "When a standard field such as ts_code / report_period / ann_date is required",
        ],
        "interfaces": [
            "tradingagents.dataflows.providers.china.tushare.TushareProvider",
            "provider.get_financial_data(symbol, limit)",
            "provider.get_historical_data(symbol, start_date, end_date)",
            "get_tushare_provider()",
        ],
        "usage_examples": [
            "from tradingagents.dataflows.providers.china.tushare import get_tushare_provider",
            "provider = get_tushare_provider()",
            "# Read the local cache first; call the provider s standard method when online complement is really needed.",
            "# When generating synchronization skills, do not invent undocumented tushare calling paths",
        ],
        "constraints": [
            "Some interfaces require token, points or higher permissions.",
            "If the demand can be met by local cache, do not directly design the skill to run Tushare online every time.",
            "Pay attention to the format conversion between ts_code and 6-bit symbol.",
        ],
        "notes": [
            "A Preferred source of stock fundamentals and financial in-depth data.",
            "If it involves dividends, main business, chips, etc., first evaluate the authority threshold.",
        ],
    },
    {
        "source_id": "eastmoney_via_akshare",
        "display_name": "Oriental Fortune (via AKShare)",
        "source_type": "public_web_api",
        "markets": ["CN"],
        "categories": ["news", "market", "fund_flow", "sector"],
        "preferred_for": [
            "A Public web page data such as stock news, quotations, sectors, capital flows, etc.",
            "When you need free public data and don t want to parse web pages directly",
        ],
        "interfaces": [
            "AKShareProvider.get_stock_news_sync(symbol)",
            "akshare Oriental wealth related interfaces",
        ],
        "usage_examples": [
            "import akshare as ak",
            "# After directly calling the Dongcai public interface of AKShare, the Chinese listing will be standardized immediately.",
        ],
        "constraints": [
            "Essentially relying on public web interfaces, its stability is weaker than databases and formal APIs.",
            "Suitable for news/market supplements, but not suitable as the only high-reliability source.",
        ],
        "notes": [
            "Common sources of downgrades for news skills.",
        ],
    },
    {
        "source_id": "google_news",
        "display_name": "Google News",
        "source_type": "search_interface",
        "markets": ["HK", "US", "global"],
        "categories": ["news", "event"],
        "preferred_for": [
            "Hong Kong stocks, US stocks, overseas company news supplement",
            "When you need to aggregate news titles and summaries across sites",
        ],
        "interfaces": [
            "tradingagents.dataflows.interface.get_google_news(query, date)",
        ],
        "usage_examples": [
            "from tradingagents.dataflows.interface import get_google_news",
            "news = get_google_news(query, curr_date)",
        ],
        "constraints": [
            "To return quality-dependent search results, timeout protection must be set.",
            "The results are more suitable as a news supplement than as a source of strictly structured financial data.",
        ],
        "notes": [
            "Commonly used supplementary source of Hong Kong stock/US stock news.",
            "Recommended to be used in combination with Finnhub or local news cache.",
        ],
    },
    {
        "source_id": "finnhub",
        "display_name": "Finnhub",
        "source_type": "api",
        "markets": ["US"],
        "categories": ["news", "market", "company"],
        "preferred_for": [
            "U.S. stock company news and event-driven information",
            "When you need to query the time range of news related to US stocks",
        ],
        "interfaces": [
            "tradingagents.dataflows.interface.get_finnhub_news(symbol, start_date, end_date)",
        ],
        "usage_examples": [
            "from tradingagents.dataflows.interface import get_finnhub_news",
            "news = get_finnhub_news(symbol, curr_date, look_back_days)",
        ],
        "constraints": [
            "Typically relying on external configuration or quotas, the failed downgrade path should be preserved when building skills.",
            "More suitable for news/event streams, not suitable for replacing financial and daily master data.",
        ],
        "notes": [
            "One of the top sources of US stock news.",
        ],
    },
]


SOURCE_CATEGORY_HINTS: Dict[str, Sequence[str]] = {
    "akshare": ("market", "technical", "news", "etf", "utility"),
    "tushare": ("fundamentals", "valuation", "market", "utility"),
    "eastmoney_via_akshare": ("news", "market"),
    "google_news": ("news", "event"),
    "finnhub": ("news", "market"),
}


def is_known_external_source(name: str) -> bool:
    """Determine whether the given source name belongs to a known external data source directory (source_id / display_name / keyword alias).

    For demand offloading: user-specified sources (e.g. "dongchedi") If it is not in the directory,
    The caller should explicitly annotate"Out-of-directory data sources"Recommended instead of fallback.
    """
    text = (name or "").strip().lower()
    if not text:
        return False
    if text in {item["source_id"] for item in EXTERNAL_DATA_SOURCE_CATALOG}:
        return True
    for item in EXTERNAL_DATA_SOURCE_CATALOG:
        display = (item.get("display_name") or "").lower()
        if display and (display in text or text in display):
            return True
    for keywords in SOURCE_KEYWORDS.values():
        for keyword in keywords:
            if keyword.lower() in text:
                return True
    return False

SOURCE_KEYWORDS: Dict[str, Sequence[str]] = {
    "akshare": (
        "akshare", "东方财富", "eastmoney", "免费", "盘口", "实时", "历史行情", "etf", "板块",
        "资金流", "quote", "snapshot", "technical", "k线",
    ),
    "tushare": (
        "tushare", "财务", "报表", "利润", "分红", "主营", "筹码", "估值", "基本面", "公告日期",
        "report_period", "ann_date", "financial", "dividend",
    ),
    "eastmoney_via_akshare": (
        "东方财富新闻", "东财", "快讯", "公开网页", "新闻", "资金流", "板块",
    ),
    "google_news": (
        "google", "google news", "港股", "美股", "海外", "global", "headline", "新闻聚合",
    ),
    "finnhub": (
        "finnhub", "美股", "us stock", "company news", "事件", "overseas",
    ),
}

PARAMETER_SOURCE_HINTS: Dict[str, Sequence[str]] = {
    "start_date": ("akshare", "tushare", "google_news", "finnhub"),
    "end_date": ("akshare", "tushare", "google_news", "finnhub"),
    "report_period": ("tushare",),
    "report_type": ("tushare",),
    "curr_date": ("google_news", "finnhub"),
    "limit": ("akshare", "google_news", "finnhub"),
}


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


def select_relevant_external_data_sources(
    *,
    category: str = "",
    description: str = "",
    data_source: str = "",
    constraints: Sequence[str] | None = None,
    expected_fields: Sequence[str] | None = None,
    parameter_names: Sequence[str] | None = None,
    max_items: int = 3,
) -> List[ExternalSourceCatalog]:
    context_text = _build_skill_context_text(
        category=category,
        description=description,
        data_source=data_source,
        constraints=constraints,
        expected_fields=expected_fields,
        parameter_names=parameter_names,
    )
    category_lower = (category or "").strip().lower()
    data_source_lower = (data_source or "").strip().lower()
    param_names = {(name or "").strip().lower() for name in (parameter_names or []) if name}

    ranked: List[tuple[int, ExternalSourceCatalog]] = []
    for item in EXTERNAL_DATA_SOURCE_CATALOG:
        source_id = item["source_id"]
        score = 0

        if category_lower in SOURCE_CATEGORY_HINTS.get(source_id, ()):
            score += 5
        if data_source_lower and source_id in data_source_lower:
            score += 8

        for keyword in SOURCE_KEYWORDS.get(source_id, ()):
            if keyword.lower() in context_text:
                score += 2

        for param_name, related_sources in PARAMETER_SOURCE_HINTS.items():
            if param_name in param_names and source_id in related_sources:
                score += 1

        ranked.append((score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for score, item in ranked if score >= 3][:max_items]

    if not selected:
        fallback_map = {
            "news": ["akshare", "google_news", "finnhub"],
            "market": ["akshare", "tushare"],
            "technical": ["akshare", "tushare"],
            "fundamentals": ["tushare", "akshare"],
            "utility": ["akshare", "tushare"],
        }
        fallback_ids = fallback_map.get(category_lower, ["akshare", "tushare"])
        selected = [item for item in EXTERNAL_DATA_SOURCE_CATALOG if item["source_id"] in fallback_ids][:max_items]

    return selected[:max_items]


def _render_source_block(item: ExternalSourceCatalog) -> str:
    lines = [
        f"- 数据源: {item['display_name']} ({item['source_id']})",
        f"  类型: {item['source_type']}",
        f"  覆盖市场: {', '.join(item.get('markets', [])) or '无'}",
        f"  适用分类: {', '.join(item.get('categories', [])) or '无'}",
        f"  推荐场景: {', '.join(item.get('preferred_for', [])) or '无'}",
        "  推荐接口:",
    ]
    for entry in item.get("interfaces", []):
        lines.append(f"    - {entry}")
    if item.get("usage_examples"):
        lines.append("  调用示例:")
        for entry in item["usage_examples"]:
            lines.append(f"    - {entry}")
    if item.get("constraints"):
        lines.append("  约束:")
        for entry in item["constraints"]:
            lines.append(f"    - {entry}")
    if item.get("notes"):
        lines.append("  维护说明:")
        for entry in item["notes"]:
            lines.append(f"    - {entry}")
    return "\n".join(lines)


def render_external_data_source_doc(
    sources: Sequence[ExternalSourceCatalog] | None = None,
    focus_summary: str = "",
) -> str:
    source_items = list(sources or EXTERNAL_DATA_SOURCE_CATALOG)
    header = [
        "【外部接口与数据源目录】",
        "The following directory only describes external data sources that are supported in the current system and are suitable for reuse when automatically generating Skills.",
        "The order of priority is always: local library first, then choose the most suitable external source, do not invent multiple undefined interfaces at the same time.",
        "If the requirements can already be met by the local cache, don t design the skill to have to rely on external APIs in real time.",
        "External data sources must call documented entries in the project and do not invent undeclared provider methods or third-party return fields.",
        "",
    ]
    if focus_summary:
        header.insert(1, f"This time only relevant external sources are loaded according to current needs.: {focus_summary}")
    body = ["\n\n".join(_render_source_block(item) for item in source_items)]
    footer = [
        "",
        "【使用原则】",
        "1. A For free online replenishment of stocks, give priority to AKShare; for A-share structured finance, give priority to Tushare or its local cache.",
        "2. For Hong Kong/US stock news, Google News or Finnhub will be given priority, and timeout and failure downgrades will be retained.",
        "3. When precise field contracts are required, give priority to using Provider encapsulation or existing interface functions. Do not directly guess the original web page fields.",
        "4. If a source has a permission/points threshold, an alternative path to a local cache or free source must be provided in the Skill.",
        "5. When generating code, give priority to following the above import and call examples. Do not make up methods such as get_mongo_connection and provider.fetch_xxx that do not exist in the project.",
    ]
    return "\n".join(header + body + footer)


def build_external_data_source_doc_for_skill(skill_spec: Any, max_items: int = 3) -> str:
    category = getattr(skill_spec, "category", "")
    description = getattr(skill_spec, "description", "")
    data_source = getattr(skill_spec, "data_source", "")
    constraints = getattr(skill_spec, "constraints", []) or []
    expected_output = getattr(skill_spec, "expected_output", None)
    expected_fields = getattr(expected_output, "fields", []) if expected_output else []
    parameter_names = [getattr(param, "name", "") for param in getattr(skill_spec, "parameters", []) or []]

    selected = select_relevant_external_data_sources(
        category=category,
        description=description,
        data_source=data_source,
        constraints=constraints,
        expected_fields=expected_fields,
        parameter_names=parameter_names,
        max_items=max_items,
    )
    focus_summary = "、".join(item["display_name"] for item in selected)
    return render_external_data_source_doc(selected, focus_summary=focus_summary)


EXTERNAL_DATA_SOURCE_DOC = render_external_data_source_doc()