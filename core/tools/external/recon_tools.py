"""The recon layer callable toolset.

Wrap read-only probe functions in skill_runtime into standalone tools available for LLM function-calling.
Each function has detailed docstring and type annotations for automatic conversion by ToolCallNormalizer.normalize_tool_definition.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_READONLY_QUERY_CALL_COUNT = 0
_PROBE_INTERFACE_CALL_COUNT = 0
_PROBE_INTERFACE_LAST_CALLED_AT: Dict[str, float] = {}
_PROBE_INTERFACE_MIN_INTERVAL_SECONDS = 0.1

# ---------------------------------------------------------------------------
# Tools 1: List available collections
# ---------------------------------------------------------------------------

def list_available_collections() -> str:
    """Lists all local MongoDB collections that the Skill runtime is allowed to access and their uses.
    Returns a JSON array, each item containing collection(Collection name), purpose(Instructions for use), preferred_access(Recommended access functions), query_keys(Common query keys). """
    from core.skill_runtime.catalog import list_supported_stock_collections
    items = list_supported_stock_collections()
    return json.dumps(items, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 2: View collection schema
# ---------------------------------------------------------------------------

def inspect_collection_schema(collection: str, sample_size: int = 20) -> str:
    """View a summary of the top fields and coverage for a specified collection.
    parameters collection: Collection name (such as stock_basic_info, market_quotes, stock_financial_data etc.).
    parameters sample_size: Number of sampled documents (default 20, maximum 100).
    Returns a JSON object containing matching_document_count, sample_count, top_level_fields, field_coverage, sample_document_summaries, etc.
    Only a summary of the structure is returned, not the full sample document."""
    from core.skill_runtime.project_access import inspect_stock_collection_schema
    sample_size = int(sample_size) if not isinstance(sample_size, int) else sample_size
    result = inspect_stock_collection_schema(collection, sample_size=sample_size)
    return json.dumps(result, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Tools 3: View field coverage
# ---------------------------------------------------------------------------

def check_field_coverage(collection: str, fields: str, sample_size: int = 50) -> str:
    """Checks the non-null coverage of several fields in the specified collection.
    parameters collection: Collection name.
    parameters fields: Comma separated list of fields, e.g. 'pe,pb,total_mv,roe'. 
    parameters sample_size: Number of documents to sample (default 50).
    Returns a JSON object containing the non_null_coverage ratio for each field."""
    from core.skill_runtime.project_access import inspect_field_coverage as _inspect
    sample_size = int(sample_size) if not isinstance(sample_size, int) else sample_size
    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    if not field_list:
        return json.dumps({"error": "fields Parameter cannot be empty"}, ensure_ascii=False)
    result = _inspect(collection, field_list, sample_size=sample_size)
    return json.dumps(result, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Tools 4: View sample documents for specified stocks
# ---------------------------------------------------------------------------

def inspect_symbol_sample(collection: str, symbol: str, limit: int = 2) -> str:
    """View a sample document summary for a specified stock in a collection.
    parameters collection: Collection name.
    parameters symbol: 6 bit stock code, e.g. '600519'. 
    parameters limit: Returns the number of documents (default 2, maximum 5).
    Returns a JSON object, including matching_document_count, returned_summary_count, documents.
    documents Only includes field overview, number of non-empty fields, identification field preview and nested structure summary, and does not return the complete original text."""
    from core.skill_runtime.project_access import inspect_symbol_documents
    limit = int(limit) if not isinstance(limit, int) else limit
    docs = inspect_symbol_documents(collection, symbol, limit=min(limit, 5))
    return json.dumps(docs, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Tools 5: Describe runtime helper function signatures and documentation
# ---------------------------------------------------------------------------

def describe_runtime_helper(module: str, function_name: str) -> str:
    """View the signature and docstring for a function in the skill_runtime public module.
    parameters module: Module short name, support 'data_access', 'project_access', 'external_sources', 'standard_financial_apis'. 
    parameters function_name: Function name, for example 'get_stock_valuation_context'. 
    Returns a JSON object containing signature(function signature)and docstring(Documentation). """
    MODULE_MAP = {
        "data_access": "core.skill_runtime.data_access",
        "project_access": "core.skill_runtime.project_access",
        "external_sources": "core.skill_runtime.external_sources",
        "standard_financial_apis": "core.skill_runtime.standard_financial_apis",
    }
    full_module = MODULE_MAP.get(module)
    if not full_module:
        return json.dumps({"error": f"不支持的模块: {module}，可选: {list(MODULE_MAP.keys())}"}, ensure_ascii=False)
    try:
        import importlib
        mod = importlib.import_module(full_module)
        func = getattr(mod, function_name, None)
        if func is None or not callable(func):
            # List available functions
            available = [name for name, obj in inspect.getmembers(mod, inspect.isfunction) if not name.startswith("_")]
            return json.dumps({"error": f"函数 {function_name} 不存在", "available_functions": available}, ensure_ascii=False)
        sig = str(inspect.signature(func))
        doc = inspect.getdoc(func) or "(无文档)"
        return json.dumps({"module": full_module, "function": function_name, "signature": f"{function_name}{sig}", "docstring": doc}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 6: List all public functions in the module
# ---------------------------------------------------------------------------

def list_runtime_functions(module: str) -> str:
    """List the names and signatures of all public functions in a skill_runtime module.
    parameters module: Module short name, support 'data_access', 'project_access', 'external_sources', 'standard_financial_apis'. 
    Returns a JSON array, each item containing name(function name)and signature(signature). """
    MODULE_MAP = {
        "data_access": "core.skill_runtime.data_access",
        "project_access": "core.skill_runtime.project_access",
        "external_sources": "core.skill_runtime.external_sources",
        "standard_financial_apis": "core.skill_runtime.standard_financial_apis",
    }
    full_module = MODULE_MAP.get(module)
    if not full_module:
        return json.dumps({"error": f"不支持的模块: {module}，可选: {list(MODULE_MAP.keys())}"}, ensure_ascii=False)
    try:
        import importlib
        mod = importlib.import_module(full_module)
        funcs = []
        for name, obj in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith("_"):
                continue
            sig = str(inspect.signature(obj))
            full_doc = inspect.getdoc(obj) or ""
            funcs.append({"name": name, "signature": f"{name}{sig}", "summary": full_doc})
        return json.dumps(funcs, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 7: List configured external data sources
# ---------------------------------------------------------------------------

def list_external_data_sources(market_category: str = "a_shares") -> str:
    """Lists the external data sources configured and enabled on the current system (such as akshare, tushare, baostock).
    parameters market_category: Market category, default 'a_shares', Optional 'hk_stocks', 'us_stocks'. 
    Returns a JSON object containing supported(All data sources supported by this market)and configured(Currently enabled data sources). 
    Functions from external data sources can be accessed via list_runtime_functions('external_sources') View."""
    from core.skill_runtime.catalog import (
        list_supported_external_sources,
        list_configured_external_sources,
    )
    supported = list_supported_external_sources(market_category)
    configured = list_configured_external_sources(market_category)
    return json.dumps({
        "market_category": market_category,
        "supported_sources": supported,
        "configured_sources": configured,
        "hint": "Use list_runtime_functions('external_sources') View callable external data acquisition functions",
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 7b: List all reusable analysis tools (core.tools.implementations)
# ---------------------------------------------------------------------------

# Analysis class subdirectory whitelist (consistent with static_validator.ALLOWED_CORE_PREFIXES)
_ANALYSIS_SUBDIRS = [
    "fundamentals", "market", "technical", "portfolio",
    "risk", "news", "social", "trade_review", "legacy_bridge",
]

def list_analysis_tools(category: str = "") -> str:
    """Lists all reusable analysis tools and their complete import paths.
    parameters category: Optional category filtering, support 'fundamentals', 'market', 'technical', 'portfolio', 'risk', 'news', 'social', 'trade_review', 'legacy_bridge'. Leave blank to return all.
    Returns a JSON array, each item contains tool_id, name, category, module_path (complete import path), function_name (function name), summary (one sentence description).
    The generated Skill code can be accessed via from <module_path> import <function_name> Call these tools.
    Note: This tool returns the full list, suitable for categorized browsing. If the most relevant tools need to be semantically matched according to the requirements, the reconnaissance phase will automatically recommend them through the CapabilityIndexService vector search."""
    import inspect as _inspect

    target_cats = {category} if category else set(_ANALYSIS_SUBDIRS)
    if category and category not in _ANALYSIS_SUBDIRS:
        return json.dumps({"error": f"不支持的分类: {category}", "allowed": _ANALYSIS_SUBDIRS}, ensure_ascii=False)

    try:
        from core.tools.registry import get_tool_registry
        registry = get_tool_registry()
        all_tools = registry.list_all()
    except Exception as exc:
        return json.dumps({"error": f"ToolRegistry Loading failed: {exc}"}, ensure_ascii=False)

    results = []
    for t in all_tools:
        if t.category not in target_cats:
            continue
        # Get the tool's callable function to determine the module path
        func = None
        try:
            func = registry.get_function(t.id)
        except Exception:
            pass
        module_path = ""
        function_name = t.id  # By default, tool_id is used as the function name
        summary = ""
        if func is not None:
            module_path = getattr(func, "__module__", "") or ""
            function_name = getattr(func, "__name__", t.id)
            doc_first = (_inspect.getdoc(func) or "").split("\n")[0]
            summary = doc_first[:100]
        results.append({
            "tool_id": t.id,
            "name": t.name,
            "category": t.category,
            "module_path": module_path,
            "function_name": function_name,
            "summary": summary,
        })

    return json.dumps(results, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 8: List registered MCP tools
# ---------------------------------------------------------------------------

def list_mcp_tools() -> str:
    """List current passes MCP (Model Context Protocol) The server registers all tools into the system.
    MCP Tools are dynamically registered capabilities for external services, possibly providing additional data retrieval or computational functionality.
    Returns a JSON array, each item contains tool_id, name, description.
    If there is no MCP tool, an empty array is returned."""
    try:
        from core.tools.registry import get_tool_registry
        registry = get_tool_registry()
        mcp_tools = [t for t in registry.list_all() if t.category == "mcp"]
        items = []
        for t in mcp_tools:
            item: Dict[str, Any] = {
                "tool_id": t.id,
                "name": t.name,
                "description": t.description or "",
            }
            # If there is a parameter definition, it also comes with
            if t.parameters:
                item["parameters"] = [
                    {"name": p.name, "type": p.type, "description": getattr(p, "description", "")}
                    for p in t.parameters
                    if hasattr(p, "name")
                ]
            items.append(item)
        return json.dumps(items, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.warning(f"[recon] Failed to list MCP tools: {exc}")
        return json.dumps([], ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 9: Read real sample documents
# ---------------------------------------------------------------------------

def _contains_mongo_operator(value: Any) -> bool:
    """Conservatively reject MongoDB operators and ensure that read-only query tools only support simple equality filtering."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).startswith("$"):
                return True
            if _contains_mongo_operator(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_mongo_operator(item) for item in value)
    return False


def _json_safe_preview(value: Any, max_chars: int = 6000) -> Any:
    """Convert to a JSON safe object and limit the return volume."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return json.loads(text)
    return {
        "truncated": True,
        "original_chars": len(text),
        "preview": text[:max_chars],
    }


def run_readonly_query(
    collection: str,
    filter: dict = None,
    projection: dict = None,
    limit: int = 20,
) -> str:
    """Execute a read-only query on a whitelisted MongoDB collection, returning real sample documents.
    parameters collection: Collection name, only collections registered in skill_runtime.catalog.SUPPORTED_COLLECTIONS are allowed.
    parameters filter: Simple equality filter, not allowed $where/$regex/$expr Wait for Mongo operators.
    parameters projection: Field projection, _id is excluded by default.
    parameters limit: Return the number of items, up to 20.
    Returns a JSON object, including collection, filter, returned_count, documents, and metrics."""
    global _READONLY_QUERY_CALL_COUNT
    _READONLY_QUERY_CALL_COUNT += 1
    started = time.perf_counter()
    from core.skill_runtime.catalog import SUPPORTED_COLLECTIONS
    from core.skill_runtime.project_access import query_stock_collection

    collection_name = str(collection or "").strip()
    if collection_name not in SUPPORTED_COLLECTIONS:
        return json.dumps({
            "success": False,
            "error": f"unsupported collection: {collection_name}",
            "allowed_collections": sorted(SUPPORTED_COLLECTIONS),
            "metrics": {"call_count": _READONLY_QUERY_CALL_COUNT},
        }, ensure_ascii=False)

    filters = filter or {}
    projections = projection or {"_id": 0}
    if not isinstance(filters, dict):
        return json.dumps({"success": False, "error": "filter must be an object", "metrics": {"call_count": _READONLY_QUERY_CALL_COUNT}}, ensure_ascii=False)
    if not isinstance(projections, dict):
        return json.dumps({"success": False, "error": "projection must be an object", "metrics": {"call_count": _READONLY_QUERY_CALL_COUNT}}, ensure_ascii=False)
    if _contains_mongo_operator(filters) or _contains_mongo_operator(projections):
        return json.dumps({
            "success": False,
            "error": "Mongo operators are not allowed in run_readonly_query; use simple equality filters only",
            "metrics": {"call_count": _READONLY_QUERY_CALL_COUNT},
        }, ensure_ascii=False)

    capped_limit = max(1, min(int(limit or 20), 20))
    try:
        docs = query_stock_collection(
            collection=collection_name,
            filters=filters,
            projection=projections,
            limit=capped_limit,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        payload = {
            "success": True,
            "collection": collection_name,
            "filter": filters,
            "projection": projections,
            "limit": capped_limit,
            "returned_count": len(docs),
            "documents": docs,
            "metrics": {
                "call_count": _READONLY_QUERY_CALL_COUNT,
                "elapsed_ms": elapsed_ms,
                "limit_capped": int(limit or 20) != capped_limit,
            },
        }
        return json.dumps(_json_safe_preview(payload), ensure_ascii=False, default=str)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning("[recon] run_readonly_query failed: %s", exc)
        return json.dumps({
            "success": False,
            "error": str(exc),
            "metrics": {"call_count": _READONLY_QUERY_CALL_COUNT, "elapsed_ms": elapsed_ms},
        }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tools 10: Actual call to runtime helper/external interface probe
# ---------------------------------------------------------------------------

def _summarize_probe_shape(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        keys = list(value.keys())
        summary: Dict[str, Any] = {
            "type": "dict",
            "keys": keys[:30],
            "key_count": len(keys),
        }
        for key in ("data", "items", "result", "records"):
            nested = value.get(key)
            if isinstance(nested, list):
                summary[f"{key}_length"] = len(nested)
                if nested:
                    summary[f"{key}_first_item_type"] = type(nested[0]).__name__
                    if isinstance(nested[0], dict):
                        summary[f"{key}_first_item_keys"] = list(nested[0].keys())[:30]
            elif isinstance(nested, dict):
                summary[f"{key}_keys"] = list(nested.keys())[:30]
        return summary
    if isinstance(value, list):
        summary = {"type": "list", "length": len(value)}
        if value:
            summary["first_item_type"] = type(value[0]).__name__
            if isinstance(value[0], dict):
                summary["first_item_keys"] = list(value[0].keys())[:30]
        return summary
    return {"type": type(value).__name__}


def _resolve_runtime_helper(source_or_helper: str):
    import importlib

    raw = str(source_or_helper or "").strip()
    if not raw:
        raise ValueError("source_or_helper is required")

    module_map = {
        "data_access": "core.skill_runtime.data_access",
        "project_access": "core.skill_runtime.project_access",
        "external_sources": "core.skill_runtime.external_sources",
        "standard_financial_apis": "core.skill_runtime.standard_financial_apis",
    }
    allowed_modules = set(module_map.values())

    if raw.count(".") >= 1:
        module_part, func_name = raw.rsplit(".", 1)
        module_name = module_map.get(module_part, module_part)
        if module_name not in allowed_modules:
            raise ValueError(f"unsupported helper module: {module_name}")
        module = importlib.import_module(module_name)
        func = getattr(module, func_name, None)
        if callable(func) and not func_name.startswith("_"):
            return module_name, func_name, func
        raise ValueError(f"helper not found: {raw}")

    for module_name in allowed_modules:
        module = importlib.import_module(module_name)
        func = getattr(module, raw, None)
        if callable(func) and not raw.startswith("_"):
            return module_name, raw, func
    raise ValueError(f"helper not found: {raw}")


def probe_interface(source_or_helper: str, sample_args: dict = None) -> str:
    """Really call the registered skill_runtime helper once, return availability, return shape and preview.
    parameters source_or_helper: helper Name, supports get_external_valuation_data, external_sources.get_external_valuation_data, core.skill_runtime.external_sources.get_external_valuation_data, etc.
    parameters sample_args: Sample parameter object, e.g. {"symbol":"600519", "start_date":"2024-01-01", "end_date":"2024-12-31"}. 
    Returns a JSON object containing success, module, function, elapsed_ms, shape, preview, metrics, or error."""
    global _PROBE_INTERFACE_CALL_COUNT
    _PROBE_INTERFACE_CALL_COUNT += 1

    # Handle cases where LLM may be passed in a JSON string
    args = sample_args
    if args is None:
        args = {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
            logger.debug(f"[probe_interface] sample_args Parsed from JSON string: {type(args)}")
        except Exception:
            pass
    if not isinstance(args, dict):
        logger.warning(f"[probe_interface] sample_args type error: {type(args)}, value: {args}")
        return json.dumps({"success": False, "error": f"sample_args must be an object (current type: {type(args).__name__}) ", "metrics": {"call_count": _PROBE_INTERFACE_CALL_COUNT}}, ensure_ascii=False)
    if _contains_mongo_operator(args):
        return json.dumps({"success": False, "error": "Mongo-style operators are not allowed in sample_args", "metrics": {"call_count": _PROBE_INTERFACE_CALL_COUNT}}, ensure_ascii=False)

    started = time.perf_counter()
    try:
        module_name, func_name, func = _resolve_runtime_helper(source_or_helper)
        rate_key = f"{module_name}.{func_name}"
        now = time.perf_counter()
        last_called = _PROBE_INTERFACE_LAST_CALLED_AT.get(rate_key, 0.0)
        min_interval = _PROBE_INTERFACE_MIN_INTERVAL_SECONDS
        waited_ms = 0.0
        if min_interval > 0 and now - last_called < min_interval:
            wait_seconds = min_interval - (now - last_called)
            time.sleep(wait_seconds)
            waited_ms = round(wait_seconds * 1000, 2)
        _PROBE_INTERFACE_LAST_CALLED_AT[rate_key] = time.perf_counter()

        result = func(**args)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        payload = {
            "success": True,
            "module": module_name,
            "function": func_name,
            "elapsed_ms": elapsed_ms,
            "shape": _summarize_probe_shape(result),
            "preview": _json_safe_preview(result, max_chars=4000),
            "metrics": {
                "call_count": _PROBE_INTERFACE_CALL_COUNT,
                "rate_limit_wait_ms": waited_ms,
                "min_interval_ms": round(min_interval * 1000, 2),
            },
        }
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning("[recon] probe_interface failed: %s", exc)
        return json.dumps({
            "success": False,
            "source_or_helper": source_or_helper,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
            "metrics": {"call_count": _PROBE_INTERFACE_CALL_COUNT},
        }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool Registry (for use by ReconnaissanceController / Agentic Loop)
# ---------------------------------------------------------------------------

RECON_TOOLS: List[callable] = [
    list_available_collections,
    inspect_collection_schema,
    check_field_coverage,
    inspect_symbol_sample,
    describe_runtime_helper,
    list_runtime_functions,
    list_analysis_tools,
    list_external_data_sources,
    list_mcp_tools,
    run_readonly_query,
    probe_interface,
]
"""List of all tool functions available during the Reconnaissance phase and the Agentic Skill generation loop."""


