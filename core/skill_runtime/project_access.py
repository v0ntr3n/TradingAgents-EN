"""Skill Runtime project access public facade."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from .catalog import (
    SUPPORTED_COLLECTIONS,
    list_configured_external_sources,
    list_supported_stock_collections,
)
from .data_access import _get_db
from .external_sources import (
    get_external_financial_data,
    get_external_historical_data,
    get_external_valuation_data,
    get_external_query_news,
    get_external_stock_news,
)


_SCALAR_PREVIEW_LIMIT = 160
_FIELD_PREVIEW_LIMIT = 20
_NESTED_KEY_PREVIEW_LIMIT = 12
_LIST_PREVIEW_LIMIT = 3
_SUMMARY_PRIORITY_FIELDS = (
    "symbol",
    "code",
    "name",
    "ts_code",
    "report_period",
    "report_date",
    "ann_date",
    "publish_time",
    "trade_date",
    "end_date",
    "industry",
    "pe",
    "pb",
    "peg",
    "roe",
    "market_value",
)


def _get_collection_metadata(collection: str) -> Dict[str, Any]:
    for item in list_supported_stock_collections():
        if item.get("collection") == collection:
            return item
    return {}


def _strip_object_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(doc or {})
    normalized.pop("_id", None)
    return normalized


def _is_non_empty_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _truncate_text(value: str, limit: int = _SCALAR_PREVIEW_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...({len(value)} chars)"


def _summarize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())
        return {
            "type": "object",
            "key_count": len(keys),
            "sample_keys": keys[:_NESTED_KEY_PREVIEW_LIMIT],
        }
    if isinstance(value, list):
        item_types = sorted({type(item).__name__ for item in value[:_LIST_PREVIEW_LIMIT]})
        return {
            "type": "array",
            "length": len(value),
            "item_types": item_types,
        }
    return _truncate_text(str(value))


def _build_scalar_preview(doc: Dict[str, Any]) -> Dict[str, Any]:
    preview: Dict[str, Any] = {}

    for field_name in _SUMMARY_PRIORITY_FIELDS:
        if field_name in doc and _is_non_empty_value(doc.get(field_name)):
            preview[field_name] = _summarize_value(doc.get(field_name))

    if len(preview) >= _FIELD_PREVIEW_LIMIT:
        return preview

    for field_name in sorted(doc.keys()):
        if field_name in preview:
            continue
        value = doc.get(field_name)
        if not _is_non_empty_value(value):
            continue
        if isinstance(value, (dict, list)):
            continue
        preview[field_name] = _summarize_value(value)
        if len(preview) >= _FIELD_PREVIEW_LIMIT:
            break

    return preview


def _build_nested_field_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    nested_fields: Dict[str, Any] = {}
    for field_name, value in doc.items():
        if isinstance(value, dict):
            nested_fields[field_name] = _summarize_value(value)
        elif isinstance(value, list):
            nested_fields[field_name] = _summarize_value(value)
    return nested_fields


def _build_document_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    field_names = sorted(doc.keys())
    summary: Dict[str, Any] = {
        "field_count": len(field_names),
        "non_null_field_count": sum(1 for value in doc.values() if _is_non_empty_value(value)),
        "fields": field_names[:_FIELD_PREVIEW_LIMIT],
    }
    remaining_field_count = max(0, len(field_names) - _FIELD_PREVIEW_LIMIT)
    if remaining_field_count:
        summary["truncated_field_count"] = remaining_field_count

    scalar_preview = _build_scalar_preview(doc)
    if scalar_preview:
        summary["scalar_preview"] = scalar_preview

    nested_fields = _build_nested_field_summary(doc)
    if nested_fields:
        summary["nested_fields"] = nested_fields

    return summary


def _get_document_count(collection_ref: Any, filters: Dict[str, Any]) -> Dict[str, Any]:
    if filters:
        return {
            "matching_document_count": collection_ref.count_documents(filters),
            "matching_count_is_estimated": False,
        }
    return {
        "matching_document_count": collection_ref.estimated_document_count(),
        "matching_count_is_estimated": True,
    }


def query_stock_collection(
    collection: str,
    filters: Optional[Dict[str, Any]] = None,
    projection: Optional[Dict[str, Any]] = None,
    sort: Optional[Sequence[Sequence[Any]]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Synchronously query the open stock collection.

    Args:
        collection: Collection name, must be in SUPPORTED_COLLECTIONS (e.g. "stock_basic_info" /
            "market_quotes" / "stock_daily_quotes" / "stock_financial_data" /
            "stock_financial_periods" / "stock_news"）
        filters: MongoDB Query filter conditions. When None, it is equivalent to an empty dict (query all). Default None
        projection: MongoDB Projection rule, when None the _id field is excluded by default ({"_id": 0}) , Default None
        sort: Sorting rules, in the form [("trade_date", -1), ("symbol", 1)] A sequence of tuples, not sorted when None, default None
        limit: The upper limit of the number of documents returned will be truncated to [1, 500] interval, default 100

    Returns:
        list[dict]: Hit document list, each element is an original document (dict) in the collection——
            - The _id field is stripped out by default (unless projection explicitly includes it)
            - List length <= limit (passed [1, 500] truncated value)
            - The document field structure varies depending on the collection definition. Common fields such as symbol/code/name/trade_date, etc.
    """
    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        raise ValueError(f"unsupported collection: {collection_name}")

    db = _get_db()
    cursor = db[collection_name].find(filters or {}, projection or {"_id": 0})
    if sort:
        cursor = cursor.sort(list(sort))
    return list(cursor.limit(max(1, min(int(limit), 500))))


def aggregate_stock_collection(
    collection: str,
    pipeline: Sequence[Dict[str, Any]],
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Synchronously execute aggregation queries for open stock collections.

    Args:
        collection: Collection name, must be in SUPPORTED_COLLECTIONS (e.g. "stock_basic_info" /
            "market_quotes" / "stock_daily_quotes" / "stock_financial_data" /
            "stock_financial_periods" / "stock_news"）
        pipeline: MongoDB Aggregation pipeline stage sequence, of the form [{"$match": {...}}, {"$group": {...}}], 
            Returns all documents if empty
        limit: The upper limit of the number of returned results will be truncated to [1, 500] interval, default 100

    Returns:
        list[dict]: Aggregation result list, each element is a document (dict) output by the aggregation pipeline——
            - The _id field has been automatically stripped out of each result
            - List length <= limit (passed [1, 500] truncated value)
            - The field structure is determined by pipeline s $group / $project Determine in stages
    """
    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        raise ValueError(f"unsupported collection: {collection_name}")

    db = _get_db()
    results = list(db[collection_name].aggregate(list(pipeline or [])))
    capped_results = results[: max(1, min(int(limit), 500))]
    for item in capped_results:
        item.pop("_id", None)
    return capped_results


def inspect_stock_collection_schema(
    collection: str,
    sample_size: int = 20,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns the top-level fields, coverage, number of entries, and structure summary in the collection sample.

    Args:
        collection: Collection name, must be in SUPPORTED_COLLECTIONS (e.g. "stock_basic_info" /
            "market_quotes" / "stock_daily_quotes" / "stock_financial_data" /
            "stock_financial_periods" / "stock_news"）
        sample_size: The number of sampled documents will be truncated to [1, 100] interval, default 20
        filters: MongoDB Query filter conditions, sample all documents when None, default None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            collection: The collection name of the actual query
            matching_document_count: Total number of hit documents (estimated when filters is empty)
            matching_count_is_estimated: Whether the number of hits is an estimate (True when filters is empty,
                False otherwise for exact count)
            sample_count: The actual number of documents sampled (<= sample_size truncated value)
            query_keys: List of commonly used query fields tagged in collection metadata (from catalog)
            preferred_access: List of recommended access methods tagged in the collection metadata (from catalog)
            top_level_fields: List of top-level field names that appear in the sample, sorted by frequency of occurrence in descending order and field name in ascending order.
            field_coverage: Field coverage dictionary {field_name: coverage_ratio}, coverage_ratio
                A floating point number with 4 decimal places between 0 and 1, indicating the proportion of occurrence of this field in the sample
            sample_document_summaries: before min(3, sample_count) summary list of documents,
                Each element structure — field_count(Total number of top-level fields),
                non_null_field_count(Number of non-null fields), fields(List of top-level field names, up to 20),
                truncated_field_count(Number of fields to be truncated, optional),
                scalar_preview(Scalar field preview dictionary, optional),
                nested_fields(Nested object/array field summary dictionary, optional)
    """
    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        raise ValueError(f"unsupported collection: {collection_name}")

    capped_sample_size = max(1, min(int(sample_size), 100))
    db = _get_db()
    collection_ref = db[collection_name]
    normalized_filters = filters or {}
    docs = [
        _strip_object_id(item)
        for item in collection_ref.find(normalized_filters, {"_id": 0}).limit(capped_sample_size)
    ]

    field_counter: Counter[str] = Counter()
    for item in docs:
        if not isinstance(item, dict):
            continue
        field_counter.update(item.keys())

    sample_count = len(docs)
    ordered_fields = sorted(
        field_counter.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )
    field_coverage = {
        field_name: round(count / sample_count, 4)
        for field_name, count in ordered_fields
        if sample_count > 0
    }
    metadata = _get_collection_metadata(collection_name)
    sample_summaries = [_build_document_summary(item) for item in docs[: min(3, sample_count)]]
    count_summary = _get_document_count(collection_ref, normalized_filters)

    return {
        "collection": collection_name,
        **count_summary,
        "sample_count": sample_count,
        "query_keys": metadata.get("query_keys", []),
        "preferred_access": metadata.get("preferred_access", []),
        "top_level_fields": [field_name for field_name, _ in ordered_fields],
        "field_coverage": field_coverage,
        "sample_document_summaries": sample_summaries,
    }


def inspect_symbol_documents(
    collection: str,
    symbol: str,
    limit: int = 5,
) -> Dict[str, Any]:
    """Returns a sample document summary of the specified symbol in the collection, rather than the full document.

    Args:
        collection: Collection name, must be in SUPPORTED_COLLECTIONS (e.g. "stock_basic_info" /
            "market_quotes" / "stock_daily_quotes" / "stock_financial_data" /
            "stock_financial_periods" / "stock_news"）
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix), internal meeting zfill(6) standardization,
            Matches both symbol or code fields
        limit: The maximum number of document summaries returned will be truncated to [1, 20] interval, default 5

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            collection: The collection name of the actual query
            symbol: Standardized 6-digit stock code
            matching_document_count: The total number of documents in the collection matching this symbol/code (exact count)
            returned_summary_count: The actual number of document summaries returned (<= limit truncated value)
            documents: Document summary list, per element structure — field_count(Total number of top-level fields),
                non_null_field_count(Number of non-null fields), fields(List of top-level field names, up to 20),
                truncated_field_count(Number of fields to be truncated, optional),
                scalar_preview(Scalar field preview dictionary, optional),
                nested_fields(Nested object/array field summary dictionary, optional)
            Sorting rules (automatically selected by collection type): stock_daily_quotes in reverse order by trade_date;
                stock_financial_data press (report_period, report_date) reverse order;
                stock_financial_periods press (report_period, ann_date) reverse order;
                stock_news Sorted in reverse order by publish_time; other collections are not sorted
    """
    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        raise ValueError(f"unsupported collection: {collection_name}")

    normalized_symbol = str(symbol or "").strip().zfill(6)
    capped_limit = max(1, min(int(limit), 20))
    db = _get_db()

    filters: Dict[str, Any] = {"$or": [{"symbol": normalized_symbol}, {"code": normalized_symbol}]}
    collection_ref = db[collection_name]
    cursor = collection_ref.find(filters, {"_id": 0})

    if collection_name == "stock_daily_quotes":
        cursor = cursor.sort("trade_date", -1)
    elif collection_name == "stock_financial_data":
        cursor = cursor.sort([("report_period", -1), ("report_date", -1)])
    elif collection_name == "stock_financial_periods":
        cursor = cursor.sort([("report_period", -1), ("ann_date", -1)])
    elif collection_name == "stock_news":
        cursor = cursor.sort("publish_time", -1)

    docs = [_strip_object_id(item) for item in cursor.limit(capped_limit)]
    return {
        "collection": collection_name,
        "symbol": normalized_symbol,
        "matching_document_count": collection_ref.count_documents(filters),
        "returned_summary_count": len(docs),
        "documents": [_build_document_summary(item) for item in docs],
    }


def inspect_field_coverage(
    collection: str,
    fields: Sequence[str],
    filters: Optional[Dict[str, Any]] = None,
    sample_size: int = 50,
) -> Dict[str, Any]:
    """Returns the occurrence rate and non-null coverage of the field in the sample document.

    Args:
        collection: Collection name, must be in SUPPORTED_COLLECTIONS (e.g. "stock_basic_info" /
            "market_quotes" / "stock_daily_quotes" / "stock_financial_data" /
            "stock_financial_periods" / "stock_news"）
        fields: Sequence of field names to be counted. Empty strings/blank fields will be automatically filtered.
        filters: MongoDB Query filter conditions, sample all documents when None, default None
        sample_size: The upper limit of the number of sampled documents will be truncated to [1, 200] interval, default 50

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            collection: The collection name of the actual query
            sample_count: The actual number of documents sampled (<= sample_size truncated value)
            fields: Field coverage row list, per element structure —
                field(Field name), present_count(The number of documents that appear),
                non_null_count(The number of non-empty documents,None/""/[]/{} Treat as empty),
                present_coverage(Occurrence 0-1 to 4 decimal places),
                non_null_coverage(Non-null coverage 0-1 with 4 decimal places;
                    sample_count When it is 0, it is 0.0)
    """
    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        raise ValueError(f"unsupported collection: {collection_name}")

    normalized_fields = [str(field).strip() for field in fields if str(field).strip()]
    capped_sample_size = max(1, min(int(sample_size), 200))
    db = _get_db()
    docs = list(db[collection_name].find(filters or {}, {"_id": 0}).limit(capped_sample_size))
    sample_count = len(docs)

    coverage_rows: List[Dict[str, Any]] = []
    for field_name in normalized_fields:
        present_count = 0
        non_null_count = 0
        for item in docs:
            if not isinstance(item, dict):
                continue
            if field_name in item:
                present_count += 1
                if item.get(field_name) not in (None, "", [], {}):
                    non_null_count += 1
        coverage_rows.append(
            {
                "field": field_name,
                "present_count": present_count,
                "non_null_count": non_null_count,
                "present_coverage": round(present_count / sample_count, 4) if sample_count else 0.0,
                "non_null_coverage": round(non_null_count / sample_count, 4) if sample_count else 0.0,
            }
        )

    return {
        "collection": collection_name,
        "sample_count": sample_count,
        "fields": coverage_rows,
    }


PROJECT_DATA_ACCESS_DOC = """
 [Project data access interface]

The generated Skill runs in an independent Python sub-process, and the execution entry point is a synchronous function.
Therefore:
- Don t define it in Skill async def
- Do not use in Skill await
- If you need an asynchronous method from an external provider, give priority to calling the synchronization method provided by this module. wrapper

Description:
- This module is the public face of the Skill runtime
- catalog.py / external_sources.py / sync_wrappers.py Belongs to the internal implementation subdivision layer
- The generated Skill code should only import this module or data_access.py, do not directly import these internal modules

Allow import:from core.skill_runtime.project_access import ...

Available synchronization interfaces:

1. list_supported_stock_collections() -> list[dict]
   - View local collection directories that are currently allowed direct access by Skills

2. query_stock_collection(collection, filters=None, projection=None, sort=None, limit=100) -> list[dict]
   - General local collection query entrance
    - Allow access: stock_basic_info, market_quotes, stock_daily_quotes, stock_financial_data, stock_financial_periods, stock_news
   - Suitable for those who need to read the library directly by field Skill

3. aggregate_stock_collection(collection, pipeline, limit=100) -> list[dict]
   - Universal local aggregation portal
   - Only use it when the helper of data_access cannot be satisfied.

Reconnaissance/diagnosis dedicated interface (pre-analysis available, final Skill main logic should generally not be relied upon):

4. inspect_stock_collection_schema(collection, sample_size=20, filters=None) -> dict
    - Returns the field list, field coverage, estimated/matched number, and few sample summaries in the collection sample

5. inspect_symbol_documents(collection, symbol, limit=5) -> dict
    - Returns the latest sample document summary, hit number and field structure of the specified symbol in the collection

6. inspect_field_coverage(collection, fields, filters=None, sample_size=50) -> dict
    - Returns the occurrence and non-null coverage of the given field

7. list_configured_external_sources(market_category="a_shares") -> list[str]
   - Returns the data source priority currently enabled in the system, excluded local

8. get_external_stock_news(symbol, source=None, limit=10, market_category="a_shares") -> dict
   - Get external news synchronously and return {source, data}

9. get_external_historical_data(symbol, start_date, end_date, period="daily", source=None, market_category="a_shares") -> dict
   - Synchronously obtain external historical quotes, and internally bridged asynchronous provider

10. get_external_financial_data(symbol, source=None, market_category="a_shares", report_type="quarterly", period=None, limit=4) -> dict
   - Synchronously obtain external financial data, internally bridged asynchronous provider

11. get_external_valuation_data(symbol, start_date, end_date, source=None, market_category="a_shares") -> dict
   - Synchronously obtain external historical valuation sequences (PE_TTM, PB_MRQ, PS_TTM, PCF_TTM) for internal use BaoStock
   - Return {source: "baostock", data: [{date, close, pe_ttm, pb_mrq, ps_ttm, pcf_ttm}, ...]}
   - Valuation skills (historical quantiles, safety margins, PE/PB channels, etc.) preferentially use this function instead of get_external_historical_data (the one only contains OHLCV prices)

12. get_external_query_news(query, curr_date, look_back_days=7, source="google_news") -> dict
   - Obtain Google News / Finnhub news through the existing interface of the project

Usage example 1: Read local collection directly
    from core.skill_runtime.project_access import query_stock_collection

    peers = query_stock_collection(
        "stock_basic_info",
        filters={"industry": {"$regex": "Liquor", "$options": "i"}, "pb": {"$gt": 0}},
        projection={"_id": 0, "symbol": 1, "name": 1, "pb": 1, "industry": 1},
        limit=50,
    )

Usage example 2: Automatically select external historical data sources according to current configuration
    from core.skill_runtime.project_access import get_external_historical_data

    history = get_external_historical_data("600519", "2024-01-01", "2025-01-01")
    rows = history["data"]

Usage example 3: Explicitly specify external financial sources
    from core.skill_runtime.project_access import get_external_financial_data

    finance = get_external_financial_data("600519", source="tushare", report_type="quarterly", limit=4)

Hard rules:
- Don t do it yourself import pymongo / MongoClient
- Do not hardcode database names
- Do not directly await provider.get_historical_data / get_financial_data
- inspect_* The series of interfaces are mainly used for pre-reconnaissance, debugging and field verification. It is not recommended to rely on them in the final Skill business logic.
- Prioritize reusing data_access.py and the synchronization interface of this module, and only directly import third-party libraries when necessary.
- Do not import directly core.skill_runtime.external_sources / sync_wrappers / catalog
"""